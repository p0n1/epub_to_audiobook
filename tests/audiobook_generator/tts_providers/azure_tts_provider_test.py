import unittest
from unittest.mock import patch

from audiobook_generator.tts_providers.azure_tts_provider import AzureTTSProvider
from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from tests.test_utils import get_azure_config


class TestAzureTtsProvider(unittest.TestCase):

    def test_missing_env_var_keys(self):
        config = get_azure_config()
        with self.assertRaises(ValueError):
            get_tts_provider(config)

    @patch.dict('os.environ', {'MS_TTS_KEY': 'fake_key', 'MS_TTS_REGION': 'fake_region'})
    def test_estimate_cost(self):
        config = get_azure_config()
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, AzureTTSProvider)
        self.assertEqual(tts_provider.estimate_cost(1000000), 16)

    @patch.dict('os.environ', {'MS_TTS_KEY': 'fake_key', 'MS_TTS_REGION': 'fake_region'})
    def test_default_args(self):
        config = get_azure_config()
        config.voice_name = None
        config.output_format = None
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, AzureTTSProvider)
        self.assertEqual(tts_provider.config.voice_name, "en-US-GuyNeural")
        self.assertEqual(tts_provider.config.output_format, "audio-24khz-48kbitrate-mono-mp3")


if __name__ == '__main__':
    unittest.main()
