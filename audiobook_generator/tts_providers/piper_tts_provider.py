import asyncio
import logging
import tempfile
from pathlib import Path
from subprocess import run

import requests
from pydub import AudioSegment
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.utils.docker_helper import get_container, get_docker_client, is_env_var_equal, \
    remove_container, wait_until_initialised
from audiobook_generator.utils.utils import set_audio_tags

logger = logging.getLogger(__name__)

class PiperTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.output_format = config.output_format or "mp3"
        self.price = 0.000
        self.docker_container_name = "piper"
        self.docker_port = 10200
        self.docker_values_checked = False
        self.base_voice_model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
        super().__init__(config)

    def __str__(self) -> str:
        return f"PiperTTSProvider(config={self.config})"

    def validate_config(self):
        pass

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        if self.config.piper_path:
            logger.info("Local Piper installation selected")
            self._text_to_speech_local(text, output_file, audio_tags)
        else:
            logger.info("Docker Piper selected")
            self._text_to_speech_docker(text, output_file, audio_tags)

    def _text_to_speech_docker(self, text: str, output_file: str, audio_tags: AudioTags):

        def start_docker_container():
            logger.info("Starting docker container")
            container = get_docker_client().containers.run(
                image=self.config.piper_docker_image,
                name=self.docker_container_name,
                detach=True,
                ports={str(self.docker_port): self.docker_port},
                environment={
                    "PUID": 1000,
                    "PGID": 1000,
                    "TZ": "Etc/UTC",
                    "PIPER_VOICE": f"{self.config.model_name}",
                    "PIPER_SPEAKER": int(self.config.piper_speaker),
                    "PIPER_NOISE_SCALE": float(self.config.piper_noise_scale),
                    "PIPER_NOISE_W_SCALE": float(self.config.piper_noise_w_scale),
                    "PIPER_LENGTH_SCALE": float(self.config.piper_length_scale),
                    "PIPER_SENTENCE_SILENCE": float(self.config.piper_sentence_silence),
                }
            )
            wait_until_initialised(container, "done.")
            return container

        def get_docker_container():
            container = get_container("piper")
            if not container:
                logger.info("Piper docker container not found")
                container = start_docker_container()
            return container

        def check_docker_values_match():
            if self.docker_values_checked:
                return
            logger.info("Checking docker values match")
            container = get_docker_container()
            values = {
                "PIPER_VOICE": f"{self.config.model_name}",
                "PIPER_SPEAKER": int(self.config.piper_speaker),
                "PIPER_NOISE_SCALE": float(self.config.piper_noise_scale),
                "PIPER_NOISE_W_SCALE": float(self.config.piper_noise_w_scale),
                "PIPER_LENGTH_SCALE": float(self.config.piper_length_scale),
                "PIPER_SENTENCE_SILENCE": float(self.config.piper_sentence_silence)
            }
            for key, val in values.items():
                if not is_env_var_equal(container, key, str(val)):
                    logger.info(f"Environment variable {key} is not equal to {val}, re-deploying docker")
                    remove_container(container)
                    start_docker_container()
                    break
            self.docker_values_checked = True

        async def synthesize_speech(input_text: str):
            client = AsyncTcpClient('localhost', 10200)
            synthesize = Synthesize(text=input_text)
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
                        sample_rate = response_event.data.get("rate", sample_rate)
                        sample_width = response_event.data.get("width", sample_width)
                        if sample_width > 4:
                            sample_width = sample_width // 8
                        channels = response_event.data.get("channels", channels)
                    elif response_event.type == "audio-chunk" and response_event.payload:
                        audio_data.extend(response_event.payload)
                    elif response_event.type == "audio-stop":
                        return AudioSegment(
                            data=bytes(audio_data),
                            sample_width=sample_width,
                            frame_rate=sample_rate,
                            channels=channels,
                        )
                    else:
                        logger.error(f"Unknown event type: {response_event.type}")
            return None, sample_rate, sample_width, channels

        # Start Text to Speech with Docker Piper
        check_docker_values_match()
        audio_segment = asyncio.run(synthesize_speech(text))
        audio_segment.export(output_file, format=self.config.output_format)
        if audio_tags:
            set_audio_tags(output_file, audio_tags)


    def _text_to_speech_local(self, text: str, output_file: str, audio_tags: AudioTags):

        def check_piper_exists():
            if not Path(self.config.piper_path).exists():
                raise FileNotFoundError(f"Piper executable not found at {self.config.piper_path}")

        def check_voice_model_present():
            piper_root_path = Path(self.config.piper_path).parent
            vmp = f"{piper_root_path}/espeak-ng-data/voices/{self.config.model_name}.onnx"
            if Path(vmp).exists():
                return vmp
            return False

        def download_voice_model():
            model_segments = self.config.model_name.split("-")
            language_short = self.config.model_name.split("_")[0]
            language_long = model_segments[0]
            voice = model_segments[1]
            quality = model_segments[2]
            piper_root_path = Path(self.config.piper_path).parent
            voice_model_root_path = f"{piper_root_path}/espeak-ng-data/voices"
            files_to_download = [
                f"{self.base_voice_model_url}/{language_short}/{language_long}/{voice}/{quality}/{self.config.model_name}.onnx?download=true",
                f"{self.base_voice_model_url}/{language_short}/{language_long}/{voice}/{quality}/{self.config.model_name}.onnx.json?download=true.json"
            ]
            for url in files_to_download:
                file_name = f"{self.config.model_name}.onnx"
                file_path = Path(f"{voice_model_root_path}/{file_name}")
                if not file_path.exists():
                    logger.info(f"Downloading {url} to {file_path}")
                    with requests.get(url, stream=True) as response:
                        response.raise_for_status()
                        with open(file_path, "wb") as file:
                            for chunk in response.iter_content(chunk_size=8192):
                                file.write(chunk)
                    logger.info(f"Finished downloading {url}")
                else:
                    logger.info(f"{file_name} already exists, skipping download")
            return f"{voice_model_root_path}/{self.config.model_name}.onnx"

        # Start Text to Speech with local Piper
        check_piper_exists()
        voice_model_path = check_voice_model_present()
        if not voice_model_path:
            logger.info(f"Voice model {self.config.model_name} not found, downloading...")
            voice_model_path = download_voice_model()
            if not voice_model_path:
                raise FileNotFoundError(f"Voice model {self.config.model_name} not found after download")

        with tempfile.TemporaryDirectory() as tmpdirname:
            logger.debug("created temporary directory %r", tmpdirname)

            tmpfilename = Path(tmpdirname) / "piper.wav"
            if not tmpfilename.exists():
                tmpfilename.touch()

            cmd = [
                self.config.piper_path,
                "--model",
                voice_model_path,
                "--speaker",
                str(self.config.piper_speaker),
                "--noise_scale",
                str(self.config.piper_noise_scale),
                " --noise_w",
                str(self.config.piper_noise_w_scale),
                "--sentence_silence",
                str(self.config.piper_sentence_silence),
                "--length_scale",
                str(self.config.piper_length_scale),
                "-f",
                tmpfilename
            ]

            logger.info(
                f"Running Piper TTS command: {' '.join(str(arg) for arg in cmd)}"
            )
            run(
                cmd,
                input=text.encode("utf-8"),
            )

            # set audio tags, need to be done before conversion or opus won't work, not sure why
            if audio_tags:
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
        return 0  # Piper is free

    def get_break_string(self):
        return "."  # Four spaces as the default break string

    def get_output_file_extension(self):
        return self.config.output_format


def get_piper_supported_languages():
    return list(voice_data.keys())

def get_piper_supported_voices(language: str):
    if language not in voice_data:
        raise ValueError(f"Language '{language}' is not supported.")
    return list(voice_data[language].keys())

def get_piper_supported_qualities(language: str, voice_name: str):
    if language not in voice_data:
        raise ValueError(f"Language '{language}' is not supported.")
    if voice_name not in voice_data[language]:
        raise ValueError(f"Voice '{voice_name}' is not supported for language '{language}'.")
    return list(voice_data[language][voice_name].keys())

def get_piper_supported_speakers(language: str, voice_name: str, quality: str):
    if language not in voice_data:
        raise ValueError(f"Language '{language}' is not supported.")
    if voice_name not in voice_data[language]:
        raise ValueError(f"Voice '{voice_name}' is not supported for language '{language}'.")
    if quality not in voice_data[language][voice_name]:
        raise ValueError(f"Quality '{quality}' is not supported for voice '{voice_name}' in language '{language}'.")
    if voice_data[language][voice_name][quality] is None:
        return ["0"]
    return list(range(voice_data[language][voice_name][quality] + 1))


voice_data = {
    "ar_JO": {
        "kareem": {"low": None, "medium": None}
    },
    "ca_ES": {
        "upc_ona": {"x_low": None, "medium": None},
        "upc_pau": {"x_low": None}
    },
    "cs_CZ": {
        "jirka": {"low": None, "medium": None}
    },
    "cy_GB": {
        "gwryw_gogleddol": {"medium": None}
    },
    "da_DK": {
        "talesyntese": {"medium": None}
    },
    "de_DE": {
        "eva_k": {"x_low": None},
        "karlsson": {"low": None},
        "kerstin": {"low": None},
        "mls": {"medium": None},
        "pavoque": {"low": None},
        "ramona": {"low": None},
        "thorsten": {"low": None, "medium": None, "high": None},
        "thorsten_emotional": {"medium": None}
    },
    "el_GR": {
        "rapunzelina": {"low": None}
    },
    "en_GB": {
        "alan": {"low": None, "medium": None},
        "alba": {"medium": None},
        "aru": {"medium": 11},
        "cori": {"medium": None, "high": None},
        "jenny_dioco": {"medium": None},
        "northern_english_male": {"medium": None},
        "semaine": {"medium": 3},
        "southern_english_female": {"low": None},
        "vctk": {"medium": 108}
    },
    "en_US": {
        "amy": {"low": None, "medium": None},
        "arctic": {"medium": 17},
        "bryce": {"medium": None},
        "danny": {"low": None},
        "hfc_female": {"medium": None},
        "hfc_male": {"medium": None},
        "joe": {"medium": None},
        "john": {"medium": None},
        "kathleen": {"low": None},
        "kristin": {"medium": None},
        "kusal": {"medium": None},
        "l2arctic": {"medium": 23},
        "lessac": {"low": None, "medium": None, "high": None},
        "libritts": {"high": 903},
        "libritts_r": {"medium": 903},
        "ljspeech": {"medium": None, "high": None},
        "norman": {"medium": None},
        "ryan": {"low": None, "medium": None, "high": None}
    },
    "es_ES": {
        "carlfm": {"x_low": None},
        "davefx": {"medium": None},
        "mls_10246": {"low": None},
        "mls_9972": {"low": None},
        "sharvard": {"medium": 1}
    },
    "es_MX": {
        "ald": {"medium": None},
        "claude": {"high": None}
    },
    "fa_IR": {
        "amir": {"medium": None},
        "gyro": {"medium": None}
    },
    "fi_FI": {
        "harri": {"low": None, "medium": None}
    },
    "fr_FR": {
        "gilles": {"low": None},
        "mls": {"medium": 124},
        "mls_1840": {"low": None},
        "siwis": {"low": None, "medium": None},
        "tom": {"medium": None},
        "upmc": {"medium": 1}
    },
    "hu_HU": {
        "anna": {"medium": None},
        "berta": {"medium": None},
        "imre": {"medium": None}
    },
    "is_IS": {
        "bui": {"medium": None},
        "salka": {"medium": None},
        "steinn": {"medium": None},
        "ugla": {"medium": None}
    },
    "it_IT": {
        "paola": {"medium": None},
        "riccardo": {"x_low": None}
    },
    "ka_GE": {
        "natia": {"medium": None}
    },
    "kk_KZ": {
        "iseke": {"x_low": None},
        "issai": {"high": 5},
        "raya": {"x_low": None}
    },
    "lb_LU": {
        "marylux": {"medium": None}
    },
    "ne_NP": {
        "google": {"x_low": 17, "medium": 17}
    },
    "nl_BE": {
        "nathalie": {"x_low": None, "medium": None},
        "rdh": {"x_low": None, "medium": None}
    },
    "nl_NL": {
        "mls": {"medium": 51},
        "mls_5809": {"low": None},
        "mls_7432": {"low": None}
    },
    "no_NO": {
        "talesyntese": {"medium": None}
    },
    "pl_PL": {
        "darkman": {"medium": None},
        "gosia": {"medium": None},
        "mc_speech": {"medium": None},
        "mls_6892": {"low": None}
    },
    "pt_BR": {
        "edresson": {"low": None},
        "faber": {"medium": None}
    },
    "pt_PT": {
        "tugаo": {"medium": None}
    },
    "ro_RO": {
        "mihai": {"medium": None}
    },
    "ru_RU": {
        "denis": {"medium": None},
        "dmitri": {"medium": None},
        "irina": {"medium": None},
        "ruslan": {"medium": None}
    },
    "sk_SK": {
        "lili": {"medium": None}
    },
    "sl_SI": {
        "artur": {"medium": None}
    },
    "sr_RS": {
        "serbski_institut": {"medium": 1}
    },
    "sv_SE": {
        "nst": {"medium": None}
    },
    "sw_CD": {
        "lanfrica": {"medium": None}
    },
    "tr_TR": {
        "dfki": {"medium": None},
        "fahrettin": {"medium": None},
        "fettah": {"medium": None}
    },
    "uk_UA": {
        "lada": {"x_low": None},
        "ukrainian_tts": {"medium": 2}
    },
    "vi_VN": {
        "25hours_single": {"low": None},
        "vais1000": {"medium": None},
        "vivos": {"x_low": 64}
    },
    "zh_CN": {
        "huayan": {"x_low": None, "medium": None}
    }
}
