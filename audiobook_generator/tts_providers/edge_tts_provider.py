import asyncio
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


# Credit: https://gist.github.com/moha-abdi/8ddbcb206c38f592c65ada1e5479f2bf
# @phuchoang2603 contributed pause support in https://github.com/p0n1/epub_to_audiobook/pull/45
class CommWithPauses:
    # This class uses edge_tts to generate text
    # but with pauses for example:- text: 'Hello
    # this is simple text. [pause: 1000] Paused 1000ms'
    def __init__(
        self,
        text: str,
        voice_name: str,
        break_string: str,
        break_duration: int = 1250,
        **kwargs,
    ) -> None:
        self.full_text = text
        self.voice_name = voice_name
        self.break_string = break_string
        self.break_duration = int(break_duration)

        self.parsed = self.parse_text()
        self.file = io.BytesIO()

    def parse_text(self):
        logger.debug(
            f"Parsing the text, looking for break/pauses in text: <{self.full_text}>"
        )
        if self.break_string not in self.full_text:
            logger.debug(f"No break/pauses found in the text")
            return [self.full_text]

        parts = self.full_text.split(self.break_string)
        logger.debug(f"split into <{len(parts)}> parts: {parts}")
        return parts

    async def chunkify(self):
        logger.debug(f"Chunkifying the text")
        for content in self.parsed:
            logger.debug(f"content from parsed: <{content}>")
            audio_bytes = await self.generate_audio(content)
            self.file.write(audio_bytes)
            if content != self.parsed[-1] and self.break_duration > 0:
                # only same break duration for all breaks is supported now
                pause_bytes = self.generate_pause(self.break_duration)
                self.file.write(pause_bytes)
        logger.debug(f"Chunkifying done")

    def generate_pause(self, time: int) -> bytes:
        logger.debug(f"Generating pause")
        # pause time should be provided in ms
        silent: AudioSegment = AudioSegment.silent(time, 24000)
        return silent.raw_data  # type: ignore

    async def generate_audio(self, text: str) -> bytes:
        logger.debug(f"Generating audio for: <{text}>")
        # this genertes the real TTS using edge_tts for this part.
        temp_chunk = io.BytesIO()
        communicate = edge_tts.Communicate(text, self.voice_name)
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

    async def save(
        self,
        audio_fname: Union[str, bytes],
    ) -> None:
        await self.chunkify()

        self.file.seek(0)
        audio: AudioSegment = AudioSegment.from_raw(
            self.file, sample_width=2, frame_rate=24000, channels=1
        )
        logger.debug(f"Exporting the audio")
        audio.export(audio_fname)
        logger.info(f"Saved the audio to: {audio_fname}")


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
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):

        communicate = CommWithPauses(
            text=text,
            voice_name=self.config.voice_name,
            break_string=self.get_break_string().strip(),
            break_duration=int(self.config.break_duration),
            rate=self.config.voice_rate,
            volume=self.config.voice_volume,
            pitch=self.config.voice_pitch,
            proxy=self.config.proxy,
        )

        asyncio.run(communicate.save(output_file))

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
