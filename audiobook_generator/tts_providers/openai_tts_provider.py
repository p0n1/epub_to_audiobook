import io
import logging
import math
import tempfile
import os
from pydub import AudioSegment

from openai import OpenAI

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.utils import split_text, set_audio_tags, merge_audio_segments
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider


logger = logging.getLogger(__name__)


def get_supported_formats():
    return ["mp3", "aac", "flac", "opus", "wav"]

def get_supported_voices():
    return ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"]

def get_supported_models():
    return ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]

def get_price(model):
    # https://platform.openai.com/docs/pricing#transcription-and-speech-generation
    if model == "tts-1": # $15 per 1 mil chars
        return 0.015
    elif model == "tts-1-hd": # $30 per 1 mil chars
        return 0.03
    elif model == "gpt-4o-mini-tts": # $12 per 1 mil tokens (not chars, as 1 token is ~4 chars)
        return 0.003 # TODO: this could be very wrong for Chinese. Not sure how openai calculates the audio token count.
    else:
        logger.warning(f"OpenAI: Unsupported model name: {model}, unable to retrieve the price")
        return 0.0


class OpenAITTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.model_name = config.model_name or "gpt-4o-mini-tts" # default to this model as it's the cheapest
        config.voice_name = config.voice_name or "alloy"
        config.speed = config.speed or 1.0
        config.instructions = config.instructions or None
        config.output_format = config.output_format or "mp3"

        self.price = get_price(config.model_name)
        super().__init__(config)

        self.client = OpenAI(max_retries=4)  # User should set OPENAI_API_KEY environment variable

    def __str__(self) -> str:
        return super().__str__()

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        # Reason: The max num of input tokens is 2000 for gpt-4o-mini-tts https://platform.openai.com/docs/models/gpt-4o-mini-tts. One token is ~4 chars in English but ~1 word/char in Chinese.
        # So we reduce the max num of chars from 4000 to 1800 to avoid the input tokens limit.
        # TODO: detect the language and set the max num of chars accordingly.
        max_chars = 1800

        text_chunks = split_text(text, max_chars, self.config.language)

        audio_segments = []
        chunk_ids = []

        for i, chunk in enumerate(text_chunks, 1):
            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
            logger.info(
                f"Processing {chunk_id}, length={len(chunk)}"
            )
            logger.debug(
                f"Processing {chunk_id}, length={len(chunk)}, text=[{chunk}]"
            )

            # NO retry for OpenAI TTS because SDK has built-in retry logic
            response = self.client.audio.speech.create(
                model=self.config.model_name,
                voice=self.config.voice_name,
                speed=self.config.speed,
                instructions=self.config.instructions,
                input=chunk,
                response_format=self.config.output_format,
            )

            # Log response details
            logger.debug(f"Remote server response: status_code={response.response.status_code}, "
                         f"size={len(response.content)} bytes, "
                         f"content={response.content[:128]}...")
            
            audio_segments.append(io.BytesIO(response.content))
            chunk_ids.append(chunk_id)
        
        # Use utility function to merge audio segments
        merge_audio_segments(audio_segments, output_file, self.config.output_format, chunk_ids, self.config.use_pydub_merge)

        set_audio_tags(output_file, audio_tags)

    def get_break_string(self):
        return "   "

    def get_output_file_extension(self):
        return self.config.output_format

    def validate_config(self):
        if self.config.output_format not in get_supported_formats():
            raise ValueError(f"OpenAI: Unsupported output format: {self.config.output_format}")
        if self.config.speed < 0.25 or self.config.speed > 4.0:
            raise ValueError(f"OpenAI: Unsupported speed: {self.config.speed}")
        if self.config.instructions and len(self.config.instructions) > 0 and self.config.model_name != "gpt-4o-mini-tts":
            raise ValueError(f"OpenAI: Instructions are only supported for 'gpt-4o-mini-tts' model")

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price
