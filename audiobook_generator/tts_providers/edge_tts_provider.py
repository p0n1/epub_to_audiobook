import asyncio
from dataclasses import dataclass
import logging
import math
import io

import edge_tts
from edge_tts import list_voices
from typing import Union
from pydub import AudioSegment

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.book_parsers import ast

logger = logging.getLogger(__name__)


async def get_supported_voices():
    # List all available voices and their attributes.
    # This pulls data from the URL used by Microsoft Edge to return a list of
    # all available voices.
    # Returns:
    #     dict: A dictionary of voice attributes.
    voices = await list_voices()
    voices = sorted(voices, key=lambda voice: voice["ShortName"])

    result = {}

    for voice in voices:
        result[voice["ShortName"]] = voice["Locale"]

    return result


async def _generate_audio(text: str, voice_name: str, pitch: str) -> bytes:
    logger.debug(f"Generating audio for: <{text}>")
    # this genertes the real TTS using edge_tts for this part.
    temp_chunk = io.BytesIO()
    communicate = edge_tts.Communicate(text, voice_name, pitch=pitch)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            temp_chunk.write(chunk["data"])

    temp_chunk.seek(0)
    # handle the case where the chunk is empty
    try:
        logger.debug(f"Decoding the chunk")
        decoded_chunk = AudioSegment.from_mp3(temp_chunk)
    except Exception as e:
        logger.warning(
            f"Failed to decode the chunk, reason: {e}, returning a silent chunk."
        )
        decoded_chunk = AudioSegment.silent(0, 24000)
    logger.debug(f"Returning the decoded chunk")
    return decoded_chunk.raw_data  # type: ignore


async def _generate(chapter: ast.Chapter, voice_name: str, file_path: str, break_duration: int = 1250):
    result = io.BytesIO()

    for item in chapter.items:
        if isinstance(item, ast.Break):
            # generate silence
            result.write(AudioSegment.silent(break_duration, 24000).raw_data)
        elif isinstance(item, ast.Text):
            result.write(await _generate_audio(item.text, voice_name, "+0Hz"))
        elif isinstance(item, ast.Quote):
            result.write(await _generate_audio(item.text, voice_name, "+30Hz"))

    result.seek(0)
    logger.debug(f"Exporting the audio")
    AudioSegment.from_raw(
        result, sample_width=2, frame_rate=24000, channels=1
    ).export(file_path)


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        # TTS provider specific config
        config.voice_name = config.voice_name or "en-US-GuyNeural"
        config.output_format = config.output_format or "audio-24khz-48kbitrate-mono-mp3"
        config.voice_rate = config.voice_rate or "+0%"
        config.voice_volume = config.voice_volume or "+0%"
        config.voice_pitch = config.voice_pitch or "+0Hz"
        config.proxy = config.proxy or None

        # 0.000$ per 1 million characters
        # or 0.000$ per 1000 characters
        self.price = 0.000
        super().__init__(config)

    def __str__(self) -> str:
        return f"{self.config}"

    def validate_config(self):
        supported_voices = asyncio.run(get_supported_voices())
        # logger.debug(f"Supported voices: {supported_voices}")
        if self.config.voice_name not in supported_voices:
            raise ValueError(
                f"EdgeTTS: Unsupported voice name: {self.config.voice_name}"
            )

    def text_to_speech(
        self,
        chapter: ast.Chapter,
        output_file: str,
        audio_tags: AudioTags,
    ):
        asyncio.run(_generate(
            chapter,
            voice_name=self.config.voice_name,
            file_path=output_file,
            break_duration=int(self.config.break_duration))
        )

        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price

    def get_break_string(self):
        return " @BRK#"

    def get_output_file_extension(self):
        if self.config.output_format.endswith("mp3"):
            return "mp3"
        else:
            # Only mp3 supported in edge-tts https://github.com/rany2/edge-tts/issues/179
            raise NotImplementedError(
                f"Unknown file extension for output format: {self.config.output_format}. Only mp3 supported in edge-tts. See https://github.com/rany2/edge-tts/issues/179."
            )
