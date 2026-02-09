import logging
import re
import tempfile
from pathlib import Path
from typing import List

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

    def _chunk_text(self, text: str, max_chars: int = 100) -> List[str]:
        """
        Split text into smaller chunks to avoid tensor size mismatches.
        Uses very conservative chunking due to Pocket-TTS internal limitations.
        
        Args:
            text: The text to chunk
            max_chars: Maximum characters per chunk (default 100, very conservative)
            
        Returns:
            List of text chunks
        """
        # Split on sentence boundaries first
        sentences = re.split(r'([.!?]+\s+)', text)
        
        chunks = []
        current_chunk = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            separator = sentences[i + 1] if i + 1 < len(sentences) else ""
            sentence_with_sep = sentence + separator
            
            # If the sentence itself is too long, split it further
            if len(sentence_with_sep) > max_chars:
                # Split long sentences by words
                words = sentence_with_sep.split()
                for word in words:
                    if len(current_chunk) + len(word) + 1 > max_chars and current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = word + " "
                    else:
                        current_chunk += word + " "
            else:
                # If adding this sentence would exceed max_chars, start a new chunk
                if len(current_chunk) + len(sentence_with_sep) > max_chars and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence_with_sep
                else:
                    current_chunk += sentence_with_sep
        
        # Add the last chunk if it's not empty
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # If we still have no chunks (text was very short), just use the original text
        if not chunks:
            chunks = [text]
        
        return chunks

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
            
            # Chunk the text to avoid tensor size mismatches with long texts
            # Using very conservative 100 char chunks due to Pocket-TTS limitations
            chunks = self._chunk_text(text, max_chars=100)
            logger.info(f"Split text into {len(chunks)} chunks (100 char limit)")
            
            # Generate audio for each chunk
            audio_segments = []
            failed_chunks = 0
            
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                    
                logger.debug(f"Generating audio for chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                
                success = False
                attempts = [100, 50, 30]  # Progressive chunk size reduction
                
                for attempt_size in attempts:
                    try:
                        if attempt_size < 100:
                            logger.info(f"Retrying chunk {i+1} with {attempt_size} char limit")
                            sub_chunks = self._chunk_text(chunk, max_chars=attempt_size)
                        else:
                            sub_chunks = [chunk]
                        
                        for sub_chunk in sub_chunks:
                            if not sub_chunk.strip():
                                continue
                            
                            # Create a fresh voice state for each chunk to avoid state corruption
                            fresh_voice_state = self.tts_model.get_state_for_audio_prompt(
                                self.config.pocket_voice or "alba"
                            )
                            
                            # Generate audio using Pocket-TTS with fresh state
                            audio_tensor = self.tts_model.generate_audio(fresh_voice_state, sub_chunk)
                            
                            # Convert torch tensor to numpy array
                            audio_data = audio_tensor.numpy()
                            
                            # Normalize to int16 range if needed
                            if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
                                # Pocket-TTS typically outputs float32 in range [-1, 1]
                                audio_data = (audio_data * 32767).astype(np.int16)
                            
                            # Create AudioSegment from raw audio data
                            audio_segment = AudioSegment(
                                data=audio_data.tobytes(),
                                sample_width=2,  # 16-bit audio = 2 bytes
                                frame_rate=self.sample_rate,
                                channels=1  # Pocket-TTS outputs mono
                            )
                            
                            audio_segments.append(audio_segment)
                        
                        success = True
                        break  # Success, no need to try smaller chunks
                        
                    except Exception as chunk_error:
                        logger.warning(f"Attempt with {attempt_size} char limit failed for chunk {i+1}: {str(chunk_error)[:100]}")
                        if attempt_size == attempts[-1]:
                            # Last attempt failed
                            logger.error(f"All attempts failed for chunk {i+1}, skipping this chunk")
                            failed_chunks += 1
                
                if not success and failed_chunks > 5:
                    raise RuntimeError(
                        f"Too many chunks failed ({failed_chunks}). "
                        "Pocket-TTS may have compatibility issues with this text."
                    )
            
            # Combine all audio segments
            if not audio_segments:
                raise RuntimeError("No audio segments were generated successfully")
            
            logger.info(f"Combining {len(audio_segments)} audio segments")
            if failed_chunks > 0:
                logger.warning(f"{failed_chunks} chunks failed to generate and were skipped")
            
            combined_audio = audio_segments[0]
            for segment in audio_segments[1:]:
                combined_audio += segment
            
            with tempfile.TemporaryDirectory() as tmpdirname:
                logger.debug("Created temporary directory %r", tmpdirname)
                
                # Create temporary WAV file
                tmpfilename = Path(tmpdirname) / "pocket_tts.wav"
                
                # Export to temporary WAV file
                combined_audio.export(tmpfilename, format="wav")
                
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
