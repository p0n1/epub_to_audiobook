import html
import io
import logging
import math
import os
from datetime import datetime, timedelta
from time import sleep
import requests

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.utils.utils import split_text, set_audio_tags, merge_audio_segments
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

MAX_RETRIES = 12  # Max_retries constant for network errors


class AzureTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        # TTS provider specific config
        if config.language == "zh-CN":
            config.voice_name = config.voice_name or "zh-CN-YunyeNeural"
        else:
            config.voice_name = config.voice_name or "en-US-GuyNeural"
        config.output_format = config.output_format or "audio-24khz-48kbitrate-mono-mp3"

        # 16$ per 1 million characters
        # or 0.016$ per 1000 characters
        self.price = 0.016
        # access token and expiry time
        self.access_token = None
        self.token_expiry_time = datetime.utcnow()
        super().__init__(config)

        subscription_key = os.environ.get("MS_TTS_KEY")
        region = os.environ.get("MS_TTS_REGION")

        if not subscription_key or not region:
            raise ValueError(
                "Please set MS_TTS_KEY and MS_TTS_REGION environment variables. Check https://github.com/p0n1/epub_to_audiobook#how-to-get-your-azure-cognitive-service-key."
            )

        self.TOKEN_URL = (
            f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
        )
        self.TOKEN_HEADERS = {"Ocp-Apim-Subscription-Key": subscription_key}
        self.TTS_URL = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def __str__(self) -> str:
        return (
                super().__str__()
                + f", voice_name={self.config.voice_name}, language={self.config.language}, break_duration={self.config.break_duration}, output_format={self.config.output_format}"
        )

    def is_access_token_expired(self) -> bool:
        return self.access_token is None or datetime.utcnow() >= self.token_expiry_time

    def auto_renew_access_token(self) -> str:
        if self.access_token is None or self.is_access_token_expired():
            logger.info(
                f"azure tts access_token doesn't exist or is expired, getting new one"
            )
            self.access_token = self.get_access_token()
            self.token_expiry_time = datetime.utcnow() + timedelta(minutes=9, seconds=1)
        return self.access_token

    def get_access_token(self) -> str:
        for retry in range(MAX_RETRIES):
            try:
                logger.info("Getting new access token")
                response = requests.post(self.TOKEN_URL, headers=self.TOKEN_HEADERS)
                response.raise_for_status()  # Will raise HTTPError for 4XX or 5XX status
                access_token = str(response.text)
                logger.info("Got new access token")
                return access_token
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Network error while getting access token (attempt {retry + 1}/{MAX_RETRIES}): {e}"
                )
                if retry < MAX_RETRIES - 1:
                    sleep(2 ** retry)
                else:
                    raise e
        raise Exception("Failed to get access token")

    def text_to_speech(
            self,
            text: str,
            output_file: str,
            audio_tags: AudioTags,
    ):
        # Adjust this value based on your testing
        max_chars = 1800 if self.config.language.startswith("zh") else 3000

        text_chunks = split_text(text, max_chars, self.config.language)

        audio_segments = []
        chunk_ids = []
        for i, chunk in enumerate(text_chunks, 1):
            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
            logger.info(
                f"Processing {chunk_id}, length={len(chunk)}"
            )
            logger.debug(
                f"Processing {chunk_id}, length={len(chunk)}, text=[{chunk}]"
            )
            escaped_text = html.escape(chunk)
            logger.debug(f"Escaped text: [{escaped_text}]")
            # replace MAGIC_BREAK_STRING with a break tag for section/paragraph break
            escaped_text = escaped_text.replace(
                self.get_break_string().strip(),
                f" <break time='{self.config.break_duration}ms' /> ",
            )  # strip in case leading bank is missing
            ssml = f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{self.config.language}'><voice name='{self.config.voice_name}'>{escaped_text}</voice></speak>"
            logger.debug(f"SSML: [{ssml}]")

            for retry in range(MAX_RETRIES):
                self.auto_renew_access_token()
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": self.config.output_format,
                    "User-Agent": "Python",
                }
                try:
                    logger.info(
                        "Sending request to Azure TTS, data length: " + str(len(ssml))
                    )
                    response = requests.post(
                        self.TTS_URL, headers=headers, data=ssml.encode("utf-8")
                    )
                    response.raise_for_status()  # Will raise HTTPError for 4XX or 5XX status
                    logger.info(
                        "Got response from Azure TTS, response length: "
                        + str(len(response.content))
                    )
                    audio_segments.append(io.BytesIO(response.content))
                    chunk_ids.append(chunk_id)
                    break
                except requests.exceptions.RequestException as e:
                    logger.warning(
                        f"Error while converting text to speech (attempt {retry + 1}): {e}"
                    )
                    if retry < MAX_RETRIES - 1:
                        logger.warning(f"Sleeping for {2 ** retry} seconds before retrying, you can also stop the program manually and check error logs.")
                        sleep(2 ** retry)
                    else:
                        raise e

        # Use utility function to merge audio segments
        merge_audio_segments(audio_segments, output_file, self.get_output_file_extension(), chunk_ids, self.config.use_pydub_merge)

        set_audio_tags(output_file, audio_tags)

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

    def validate_config(self):
        if self.config.language not in get_azure_supported_languages():
            raise ValueError(
                f"AzureTTS: Unsupported language: {self.config.language}"
            )
        if self.config.voice_name not in get_azure_supported_voices():
            raise ValueError(
                f"AzureTTS: Unsupported voice name: {self.config.voice_name}"
            )
        if self.config.output_format not in get_azure_supported_output_formats():
            raise ValueError(
                f"AzureTTS: Unsupported output format: {self.config.output_format}"
            )

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price


def get_azure_supported_output_formats():
    return [
        "amr-wb-16000hz", "audio-16khz-16bit-32kbps-mono-opus", "audio-16khz-32kbitrate-mono-mp3",
        "audio-16khz-64kbitrate-mono-mp3", "audio-16khz-128kbitrate-mono-mp3", "audio-24khz-16bit-24kbps-mono-opus",
        "audio-24khz-16bit-48kbps-mono-opus", "audio-24khz-48kbitrate-mono-mp3", "audio-24khz-96kbitrate-mono-mp3",
        "audio-24khz-160kbitrate-mono-mp3", "audio-48khz-96kbitrate-mono-mp3", "audio-48khz-192kbitrate-mono-mp3",
        "g722-16khz-64kbps", "ogg-16khz-16bit-mono-opus", "ogg-24khz-16bit-mono-opus", "ogg-48khz-16bit-mono-opus",
        "raw-8khz-8bit-mono-alaw", "raw-8khz-8bit-mono-mulaw", "raw-8khz-16bit-mono-pcm", "raw-16khz-16bit-mono-pcm",
        "raw-16khz-16bit-mono-truesilk", "raw-22050hz-16bit-mono-pcm", "raw-24khz-16bit-mono-pcm",
        "raw-24khz-16bit-mono-truesilk", "raw-44100hz-16bit-mono-pcm", "raw-48khz-16bit-mono-pcm",
        "webm-16khz-16bit-mono-opus", "webm-24khz-16bit-24kbps-mono-opus", "webm-24khz-16bit-mono-opus"
    ]

def get_azure_supported_languages():
    return [ "af-ZA", "am-ET", "ar-AE", "ar-BH", "ar-DZ", "ar-EG", "ar-IQ", "ar-JO", "ar-KW", "ar-LB", "ar-LY", "ar-MA",
             "ar-OM", "ar-QA", "ar-SA", "ar-SY", "ar-TN", "ar-YE", "as-IN", "az-AZ", "bg-BG", "bn-BD", "bn-IN", "bs-BA",
             "ca-ES", "cs-CZ", "cy-GB", "da-DK", "de-AT", "de-CH", "de-DE", "el-GR", "en-AU", "en-CA", "en-GB", "en-HK",
             "en-IE", "en-IN", "en-KE", "en-NG", "en-NZ", "en-PH", "en-SG", "en-TZ", "en-US", "en-ZA", "es-AR", "es-BO",
             "es-CL", "es-CO", "es-CR", "es-CU", "es-DO", "es-EC", "es-ES", "es-GQ", "es-GT", "es-HN", "es-MX", "es-NI",
             "es-PA", "es-PE", "es-PR", "es-PY", "es-SV", "es-US", "es-UY", "es-VE", "et-EE", "eu-ES", "fa-IR", "fi-FI",
             "fil-PH", "fr-BE", "fr-CA", "fr-CH", "fr-FR", "ga-IE", "gl-ES", "gu-IN", "he-IL", "hi-IN", "hr-HR", "hu-HU",
             "hy-AM", "id-ID", "is-IS", "it-IT", "iu-CANS-CA", "iu-LATN-CA", "ja-JP", "jv-ID", "ka-GE", "kk-KZ", "km-KH",
             "kn-IN", "ko-KR", "lo-LA", "lt-LT", "lv-LV", "mk-MK", "ml-IN", "mn-MN", "mr-IN", "ms-MY", "mt-MT", "my-MM",
             "nb-NO", "ne-NP", "nl-BE", "nl-NL", "or-IN", "pa-IN", "pl-PL", "ps-AF", "pt-BR", "pt-PT", "ro-RO", "ru-RU",
             "si-LK", "sk-SK", "sl-SI", "so-SO", "sq-AL", "sr-LATN-RS", "sr-RS", "su-ID", "sv-SE", "sw-KE", "sw-TZ",
             "ta-IN", "ta-LK", "ta-MY", "ta-SG", "te-IN", "th-TH", "tr-TR", "uk-UA", "ur-IN", "ur-PK", "uz-UZ", "vi-VN",
             "wuu-CN", "yue-CN", "zh-CN", "zh-CN-GUANGXI", "zh-CN-henan", "zh-CN-liaoning", "zh-CN-shaanxi", "zh-CN-shandong",
             "zh-CN-sichuan", "zh-HK", "zh-TW", "zu-ZA"
    ]

def get_azure_supported_voices():
    return [
        "af-ZA-AdriNeural", "af-ZA-WillemNeural", "am-ET-AmehaNeural", "am-ET-MekdesNeural", "ar-AE-FatimaNeural",
        "ar-AE-HamdanNeural", "ar-BH-AliNeural", "ar-BH-LailaNeural", "ar-DZ-AminaNeural", "ar-DZ-IsmaelNeural",
        "ar-EG-SalmaNeural", "ar-EG-ShakirNeural", "ar-IQ-BasselNeural", "ar-IQ-RanaNeural", "ar-JO-SanaNeural",
        "ar-JO-TaimNeural", "ar-KW-FahedNeural", "ar-KW-NouraNeural", "ar-LB-LaylaNeural","ar-LB-RamiNeural",
        "ar-LY-ImanNeural", "ar-LY-OmarNeural", "ar-MA-JamalNeural", "ar-MA-MounaNeural", "ar-OM-AbdullahNeural",
        "ar-OM-AyshaNeural", "ar-QA-AmalNeural", "ar-QA-MoazNeural", "ar-SA-HamedNeural", "ar-SA-ZariyahNeural",
        "ar-SY-AmanyNeural", "ar-SY-LaithNeural", "ar-TN-HediNeural", "ar-TN-ReemNeural", "ar-YE-MaryamNeural",
        "ar-YE-SalehNeural", "as-IN-PriyomNeural", "as-IN-YashicaNeural", "az-AZ-BabekNeural", "az-AZ-BanuNeural",
        "bg-BG-BorislavNeural", "bg-BG-KalinaNeural", "bn-BD-NabanitaNeural", "bn-BD-PradeepNeural", "bn-IN-BashkarNeural",
        "bn-IN-TanishaaNeural", "bs-BA-GoranNeural", "bs-BA-VesnaNeural", "ca-ES-AlbaNeural", "ca-ES-EnricNeural",
        "ca-ES-JoanaNeural", "cs-CZ-AntoninNeural", "cs-CZ-VlastaNeural", "cy-GB-AledNeural", "cy-GB-NiaNeural",
        "da-DK-ChristelNeural", "da-DK-JeppeNeural", "de-AT-IngridNeural", "de-AT-JonasNeural", "de-CH-JanNeural",
        "de-CH-LeniNeural", "de-DE-AmalaNeural", "de-DE-BerndNeural", "de-DE-ChristophNeural", "de-DE-ConradNeural",
        "de-DE-ElkeNeural", "de-DE-Florian:DragonHDLatestNeural", "de-DE-FlorianMultilingualNeural", "de-DE-GiselaNeural",
        "de-DE-KasperNeural", "de-DE-KatjaNeural", "de-DE-KillianNeural", "de-DE-KlarissaNeural", "de-DE-KlausNeural",
        "de-DE-LouisaNeural", "de-DE-MajaNeural", "de-DE-RalfNeural", "de-DE-Seraphina:DragonHDLatestNeural",
        "de-DE-SeraphinaMultilingualNeural", "de-DE-TanjaNeural", "el-GR-AthinaNeural", "el-GR-NestorasNeural",
        "en-AU-AnnetteNeural", "en-AU-CarlyNeural", "en-AU-DarrenNeural", "en-AU-DuncanNeural", "en-AU-ElsieNeural",
        "en-AU-FreyaNeural", "en-AU-JoanneNeural", "en-AU-KenNeural", "en-AU-KimNeural", "en-AU-NatashaNeural",
        "en-AU-NeilNeural", "en-AU-TimNeural", "en-AU-TinaNeural", "en-AU-WilliamNeural", "en-CA-ClaraNeural",
        "en-CA-LiamNeural", "en-GB-AbbiNeural", "en-GB-AdaMultilingualNeural", "en-GB-AlfieNeural", "en-GB-BellaNeural",
        "en-GB-ElliotNeural", "en-GB-EthanNeural", "en-GB-HollieNeural", "en-GB-LibbyNeural", "en-GB-MaisieNeural",
        "en-GB-NoahNeural", "en-GB-OliverNeural", "en-GB-OliviaNeural", "en-GB-OllieMultilingualNeural",
        "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-GB-ThomasNeural", "en-HK-SamNeural", "en-HK-YanNeural",
        "en-IE-ConnorNeural", "en-IE-EmilyNeural", "en-IN-AaravNeural", "en-IN-AartiNeural", "en-IN-AashiNeural",
        "en-IN-AnanyaNeural", "en-IN-ArjunNeural", "en-IN-KavyaNeural", "en-IN-KunalNeural", "en-IN-NeerjaNeural",
        "en-IN-PrabhatNeural", "en-IN-RehaanNeural", "en-KE-AsiliaNeural", "en-KE-ChilembaNeural", "en-NG-AbeoNeural",
        "en-NG-EzinneNeural", "en-NZ-MitchellNeural", "en-NZ-MollyNeural", "en-PH-JamesNeural", "en-PH-RosaNeural",
        "en-SG-LunaNeural", "en-SG-WayneNeural", "en-TZ-ElimuNeural", "en-TZ-ImaniNeural", "en-US-AIGenerate1Neural",
        "en-US-AIGenerate2Neural", "en-US-Adam:DragonHDLatestNeural", "en-US-AdamMultilingualNeural",
        "en-US-Alloy:DragonHDLatestNeural", "en-US-AlloyMultilingualNeural", "en-US-AlloyMultilingualNeuralHD",
        "en-US-AlloyTurboMultilingualNeural", "en-US-AmandaMultilingualNeural", "en-US-AmberNeural", "en-US-AnaNeural",
        "en-US-Andrew2:DragonHDLatestNeural", "en-US-Andrew:DragonHDLatestNeural", "en-US-AndrewMultilingualNeural",
        "en-US-AndrewNeural", "en-US-Aria:DragonHDLatestNeural", "en-US-AriaNeural", "en-US-AshleyNeural",
        "en-US-Ava:DragonHDLatestNeural", "en-US-AvaMultilingualNeural", "en-US-AvaNeural", "en-US-BlueNeural",
        "en-US-BrandonMultilingualNeural", "en-US-BrandonNeural", "en-US-Brian:DragonHDLatestNeural",
        "en-US-BrianMultilingualNeural", "en-US-BrianNeural", "en-US-ChristopherMultilingualNeural",
        "en-US-ChristopherNeural", "en-US-CoraMultilingualNeural", "en-US-CoraNeural", "en-US-Davis:DragonHDLatestNeural",
        "en-US-DavisMultilingualNeural", "en-US-DavisNeural", "en-US-DerekMultilingualNeural",
        "en-US-DustinMultilingualNeural", "en-US-EchoMultilingualNeural", "en-US-EchoMultilingualNeuralHD",
        "en-US-EchoTurboMultilingualNeural", "en-US-ElizabethNeural", "en-US-Emma2:DragonHDLatestNeural",
        "en-US-Emma:DragonHDLatestNeural", "en-US-EmmaMultilingualNeural", "en-US-EmmaNeural", "en-US-EricNeural",
        "en-US-EvelynMultilingualNeural", "en-US-FableMultilingualNeural", "en-US-FableMultilingualNeuralHD",
        "en-US-FableTurboMultilingualNeural", "en-US-GuyNeural", "en-US-JacobNeural", "en-US-JaneNeural",
        "en-US-JasonNeural", "en-US-Jenny:DragonHDLatestNeural", "en-US-JennyMultilingualNeural", "en-US-JennyNeural",
        "en-US-KaiNeural", "en-US-LewisMultilingualNeural", "en-US-LolaMultilingualNeural", "en-US-LunaNeural",
        "en-US-MichelleNeural", "en-US-MonicaNeural", "en-US-NancyMultilingualNeural", "en-US-NancyNeural",
        "en-US-Nova:DragonHDLatestNeural", "en-US-NovaMultilingualNeural", "en-US-NovaMultilingualNeuralHD",
        "en-US-NovaTurboMultilingualNeural", "en-US-OnyxMultilingualNeural", "en-US-OnyxMultilingualNeuralHD",
        "en-US-OnyxTurboMultilingualNeural", "en-US-Phoebe:DragonHDLatestNeural",
        "en-US-PhoebeMultilingualNeural", "en-US-RogerNeural", "en-US-RyanMultilingualNeural",
        "en-US-SamuelMultilingualNeural", "en-US-SaraNeural", "en-US-Serena:DragonHDLatestNeural",
        "en-US-SerenaMultilingualNeural", "en-US-ShimmerMultilingualNeural", "en-US-ShimmerMultilingualNeuralHD",
        "en-US-ShimmerTurboMultilingualNeural", "en-US-Steffan:DragonHDLatestNeural", "en-US-SteffanMultilingualNeural",
        "en-US-SteffanNeural", "en-US-TonyNeural", "en-ZA-LeahNeural", "en-ZA-LukeNeural", "es-AR-ElenaNeural",
        "es-AR-TomasNeural", "es-BO-MarceloNeural", "es-BO-SofiaNeural", "es-CL-CatalinaNeural", "es-CL-LorenzoNeural",
        "es-CO-GonzaloNeural", "es-CO-SalomeNeural", "es-CR-JuanNeural", "es-CR-MariaNeural", "es-CU-BelkysNeural",
        "es-CU-ManuelNeural", "es-DO-EmilioNeural", "es-DO-RamonaNeural", "es-EC-AndreaNeural", "es-EC-LuisNeural",
        "es-ES-AbrilNeural", "es-ES-AlvaroNeural", "es-ES-ArabellaMultilingualNeural", "es-ES-ArnauNeural",
        "es-ES-DarioNeural", "es-ES-EliasNeural", "es-ES-ElviraNeural", "es-ES-EstrellaNeural", "es-ES-IreneNeural",
        "es-ES-IsidoraMultilingualNeural", "es-ES-LaiaNeural", "es-ES-LiaNeural", "es-ES-NilNeural", "es-ES-SaulNeural",
        "es-ES-TeoNeural", "es-ES-TrianaNeural", "es-ES-Tristan:DragonHDLatestNeural", "es-ES-TristanMultilingualNeural",
        "es-ES-VeraNeural", "es-ES-Ximena:DragonHDLatestNeural", "es-ES-XimenaMultilingualNeural", "es-ES-XimenaNeural",
        "es-GQ-JavierNeural", "es-GQ-TeresaNeural", "es-GT-AndresNeural", "es-GT-MartaNeural", "es-HN-CarlosNeural",
        "es-HN-KarlaNeural", "es-MX-BeatrizNeural", "es-MX-CandelaNeural", "es-MX-CarlotaNeural", "es-MX-CecilioNeural",
        "es-MX-DaliaNeural", "es-MX-GerardoNeural", "es-MX-JorgeNeural", "es-MX-LarissaNeural", "es-MX-LibertoNeural",
        "es-MX-LucianoNeural", "es-MX-MarinaNeural", "es-MX-NuriaNeural", "es-MX-PelayoNeural", "es-MX-RenataNeural",
        "es-MX-YagoNeural", "es-NI-FedericoNeural", "es-NI-YolandaNeural", "es-PA-MargaritaNeural", "es-PA-RobertoNeural",
        "es-PE-AlexNeural", "es-PE-CamilaNeural", "es-PR-KarinaNeural", "es-PR-VictorNeural", "es-PY-MarioNeural",
        "es-PY-TaniaNeural", "es-SV-LorenaNeural", "es-SV-RodrigoNeural", "es-US-AlonsoNeural", "es-US-PalomaNeural",
        "es-UY-MateoNeural", "es-UY-ValentinaNeural", "es-VE-PaolaNeural", "es-VE-SebastianNeural", "et-EE-AnuNeural",
        "et-EE-KertNeural", "eu-ES-AinhoaNeural", "eu-ES-AnderNeural", "fa-IR-DilaraNeural", "fa-IR-FaridNeural",
        "fi-FI-HarriNeural", "fi-FI-NooraNeural", "fi-FI-SelmaNeural", "fil-PH-AngeloNeural", "fil-PH-BlessicaNeural",
        "fr-BE-CharlineNeural", "fr-BE-GerardNeural", "fr-CA-AntoineNeural", "fr-CA-JeanNeural", "fr-CA-SylvieNeural",
        "fr-CA-ThierryNeural", "fr-CH-ArianeNeural", "fr-CH-FabriceNeural", "fr-FR-AlainNeural", "fr-FR-BrigitteNeural",
        "fr-FR-CelesteNeural", "fr-FR-ClaudeNeural", "fr-FR-CoralieNeural", "fr-FR-DeniseNeural", "fr-FR-EloiseNeural",
        "fr-FR-HenriNeural", "fr-FR-JacquelineNeural", "fr-FR-JeromeNeural", "fr-FR-JosephineNeural",
        "fr-FR-LucienMultilingualNeural", "fr-FR-MauriceNeural", "fr-FR-Remy:DragonHDLatestNeural",
        "fr-FR-RemyMultilingualNeural", "fr-FR-Vivienne:DragonHDLatestNeural", "fr-FR-VivienneMultilingualNeural",
        "fr-FR-YvesNeural", "fr-FR-YvetteNeural", "ga-IE-ColmNeural", "ga-IE-OrlaNeural", "gl-ES-RoiNeural",
        "gl-ES-SabelaNeural", "gu-IN-DhwaniNeural", "gu-IN-NiranjanNeural", "he-IL-AvriNeural", "he-IL-HilaNeural",
        "hi-IN-AaravNeural", "hi-IN-AartiNeural", "hi-IN-AnanyaNeural", "hi-IN-ArjunNeural", "hi-IN-KavyaNeural",
        "hi-IN-KunalNeural", "hi-IN-MadhurNeural", "hi-IN-RehaanNeural", "hi-IN-SwaraNeural", "hr-HR-GabrijelaNeural",
        "hr-HR-SreckoNeural", "hu-HU-NoemiNeural", "hu-HU-TamasNeural", "hy-AM-AnahitNeural", "hy-AM-HaykNeural",
        "id-ID-ArdiNeural", "id-ID-GadisNeural", "is-IS-GudrunNeural", "is-IS-GunnarNeural",
        "it-IT-AlessioMultilingualNeural", "it-IT-BenignoNeural", "it-IT-CalimeroNeural", "it-IT-CataldoNeural",
        "it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-FabiolaNeural", "it-IT-FiammaNeural", "it-IT-GianniNeural",
        "it-IT-GiuseppeMultilingualNeural", "it-IT-GiuseppeNeural", "it-IT-ImeldaNeural", "it-IT-IrmaNeural",
        "it-IT-IsabellaMultilingualNeural", "it-IT-IsabellaNeural", "it-IT-LisandroNeural",
        "it-IT-MarcelloMultilingualNeural", "it-IT-PalmiraNeural", "it-IT-PierinaNeural",
        "it-IT-RinaldoNeural", "iu-Cans-CA-SiqiniqNeural", "iu-Cans-CA-TaqqiqNeural", "iu-Latn-CA-SiqiniqNeural",
        "iu-Latn-CA-TaqqiqNeural", "ja-JP-AoiNeural", "ja-JP-DaichiNeural", "ja-JP-KeitaNeural",
        "ja-JP-Masaru:DragonHDLatestNeural", "ja-JP-MasaruMultilingualNeural", "ja-JP-MayuNeural",
        "ja-JP-Nanami:DragonHDLatestNeural", "ja-JP-NanamiNeural", "ja-JP-NaokiNeural", "ja-JP-ShioriNeural",
        "jv-ID-DimasNeural", "jv-ID-SitiNeural", "ka-GE-EkaNeural", "ka-GE-GiorgiNeural", "kk-KZ-AigulNeural",
        "kk-KZ-DauletNeural", "km-KH-PisethNeural", "km-KH-SreymomNeural", "kn-IN-GaganNeural", "kn-IN-SapnaNeural",
        "ko-KR-BongJinNeural", "ko-KR-GookMinNeural", "ko-KR-HyunsuMultilingualNeural", "ko-KR-HyunsuNeural",
        "ko-KR-InJoonNeural", "ko-KR-JiMinNeural", "ko-KR-SeoHyeonNeural", "ko-KR-SoonBokNeural", "ko-KR-SunHiNeural",
        "ko-KR-YuJinNeural", "lo-LA-ChanthavongNeural", "lo-LA-KeomanyNeural", "lt-LT-LeonasNeural", "lt-LT-OnaNeural",
        "lv-LV-EveritaNeural", "lv-LV-NilsNeural", "mk-MK-AleksandarNeural", "mk-MK-MarijaNeural", "ml-IN-MidhunNeural",
        "ml-IN-SobhanaNeural", "mn-MN-BataaNeural", "mn-MN-YesuiNeural", "mr-IN-AarohiNeural", "mr-IN-ManoharNeural",
        "ms-MY-OsmanNeural", "ms-MY-YasminNeural", "mt-MT-GraceNeural", "mt-MT-JosephNeural", "my-MM-NilarNeural",
        "my-MM-ThihaNeural", "nb-NO-FinnNeural", "nb-NO-IselinNeural", "nb-NO-PernilleNeural", "ne-NP-HemkalaNeural",
        "ne-NP-SagarNeural", "nl-BE-ArnaudNeural", "nl-BE-DenaNeural", "nl-NL-ColetteNeural", "nl-NL-FennaNeural",
        "nl-NL-MaartenNeural", "or-IN-SubhasiniNeural", "or-IN-SukantNeural", "pa-IN-OjasNeural", "pa-IN-VaaniNeural",
        "pl-PL-AgnieszkaNeural", "pl-PL-MarekNeural", "pl-PL-ZofiaNeural", "ps-AF-GulNawazNeural", "ps-AF-LatifaNeural",
        "pt-BR-AntonioNeural", "pt-BR-BrendaNeural", "pt-BR-DonatoNeural", "pt-BR-ElzaNeural", "pt-BR-FabioNeural",
        "pt-BR-FranciscaNeural", "pt-BR-GiovannaNeural", "pt-BR-HumbertoNeural", "pt-BR-JulioNeural", "pt-BR-LeilaNeural",
        "pt-BR-LeticiaNeural", "pt-BR-MacerioMultilingualNeural", "pt-BR-ManuelaNeural", "pt-BR-NicolauNeural",
        "pt-BR-ThalitaMultilingualNeural", "pt-BR-ThalitaNeural", "pt-BR-ValerioNeural", "pt-BR-YaraNeural",
        "pt-PT-DuarteNeural", "pt-PT-FernandaNeural", "pt-PT-RaquelNeural", "ro-RO-AlinaNeural", "ro-RO-EmilNeural",
        "ru-RU-DariyaNeural", "ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural", "si-LK-SameeraNeural", "si-LK-ThiliniNeural",
        "sk-SK-LukasNeural", "sk-SK-ViktoriaNeural", "sl-SI-PetraNeural", "sl-SI-RokNeural", "so-SO-MuuseNeural",
        "so-SO-UbaxNeural", "sq-AL-AnilaNeural", "sq-AL-IlirNeural", "sr-Latn-RS-NicholasNeural", "sr-Latn-RS-SophieNeural",
        "sr-RS-NicholasNeural", "sr-RS-SophieNeural", "su-ID-JajangNeural", "su-ID-TutiNeural", "sv-SE-HilleviNeural",
        "sv-SE-MattiasNeural", "sv-SE-SofieNeural", "sw-KE-RafikiNeural", "sw-KE-ZuriNeural", "sw-TZ-DaudiNeural",
        "sw-TZ-RehemaNeural", "ta-IN-PallaviNeural", "ta-IN-ValluvarNeural", "ta-LK-KumarNeural", "ta-LK-SaranyaNeural",
        "ta-MY-KaniNeural", "ta-MY-SuryaNeural", "ta-SG-AnbuNeural", "ta-SG-VenbaNeural", "te-IN-MohanNeural",
        "te-IN-ShrutiNeural", "th-TH-AcharaNeural", "th-TH-NiwatNeural", "th-TH-PremwadeeNeural", "tr-TR-AhmetNeural",
        "tr-TR-EmelNeural", "uk-UA-OstapNeural", "uk-UA-PolinaNeural", "ur-IN-GulNeural", "ur-IN-SalmanNeural",
        "ur-PK-AsadNeural", "ur-PK-UzmaNeural", "uz-UZ-MadinaNeural", "uz-UZ-SardorNeural", "vi-VN-HoaiMyNeural",
        "vi-VN-NamMinhNeural", "wuu-CN-XiaotongNeural", "wuu-CN-YunzheNeural", "yue-CN-XiaoMinNeural",
        "yue-CN-YunSongNeural", "zh-CN-Xiaochen:DragonHDLatestNeural", "zh-CN-Xiaochen:DragonHDFlashLatestNeural", "zh-CN-XiaochenMultilingualNeural",
        "zh-CN-XiaochenNeural", "zh-CN-XiaohanNeural", "zh-CN-XiaomengNeural", "zh-CN-XiaomoNeural",
        "zh-CN-XiaoqiuNeural", "zh-CN-XiaorouNeural", "zh-CN-XiaoruiNeural", "zh-CN-XiaoshuangNeural",
        "zh-CN-XiaoxiaoDialectsNeural", "zh-CN-XiaoxiaoMultilingualNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural", "zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural",
        "zh-CN-XiaoyanNeural", "zh-CN-XiaoyiNeural", "zh-CN-XiaoyouNeural", "zh-CN-XiaoyuMultilingualNeural",
        "zh-CN-XiaozhenNeural", "zh-CN-Yunfan:DragonHDLatestNeural", "zh-CN-YunfanMultilingualNeural",
        "zh-CN-YunfengNeural", "zh-CN-YunhaoNeural", "zh-CN-YunjianNeural", "zh-CN-YunjieNeural", "zh-CN-YunxiNeural",
        "zh-CN-YunxiaNeural", "zh-CN-YunxiaoMultilingualNeural", "zh-CN-Yunxiao:DragonHDFlashLatestNeural", "zh-CN-YunyangNeural", "zh-CN-YunyeNeural",
        "zh-CN-YunyiMultilingualNeural", "zh-CN-Yunyi:DragonHDFlashLatestNeural", "zh-CN-YunzeNeural", "zh-CN-guangxi-YunqiNeural", "zh-CN-henan-YundengNeural",
        "zh-CN-liaoning-XiaobeiNeural", "zh-CN-liaoning-YunbiaoNeural", "zh-CN-shaanxi-XiaoniNeural",
        "zh-CN-shandong-YunxiangNeural", "zh-CN-sichuan-YunxiNeural", "zh-HK-HiuGaaiNeural", "zh-HK-HiuMaanNeural",
        "zh-HK-WanLungNeural", "zh-TW-HsiaoChenNeural", "zh-TW-HsiaoYuNeural", "zh-TW-YunJheNeural",
        "zu-ZA-ThandoNeural", "zu-ZA-ThembaNeural"
    ]
