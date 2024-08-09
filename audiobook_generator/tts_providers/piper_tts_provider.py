import logging
import math
from pathlib import Path
import subprocess

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider


logger = logging.getLogger(__name__)


def get_supported_models():
    return []


def get_supported_voices():
    # really, whatever is in the configured "piper_voice_folder"
    # note, you may have to name the onnx and onnx.json files to
    # match what is expected below
    return []


def get_supported_formats():
    # piper only supports output as a wav
    return ["wav"]


class PiperTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        logger.setLevel(config.log)
        config.model_name = config.model_name or "joe"
        config.voice_name = config.voice_name or "joe"
        config.output_format = config.output_format or "wav"
        self.price = 0.00
        super().__init__(config)

    def __str__(self) -> str:
        return super().__str__()

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        logger.info(
            f"Processing chapter-{audio_tags.idx} <{audio_tags.title}>"
        )
        logger.debug(f"Text: [{text}]")

        lang_underscore = self.config.language.replace("-", "_")
        voice_folder = Path(self.config.piper_voice_folder)
        model_path = voice_folder / f"{lang_underscore}-{self.config.voice_name}-{self.config.piper_quality}.onnx"
        config_path = voice_folder / f"{lang_underscore}_{self.config.voice_name}_{self.config.piper_quality}_{lang_underscore}-{self.config.voice_name}-{self.config.piper_quality}.onnx.json"
        cmd = [
            self.config.path_to_piper,
            "-m", f"{model_path}",
            "-c", f"{config_path}",
            "-f", output_file,
            "--length_scale", self.config.piper_length_scale,
            "--sentence_silence", self.config.piper_sentence_silence,
        ]
        logger.info(" ".join(cmd))
        results = subprocess.run(
            " ".join(cmd),
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
