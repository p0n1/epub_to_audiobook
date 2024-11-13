from math import e
import os
import asyncio
import logging
import timeit
from typing import Optional, Union, List, Tuple


from pydub import AudioSegment
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

__all__ = ["PiperDockerTTSProvider"]


class PiperCommWithPauses:
    def __init__(
        self,
        text: str,
        break_string: str = "    ",
        break_duration: int = 1250,
        output_format: str = "mp3",
        **kwargs,
    ):
        self.full_text = text
        self.host = os.getenv("PIPER_HOST", "piper")
        self.port = int(os.getenv("PIPER_PORT", 10200))
        self.break_string = break_string
        self.break_duration = int(break_duration)
        self.output_format = output_format
        self.client: Optional[AsyncTcpClient] = None

        self.parsed = self.parse_text()

    def parse_text(self) -> List[str]:
        logger.debug(
            f"Parsing the text, looking for breaks/pauses using break string: '{self.break_string}'"
        )
        if self.break_string not in self.full_text or not self.break_string:
            logger.debug("No breaks/pauses found in the text")
            return [self.full_text]

        parts = self.full_text.split(self.break_string)
        parts = [part for part in parts if part.strip() != ""]
        new_parts = [
            self.break_string.join(parts[i : i + 10]) for i in range(0, len(parts), 10)
        ]
        logger.debug(f"Split into {len(new_parts)} parts")
        return new_parts

    def generate_pause(self, duration_ms: int) -> AudioSegment:
        logger.debug(f"Generating pause of {duration_ms} ms")
        # Generate a silent AudioSegment as a pause
        silent = AudioSegment.silent(duration=duration_ms)
        return silent

    async def synthesize_and_convert_with_semaphore(
        self, idx_text: Tuple[int, str], sem: asyncio.Semaphore
    ) -> Tuple[int, AudioSegment]:
        async with sem:
            return await self.synthesize_and_convert(idx_text)

    async def synthesize(self, text: str) -> Tuple[bytes, int, int, int]:
        """Sends a synthesis request to the Piper TTS server and returns the audio data and metadata."""

        audio_data, sample_rate, sample_width, channels = await self.synthesize_speech(
            text, host=self.host, port=self.port
        )
        if not audio_data:
            logger.error("No audio data received")
            return b"", 0, 0, 0
        return audio_data, sample_rate, sample_width, channels

    async def synthesize_and_convert(
        self, idx_text: Tuple[int, str]
    ) -> Tuple[int, AudioSegment]:
        """Asynchronously synthesizes text and returns a tuple of index and AudioSegment."""
        idx, text = idx_text
        audio_data, rate, width, channels = await self.synthesize(text)
        if audio_data == b"":
            raise ValueError("No audio data received")
        # Ensure sample_width is in bytes per sample
        if width > 4:  # Assume width is in bits
            width = width // 8
        # Convert audio data (bytes) to AudioSegment
        audio_segment = AudioSegment(
            data=audio_data,
            sample_width=width,
            frame_rate=rate,
            channels=channels,
        )
        return idx, audio_segment

    async def chunkify(self) -> AudioSegment:
        """Old perf: 11x realtime

        Returns:
            AudioSegment: _description_
        """
        logger.debug("Starting chunkify process")
        # Prepare the list of texts with their indices

        indexed_texts = list(enumerate(self.parsed))
        max_concurrent_tasks = 5
        sem = asyncio.Semaphore(max_concurrent_tasks)

        tasks = [
            self.synthesize_and_convert_with_semaphore(idx_text, sem)
            for idx_text in indexed_texts
        ]

        results = []
        start = timeit.default_timer()
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            now = timeit.default_timer()
            elapsed = now - start
            total_seconds_remaining = (len(tasks) - len(results)) * (
                elapsed / max(1, len(results))
            )
            estimated_remaining_time_m = total_seconds_remaining // 60
            estimated_remaining_time_s = total_seconds_remaining % 60
            print(
                f"Processed {len(results)} of {len(tasks)} chunks in chapter. Estimated time remaining for chapter: {round(estimated_remaining_time_m)} min, {round(estimated_remaining_time_s)} sec",
                end="\r",
                flush=True,
            )

        # results = await asyncio.gather(*tasks, return_exceptions=True)

        audio_segments = []
        # Collect results and reconstruct the audio segments in order
        results_dict = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"An error occurred during synthesis: {result}")
                continue
            if not isinstance(result, tuple):
                logger.error(f"Unexpected result: {result}")
                continue
            idx, audio_segment = result
            results_dict[idx] = audio_segment

        for idx in range(len(self.parsed)):
            audio_segment = results_dict.get(idx)
            if audio_segment:
                audio_segments.append(audio_segment)
                if idx < len(self.parsed) - 1 and self.break_duration > 0:
                    # Insert pause
                    pause_segment = self.generate_pause(self.break_duration)
                    audio_segments.append(pause_segment)
            else:
                logger.error(f"Missing audio segment at index {idx}")

        # Stitch the audio segments together
        combined = sum(audio_segments, AudioSegment.empty())
        logger.debug("Chunkify process completed")
        return combined

    def save(self, audio_fname: Union[str, bytes]) -> None:
        combined = asyncio.run(self.chunkify())
        # Export the combined audio to the desired format
        combined.export(audio_fname, format=self.output_format)
        logger.info(f"Audio saved to: {audio_fname}")

    def get_client(self, host: str, port: int) -> AsyncTcpClient:
        # if not self.client:
        #     self.client = AsyncTcpClient(host, port)
        # return self.client
        return AsyncTcpClient(host, port)

    async def synthesize_speech(self, text: str, host: str, port: int):
        client = self.get_client(host, port)
        synthesize = Synthesize(text=text)
        request_event = synthesize.event()

        audio_data = bytearray()
        sample_rate = 22050  # Default sample rate
        sample_width = 2  # Default to 16-bit audio
        channels = 1  # Default to mono

        async with client:
            await client.write_event(request_event)

            while True:
                response_event = await client.read_event()
                if response_event is None:
                    break

                if response_event.type == "audio-start":
                    # Extract audio metadata if available
                    sample_rate = response_event.data.get("rate", sample_rate)
                    sample_width = response_event.data.get("width", sample_width)
                    channels = response_event.data.get("channels", channels)
                elif response_event.type == "audio-chunk" and response_event.payload:
                    audio_data.extend(response_event.payload)
                elif response_event.type == "audio-stop":
                    return bytes(audio_data), sample_rate, sample_width, channels
                else:
                    raise ValueError(f"Unexpected event type: {response_event.type}")
        return None, sample_rate, sample_width, channels


class PiperDockerTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        # TTS provider specific config
        config.output_format = config.output_format or "mp3"
        config.break_duration = int(config.break_duration or 1250)  # in milliseconds

        self.price = 0.000  # Piper is free to use
        super().__init__(config)

    def __str__(self) -> str:
        return f"PiperDockerTTSProvider(config={self.config})"

    def validate_config(self):
        # Add any necessary validation for the config here
        pass

    def text_to_speech(
        self,
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):
        piper_comm = PiperCommWithPauses(
            text=text,
            break_string=self.get_break_string().strip(),
            break_duration=self.config.break_duration,
            output_format=self.config.output_format,
        )

        piper_comm.save(output_file)

        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        return 0  # Piper is free

    def get_break_string(self):
        return "."  # Four spaces as the default break string

    def get_output_file_extension(self):
        return self.config.output_format
