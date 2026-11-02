import io
import logging
import math
import os
import time

import requests

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.utils.utils import split_text, set_audio_tags, merge_audio_segments
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider


logger = logging.getLogger(__name__)

MAX_RETRIES = 4
RETRY_BACKOFF = 2  # seconds, doubles each retry


def get_camb_supported_models():
    return ["mars-pro", "mars-flash", "mars-instruct"]


def get_camb_supported_output_formats():
    return ["mp3", "wav", "flac"]


class CambTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.model_name = config.model_name or "mars-pro"
        config.output_format = config.output_format or "mp3"
        config.voice_name = config.voice_name or "147320"
        config.language = config.language or "en-us"

        super().__init__(config)

        self.api_key = os.environ.get("CAMB_API_KEY")
        if not self.api_key:
            raise ValueError(
                "CAMB AI: CAMB_API_KEY environment variable must be set"
            )

    def __str__(self) -> str:
        return super().__str__()

    def validate_config(self):
        if self.config.model_name not in get_camb_supported_models():
            raise ValueError(
                f"CAMB AI: Unsupported model: {self.config.model_name}. "
                f"Supported models: {get_camb_supported_models()}"
            )
        if self.config.output_format not in get_camb_supported_output_formats():
            raise ValueError(
                f"CAMB AI: Unsupported output format: {self.config.output_format}. "
                f"Supported formats: {get_camb_supported_output_formats()}"
            )
        try:
            int(self.config.voice_name)
        except (ValueError, TypeError):
            raise ValueError(
                f"CAMB AI: voice_name must be a numeric voice ID, got: {self.config.voice_name}"
            )
        if (
            self.config.camb_instructions
            and self.config.model_name != "mars-instruct"
        ):
            raise ValueError(
                "CAMB AI: Instructions are only supported for 'mars-instruct' model"
            )

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        max_chars = 2000
        text_chunks = split_text(text, max_chars, self.config.language)

        audio_segments = []
        chunk_ids = []

        for i, chunk in enumerate(text_chunks, 1):
            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
            logger.info(f"Processing {chunk_id}, length={len(chunk)}")
            logger.debug(f"Processing {chunk_id}, length={len(chunk)}, text=[{chunk}]")

            payload = {
                "text": chunk,
                "language": self.config.language.lower(),
                "voice_id": int(self.config.voice_name),
                "speech_model": self.config.model_name,
                "output_configuration": {"format": self.config.output_format},
            }

            if self.config.speaking_rate is not None:
                payload["speaking_rate"] = self.config.speaking_rate

            if (
                self.config.camb_instructions
                and self.config.model_name == "mars-instruct"
            ):
                payload["user_instructions"] = self.config.camb_instructions

            audio_data = self._call_api_with_retry(payload, chunk_id)
            audio_segments.append(io.BytesIO(audio_data))
            chunk_ids.append(chunk_id)

        merge_audio_segments(
            audio_segments,
            output_file,
            self.config.output_format,
            chunk_ids,
            self.config.use_pydub_merge,
        )

        set_audio_tags(output_file, audio_tags)

    def _call_api_with_retry(self, payload: dict, chunk_id: str) -> bytes:
        url = "https://client.camb.ai/apis/tts-stream"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=120,
                )
                response.raise_for_status()

                audio_data = b""
                for data in response.iter_content(chunk_size=8192):
                    if data:
                        audio_data += data

                logger.debug(
                    f"CAMB AI response for {chunk_id}: "
                    f"status={response.status_code}, size={len(audio_data)} bytes"
                )

                return audio_data

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    logger.warning(
                        f"CAMB AI: HTTP {status} for {chunk_id}, "
                        f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise
            except requests.exceptions.ConnectionError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    logger.warning(
                        f"CAMB AI: Connection error for {chunk_id}, "
                        f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    raise

    def get_break_string(self):
        return "   "

    def get_output_file_extension(self):
        return self.config.output_format

    def estimate_cost(self, total_chars):
        logger.warning(
            "CAMB AI: Cost estimation is not available. "
            "Please check https://camb.ai for current pricing."
        )
        return 0
