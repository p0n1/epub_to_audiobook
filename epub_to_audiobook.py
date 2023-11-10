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
from mutagen.id3 import ID3
from mutagen.id3._util import ID3NoHeaderError
from mutagen.id3._frames import TIT2, TPE1, TALB, TRCK
import logging
from time import sleep
import dataclasses
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


MAX_RETRIES = 12  # Max_retries constant for network errors
MAGIC_BREAK_STRING = " @BRK#"  # leading blank is for text split

TTS_AZURE = "azure"
TTS_OPENAI = "openai"


@dataclasses.dataclass
class AudioTags:
    title: str  # for TIT2
    author: str  # for TPE1
    book_title: str  # for TALB
    idx: int  # for TRCK


class GeneralConfig:
    def __init__(self, args):
        self.input_file = args.input_file
        self.output_folder = args.output_folder
        self.tts = args.tts
        self.preview = args.preview
        self.language = args.language
        self.newline_mode = args.newline_mode
        self.chapter_start = args.chapter_start
        self.chapter_end = args.chapter_end
        self.output_text = args.output_text
        self.remove_endnotes = args.remove_endnotes

    def __str__(self):
        return f"input_file={self.input_file}, output_folder={self.output_folder}, tts={self.tts}, preview={self.preview}, newline_mode={self.newline_mode}, chapter_start={self.chapter_start}, chapter_end={self.chapter_end}, output_text={self.output_text}, remove_endnotes={self.remove_endnotes}"


class TTSProvider:
    # Base provider interface
    def __init__(self, general_config: GeneralConfig):
        self.general_config = general_config

    def __str__(self) -> str:
        return f"{self.general_config}"

    def text_to_speech(self, *args, **kwargs):
        raise NotImplementedError


class AzureTTSProvider(TTSProvider):
    def __init__(
        self,
        general_config: GeneralConfig,
        voice_name,
        break_duration,
        output_format,
    ):
        super().__init__(general_config)

        # TTS provider specific config
        self.voice_name = voice_name
        self.break_duration = break_duration
        self.output_format = output_format

        # access token and expiry time
        self.access_token = None
        self.token_expiry_time = datetime.utcnow()

        subscription_key = os.environ.get("MS_TTS_KEY")
        region = os.environ.get("MS_TTS_REGION")

        if not subscription_key or not region:
            raise ValueError(
                "Please set MS_TTS_KEY and MS_TTS_REGION environment variables. Check https://github.com/p0n1/epub_to_audiobook#how-to-get-your-azure-cognitive-service-key."
            )

        self.TOKEN_URL = (
            f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
        )
        self.TOKEN_HEADERS = {"Ocp-Apim-Subscription-Key": subscription_key}
        self.TTS_URL = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def __str__(self) -> str:
        return (
            super().__str__()
            + f", voice_name={self.voice_name}, language={self.general_config.language}, break_duration={self.break_duration}, output_format={self.output_format}"
        )

    def is_access_token_expired(self) -> bool:
        return self.access_token is None or datetime.utcnow() >= self.token_expiry_time

    def auto_renew_access_token(self) -> str:
        if self.access_token is None or self.is_access_token_expired():
            logger.info(
                f"azure tts access_token doesn't exist or is expired, getting new one"
            )
            self.access_token = self.get_access_token()
            self.token_expiry_time = datetime.utcnow() + timedelta(minutes=9, seconds=1)
        return self.access_token

    def get_access_token(self) -> str:
        for retry in range(MAX_RETRIES):
            try:
                response = requests.post(self.TOKEN_URL, headers=self.TOKEN_HEADERS)
                access_token = str(response.text)
                logger.info("Got new access token")
                return access_token
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Network error while getting access token (attempt {retry + 1}/{MAX_RETRIES}): {e}"
                )
                if retry < MAX_RETRIES - 1:
                    sleep(2**retry)
                else:
                    raise e
        raise Exception("Failed to get access token")

    def text_to_speech(
        self,
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):
        # Adjust this value based on your testing
        max_chars = 1800 if self.general_config.language.startswith("zh") else 3000

        text_chunks = split_text(text, max_chars, self.general_config.language)

        audio_segments = []

        for i, chunk in enumerate(text_chunks, 1):
            logger.debug(
                f"Processing chunk {i} of {len(text_chunks)}, length={len(chunk)}, text=[{chunk}]"
            )
            escaped_text = html.escape(chunk)
            logger.debug(f"Escaped text: [{escaped_text}]")
            # replace MAGIC_BREAK_STRING with a break tag for section/paragraph break
            escaped_text = escaped_text.replace(
                MAGIC_BREAK_STRING.strip(),
                f" <break time='{self.break_duration}ms' /> ",
            )  # strip in case leading bank is missing
            logger.info(
                f"Processing chapter-{audio_tags.idx} <{audio_tags.title}>, chunk {i} of {len(text_chunks)}"
            )
            ssml = f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{self.general_config.language}'><voice name='{self.voice_name}'>{escaped_text}</voice></speak>"
            logger.debug(f"SSML: [{ssml}]")

            for retry in range(MAX_RETRIES):
                self.auto_renew_access_token()
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": self.output_format,
                    "User-Agent": "Python",
                }
                try:
                    response = requests.post(
                        self.TTS_URL, headers=headers, data=ssml.encode("utf-8")
                    )
                    audio_segments.append(io.BytesIO(response.content))
                    break
                except requests.exceptions.RequestException as e:
                    logger.warning(
                        f"Error while converting text to speech (attempt {retry + 1}): {e}"
                    )
                    if retry < MAX_RETRIES - 1:
                        sleep(2**retry)
                    else:
                        raise e

        with open(output_file, "wb") as outfile:
            for segment in audio_segments:
                segment.seek(0)
                outfile.write(segment.read())

        set_audio_tags(output_file, audio_tags)


class OpenAITTSProvider(TTSProvider):
    def __init__(self, general_config: GeneralConfig, model, voice, format):
        super().__init__(general_config)
        self.model = model
        self.voice = voice
        self.format = format
        self.client = OpenAI()  # User should set OPENAI_API_KEY environment variable

    def __str__(self) -> str:
        return (
            super().__str__()
            + f", model={self.model}, voice={self.voice}, format={self.format}"
        )

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        max_chars = 4000  # should be less than 4096 for OpenAI

        text_chunks = split_text(text, max_chars, self.general_config.language)

        audio_segments = []

        for i, chunk in enumerate(text_chunks, 1):
            logger.debug(
                f"Processing chunk {i} of {len(text_chunks)}, length={len(chunk)}, text=[{chunk}]"
            )
            # replace MAGIC_BREAK_STRING with blank space because OpenAI TTS doesn't support SSML
            chunk = chunk.replace(
                MAGIC_BREAK_STRING.strip(),
                "   ",
            )  # strip in case leading bank is missing
            logger.info(
                f"Processing chapter-{audio_tags.idx} <{audio_tags.title}>, chunk {i} of {len(text_chunks)}"
            )

            logger.debug(f"Text: [{chunk}], length={len(chunk)}")

            # NO retry for OpenAI TTS because SDK has built-in retry logic
            response = self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=chunk,
                response_format=self.format,
            )
            audio_segments.append(io.BytesIO(response.content))

            with open(output_file, "wb") as outfile:
                for segment in audio_segments:
                    segment.seek(0)
                    outfile.write(segment.read())

            set_audio_tags(output_file, audio_tags)


def sanitize_title(title: str) -> str:
    # replace MAGIC_BREAK_STRING with a blank space
    # strip incase leading bank is missing
    title = title.replace(MAGIC_BREAK_STRING.strip(), " ")
    sanitized_title = re.sub(r"[^\w\s]", "", title, flags=re.UNICODE)
    sanitized_title = re.sub(r"\s+", "_", sanitized_title.strip())
    return sanitized_title


def extract_chapters(
    epub_book: epub.EpubBook, newline_mode: str, remove_endnotes: bool
) -> List[Tuple[str, str]]:
    chapters = []
    for item in epub_book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content()
            soup = BeautifulSoup(content, "lxml")
            title = soup.title.string if soup.title else ""
            raw = soup.get_text(strip=False)
            logger.debug(f"Raw text: <{raw[:]}>")

            # Replace excessive whitespaces and newline characters based on the mode
            if newline_mode == "single":
                cleaned_text = re.sub(r"[\n]+", MAGIC_BREAK_STRING, raw.strip())
            elif newline_mode == "double":
                cleaned_text = re.sub(r"[\n]{2,}", MAGIC_BREAK_STRING, raw.strip())
            else:
                raise ValueError(f"Invalid newline mode: {newline_mode}")

            logger.debug(f"Cleaned text step 1: <{cleaned_text[:]}>")
            cleaned_text = re.sub(r"\s+", " ", cleaned_text)
            logger.info(f"Cleaned text step 2: <{cleaned_text[:100]}>")

            # Removes endnote numbers
            if remove_endnotes == True:
                cleaned_text = re.sub(r'(?<=[a-zA-Z.,!?;”")])\d+', "", cleaned_text)
                logger.info(f"Cleaned text step 4: <{cleaned_text[:100]}>")

            # fill in the title if it's missing
            if not title:
                title = cleaned_text[:60]
            logger.debug(f"Raw title: <{title}>")
            title = sanitize_title(title)
            logger.info(f"Sanitized title: <{title}>")

            chapters.append((title, cleaned_text))
            soup.decompose()
    return chapters


def is_special_char(char: str) -> bool:
    # Check if the character is a English letter, number or punctuation or a punctuation in Chinese, never split these characters.
    ord_char = ord(char)
    result = (
        (ord_char >= 33 and ord_char <= 126)
        or (char in "。，、？！：；“”‘’（）《》【】…—～·「」『』〈〉〖〗〔〕")
        or (char in "∶")
    )  # special unicode punctuation
    logger.debug(f"is_special_char> char={char}, ord={ord_char}, result={result}")
    return result


def split_text(text: str, max_chars: int, language: str) -> List[str]:
    chunks = []
    current_chunk = ""

    if language.startswith("zh"):  # Chinese
        for char in text:
            if len(current_chunk) + 1 <= max_chars or is_special_char(char):
                current_chunk += char
            else:
                chunks.append(current_chunk)
                current_chunk = char

        if current_chunk:
            chunks.append(current_chunk)

    else:
        words = text.split()

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
            f"Chunk {i}: Length={len(chunk)}, Start={first_100}..., End={last_100}"
        )

    return chunks


def set_audio_tags(output_file, audio_tags):
    try:
        try:
            tags = ID3(output_file)
            print(tags)
        except ID3NoHeaderError:
            logger.debug(f"handling ID3NoHeaderError: {output_file}")
            tags = ID3()
        tags.add(TIT2(encoding=3, text=audio_tags.title))
        tags.add(TPE1(encoding=3, text=audio_tags.author))
        tags.add(TALB(encoding=3, text=audio_tags.book_title))
        tags.add(TRCK(encoding=3, text=str(audio_tags.idx)))
        tags.save(output_file)
    except Exception as e:
        logger.error(f"Error while setting audio tags: {e}, {output_file}")
        raise e  # TODO: use this raise to catch unknown errors for now


def epub_to_audiobook(tts_provider: TTSProvider):
    # assign config values
    conf = tts_provider.general_config
    input_file = conf.input_file
    output_folder = conf.output_folder
    preview = conf.preview
    newline_mode = conf.newline_mode
    chapter_start = conf.chapter_start
    chapter_end = conf.chapter_end
    remove_endnotes = conf.remove_endnotes
    output_text = conf.output_text

    book = epub.read_epub(input_file)
    chapters = extract_chapters(book, newline_mode, remove_endnotes)

    os.makedirs(output_folder, exist_ok=True)

    # Get the book title and author from metadata or use fallback values
    book_title = "Untitled"
    author = "Unknown"
    if book.get_metadata("DC", "title"):
        book_title = book.get_metadata("DC", "title")[0][0]
    if book.get_metadata("DC", "creator"):
        author = book.get_metadata("DC", "creator")[0][0]

    # Filter out empty or very short chapters
    chapters = [(title, text) for title, text in chapters if text.strip()]

    logger.info(f"Chapters count: {len(chapters)}.")

    # Check chapter start and end args
    if chapter_start < 1 or chapter_start > len(chapters):
        raise ValueError(
            f"Chapter start index {chapter_start} is out of range. Check your input."
        )
    if chapter_end < -1 or chapter_end > len(chapters):
        raise ValueError(
            f"Chapter end index {chapter_end} is out of range. Check your input."
        )
    if chapter_end == -1:
        chapter_end = len(chapters)
    if chapter_start > chapter_end:
        raise ValueError(
            f"Chapter start index {chapter_start} is larger than chapter end index {chapter_end}. Check your input."
        )

    logger.info(f"Converting chapters {chapter_start} to {chapter_end}.")

    # Set the audio suffix based on the TTS provider
    audio_suffix = "mp3"
    if isinstance(tts_provider, OpenAITTSProvider):
        audio_suffix = f"{tts_provider.format}"  # mp3, opus, aac, or flac
    elif isinstance(tts_provider, AzureTTSProvider):
        audio_suffix = "mp3"  # only mp3 is supported for Azure TTS for now
    else:
        raise ValueError(f"Invalid TTS provider: {tts_provider.general_config.tts}")

    # Initialize total_characters to 0
    total_characters = 0

    # Loop through each chapter and convert it to speech using the provided TTS provider
    for idx, (title, text) in enumerate(chapters, start=1):
        if idx < chapter_start:
            continue
        if idx > chapter_end:
            break
        logger.info(
            f"Converting chapter {idx}/{len(chapters)}: {title}, characters: {len(text)}"
        )

        total_characters += len(text)

        if output_text:
            text_file = os.path.join(output_folder, f"{idx:04d}_{title}.txt")
            with open(text_file, "w") as file:
                file.write(text)

        if preview:
            continue

        output_file = os.path.join(output_folder, f"{idx:04d}_{title}.{audio_suffix}")

        audio_tags = AudioTags(title, author, book_title, idx)
        tts_provider.text_to_speech(
            text,
            output_file,
            audio_tags,
        )

    logger.info(f"✨ Total characters in selected chapters: {total_characters} ✨")


def main():
    parser = argparse.ArgumentParser(description="Convert EPUB to audiobook")
    parser.add_argument("input_file", help="Path to the EPUB file")
    parser.add_argument("output_folder", help="Path to the output folder")
    parser.add_argument(
        "--tts",
        choices=[TTS_AZURE, TTS_OPENAI],
        default=TTS_AZURE,
        help="Choose TTS provider (default: azure). azure: Azure Cognitive Services, openai: OpenAI TTS API. When using azure, environment variables MS_TTS_KEY and MS_TTS_REGION must be set. When using openai, environment variable OPENAI_API_KEY must be set.",
    )
    parser.add_argument(
        "--log",
        default="INFO",
        help="Log level (default: INFO), can be DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Enable preview mode. In preview mode, the script will not convert the text to speech. Instead, it will print the chapter index, titles, and character counts.",
    )
    parser.add_argument(
        "--language",
        default="en-US",
        help="Language for the text-to-speech service (default: en-US). For Azure TTS (--tts=azure), check https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts#text-to-speech for supported languages. For OpenAI TTS (--tts=openai), their API detects the language automatically. But setting this will also help on splitting the text into chunks with different strategies in this tool, especially for Chinese characters. For Chinese books, use zh-CN, zh-TW, or zh-HK.",
    )
    parser.add_argument(
        "--newline_mode",
        choices=["single", "double"],
        default="double",
        help="Choose the mode of detecting new paragraphs: 'single' or 'double'. 'single' means a single newline character, while 'double' means two consecutive newline characters. (default: double, works for most ebooks but will detect less paragraphs for some ebooks)",
    )
    parser.add_argument(
        "--chapter_start",
        default=1,
        type=int,
        help="Chapter start index (default: 1, starting from 1)",
    )
    parser.add_argument(
        "--chapter_end",
        default=-1,
        type=int,
        help="Chapter end index (default: -1, meaning to the last chapter)",
    )
    parser.add_argument(
        "--output_text",
        action="store_true",
        help="Enable Output Text. This will export a plain text file for each chapter specified and write the files to the output folder specified.",
    )
    parser.add_argument(
        "--remove_endnotes",
        action="store_true",
        help="This will remove endnote numbers from the end or middle of sentences. This is useful for academic books.",
    )

    # Azure specific arguments
    azure_group = parser.add_argument_group("Azure TTS Options")
    azure_group.add_argument(
        "--voice_name",
        default="en-US-GuyNeural",
        help="Voice name for the text-to-speech service (default: en-US-GuyNeural). You can use zh-CN-YunyeNeural for Chinese ebooks.",
    )
    azure_group.add_argument(
        "--break_duration",
        default="1250",
        help="Break duration in milliseconds for the different paragraphs or sections (default: 1250). Valid values range from 0 to 5000 milliseconds.",
    )
    azure_group.add_argument(
        "--output_format",
        default="audio-24khz-48kbitrate-mono-mp3",
        help="Output format for the text-to-speech service (default: audio-24khz-48kbitrate-mono-mp3). Support formats: audio-16khz-32kbitrate-mono-mp3 audio-16khz-64kbitrate-mono-mp3 audio-16khz-128kbitrate-mono-mp3 audio-24khz-48kbitrate-mono-mp3 audio-24khz-96kbitrate-mono-mp3 audio-24khz-160kbitrate-mono-mp3 audio-48khz-96kbitrate-mono-mp3 audio-48khz-192kbitrate-mono-mp3. See https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech?tabs=streaming#audio-outputs. Only mp3 is supported for now. Different formats will result in different audio quality and file size.",
    )

    # OpenAI specific arguments
    openai_group = parser.add_argument_group("OpenAI TTS Options")
    openai_group.add_argument(
        "--openai_model",
        default="tts-1",
        help="Available OpenAI model options: tts-1 and tts-1-hd. Check https://platform.openai.com/docs/guides/text-to-speech/audio-quality.",
    )
    openai_group.add_argument(
        "--openai_voice",
        default="alloy",
        help="Available OpenAI voice options: alloy, echo, fable, onyx, nova, and shimmer. Check https://platform.openai.com/docs/guides/text-to-speech/voice-options.",
    )
    openai_group.add_argument(
        "--openai_format",
        default="mp3",
        help="Available OpenAI output options: mp3, opus, aac, and flac. Check https://platform.openai.com/docs/guides/text-to-speech/supported-output-formats.",
    )

    args = parser.parse_args()

    logger.setLevel(args.log)

    general_config = GeneralConfig(args)

    if args.tts == TTS_AZURE:
        tts_provider = AzureTTSProvider(
            general_config,
            args.voice_name,
            args.break_duration,
            args.output_format,
        )
    elif args.tts == TTS_OPENAI:
        tts_provider = OpenAITTSProvider(
            general_config, args.openai_model, args.openai_voice, args.openai_format
        )
    else:
        raise ValueError(f"Invalid TTS provider: {args.tts}")

    epub_to_audiobook(tts_provider)
    logger.info("Done! 👍")
    logger.info(f"args = {args}")


if __name__ == "__main__":
    main()
