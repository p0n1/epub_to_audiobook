# Pocket-TTS Integration Summary

This document summarizes the integration of Pocket-TTS into the EPUB to Audiobook converter.

## What is Pocket-TTS?

Pocket-TTS is a lightweight, CPU-based text-to-speech engine developed by Kyutai that:
- Runs entirely on CPU (no GPU required)
- Has a small model size (~100M parameters)
- Provides low latency (~200ms to first audio chunk)
- Generates audio faster than real-time (~6x on modern CPUs)
- Supports Python 3.10-3.14
- Requires PyTorch 2.5+
- Supports voice cloning from custom .wav files

## Files Created/Modified

### New Files
1. **`audiobook_generator/tts_providers/pocket_tts_provider.py`**
   - Main implementation of the Pocket-TTS provider
   - Implements the BaseTTSProvider interface
   - Handles model initialization, voice loading, and audio generation
   - Supports built-in voices and custom voice files
   - Converts torch tensors to audio files

### Modified Files
1. **`audiobook_generator/tts_providers/base_tts_provider.py`**
   - Added `TTS_POCKET = "pocket"` constant
   - Added "pocket" to supported TTS providers list
   - Added import logic for PocketTTSProvider

2. **`audiobook_generator/config/general_config.py`**
   - Added `pocket_voice` configuration parameter

3. **`main.py`**
   - Added `--pocket_voice` command-line argument
   - Added pocket-tts specific argument group with voice selection

4. **`audiobook_generator/ui/web_ui.py`**
   - Added import for `get_pocket_supported_voices`
   - Updated `process_ui_form` to accept pocket parameters
   - Added Pocket-TTS tab to the web interface
   - Added voice and output format selectors
   - Updated Start button inputs

5. **`requirements.txt`**
   - Added `pocket-tts` dependency
   - Added `numpy` dependency

6. **`README.md`**
   - Added Pocket-TTS to requirements section
   - Added Pocket-TTS audio sample link
   - Updated WebUI features to mention Pocket-TTS
   - Added Pocket-TTS configuration documentation
   - Added troubleshooting section for Pocket-TTS

## Built-in Voices

Pocket-TTS includes 8 built-in voices:
- **alba** - Female, British English (default)
- **marius** - Male voice
- **javert** - Male voice
- **jean** - Male voice
- **fantine** - Female voice
- **cosette** - Female voice
- **eponine** - Female voice
- **azelma** - Female voice

## Usage Examples

### Command Line
```bash
# Use default voice (alba)
python3 main.py book.epub output/ --tts=pocket

# Use specific voice
python3 main.py book.epub output/ --tts=pocket --pocket_voice=marius

# Use custom voice file for cloning
python3 main.py book.epub output/ --tts=pocket --pocket_voice=/path/to/voice.wav
```

### Web UI
1. Start the web interface: `python3 main_ui.py`
2. Navigate to the Pocket-TTS tab
3. Select a voice from the dropdown
4. Choose output format (mp3, wav, opus, flac)
5. Upload your EPUB and click Start

## Technical Details

### Audio Processing
- Pocket-TTS outputs audio as PyTorch tensors
- Audio is in float32 format, range [-1, 1]
- Converted to int16 (16-bit PCM) for compatibility
- Supports mono audio output
- Uses pydub for format conversion

### Model Loading
- Model is loaded once and kept in memory for efficiency
- Voice state is cached to avoid reloading
- Automatic fallback to 'alba' voice if specified voice fails

### Performance
- No GPU required
- Approximately 6x faster than real-time on modern CPUs
- Low memory footprint (~100M model)
- Suitable for long audiobook generation

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install pocket-tts directly
pip install pocket-tts
```

## Benefits Over Other TTS Providers

1. **No API Key Required** - Runs completely locally
2. **No GPU Needed** - Efficient CPU-only operation
3. **Free** - No usage costs
4. **Fast** - Faster than real-time generation
5. **Privacy** - All processing happens locally
6. **Voice Cloning** - Supports custom voice files

## Limitations

- English only at the moment (as of the model version)
- Limited number of built-in voices (8)
- Requires PyTorch installation (though CPU version is sufficient)

## Future Enhancements

Possible improvements for future versions:
- Support for additional languages when available
- Pre-download and cache voice models
- Streaming audio generation for very long texts
- Additional voice customization parameters
- Support for ONNX/WebAssembly for even lighter deployment

## References

- [Pocket-TTS Model Card](https://huggingface.co/kyutai/pocket-tts)
- [Pocket-TTS GitHub](https://github.com/kyutai-labs/pocket-tts)
- [Kyutai Website Demo](https://kyutai.org/next/tts)
- [Research Paper](https://arxiv.org/abs/2509.06926)
