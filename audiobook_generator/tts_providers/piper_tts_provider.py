import io
import logging
import math
import subprocess

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
    return ["mp3", "aac", "flac", "opus"]


class PiperTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        logger.setLevel(config.log)
        config.model_name = config.model_name or "joe"
        config.voice_name = config.voice_name or "joe"
        config.output_format = config.output_format or "mp3"
        self.price = 0.00
        super().__init__(config)

    def __str__(self) -> str:
        return super().__str__()

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        logger.info(
            f"Processing chapter-{audio_tags.idx} <{audio_tags.title}>"
        )
        logger.debug(f"Text: [{text}]")

        cmd = [
            "/opt/local/piper/piper/piper",
            "-m", "/opt/local/piper/en_US-joe-medium.onnx",
            "-c", "/opt/local/piper/en_en_US_joe_medium_en_US-joe-medium.onnx.json",
            "-f", output_file,
            "--length_scale", "1.2",
            "--sentence_silence", "0.4",
        ]
        logger.info(" ".join(cmd))
        results = subprocess.run(
            " ".join(cmd),
            cwd="/opt/local",
            input=text.encode("utf-8"),
            shell=True,
            capture_output=True)
        if results.returncode != 0:
            raise Exception(results.stderr)

        set_audio_tags(output_file, audio_tags)

    def get_break_string(self):
        return "   "

    def get_output_file_extension(self):
        return self.config.output_format

    def validate_config(self):
        pass

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price
