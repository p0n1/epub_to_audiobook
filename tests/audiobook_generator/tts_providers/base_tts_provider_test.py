import unittest
from unittest.mock import patch

from audiobook_generator.tts_providers.azure_tts_provider import AzureTTSProvider
from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from audiobook_generator.tts_providers.openai_tts_provider import OpenAITTSProvider
from tests.test_utils import get_azure_config, get_openai_config


class TestBaseTtsProvider(unittest.TestCase):

    @patch.dict('os.environ', {'MS_TTS_KEY': 'fake_key', 'MS_TTS_REGION': 'fake_region'})
    def test_get_tts_provider_azure(self):
        config = get_azure_config()
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, AzureTTSProvider)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
    def test_get_tts_provider_openai(self):
        config = get_openai_config()
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, OpenAITTSProvider)

    def test_get_tts_provider_invalid(self):
        config = get_openai_config()
        config.tts = 'invalid_tts_provider'
        with self.assertRaises(ValueError):
            get_tts_provider(config)


if __name__ == '__main__':
    unittest.main()
