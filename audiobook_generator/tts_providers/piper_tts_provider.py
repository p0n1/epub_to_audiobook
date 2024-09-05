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

        # TTS provider specific config
        config.output_format = config.output_format or "mp3"

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

            cmd = [
                self.config.piper_path,
                "--model",
                self.config.model_name,
                "--speaker",
                str(self.config.piper_speaker),
                "--sentence_silence",
                str(self.config.piper_sentence_silence),
                "--length_scale",
                str(self.config.piper_length_scale),
                "-f",
                tmpfilename,
                "--debug",
            ]

            logger.info(
                f"Running Piper TTS command: {' '.join(str(arg) for arg in cmd)}"
            )
            run(
                cmd,
                input=text.encode("utf-8"),
            )

            # set audio tags, need to be done before conversion or opus won't work, not sure why
            set_audio_tags(tmpfilename, audio_tags)

            logger.info(
                f"Piper TTS command completed, converting {tmpfilename} to {self.config.output_format} format"
            )

            # Convert the wav file to the desired format
            AudioSegment.from_wav(tmpfilename).export(
                output_file, format=self.config.output_format
            )

            logger.info(f"Conversion completed, output file: {output_file}")

    def estimate_cost(self, total_chars):
        return 0

    def get_break_string(self):
        return "    "

    def get_output_file_extension(self):
        return self.config.output_format
