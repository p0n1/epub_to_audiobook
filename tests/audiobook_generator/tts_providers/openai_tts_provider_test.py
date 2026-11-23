import unittest
from unittest.mock import patch

from openai import OpenAIError

from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from audiobook_generator.tts_providers.openai_tts_provider import OpenAITTSProvider
from tests.test_utils import get_openai_config

PROVIDER_LOG = "audiobook_generator.tts_providers.openai_tts_provider"


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
        self.assertEqual(tts_provider.config.model_name, "gpt-4o-mini-tts")
        self.assertEqual(tts_provider.config.voice_name, "alloy")
        self.assertEqual(tts_provider.config.output_format, "mp3")


    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake_key", "OPENAI_BASE_URL": "https://api.openai.com/v1"})
    def test_native_openai_retirement_warning(self):
        for model in (None, "tts-1", "tts-1-hd", "gpt-4o-mini-tts-2025-03-20", "gpt-4o-mini-tts-2025-12-15"):
            with self.subTest(model=model):
                config = get_openai_config()
                config.model_name = model
                with self.assertLogs(PROVIDER_LOG, level="WARNING") as capture:
                    tts_provider = get_tts_provider(config)
                tts_provider.client.close()
                warnings = [line for line in capture.output if "January 6, 2027" in line]
                self.assertEqual(len(warnings), 1)
                self.assertIn("Realtime API", warnings[0])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake_key", "OPENAI_BASE_URL": "http://127.0.0.1:8880/v1"})
    def test_local_compatible_endpoint_has_no_openai_retirement_warning(self):
        config = get_openai_config()
        config.model_name = "tts-1"
        with self.assertNoLogs(PROVIDER_LOG, level="WARNING"):
            tts_provider = get_tts_provider(config)
        tts_provider.client.close()


if __name__ == '__main__':
    unittest.main()
