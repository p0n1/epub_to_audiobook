import unittest
from unittest.mock import patch

from openai import OpenAIError

from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from audiobook_generator.tts_providers.openai_tts_provider import OpenAITTSProvider
from tests.test_utils import get_openai_config


class TestOpenAiTtsProvider(unittest.TestCase):

    def test_missing_env_var_keys(self):
        config = get_openai_config()
        with self.assertRaises(OpenAIError):
            get_tts_provider(config)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
    def test_estimate_cost(self):
        config = get_openai_config()
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, OpenAITTSProvider)
        self.assertEqual(tts_provider.estimate_cost(1000000), 15)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
    def test_default_args(self):
        config = get_openai_config()
        config.model_name = None
        config.voice_name = None
        config.output_format = None
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, OpenAITTSProvider)
        self.assertEqual(tts_provider.config.model_name, "tts-1")
        self.assertEqual(tts_provider.config.voice_name, "alloy")
        self.assertEqual(tts_provider.config.output_format, "mp3")


if __name__ == '__main__':
    unittest.main()
