import os
import re
import io
import argparse
import html
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import requests
from typing import List, Tuple
from datetime import datetime, timedelta
from mutagen.mp3 import MP3
from mutagen.id3 import TIT2, TPE1, TALB, TRCK
import logging
from time import sleep

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Added max_retries constant
MAX_RETRIES = 10


subscription_key = os.environ.get("MS_TTS_KEY")
region = os.environ.get("MS_TTS_REGION")

if not subscription_key or not region:
    raise ValueError(
        "Please set AZURE_SUBSCRIPTION_KEY and AZURE_REGION environment variables")

TOKEN_URL = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
TOKEN_HEADERS = {
    "Ocp-Apim-Subscription-Key": subscription_key
}

TTS_URL = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

MAGIC_BREAK_STRING = " @BRK#"  # leading blank is for text split


def sanitize_title(title: str) -> str:
    # replace MAGIC_BREAK_STRING with a blank space
    # strip incase leading bank is missing
    title = title.replace(MAGIC_BREAK_STRING.strip(), " ")
    sanitized_title = re.sub(r"[^\w\s]", "", title, flags=re.UNICODE)
    sanitized_title = re.sub(r"\s+", "_", sanitized_title.strip())
    return sanitized_title


def extract_chapters(epub_book: epub.EpubBook) -> List[Tuple[str, str]]:
    chapters = []
    for item in epub_book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content()
            soup = BeautifulSoup(content, 'lxml')
            title = soup.title.string if soup.title else ''
            raw = soup.get_text(strip=False)
            logger.debug(f"Raw text: <{raw[:100]}>")

            # Replace excessive whitespaces and newline characters
            cleaned_text = re.sub(r'[\n]+', MAGIC_BREAK_STRING, raw.strip())
            logger.debug(f"Cleaned text step 1: <{cleaned_text[:100]}>")
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
            logger.info(f"Cleaned text step 2: <{cleaned_text[:100]}>")

            # fill in the title if it's missing
            if not title:
                title = cleaned_text[:60]
            logger.debug(f"Raw title: <{title}>")
            title = sanitize_title(title)
            logger.info(f"Sanitized title: <{title}>")

            chapters.append((title, cleaned_text))
            soup.decompose()
    return chapters


class AccessToken:
    def __init__(self, token: str, expiry_time: datetime):
        self.token = token
        self.expiry_time = expiry_time

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expiry_time


def get_access_token() -> AccessToken:
    for retry in range(MAX_RETRIES):
        try:
            response = requests.post(TOKEN_URL, headers=TOKEN_HEADERS)
            response.raise_for_status()
            access_token = str(response.text)
            expiry_time = datetime.utcnow() + timedelta(minutes=9, seconds=30)
            return AccessToken(access_token, expiry_time)
        except requests.exceptions.RequestException as e:
            if retry < MAX_RETRIES - 1:
                logger.warning(
                    f"Network error while getting access token (attempt {retry + 1}): {e}")
                sleep(2 ** retry)
            else:
                logger.error(
                    f"Network error while getting access token (attempt {retry + 1}): {e}")
                raise


def split_text(text: str, max_chars: int, language: str) -> List[str]:
    if language.startswith("zh"):
        chunks = [text[i:i + max_chars]
                  for i in range(0, len(text), max_chars)]
    else:
        words = text.split()
        chunks = []
        current_chunk = ""

        for word in words:
            if len(current_chunk) + len(word) + 1 <= max_chars:
                current_chunk += (" " if current_chunk else "") + word
            else:
                chunks.append(current_chunk)
                current_chunk = word

        if current_chunk:
            chunks.append(current_chunk)

    logger.info(f"Split text into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks, 1):
        first_100 = chunk[:100]
        last_100 = chunk[-100:] if len(chunk) > 100 else ""
        logger.info(
            f"Chunk {i}: Length={len(chunk)}, Start={first_100}..., End={last_100}")

    return chunks


def text_to_speech(session: requests.Session, text: str, output_file: str, voice_name: str, language: str, break_duration: int, access_token: AccessToken, title: str, author: str, book_title: str, idx: int) -> AccessToken:
    # Adjust this value based on your testing
    max_chars = 1800 if language.startswith("zh") else 3000

    text_chunks = split_text(text, max_chars, language)

    audio_segments = []

    for i, chunk in enumerate(text_chunks, 1):
        logger.debug(
            f"Processing chunk {i} of {len(text_chunks)}, length={len(chunk)}, text=[{chunk}]")
        escaped_text = html.escape(chunk)
        logger.debug(f"Escaped text: [{escaped_text}]")
        # replace MAGIC_BREAK_STRING with a break tag for section/paragraph break
        escaped_text = escaped_text.replace(
            MAGIC_BREAK_STRING.strip(), f" <break time='{break_duration}ms' /> ")  # strip incase leading bank is missing
        logger.info(
            f"Processing chapter-{idx} <{title}>, chunk {i} of {len(text_chunks)}")
        ssml = f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{language}'><voice name='{voice_name}'>{escaped_text}</voice></speak>"
        logger.debug(f"SSML: [{ssml}]")

        for retry in range(MAX_RETRIES):
            if access_token.is_expired():
                logger.info(f"access_token is expired, getting new one")
                access_token = get_access_token()
            headers = {
                "Authorization": f"Bearer {access_token.token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "Python"
            }
            try:
                response = session.post(TTS_URL, headers=headers,
                                        data=ssml.encode('utf-8'))
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if retry < MAX_RETRIES - 1:
                    logger.warning(
                        f"Network error while converting text to speech (attempt {retry + 1}): {e}")
                    sleep(2 ** retry)
                else:
                    logger.error(
                        f"Network error while converting text to speech (attempt {retry + 1}): {e}")
                    raise

        audio_segments.append(io.BytesIO(response.content))

    with open(output_file, "wb") as outfile:
        for segment in audio_segments:
            segment.seek(0)
            outfile.write(segment.read())

    # Add ID3 tags to the generated MP3 file
    audio = MP3(output_file)
    audio["TIT2"] = TIT2(encoding=3, text=title)
    audio["TPE1"] = TPE1(encoding=3, text=author)
    audio["TALB"] = TALB(encoding=3, text=book_title)
    audio["TRCK"] = TRCK(encoding=3, text=str(idx))
    audio.save()
    return access_token


def epub_to_audiobook(input_file: str, output_folder: str, voice_name: str, language: str, preview: bool, break_duration: int, chapter_start: int, chapter_end: int) -> None:
    book = epub.read_epub(input_file)
    chapters = extract_chapters(book)

    os.makedirs(output_folder, exist_ok=True)

    access_token = get_access_token()

    # Get the book title and author from metadata or use fallback values
    book_title = "Untitled"
    author = "Unknown"
    if book.get_metadata('DC', 'title'):
        book_title = book.get_metadata('DC', 'title')[0][0]
    if book.get_metadata('DC', 'creator'):
        author = book.get_metadata('DC', 'creator')[0][0]

    # Filter out empty or very short chapters
    chapters = [(title, text) for title, text in chapters if text.strip()]

    logger.info(f"Chapters count: {len(chapters)}.")

    # Check chapter start and end args
    if chapter_start < 1 or chapter_start > len(chapters):
        raise ValueError(
            f"Chapter start index {chapter_start} is out of range. Check your input.")
    if chapter_end < -1 or chapter_end > len(chapters):
        raise ValueError(
            f"Chapter end index {chapter_end} is out of range. Check your input.")
    if chapter_end == -1:
        chapter_end = len(chapters)
    if chapter_start > chapter_end:
        raise ValueError(
            f"Chapter start index {chapter_start} is larger than chapter end index {chapter_end}. Check your input.")

    logger.info(f"Converting chapters {chapter_start} to {chapter_end}.")

    with requests.Session() as session:
        for idx, (title, text) in enumerate(chapters, start=1):
            if idx < chapter_start:
                continue
            if idx > chapter_end:
                break
            logger.info(f"Converting chapter {idx}/{len(chapters)}: {title}")
            if preview:
                continue

            output_file = os.path.join(output_folder, f"{idx:04d}_{title}.mp3")
            access_token = text_to_speech(session, text, output_file, voice_name,
                                          language, break_duration, access_token, title, author, book_title, idx)


def main():
    parser = argparse.ArgumentParser(description="Convert EPUB to audiobook")
    parser.add_argument("input_file", help="Path to the EPUB file")
    parser.add_argument("output_folder", help="Path to the output folder")
    parser.add_argument("--voice_name", default="en-US-GuyNeural",
                        help="Voice name for the text-to-speech service (default: en-US-GuyNeural). You can use zh-CN-YunyeNeural for Chinese ebooks.")
    parser.add_argument("--language", default="en-US",
                        help="Language for the text-to-speech service (default: en-US)")
    parser.add_argument("--preview", action="store_true",
                        help="Enable preview mode. In preview mode, the script will not convert the text to speech. Instead, it will print the chapter index and titles.")
    parser.add_argument("--break_duration", default="1250",
                        help="Break duration in milliseconds for the different paragraphs or sections (default: 1250). Valid values range from 0 to 5000 milliseconds.")
    parser.add_argument("--chapter_start", default=1, type=int,
                        help="Chapter start index (default: 1, starting from 1)")
    parser.add_argument("--chapter_end", default=-1, type=int,
                        help="Chapter end index (default: -1, meaning to the last chapter)")
    parser.add_argument("--log", default="INFO",
                        help="Log level (default: INFO), can be DEBUG, INFO, WARNING, ERROR, CRITICAL")
    args = parser.parse_args()

    logger.setLevel(args.log)

    epub_to_audiobook(args.input_file, args.output_folder,
                      args.voice_name, args.language, args.preview, args.break_duration, args.chapter_start, args.chapter_end)
    logger.info("Done! 👍")
    logger.info(f"args = {args}")


if __name__ == "__main__":
    main()
