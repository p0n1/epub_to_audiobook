import io
import logging
import math

from openai import OpenAI

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.utils import split_text, set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider


logger = logging.getLogger(__name__)


def get_supported_models():
    return ["tts-1", "tts-1-hd"]


def get_supported_voices():
    return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


def get_supported_formats():
    return ["mp3", "acc", "flac", "opus"]


class OpenAITTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        logger.setLevel(config.log)
        config.model_name = config.model_name or "tts-1"
        config.voice_name = config.voice_name or "alloy"
        config.output_format = config.output_format or "mp3"

        # per 1000 characters (0.03$ for HD model, 0.015$ for standard model)
        self.price = 0.03 if config.model_name == "tts-1-hd" else 0.015
        super().__init__(config)

        self.client = OpenAI()  # User should set OPENAI_API_KEY environment variable

    def __str__(self) -> str:
        return super().__str__()

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        max_chars = 4000  # should be less than 4096 for OpenAI

        text_chunks = split_text(text, max_chars, self.config.language)

        audio_segments = []

        for i, chunk in enumerate(text_chunks, 1):
            logger.debug(
                f"Processing chunk {i} of {len(text_chunks)}, length={len(chunk)}, text=[{chunk}]"
            )
            logger.info(
                f"Processing chapter-{audio_tags.idx} <{audio_tags.title}>, chunk {i} of {len(text_chunks)}"
            )

            logger.debug(f"Text: [{chunk}], length={len(chunk)}")

            # NO retry for OpenAI TTS because SDK has built-in retry logic
            response = self.client.audio.speech.create(
                model=self.config.model_name,
                voice=self.config.voice_name,
                input=chunk,
                response_format=self.config.output_format,
            )
            audio_segments.append(io.BytesIO(response.content))

        with open(output_file, "wb") as outfile:
            for segment in audio_segments:
                segment.seek(0)
                outfile.write(segment.read())

        set_audio_tags(output_file, audio_tags)

    def get_break_string(self):
        return "   "

    def get_output_file_extension(self):
        return self.config.output_format

    def validate_config(self):
        if self.config.model_name not in get_supported_models():
            raise ValueError(f"OpenAI: Unsupported model name: {self.config.model_name}")
        if self.config.voice_name not in get_supported_voices():
            raise ValueError(f"OpenAI: Unsupported voice name: {self.config.voice_name}")
        if self.config.output_format not in get_supported_formats():
            raise ValueError(f"OpenAI: Unsupported output format: {self.config.output_format}")

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price
