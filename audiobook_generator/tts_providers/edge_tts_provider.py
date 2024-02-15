import asyncio
import logging
import math
import io

from edge_tts.communicate import Communicate
from typing import Union, Optional
from pydub import AudioSegment

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.utils import set_audio_tags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

MAX_RETRIES = 12  # Max_retries constant for network errors


def get_supported_voices():
    # https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/voices/list?trustedclienttoken=6A5AA1D4EAFF4E9FB37E23D68491D6F4
    return {
        'zh-CN-XiaoxiaoNeural': 'zh-CN',
        'zh-CN-XiaoyiNeural': 'zh-CN',
        'zh-CN-YunjianNeural': 'zh-CN',
        'zh-CN-YunxiNeural': 'zh-CN',
        'zh-CN-YunxiaNeural': 'zh-CN',
        'zh-CN-YunyangNeural': 'zh-CN',
        'zh-HK-HiuGaaiNeural': 'zh-HK',
        'zh-HK-HiuMaanNeural': 'zh-HK',
        'zh-HK-WanLungNeural': 'zh-HK',
        'zh-TW-HsiaoChenNeural': 'zh-TW',
        'zh-TW-YunJheNeural': 'zh-TW',
        'zh-TW-HsiaoYuNeural': 'zh-TW',
        'af-ZA-AdriNeural': 'af-ZA',
        'af-ZA-WillemNeural': 'af-ZA',
        'am-ET-AmehaNeural': 'am-ET',
        'am-ET-MekdesNeural': 'am-ET',
        'ar-AE-FatimaNeural': 'ar-AE',
        'ar-AE-HamdanNeural': 'ar-AE',
        'ar-BH-AliNeural': 'ar-BH',
        'ar-BH-LailaNeural': 'ar-BH',
        'ar-DZ-AminaNeural': 'ar-DZ',
        'ar-DZ-IsmaelNeural': 'ar-DZ',
        'ar-EG-SalmaNeural': 'ar-EG',
        'ar-EG-ShakirNeural': 'ar-EG',
        'ar-IQ-BasselNeural': 'ar-IQ',
        'ar-IQ-RanaNeural': 'ar-IQ',
        'ar-JO-SanaNeural': 'ar-JO',
        'ar-JO-TaimNeural': 'ar-JO',
        'ar-KW-FahedNeural': 'ar-KW',
        'ar-KW-NouraNeural': 'ar-KW',
        'ar-LB-LaylaNeural': 'ar-LB',
        'ar-LB-RamiNeural': 'ar-LB',
        'ar-LY-ImanNeural': 'ar-LY',
        'ar-LY-OmarNeural': 'ar-LY',
        'ar-MA-JamalNeural': 'ar-MA',
        'ar-MA-MounaNeural': 'ar-MA',
        'ar-OM-AbdullahNeural': 'ar-OM',
        'ar-OM-AyshaNeural': 'ar-OM',
        'ar-QA-AmalNeural': 'ar-QA',
        'ar-QA-MoazNeural': 'ar-QA',
        'ar-SA-HamedNeural': 'ar-SA',
        'ar-SA-ZariyahNeural': 'ar-SA',
        'ar-SY-AmanyNeural': 'ar-SY',
        'ar-SY-LaithNeural': 'ar-SY',
        'ar-TN-HediNeural': 'ar-TN',
        'ar-TN-ReemNeural': 'ar-TN',
        'ar-YE-MaryamNeural': 'ar-YE',
        'ar-YE-SalehNeural': 'ar-YE',
        'az-AZ-BabekNeural': 'az-AZ',
        'az-AZ-BanuNeural': 'az-AZ',
        'bg-BG-BorislavNeural': 'bg-BG',
        'bg-BG-KalinaNeural': 'bg-BG',
        'bn-BD-NabanitaNeural': 'bn-BD',
        'bn-BD-PradeepNeural': 'bn-BD',
        'bn-IN-BashkarNeural': 'bn-IN',
        'bn-IN-TanishaaNeural': 'bn-IN',
        'bs-BA-GoranNeural': 'bs-BA',
        'bs-BA-VesnaNeural': 'bs-BA',
        'ca-ES-EnricNeural': 'ca-ES',
        'ca-ES-JoanaNeural': 'ca-ES',
        'cs-CZ-AntoninNeural': 'cs-CZ',
        'cs-CZ-VlastaNeural': 'cs-CZ',
        'cy-GB-AledNeural': 'cy-GB',
        'cy-GB-NiaNeural': 'cy-GB',
        'da-DK-ChristelNeural': 'da-DK',
        'da-DK-JeppeNeural': 'da-DK',
        'de-AT-IngridNeural': 'de-AT',
        'de-AT-JonasNeural': 'de-AT',
        'de-CH-JanNeural': 'de-CH',
        'de-CH-LeniNeural': 'de-CH',
        'de-DE-AmalaNeural': 'de-DE',
        'de-DE-ConradNeural': 'de-DE',
        'de-DE-KatjaNeural': 'de-DE',
        'de-DE-KillianNeural': 'de-DE',
        'el-GR-AthinaNeural': 'el-GR',
        'el-GR-NestorasNeural': 'el-GR',
        'en-AU-NatashaNeural': 'en-AU',
        'en-AU-WilliamNeural': 'en-AU',
        'en-CA-ClaraNeural': 'en-CA',
        'en-CA-LiamNeural': 'en-CA',
        'en-GB-LibbyNeural': 'en-GB',
        'en-GB-MaisieNeural': 'en-GB',
        'en-GB-RyanNeural': 'en-GB',
        'en-GB-SoniaNeural': 'en-GB',
        'en-GB-ThomasNeural': 'en-GB',
        'en-HK-SamNeural': 'en-HK',
        'en-HK-YanNeural': 'en-HK',
        'en-IE-ConnorNeural': 'en-IE',
        'en-IE-EmilyNeural': 'en-IE',
        'en-IN-NeerjaNeural': 'en-IN',
        'en-IN-PrabhatNeural': 'en-IN',
        'en-KE-AsiliaNeural': 'en-KE',
        'en-KE-ChilembaNeural': 'en-KE',
        'en-NG-AbeoNeural': 'en-NG',
        'en-NG-EzinneNeural': 'en-NG',
        'en-NZ-MitchellNeural': 'en-NZ',
        'en-NZ-MollyNeural': 'en-NZ',
        'en-PH-JamesNeural': 'en-PH',
        'en-PH-RosaNeural': 'en-PH',
        'en-SG-LunaNeural': 'en-SG',
        'en-SG-WayneNeural': 'en-SG',
        'en-TZ-ElimuNeural': 'en-TZ',
        'en-TZ-ImaniNeural': 'en-TZ',
        'en-US-AnaNeural': 'en-US',
        'en-US-AriaNeural': 'en-US',
        'en-US-ChristopherNeural': 'en-US',
        'en-US-EricNeural': 'en-US',
        'en-US-GuyNeural': 'en-US',
        'en-US-JennyNeural': 'en-US',
        'en-US-MichelleNeural': 'en-US',
        'en-ZA-LeahNeural': 'en-ZA',
        'en-ZA-LukeNeural': 'en-ZA',
        'es-AR-ElenaNeural': 'es-AR',
        'es-AR-TomasNeural': 'es-AR',
        'es-BO-MarceloNeural': 'es-BO',
        'es-BO-SofiaNeural': 'es-BO',
        'es-CL-CatalinaNeural': 'es-CL',
        'es-CL-LorenzoNeural': 'es-CL',
        'es-CO-GonzaloNeural': 'es-CO',
        'es-CO-SalomeNeural': 'es-CO',
        'es-CR-JuanNeural': 'es-CR',
        'es-CR-MariaNeural': 'es-CR',
        'es-CU-BelkysNeural': 'es-CU',
        'es-CU-ManuelNeural': 'es-CU',
        'es-DO-EmilioNeural': 'es-DO',
        'es-DO-RamonaNeural': 'es-DO',
        'es-EC-AndreaNeural': 'es-EC',
        'es-EC-LuisNeural': 'es-EC',
        'es-ES-AlvaroNeural': 'es-ES',
        'es-ES-ElviraNeural': 'es-ES',
        'es-ES-ManuelEsCUNeural': 'es-ES',
        'es-GQ-JavierNeural': 'es-GQ',
        'es-GQ-TeresaNeural': 'es-GQ',
        'es-GT-AndresNeural': 'es-GT',
        'es-GT-MartaNeural': 'es-GT',
        'es-HN-CarlosNeural': 'es-HN',
        'es-HN-KarlaNeural': 'es-HN',
        'es-MX-DaliaNeural': 'es-MX',
        'es-MX-JorgeNeural': 'es-MX',
        'es-MX-LorenzoEsCLNeural': 'es-MX',
        'es-NI-FedericoNeural': 'es-NI',
        'es-NI-YolandaNeural': 'es-NI',
        'es-PA-MargaritaNeural': 'es-PA',
        'es-PA-RobertoNeural': 'es-PA',
        'es-PE-AlexNeural': 'es-PE',
        'es-PE-CamilaNeural': 'es-PE',
        'es-PR-KarinaNeural': 'es-PR',
        'es-PR-VictorNeural': 'es-PR',
        'es-PY-MarioNeural': 'es-PY',
        'es-PY-TaniaNeural': 'es-PY',
        'es-SV-LorenaNeural': 'es-SV',
        'es-SV-RodrigoNeural': 'es-SV',
        'es-US-AlonsoNeural': 'es-US',
        'es-US-PalomaNeural': 'es-US',
        'es-UY-MateoNeural': 'es-UY',
        'es-UY-ValentinaNeural': 'es-UY',
        'es-VE-PaolaNeural': 'es-VE',
        'es-VE-SebastianNeural': 'es-VE',
        'et-EE-AnuNeural': 'et-EE',
        'et-EE-KertNeural': 'et-EE',
        'fa-IR-DilaraNeural': 'fa-IR',
        'fa-IR-FaridNeural': 'fa-IR',
        'fi-FI-HarriNeural': 'fi-FI',
        'fi-FI-NooraNeural': 'fi-FI',
        'fil-PH-AngeloNeural': 'fil-PH',
        'fil-PH-BlessicaNeural': 'fil-PH',
        'fr-BE-CharlineNeural': 'fr-BE',
        'fr-BE-GerardNeural': 'fr-BE',
        'fr-CA-AntoineNeural': 'fr-CA',
        'fr-CA-JeanNeural': 'fr-CA',
        'fr-CA-SylvieNeural': 'fr-CA',
        'fr-CH-ArianeNeural': 'fr-CH',
        'fr-CH-FabriceNeural': 'fr-CH',
        'fr-FR-DeniseNeural': 'fr-FR',
        'fr-FR-EloiseNeural': 'fr-FR',
        'fr-FR-HenriNeural': 'fr-FR',
        'ga-IE-ColmNeural': 'ga-IE',
        'ga-IE-OrlaNeural': 'ga-IE',
        'gl-ES-RoiNeural': 'gl-ES',
        'gl-ES-SabelaNeural': 'gl-ES',
        'gu-IN-DhwaniNeural': 'gu-IN',
        'gu-IN-NiranjanNeural': 'gu-IN',
        'he-IL-AvriNeural': 'he-IL',
        'he-IL-HilaNeural': 'he-IL',
        'hi-IN-MadhurNeural': 'hi-IN',
        'hi-IN-SwaraNeural': 'hi-IN',
        'hr-HR-GabrijelaNeural': 'hr-HR',
        'hr-HR-SreckoNeural': 'hr-HR',
        'hu-HU-NoemiNeural': 'hu-HU',
        'hu-HU-TamasNeural': 'hu-HU',
        'id-ID-ArdiNeural': 'id-ID',
        'id-ID-GadisNeural': 'id-ID',
        'is-IS-GudrunNeural': 'is-IS',
        'is-IS-GunnarNeural': 'is-IS',
        'it-IT-DiegoNeural': 'it-IT',
        'it-IT-ElsaNeural': 'it-IT',
        'it-IT-IsabellaNeural': 'it-IT',
        'ja-JP-KeitaNeural': 'ja-JP',
        'ja-JP-NanamiNeural': 'ja-JP',
        'jv-ID-DimasNeural': 'jv-ID',
        'jv-ID-SitiNeural': 'jv-ID',
        'ka-GE-EkaNeural': 'ka-GE',
        'ka-GE-GiorgiNeural': 'ka-GE',
        'kk-KZ-AigulNeural': 'kk-KZ',
        'kk-KZ-DauletNeural': 'kk-KZ',
        'km-KH-PisethNeural': 'km-KH',
        'km-KH-SreymomNeural': 'km-KH',
        'kn-IN-GaganNeural': 'kn-IN',
        'kn-IN-SapnaNeural': 'kn-IN',
        'ko-KR-InJoonNeural': 'ko-KR',
        'ko-KR-SunHiNeural': 'ko-KR',
        'lo-LA-ChanthavongNeural': 'lo-LA',
        'lo-LA-KeomanyNeural': 'lo-LA',
        'lt-LT-LeonasNeural': 'lt-LT',
        'lt-LT-OnaNeural': 'lt-LT',
        'lv-LV-EveritaNeural': 'lv-LV',
        'lv-LV-NilsNeural': 'lv-LV',
        'mk-MK-AleksandarNeural': 'mk-MK',
        'mk-MK-MarijaNeural': 'mk-MK',
        'ml-IN-MidhunNeural': 'ml-IN',
        'ml-IN-SobhanaNeural': 'ml-IN',
        'mn-MN-BataaNeural': 'mn-MN',
        'mn-MN-YesuiNeural': 'mn-MN',
        'mr-IN-AarohiNeural': 'mr-IN',
        'mr-IN-ManoharNeural': 'mr-IN',
        'ms-MY-OsmanNeural': 'ms-MY',
        'ms-MY-YasminNeural': 'ms-MY',
        'mt-MT-GraceNeural': 'mt-MT',
        'mt-MT-JosephNeural': 'mt-MT',
        'my-MM-NilarNeural': 'my-MM',
        'my-MM-ThihaNeural': 'my-MM',
        'nb-NO-FinnNeural': 'nb-NO',
        'nb-NO-PernilleNeural': 'nb-NO',
        'ne-NP-HemkalaNeural': 'ne-NP',
        'ne-NP-SagarNeural': 'ne-NP',
        'nl-BE-ArnaudNeural': 'nl-BE',
        'nl-BE-DenaNeural': 'nl-BE',
        'nl-NL-ColetteNeural': 'nl-NL',
        'nl-NL-FennaNeural': 'nl-NL',
        'nl-NL-MaartenNeural': 'nl-NL',
        'pl-PL-MarekNeural': 'pl-PL',
        'pl-PL-ZofiaNeural': 'pl-PL',
        'ps-AF-GulNawazNeural': 'ps-AF',
        'ps-AF-LatifaNeural': 'ps-AF',
        'pt-BR-AntonioNeural': 'pt-BR',
        'pt-BR-FranciscaNeural': 'pt-BR',
        'pt-PT-DuarteNeural': 'pt-PT',
        'pt-PT-RaquelNeural': 'pt-PT',
        'ro-RO-AlinaNeural': 'ro-RO',
        'ro-RO-EmilNeural': 'ro-RO',
        'ru-RU-DmitryNeural': 'ru-RU',
        'ru-RU-SvetlanaNeural': 'ru-RU',
        'si-LK-SameeraNeural': 'si-LK',
        'si-LK-ThiliniNeural': 'si-LK',
        'sk-SK-LukasNeural': 'sk-SK',
        'sk-SK-ViktoriaNeural': 'sk-SK',
        'sl-SI-PetraNeural': 'sl-SI',
        'sl-SI-RokNeural': 'sl-SI',
        'so-SO-MuuseNeural': 'so-SO',
        'so-SO-UbaxNeural': 'so-SO',
        'sq-AL-AnilaNeural': 'sq-AL',
        'sq-AL-IlirNeural': 'sq-AL',
        'sr-RS-NicholasNeural': 'sr-RS',
        'sr-RS-SophieNeural': 'sr-RS',
        'su-ID-JajangNeural': 'su-ID',
        'su-ID-TutiNeural': 'su-ID',
        'sv-SE-MattiasNeural': 'sv-SE',
        'sv-SE-SofieNeural': 'sv-SE',
        'sw-KE-RafikiNeural': 'sw-KE',
        'sw-KE-ZuriNeural': 'sw-KE',
        'sw-TZ-DaudiNeural': 'sw-TZ',
        'sw-TZ-RehemaNeural': 'sw-TZ',
        'ta-IN-PallaviNeural': 'ta-IN',
        'ta-IN-ValluvarNeural': 'ta-IN',
        'ta-LK-KumarNeural': 'ta-LK',
        'ta-LK-SaranyaNeural': 'ta-LK',
        'ta-MY-KaniNeural': 'ta-MY',
        'ta-MY-SuryaNeural': 'ta-MY',
        'ta-SG-AnbuNeural': 'ta-SG',
        'ta-SG-VenbaNeural': 'ta-SG',
        'te-IN-MohanNeural': 'te-IN',
        'te-IN-ShrutiNeural': 'te-IN',
        'th-TH-NiwatNeural': 'th-TH',
        'th-TH-PremwadeeNeural': 'th-TH',
        'tr-TR-AhmetNeural': 'tr-TR',
        'tr-TR-EmelNeural': 'tr-TR',
        'uk-UA-OstapNeural': 'uk-UA',
        'uk-UA-PolinaNeural': 'uk-UA',
        'ur-IN-GulNeural': 'ur-IN',
        'ur-IN-SalmanNeural': 'ur-IN',
        'ur-PK-AsadNeural': 'ur-PK',
        'ur-PK-UzmaNeural': 'ur-PK',
        'uz-UZ-MadinaNeural': 'uz-UZ',
        'uz-UZ-SardorNeural': 'uz-UZ',
        'vi-VN-HoaiMyNeural': 'vi-VN',
        'vi-VN-NamMinhNeural': 'vi-VN',
        'zu-ZA-ThandoNeural': 'zu-ZA',
        'zu-ZA-ThembaNeural': 'zu-ZA',
    }

class NoPausesFound(Exception):
    def __init__(self, description = None) -> None:
        self.description = (f'No pauses were found in the text. Please '
            + f'consider using `edge_tts.Communicate` instead.')

        super().__init__(self.description)

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
            raise NoPausesFound

        parts = self.text.split("[pause:")
        for part in parts:
            if "]" in part:
                pause_time, content = part.split("]", 1)
                pause_time = self.parse_time(pause_time)

                yield pause_time, content.strip()

            else:
                content = part
                yield 0, content.strip()

    def parse_time(self, time_str: str) -> int:
        if time_str[-2:] == 'ms':
            unit = 'ms'
            time_value = int(time_str[:-2])
            return time_value
        else:
            raise ValueError(f"Invalid time unit! only ms are allowed")

    async def chunkify(self):
        for pause_time, content in self.parsed:
            if not pause_time and not content:
                pass

            elif not pause_time and content:
                audio_bytes = await self.generate_audio(content)
                self.file.write(audio_bytes)

            elif not content and pause_time:
                pause_bytes = self.generate_pause(pause_time)
                self.file.write(pause_bytes)

            else:
                pause_bytes = self.generate_pause(pause_time)
                audio_bytes = await self.generate_audio(content)
                self.file.write(pause_bytes)
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
        decoded_chunk = AudioSegment.from_mp3(temp_chunk)
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

    def validate_config(self):
        if self.config.voice_name not in get_supported_voices():
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
            f"[pause: {self.config.break_duration}ms]"
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
