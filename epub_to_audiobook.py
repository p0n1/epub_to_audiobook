import os
import re
import argparse
import html
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import requests
from typing import List, Tuple
from datetime import datetime, timedelta

subscription_key = os.environ.get("MS_TTS_KEY")
region = os.environ.get("MS_TTS_REGION")

if not subscription_key or not region:
    raise ValueError(
        "Please set AZURE_SUBSCRIPTION_KEY and AZURE_REGION environment variables")


def sanitize_title(title: str) -> str:
    sanitized_title = re.sub(r"[^\w\s]", "", title, flags=re.UNICODE)
    sanitized_title = re.sub(r"\s", "_", sanitized_title.strip())
    return sanitized_title


def extract_chapters(epub_book: ebooklib.epub.EpubBook) -> List[Tuple[str, str]]:
    chapters = []
    for item in epub_book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content()
            soup = BeautifulSoup(content, 'lxml')
            title = soup.title.string if soup.title else ''
            raw = soup.get_text(strip=False)
            print(f"Raw text: <{raw[:100]}>")
            text = soup.get_text(separator=" ", strip=True)
            print(f"Stripped text: <{text[:100]}>")
            chapters.append((title, text))
            soup.decompose()
    return chapters


class AccessToken:
    def __init__(self, token: str, expiry_time: datetime):
        self.token = token
        self.expiry_time = expiry_time

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expiry_time


def get_access_token() -> AccessToken:
    token_url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key
    }
    response = requests.post(token_url, headers=headers)
    response.raise_for_status()
    access_token = str(response.text)
    expiry_time = datetime.utcnow() + timedelta(minutes=9, seconds=30)
    return AccessToken(access_token, expiry_time)


session = requests.Session()


def text_to_speech(text: str, output_file: str, voice_name: str, language: str, access_token: AccessToken) -> None:
    if access_token.is_expired():
        access_token = get_access_token()

    escaped_text = html.escape(text)
    ssml = f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{language}'><voice name='{voice_name}'>{escaped_text}</voice></speak>"

    tts_url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Authorization": f"Bearer {access_token.token}",
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "Python"
    }

    response = session.post(tts_url, headers=headers,
                            data=ssml.encode('utf-8'))
    response.raise_for_status()

    with open(output_file, 'wb') as audio:
        audio.write(response.content)


def epub_to_audiobook(input_file: str, output_folder: str, voice_name: str, language: str) -> None:
    book = epub.read_epub(input_file)
    chapters = extract_chapters(book)

    os.makedirs(output_folder, exist_ok=True)

    access_token = get_access_token()

    for idx, (title, text) in enumerate(chapters, start=1):
        if not title:
            title = text[:42]
        print(f"Raw title: <{title}>")
        title = sanitize_title(title)
        print(f"Converting chapter {idx}: {title}")

        output_file = os.path.join(output_folder, f"{idx:04d}_{title}.mp3")
        text_to_speech(text, output_file, voice_name, language, access_token)


def main():
    parser = argparse.ArgumentParser(description="Convert EPUB to audiobook")
    parser.add_argument("input_file", help="Path to the EPUB file")
    parser.add_argument("output_folder", help="Path to the output folder")
    parser.add_argument("--voice_name", default="en-US-GuyNeural",
                        help="Voice name for the text-to-speech service (default: en-US-GuyNeural)")
    parser.add_argument("--language", default="en-US",
                        help="Language for the text-to-speech service (default: en-US)")
    args = parser.parse_args()

    epub_to_audiobook(args.input_file, args.output_folder,
                      args.voice_name, args.language)


if __name__ == "__main__":
    main()
