import asyncio
import logging
import math
import io

from edge_tts import Communicate, list_voices
from typing import Union, Optional
from pydub import AudioSegment

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

MAX_RETRIES = 12  # Max_retries constant for network errors


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

class CommWithPauses(Communicate):
    # This class uses edge_tts to generate text
    # but with pauses for example:- text: 'Hello
    # this is simple text. [pause: 2s] Paused 2s'
    def __init__(
        self,
        text: str,
        voice_name: str,
        **kwargs
    ) -> None:
        super().__init__(text, voice_name, **kwargs)
        self.parsed = self.parse_text()
        self.file = io.BytesIO()

    def parse_text(self):
        if not "[pause:" in self.text:
            return [(0, self.text)]
        
        parts = self.text.split("[pause:")
        for part in parts:
            if "]" in part:
                pause_time, content = part.split("]", 1)
                yield int(pause_time), content.strip()

            else:
                content = part
                yield 0, content.strip()

    async def chunkify(self):
        for pause_time, content in self.parsed:
            if pause_time:
                pause_bytes = self.generate_pause(pause_time)
                self.file.write(pause_bytes)

            if content:
                audio_bytes = await self.generate_audio(content)
                self.file.write(audio_bytes)

    def generate_pause(self, time: int) -> bytes:
        # pause time should be provided in ms
        silent: AudioSegment = AudioSegment.silent(time, 24000)
        return silent.raw_data

    async def generate_audio(self, text: str) -> bytes:
        # this genertes the real TTS using edge_tts for this part.
        temp_chunk = io.BytesIO()
        self.text = text
        async for chunk in self.stream():
            if chunk['type'] == 'audio':
                temp_chunk.write(chunk['data'])

        temp_chunk.seek(0)
        # handle the case where the chunk is empty
        try:
            decoded_chunk = AudioSegment.from_mp3(temp_chunk)
        except:
            decoded_chunk = AudioSegment.silent(0, 24000)
        return decoded_chunk.raw_data

    async def save(
        self,
        audio_fname: Union[str, bytes],
        metadata_fname: Optional[Union[str, bytes]] = None,
    ) -> None:
        # Save the audio and metadata to the specified files.
        await self.chunkify()
        await super().save(audio_fname, metadata_fname)

        self.file.seek(0)
        audio: AudioSegment = AudioSegment.from_raw(
            self.file,
            sample_width=2,
            frame_rate=24000,
            channels=1
        )
        audio.export(audio_fname)

class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        logger.setLevel(config.log)
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

    async def validate_config(self):
        if self.config.voice_name not in await get_supported_voices():
            raise ValueError(f"EdgeTTS: Unsupported voice name: {self.config.voice_name}")

    def text_to_speech(
            self,
            text: str,
            output_file: str,
            audio_tags: AudioTags,
    ):
        # Replace break string with pause tag
        text = text.replace(
            self.get_break_string().strip(),
            f"[pause: {self.config.break_duration}]"
        )

        communicate = CommWithPauses(
            text=text,
            voice_name=self.config.voice_name,
            rate=self.config.voice_rate,
            volume=self.config.voice_volume,
            pitch=self.config.voice_pitch,
            proxy=self.config.proxy
        )

        asyncio.run(
            communicate.save(output_file)
        )

        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price

    def get_break_string(self):
        return " @BRK#"

    def get_output_file_extension(self):
        if self.config.output_format.startswith("amr"):
            return "amr"
        elif self.config.output_format.startswith("ogg"):
            return "ogg"
        elif self.config.output_format.endswith("truesilk"):
            return "silk"
        elif self.config.output_format.endswith("pcm"):
            return "pcm"
        elif self.config.output_format.startswith("raw"):
            return "wav"
        elif self.config.output_format.startswith("webm"):
            return "webm"
        elif self.config.output_format.endswith("opus"):
            return "opus"
        elif self.config.output_format.endswith("mp3"):
            return "mp3"
        else:
            raise NotImplementedError(f"Unknown file extension for output format: {self.config.output_format}")
