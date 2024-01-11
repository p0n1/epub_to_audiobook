from typing import List

from audiobook_generator.config.general_config import GeneralConfig

TTS_AZURE = "azure"
TTS_OPENAI = "openai"
TTS_EDGE = "edge"


class BaseTTSProvider:  # Base interface for TTS providers
    # Base provider interface
    def __init__(self, config: GeneralConfig):
        self.config = config
        self.validate_config()

    def __str__(self) -> str:
        return f"{self.config}"

    def validate_config(self):
        raise NotImplementedError

    def text_to_speech(self, *args, **kwargs):
        raise NotImplementedError

    def estimate_cost(self, total_chars):
        raise NotImplementedError

    def get_break_string(self):
        raise NotImplementedError

    def get_output_file_extension(self):
        raise NotImplementedError


# Common support methods for all TTS providers
def get_supported_tts_providers() -> List[str]:
    return [TTS_AZURE, TTS_OPENAI, TTS_EDGE]


def get_tts_provider(config) -> BaseTTSProvider:
    if config.tts == TTS_AZURE:
        from audiobook_generator.tts_providers.azure_tts_provider import AzureTTSProvider
        return AzureTTSProvider(config)
    elif config.tts == TTS_OPENAI:
        from audiobook_generator.tts_providers.openai_tts_provider import OpenAITTSProvider
        return OpenAITTSProvider(config)
    elif config.tts == TTS_EDGE:
        from audiobook_generator.tts_providers.edge_tts_provider import EdgeTTSProvider
        return EdgeTTSProvider(config)
    else:
        raise ValueError(f"Invalid TTS provider: {config.tts}")
