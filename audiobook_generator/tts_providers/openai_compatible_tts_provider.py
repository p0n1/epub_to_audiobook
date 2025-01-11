import os

from audiobook_generator.tts_providers.openai_tts_provider import OpenAITTSProvider


class OpenAICompatibleTTSProvider(OpenAITTSProvider):
    def validate_config(self):
        if not os.environ.get('OPENAI_BASE_URL'):
            raise ValueError(f"OpenAICompatible: Environment variable 'OPENAI_BASE_URL' is not set.")

    def estimate_cost(self, total_chars):
        return None
