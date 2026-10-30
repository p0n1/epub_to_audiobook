import base64
import io
import logging
import math
import os

import requests

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.utils.utils import merge_audio_segments, set_audio_tags, split_text

logger = logging.getLogger(__name__)

MAX_CHARS = 2000
DEFAULT_BASE_URL = "https://api.inworld.ai"
SUPPORTED_OUTPUT_FORMATS = ["mp3", "wav", "ogg", "opus"]
SUPPORTED_MODELS = [
    "inworld-tts-1.5-max",
    "inworld-tts-1.5-mini",
    "inworld-tts-1-max",
    "inworld-tts-1",
]
SUPPORTED_AUDIO_ENCODINGS = {
    "mp3": "MP3",
    "wav": "LINEAR16",
    "ogg": "OGG_OPUS",
    "opus": "OGG_OPUS",
}
MODEL_PRICES = {
    "inworld-tts-1.5-mini": 0.005,
    "inworld-tts-1.5-max": 0.01,
}


class InworldTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.voice_name = config.voice_name or os.environ.get("INWORLD_VOICE_ID")
        config.model_name = config.model_name or os.environ.get("INWORLD_MODEL_ID")
        config.output_format = config.output_format or "mp3"
        self.base_url = os.environ.get("INWORLD_TTS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.api_key = os.environ.get("INWORLD_API_KEY")
        self.price = 0.0
        super().__init__(config)

    def validate_config(self):
        if not self.api_key:
            raise ValueError(
                "Inworld TTS requires INWORLD_API_KEY environment variable containing the Basic (Base64) credential from Inworld."
            )
        if not self.config.voice_name:
            raise ValueError("Inworld TTS requires a voice_name/voiceId value.")
        if not self.config.model_name:
            raise ValueError("Inworld TTS requires a model_name/modelId value.")
        if self.config.model_name not in SUPPORTED_MODELS:
            raise ValueError(
                f"Inworld TTS: Unsupported model name: {self.config.model_name}. Supported models: {', '.join(SUPPORTED_MODELS)}"
            )
        if self.config.output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(
                f"Inworld TTS: Unsupported output format: {self.config.output_format}. Supported formats: {', '.join(SUPPORTED_OUTPUT_FORMATS)}"
            )

    def _request_audio(self, text: str) -> bytes:
        payload = {
            "text": text,
            "voiceId": self.config.voice_name,
            "modelId": self.config.model_name,
            "audioConfig": {"audioEncoding": SUPPORTED_AUDIO_ENCODINGS[self.config.output_format]},
        }
        url = f"{self.base_url}/tts/v1/voice"
        logger.debug("Sending request to Inworld TTS url=%s payload_keys=%s", url, list(payload.keys()))
        response = requests.post(
            url,
            headers={
                "Authorization": f"Basic {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        audio_content = data.get("audioContent")
        if not audio_content:
            raise ValueError("Inworld TTS response did not contain audioContent.")
        if isinstance(audio_content, str):
            try:
                return base64.b64decode(audio_content)
            except Exception:
                return audio_content.encode("utf-8")
        if isinstance(audio_content, bytes):
            return audio_content
        raise ValueError(f"Unexpected audioContent type from Inworld TTS: {type(audio_content)!r}")

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        text_chunks = split_text(text, MAX_CHARS, self.config.language)
        audio_segments = []
        chunk_ids = []

        for i, chunk in enumerate(text_chunks, 1):
            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
            logger.info("Processing %s, length=%s", chunk_id, len(chunk))
            logger.debug("Processing %s, length=%s, text=[%s]", chunk_id, len(chunk), chunk)
            audio_segments.append(io.BytesIO(self._request_audio(chunk)))
            chunk_ids.append(chunk_id)

        merge_audio_segments(
            audio_segments,
            output_file,
            self.config.output_format,
            chunk_ids,
            self.config.use_pydub_merge,
        )
        set_audio_tags(output_file, audio_tags)

    def estimate_cost(self, total_chars):
        # Inworld bills per million characters, so convert that into a per-1000-char estimate like the other providers.
        return math.ceil(total_chars / 1000) * MODEL_PRICES.get(self.config.model_name, 0.0)

    def get_break_string(self):
        return "   "

    def get_output_file_extension(self):
        return self.config.output_format


def get_inworld_supported_models():
    return SUPPORTED_MODELS
