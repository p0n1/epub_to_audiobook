import asyncio
import logging
import math
import io
from time import sleep

import edge_tts
from edge_tts import list_voices
from pydub import AudioSegment

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.utils.utils import (
    set_audio_tags,
    split_text,
)
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


# Credit: https://gist.github.com/moha-abdi/8ddbcb206c38f592c65ada1e5479f2bf
# @phuchoang2603 contributed pause support in https://github.com/p0n1/epub_to_audiobook/pull/45
class CommWithPauses:
    # This class uses edge_tts to generate text
    # but with pauses for example:- text: 'Hello
    # this is simple text. [pause: 1000] Paused 1000ms'
    def __init__(
        self,
        text: str,
        voice_name: str,
        break_string: str,
        break_duration: int = 1250,
        output_format_ext: str = "mp3",
        **kwargs,
    ) -> None:
        self.full_text = text
        self.voice_name = voice_name
        self.break_string = break_string
        self.break_duration = int(break_duration)
        self.output_format_ext = output_format_ext
        self.kwargs = kwargs

        self.parsed = self.parse_text()
        self.file = io.BytesIO()

    def parse_text(self):
        logger.debug(
            "Parsing the text, looking for break/pauses in text: "
            f"<{self.full_text}>"
        )
        if self.break_string not in self.full_text:
            logger.debug("No break/pauses found in the text")
            return [self.full_text]

        parts = self.full_text.split(self.break_string)

        # Filter out empty parts and parts that don't contain meaningful text which may cause NoAudioReceived error in Edge TTS, then strip each meaningful part
        meaningful_parts = []
        for part in parts:
            if self._is_meaningful_text(part):
                meaningful_parts.append(part.strip())
        
        logger.debug(f"split into <{len(meaningful_parts)}> meaningful parts: {meaningful_parts}")
        return meaningful_parts

    def _is_meaningful_text(self, text: str) -> bool:
        """
        Check if a text chunk contains meaningful content for Edge TTS generation.

        Args:
            text: The text chunk to check

        Returns:
            True if the text is meaningful for Edge TTS, False otherwise
        """

        stripped_text = text.strip()
        if not stripped_text:
            return False

        # Check if the text contains any alphanumeric characters
        # This filters out problematic pure punctuations without alphanumeric content which may cause NoAudioReceived error in Edge TTS
        # but keeps single letters like 'A', 'B', 'C', or 'A,' 'B,' 'C,'
        if not any(
            char.isalnum() for char in stripped_text
        ):  # means every character in the text is not alphanumeric
            if len(stripped_text) >= 50:
                logger.warning(
                    f"Found a long text chunk without alphanumeric content: <{stripped_text}>, this might be a bug for specific text, please open an issue on https://github.com/p0n1/epub_to_audiobook/issues"
                )
            return False
        return True

    async def chunkify(self):
        logger.debug("Chunkifying the text")
        for content in self.parsed:
            logger.debug(f"content from parsed: <{content}>")
            audio_bytes = await self.generate_audio(content)
            self.file.write(audio_bytes)
            if content != self.parsed[-1] and self.break_duration > 0:
                # only same break duration for all breaks is supported now
                pause_bytes = self.generate_pause(self.break_duration)
                self.file.write(pause_bytes)
        logger.debug("Chunkifying done")

    def generate_pause(self, time: int) -> bytes:
        logger.debug("Generating pause")
        # pause time should be provided in ms
        silent: AudioSegment = AudioSegment.silent(time, 24000)
        return silent.raw_data  # type: ignore

    async def generate_audio(self, text: str) -> bytes:
        logger.debug(f"Generating audio for: <{text}>")
        # this genertes the real TTS using edge_tts for this part.
        temp_chunk = io.BytesIO()
        communicate = edge_tts.Communicate(text, self.voice_name, **self.kwargs)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                temp_chunk.write(chunk["data"])

        temp_chunk.seek(0)
        # handle the case where the chunk is empty
        try:
            logger.debug("Decoding the chunk")
            decoded_chunk = AudioSegment.from_mp3(temp_chunk)
        except Exception as e:
            logger.warning(
                f"Failed to decode the chunk, reason: {e}, returning a silent chunk."
            )
            decoded_chunk = AudioSegment.silent(0, 24000)
        logger.debug("Returning the decoded chunk")
        return decoded_chunk.raw_data  # type: ignore

    async def get_audio_stream(self) -> io.BytesIO:
        await self.chunkify() # main logic to chunkify the text and generate audio segments

        self.file.seek(0)
        audio: AudioSegment = AudioSegment.from_raw(
            self.file, sample_width=2, frame_rate=24000, channels=1
        )

        output_bytes = io.BytesIO()
        audio.export(output_bytes, format=self.output_format_ext)
        output_bytes.seek(0)
        return output_bytes

    async def get_audio_segment(self) -> AudioSegment:
        """
        Generate and return an AudioSegment (PCM) so callers can merge in-memory
        and perform a single encode at the end to avoid quality loss.
        """
        await self.chunkify()
        self.file.seek(0)
        return AudioSegment.from_raw(self.file, sample_width=2, frame_rate=24000, channels=1)


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        # TTS provider specific config
        if config.language == "zh-CN":
            config.voice_name = config.voice_name or "zh-CN-YunxiNeural"
        else:
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
        # no need to send request to edge-tts to get supported voices, just use the hardcoded list.
        # supported_voices = asyncio.run(get_supported_voices())
        supported_voices = get_edge_tts_supported_voices()
        # logger.debug(f"Supported voices: {supported_voices}")
        if self.config.voice_name not in supported_voices:
            raise ValueError(
                f"EdgeTTS: Unsupported voice name: {self.config.voice_name}"
            )

    def text_to_speech(
        self,
        text: str,
        output_file: str,
        audio_tags: AudioTags,
    ):
        # edge-tts package has a much higher limit than below, but I feels better to use a smaller limit to reduce the risk of error.
        # just use the same value as azure-tts-provider now, change it if needed.
        max_chars = 1800 if self.config.language.startswith("zh") else 3000

        text_chunks = split_text(text, max_chars, self.config.language)

        # Build in-memory PCM segments for each chunk, then export once to MP3 at target bitrate
        segments: list[AudioSegment] = []
        for i, chunk in enumerate(text_chunks, 1):
            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
            logger.info(f"Processing {chunk_id}, length={len(chunk)}")
            logger.debug(f"Processing {chunk_id}, length={len(chunk)}, text=[{chunk}]")

            for retry in range(MAX_RETRIES):
                try:
                    communicate = CommWithPauses(
                        text=chunk,
                        voice_name=self.config.voice_name,
                        break_string=self.get_break_string().strip(),
                        break_duration=int(self.config.break_duration),
                        output_format_ext=self.get_output_file_extension(),
                        rate=self.config.voice_rate,
                        volume=self.config.voice_volume,
                        pitch=self.config.voice_pitch,
                        proxy=self.config.proxy,
                    )
                    segment = asyncio.run(communicate.get_audio_segment())
                    segments.append(segment)
                    break  # success
                except Exception as e:
                    logger.warning(
                        f"Error while converting text to speech for {chunk_id} (attempt {retry + 1}/{MAX_RETRIES}): {e}"
                    )
                    if retry < MAX_RETRIES - 1:
                        sleep_time = 2**retry
                        logger.warning(
                            f"Sleeping for {sleep_time} seconds before retrying, you can also stop the program manually and check error logs."
                        )
                        sleep(sleep_time)
                    else:
                        raise e

        # Merge all PCM segments
        combined = AudioSegment.empty()
        for seg in segments:
            combined += seg

        # Export once to MP3 at the desired bitrate to avoid downsampling artifacts
        target_bitrate = self._get_target_bitrate()
        combined.export(output_file, format=self.get_output_file_extension(), bitrate=target_bitrate)

        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price

    def get_break_string(self):
        return " @BRK#"

    def get_output_file_extension(self):
        if self.config.output_format.endswith("mp3"):
            return "mp3"
        else:
            # Only mp3 supported in edge-tts https://github.com/rany2/edge-tts/issues/179
            raise NotImplementedError(
                f"Unknown file extension for output format: {self.config.output_format}. Only mp3 supported in edge-tts. See https://github.com/rany2/edge-tts/issues/179."
            )

    def _get_target_bitrate(self) -> str:
        """
        Edge TTS only supports MP3; use 48 kbps to match edge-tts stream quality.
        """
        return "48k"


def get_edge_tts_supported_output_formats():
    return ["mp3"]


def get_edge_tts_supported_language():
    return [
        "af-ZA", "am-ET", "ar-AE", "ar-BH", "ar-DZ", "ar-EG", "ar-IQ", "ar-JO", "ar-KW", "ar-LB", "ar-LY", "ar-MA",
        "ar-OM", "ar-QA", "ar-SA", "ar-SY", "ar-TN", "ar-YE", "az-AZ", "bg-BG", "bn-BD", "bn-IN", "bs-BA", "ca-ES",
        "cs-CZ", "cy-GB", "da-DK", "de-AT", "de-CH", "de-DE", "el-GR", "en-AU", "en-CA", "en-GB", "en-HK", "en-IE",
        "en-IN", "en-KE", "en-NG", "en-NZ", "en-PH", "en-SG", "en-TZ", "en-US", "en-ZA", "es-AR", "es-BO", "es-CL",
        "es-CO", "es-CR", "es-CU", "es-DO", "es-EC", "es-ES", "es-GQ", "es-GT", "es-HN", "es-MX", "es-NI", "es-PA",
        "es-PE", "es-PR", "es-PY", "es-SV", "es-US", "es-UY", "es-VE", "et-EE", "fa-IR", "fi-FI", "fil-P", "fr-BE",
        "fr-CA", "fr-CH", "fr-FR", "ga-IE", "gl-ES", "gu-IN", "he-IL", "hi-IN", "hr-HR", "hu-HU", "id-ID", "is-IS",
        "it-IT", "iu-Ca", "iu-La", "ja-JP", "jv-ID", "ka-GE", "kk-KZ", "km-KH", "kn-IN", "ko-KR", "lo-LA", "lt-LT",
        "lv-LV", "mk-MK", "ml-IN", "mn-MN", "mr-IN", "ms-MY", "mt-MT", "my-MM", "nb-NO", "ne-NP", "nl-BE", "nl-NL",
        "pl-PL", "ps-AF", "pt-BR", "pt-PT", "ro-RO", "ru-RU", "si-LK", "sk-SK", "sl-SI", "so-SO", "sq-AL", "sr-RS",
        "su-ID", "sv-SE", "sw-KE", "sw-TZ", "ta-IN", "ta-LK", "ta-MY", "ta-SG", "te-IN", "th-TH", "tr-TR", "uk-UA",
        "ur-IN", "ur-PK", "uz-UZ", "vi-VN", "zh-CN", "zh-HK", "zh-TW", "zu-ZA"
    ]

def get_edge_tts_supported_voices():
    return [
        "af-ZA-AdriNeural", "af-ZA-WillemNeural", "am-ET-AmehaNeural", "am-ET-MekdesNeural", "ar-AE-FatimaNeural",
        "ar-AE-HamdanNeural", "ar-BH-AliNeural", "ar-BH-LailaNeural", "ar-DZ-AminaNeural", "ar-DZ-IsmaelNeural",
        "ar-EG-SalmaNeural", "ar-EG-ShakirNeural", "ar-IQ-BasselNeural", "ar-IQ-RanaNeural", "ar-JO-SanaNeural",
        "ar-JO-TaimNeural", "ar-KW-FahedNeural", "ar-KW-NouraNeural", "ar-LB-LaylaNeural", "ar-LB-RamiNeural",
        "ar-LY-ImanNeural", "ar-LY-OmarNeural", "ar-MA-JamalNeural", "ar-MA-MounaNeural", "ar-OM-AbdullahNeural",
        "ar-OM-AyshaNeural", "ar-QA-AmalNeural", "ar-QA-MoazNeural", "ar-SA-HamedNeural", "ar-SA-ZariyahNeural",
        "ar-SY-AmanyNeural", "ar-SY-LaithNeural", "ar-TN-HediNeural", "ar-TN-ReemNeural", "ar-YE-MaryamNeural",
        "ar-YE-SalehNeural", "az-AZ-BabekNeural", "az-AZ-BanuNeural", "bg-BG-BorislavNeural", "bg-BG-KalinaNeural",
        "bn-BD-NabanitaNeural", "bn-BD-PradeepNeural", "bn-IN-BashkarNeural", "bn-IN-TanishaaNeural",
        "bs-BA-GoranNeural", "bs-BA-VesnaNeural", "ca-ES-EnricNeural", "ca-ES-JoanaNeural", "cs-CZ-AntoninNeural",
        "cs-CZ-VlastaNeural", "cy-GB-AledNeural", "cy-GB-NiaNeural", "da-DK-ChristelNeural", "da-DK-JeppeNeural",
        "de-AT-IngridNeural", "de-AT-JonasNeural", "de-CH-JanNeural", "de-CH-LeniNeural", "de-DE-AmalaNeural",
        "de-DE-ConradNeural", "de-DE-FlorianMultilingualNeural", "de-DE-KatjaNeural", "de-DE-KillianNeural",
        "de-DE-SeraphinaMultilingualNeural", "el-GR-AthinaNeural", "el-GR-NestorasNeural", "en-AU-NatashaNeural",
        "en-AU-WilliamNeural", "en-CA-ClaraNeural", "en-CA-LiamNeural", "en-GB-LibbyNeural", "en-GB-MaisieNeural",
        "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-GB-ThomasNeural", "en-HK-SamNeural", "en-HK-YanNeural",
        "en-IE-ConnorNeural", "en-IE-EmilyNeural", "en-IN-NeerjaExpressiveNeural", "en-IN-NeerjaNeural",
        "en-IN-PrabhatNeural", "en-KE-AsiliaNeural", "en-KE-ChilembaNeural", "en-NG-AbeoNeural", "en-NG-EzinneNeural",
        "en-NZ-MitchellNeural", "en-NZ-MollyNeural", "en-PH-JamesNeural", "en-PH-RosaNeural", "en-SG-LunaNeural",
        "en-SG-WayneNeural", "en-TZ-ElimuNeural", "en-TZ-ImaniNeural", "en-US-AnaNeural", "en-US-AndrewMultilingualNeural",
        "en-US-AndrewNeural", "en-US-AriaNeural", "en-US-AvaMultilingualNeural", "en-US-AvaNeural",
        "en-US-BrianMultilingualNeural", "en-US-BrianNeural", "en-US-ChristopherNeural", "en-US-EmmaMultilingualNeural",
        "en-US-EmmaNeural", "en-US-EricNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-MichelleNeural",
        "en-US-RogerNeural", "en-US-SteffanNeural", "en-ZA-LeahNeural", "en-ZA-LukeNeural", "es-AR-ElenaNeural",
        "es-AR-TomasNeural", "es-BO-MarceloNeural", "es-BO-SofiaNeural", "es-CL-CatalinaNeural", "es-CL-LorenzoNeural",
        "es-CO-GonzaloNeural", "es-CO-SalomeNeural", "es-CR-JuanNeural", "es-CR-MariaNeural", "es-CU-BelkysNeural",
        "es-CU-ManuelNeural", "es-DO-EmilioNeural", "es-DO-RamonaNeural", "es-EC-AndreaNeural", "es-EC-LuisNeural",
        "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-ES-XimenaNeural", "es-GQ-JavierNeural", "es-GQ-TeresaNeural",
        "es-GT-AndresNeural", "es-GT-MartaNeural", "es-HN-CarlosNeural", "es-HN-KarlaNeural", "es-MX-DaliaNeural",
        "es-MX-JorgeNeural", "es-NI-FedericoNeural", "es-NI-YolandaNeural", "es-PA-MargaritaNeural", "es-PA-RobertoNeural",
        "es-PE-AlexNeural", "es-PE-CamilaNeural", "es-PR-KarinaNeural", "es-PR-VictorNeural", "es-PY-MarioNeural",
        "es-PY-TaniaNeural", "es-SV-LorenaNeural", "es-SV-RodrigoNeural", "es-US-AlonsoNeural", "es-US-PalomaNeural",
        "es-UY-MateoNeural", "es-UY-ValentinaNeural", "es-VE-PaolaNeural", "es-VE-SebastianNeural", "et-EE-AnuNeural",
        "et-EE-KertNeural", "fa-IR-DilaraNeural", "fa-IR-FaridNeural", "fi-FI-HarriNeural", "fi-FI-NooraNeural",
        "fil-PH-AngeloNeural", "fil-PH-BlessicaNeural", "fr-BE-CharlineNeural", "fr-BE-GerardNeural", "fr-CA-AntoineNeural",
        "fr-CA-JeanNeural", "fr-CA-SylvieNeural", "fr-CA-ThierryNeural", "fr-CH-ArianeNeural", "fr-CH-FabriceNeural",
        "fr-FR-DeniseNeural", "fr-FR-EloiseNeural", "fr-FR-HenriNeural", "fr-FR-RemyMultilingualNeural",
        "fr-FR-VivienneMultilingualNeural", "ga-IE-ColmNeural", "ga-IE-OrlaNeural", "gl-ES-RoiNeural", "gl-ES-SabelaNeural",
        "gu-IN-DhwaniNeural", "gu-IN-NiranjanNeural", "he-IL-AvriNeural", "he-IL-HilaNeural", "hi-IN-MadhurNeural",
        "hi-IN-SwaraNeural", "hr-HR-GabrijelaNeural", "hr-HR-SreckoNeural", "hu-HU-NoemiNeural", "hu-HU-TamasNeural",
        "id-ID-ArdiNeural", "id-ID-GadisNeural", "is-IS-GudrunNeural", "is-IS-GunnarNeural", "it-IT-DiegoNeural",
        "it-IT-ElsaNeural", "it-IT-GiuseppeMultilingualNeural", "it-IT-IsabellaNeural", "iu-Cans-CA-SiqiniqNeural",
        "iu-Cans-CA-TaqqiqNeural", "iu-Latn-CA-SiqiniqNeural", "iu-Latn-CA-TaqqiqNeural", "ja-JP-KeitaNeural",
        "ja-JP-NanamiNeural", "jv-ID-DimasNeural", "jv-ID-SitiNeural", "ka-GE-EkaNeural", "ka-GE-GiorgiNeural",
        "kk-KZ-AigulNeural", "kk-KZ-DauletNeural", "km-KH-PisethNeural", "km-KH-SreymomNeural", "kn-IN-GaganNeural",
        "kn-IN-SapnaNeural", "ko-KR-HyunsuMultilingualNeural", "ko-KR-InJoonNeural", "ko-KR-SunHiNeural",
        "lo-LA-ChanthavongNeural", "lo-LA-KeomanyNeural", "lt-LT-LeonasNeural", "lt-LT-OnaNeural", "lv-LV-EveritaNeural",
        "lv-LV-NilsNeural", "mk-MK-AleksandarNeural", "mk-MK-MarijaNeural", "ml-IN-MidhunNeural", "ml-IN-SobhanaNeural",
        "mn-MN-BataaNeural", "mn-MN-YesuiNeural", "mr-IN-AarohiNeural", "mr-IN-ManoharNeural", "ms-MY-OsmanNeural",
        "ms-MY-YasminNeural", "mt-MT-GraceNeural", "mt-MT-JosephNeural", "my-MM-NilarNeural", "my-MM-ThihaNeural",
        "nb-NO-FinnNeural", "nb-NO-PernilleNeural", "ne-NP-HemkalaNeural", "ne-NP-SagarNeural", "nl-BE-ArnaudNeural",
        "nl-BE-DenaNeural", "nl-NL-ColetteNeural", "nl-NL-FennaNeural", "nl-NL-MaartenNeural", "pl-PL-MarekNeural",
        "pl-PL-ZofiaNeural", "ps-AF-GulNawazNeural", "ps-AF-LatifaNeural", "pt-BR-AntonioNeural", "pt-BR-FranciscaNeural",
        "pt-BR-ThalitaMultilingualNeural", "pt-PT-DuarteNeural", "pt-PT-RaquelNeural", "ro-RO-AlinaNeural",
        "ro-RO-EmilNeural", "ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural", "si-LK-SameeraNeural", "si-LK-ThiliniNeural",
        "sk-SK-LukasNeural", "sk-SK-ViktoriaNeural", "sl-SI-PetraNeural", "sl-SI-RokNeural", "so-SO-MuuseNeural",
        "so-SO-UbaxNeural", "sq-AL-AnilaNeural", "sq-AL-IlirNeural", "sr-RS-NicholasNeural", "sr-RS-SophieNeural",
        "su-ID-JajangNeural", "su-ID-TutiNeural", "sv-SE-MattiasNeural", "sv-SE-SofieNeural", "sw-KE-RafikiNeural",
        "sw-KE-ZuriNeural", "sw-TZ-DaudiNeural", "sw-TZ-RehemaNeural", "ta-IN-PallaviNeural", "ta-IN-ValluvarNeural",
        "ta-LK-KumarNeural", "ta-LK-SaranyaNeural", "ta-MY-KaniNeural", "ta-MY-SuryaNeural", "ta-SG-AnbuNeural",
        "ta-SG-VenbaNeural", "te-IN-MohanNeural", "te-IN-ShrutiNeural", "th-TH-NiwatNeural", "th-TH-PremwadeeNeural",
        "tr-TR-AhmetNeural", "tr-TR-EmelNeural", "uk-UA-OstapNeural", "uk-UA-PolinaNeural", "ur-IN-GulNeural",
        "ur-IN-SalmanNeural", "ur-PK-AsadNeural", "ur-PK-UzmaNeural", "uz-UZ-MadinaNeural", "uz-UZ-SardorNeural",
        "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural",
        "zh-CN-YunxiNeural", "zh-CN-YunxiaNeural", "zh-CN-YunyangNeural", "zh-CN-liaoning-XiaobeiNeural",
        "zh-CN-shaanxi-XiaoniNeural", "zh-HK-HiuGaaiNeural", "zh-HK-HiuMaanNeural", "zh-HK-WanLungNeural",
        "zh-TW-HsiaoChenNeural", "zh-TW-HsiaoYuNeural", "zh-TW-YunJheNeural", "zu-ZA-ThandoNeural", "zu-ZA-ThembaNeural"
    ]
