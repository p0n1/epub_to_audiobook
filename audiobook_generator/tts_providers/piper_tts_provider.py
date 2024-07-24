import tempfile
from subprocess import run
from pathlib import Path
import logging


from pydub import AudioSegment

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

__all__ = ["PiperTTSProvider"]


class PiperTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        logger.setLevel(config.log)

        # TTS provider specific config
        config.output_format = config.output_format or "opus"

        if config.voice_rate is None:
            config.voice_rate = 1.0
        else:
            try:
                config.voice_rate = float(config.voice_rate)
            except ValueError:
                logger.error("Invalid voice_rate %r", config.voice_rate)
                config.voice_rate = 1.0
        config.voice_name = config.voice_name or "0"
        config.break_duration = config.break_duration or 0.2

        # 0.000$ per 1 million characters
        # or 0.000$ per 1000 characters
        self.price = 0.000
        super().__init__(config)

    def __str__(self) -> str:
        return f"{self.config}"

    def validate_config(self):
        pass

    def text_to_speech(
        self,
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):

        with tempfile.TemporaryDirectory() as tmpdirname:
            logger.debug("created temporary directory %r", tmpdirname)

            tmpfilename = Path(tmpdirname) / "piper.wav"

            run(
                [
                    "piper-tts",
                    "--model",
                    self.config.model_name,
                    "--speaker",
                    self.config.voice_name,
                    "--sentence_silence",
                    str(self.config.break_duration),
                    "--length_scale",
                    str(1.0 / self.config.voice_rate),
                    "-f",
                    tmpfilename,
                ],
                input=text.encode("utf-8"),
            )

            # Convert the wav file to the desired format
            AudioSegment.from_wav(tmpfilename).export(
                output_file, format=self.config.output_format
            )

        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        return 0

    def get_break_string(self):
        return "    "

    def get_output_file_extension(self):
        return self.config.output_format
