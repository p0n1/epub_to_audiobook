import logging
import tempfile
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.utils.utils import set_audio_tags

logger = logging.getLogger(__name__)


class PocketTTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.output_format = config.output_format or "mp3"
        self.price = 0.000
        self.tts_model = None
        self.voice_state = None
        self.sample_rate = None
        super().__init__(config)

    def __str__(self) -> str:
        return f"PocketTTSProvider(config={self.config})"

    def validate_config(self):
        """Validate Pocket-TTS configuration."""
        pass

    def _initialize_model(self):
        """Initialize the Pocket-TTS model and voice state if not already loaded."""
        if self.tts_model is None:
            try:
                from pocket_tts import TTSModel
                logger.info("Loading Pocket-TTS model...")
                self.tts_model = TTSModel.load_model()
                self.sample_rate = self.tts_model.sample_rate
                logger.info(f"Pocket-TTS model loaded successfully with sample rate: {self.sample_rate}")
            except ImportError:
                raise ImportError(
                    "pocket-tts package is not installed. "
                    "Please install it with: pip install pocket-tts"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to load Pocket-TTS model: {e}")

        if self.voice_state is None:
            self._load_voice()

    def _load_voice(self):
        """Load the voice state for the selected voice."""
        voice_name = self.config.pocket_voice or "alba"
        
        # Check if voice_name is a path to a custom wav file
        if Path(voice_name).exists() and voice_name.endswith('.wav'):
            logger.info(f"Loading custom voice from: {voice_name}")
            self.voice_state = self.tts_model.get_state_for_audio_prompt(voice_name)
        else:
            # Use built-in voice by name
            # Built-in voices: alba, marius, javert, jean, fantine, cosette, eponine, azelma
            # For catalog voices, just pass the name directly (not a file path)
            logger.info(f"Loading built-in voice: {voice_name}")
            try:
                self.voice_state = self.tts_model.get_state_for_audio_prompt(voice_name)
                logger.info(f"Voice '{voice_name}' loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load voice '{voice_name}': {e}. Falling back to 'alba'")
                self.voice_state = self.tts_model.get_state_for_audio_prompt("alba")

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        """
        Convert text to speech using Pocket-TTS.
        
        Args:
            text: The text to convert to speech
            output_file: Path to save the output audio file
            audio_tags: Audio metadata tags to apply
        """
        # Initialize model and voice if not already done
        self._initialize_model()

        try:
            logger.info(f"Generating audio for text of length {len(text)} characters")
            
            # Generate audio using Pocket-TTS
            audio_tensor = self.tts_model.generate_audio(self.voice_state, text)
            
            # Convert torch tensor to numpy array
            audio_data = audio_tensor.numpy()
            
            # Normalize to int16 range if needed
            if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
                # Pocket-TTS typically outputs float32 in range [-1, 1]
                audio_data = (audio_data * 32767).astype(np.int16)
            
            with tempfile.TemporaryDirectory() as tmpdirname:
                logger.debug("Created temporary directory %r", tmpdirname)
                
                # Create temporary WAV file
                tmpfilename = Path(tmpdirname) / "pocket_tts.wav"
                
                # Create AudioSegment from raw audio data
                audio_segment = AudioSegment(
                    data=audio_data.tobytes(),
                    sample_width=2,  # 16-bit audio = 2 bytes
                    frame_rate=self.sample_rate,
                    channels=1  # Pocket-TTS outputs mono
                )
                
                # Export to temporary WAV file
                audio_segment.export(tmpfilename, format="wav")
                
                # Set audio tags if provided
                if audio_tags:
                    set_audio_tags(tmpfilename, audio_tags)
                    
                logger.info(
                    f"Audio generated, converting to {self.config.output_format} format"
                )
                
                # Convert to desired output format
                AudioSegment.from_wav(tmpfilename).export(
                    output_file, format=self.config.output_format
                )
                
                logger.info(f"Conversion completed, output file: {output_file}")
                
        except Exception as e:
            logger.error(f"Error generating speech with Pocket-TTS: {e}")
            raise

    def estimate_cost(self, total_chars):
        """Pocket-TTS is free to use."""
        return 0

    def get_break_string(self):
        """Return the string used for breaks between sentences."""
        return "."

    def get_output_file_extension(self):
        """Return the output file extension."""
        return self.config.output_format


def get_pocket_supported_voices():
    """
    Get list of supported built-in voices for Pocket-TTS.
    
    Returns:
        List of voice names that can be used with Pocket-TTS
    """
    return [
        "alba",      # Female British English
        "marius",    # Male voice
        "javert",    # Male voice
        "jean",      # Male voice
        "fantine",   # Female voice
        "cosette",   # Female voice
        "eponine",   # Female voice
        "azelma"     # Female voice
    ]
