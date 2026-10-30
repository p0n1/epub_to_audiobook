import os
import unittest
from unittest.mock import patch

from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from audiobook_generator.tts_providers.inworld_tts_provider import InworldTTSProvider, get_inworld_supported_models
from tests.test_utils import get_inworld_config


class TestInworldTtsProvider(unittest.TestCase):

    def test_missing_env_var_keys(self):
        config = get_inworld_config()
        with self.assertRaises(ValueError):
            get_tts_provider(config)

    @patch.dict('os.environ', {'INWORLD_API_KEY': 'fake_key'})
    def test_default_args(self):
        config = get_inworld_config()
        config.voice_name = None
        config.model_name = None
        config.output_format = None
        with patch.dict(os.environ, {'INWORLD_VOICE_ID': 'voice-1', 'INWORLD_MODEL_ID': 'inworld-tts-1.5-mini'}):
            tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, InworldTTSProvider)
        self.assertEqual(tts_provider.config.voice_name, "voice-1")
        self.assertEqual(tts_provider.config.model_name, "inworld-tts-1.5-mini")
        self.assertEqual(tts_provider.config.output_format, "mp3")

    @patch.dict('os.environ', {'INWORLD_API_KEY': 'fake_key'})
    def test_estimate_cost(self):
        config = get_inworld_config()
        tts_provider = get_tts_provider(config)
        self.assertIsInstance(tts_provider, InworldTTSProvider)
        self.assertEqual(tts_provider.estimate_cost(1000000), 5.0)

    def test_supported_models(self):
        self.assertIn("inworld-tts-1.5-mini", get_inworld_supported_models())


if __name__ == '__main__':
    unittest.main()
