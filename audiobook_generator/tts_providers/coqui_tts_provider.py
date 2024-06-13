import logging
import math
import tempfile

import torch
from pydub import AudioSegment
from TTS.api import TTS

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)


class CoquiTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        # Init TTS with the target model name

        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        logger.setLevel(config.log)

        # TTS provider specific config
        config.output_format = config.output_format or 'mp3'
        config.model_name = config.model_name or 'tts_models/en/ljspeech/tacotron2-DDC'
        config.language_coqui = config.language_coqui or 'en'
        config.voice_sample_wav_path = config.voice_sample_wav_path or ''

        self.tts = TTS(
            model_name=config.model_name,
            progress_bar=True,
        ).to(device)

        self.price = 0.000
        super().__init__(config)

    def __str__(self) -> str:
        return f'{self.config}'

    def validate_config(self):
        pass

    def text_to_speech(
        self,
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):

        with tempfile.TemporaryDirectory() as tmpdirname:
            print('created temporary directory', tmpdirname)

            tmpfilename = tmpdirname + '/file.wav'

            if self.tts.is_multi_lingual:
                print(len(text))
                self.tts.tts_to_file(
                    text,
                    speaker_wav=self.config.voice_sample_wav_path,
                    language=self.config.language_coqui,
                    file_path=tmpfilename,
                    split_sentences=True,
                )
            else:
                self.tts.tts_to_file(
                    text,
                    file_path=tmpfilename,
                    split_sentences=True,
                )

            # Convert the wav file to the desired format
            AudioSegment.from_wav(tmpfilename).export(output_file, format=self.config.output_format)

        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price

    def get_break_string(self):
        return '    '

    def get_output_file_extension(self):
        if self.config.output_format.startswith('amr'):
            return 'amr'
        elif self.config.output_format.startswith('ogg'):
            return 'ogg'
        elif self.config.output_format.endswith('truesilk'):
            return 'silk'
        elif self.config.output_format.endswith('pcm'):
            return 'pcm'
        elif self.config.output_format.startswith('raw'):
            return 'wav'
        elif self.config.output_format.startswith('webm'):
            return 'webm'
        elif self.config.output_format.endswith('opus'):
            return 'opus'
        elif self.config.output_format.endswith('mp3'):
            return 'mp3'
        else:
            raise NotImplementedError(
                f'Unknown file extension for output format: {self.config.output_format}'
            )

    def get_supported_models(self):
        print(self.tts.list_models())
