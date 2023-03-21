# EPUB to Audiobook Converter

This project provides a command-line tool to convert EPUB ebooks into audiobooks. It uses the [Microsoft Azure Text-to-Speech API](https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/rest-text-to-speech) to generate the audio for each chapter in the ebook. The output audio files are optimized for use with [Audiobookshelf](https://github.com/advplyr/audiobookshelf).

## Requirements

- Python 3.6+
- A Microsoft Azure account with access to the [Microsoft Cognitive Services Speech Services](https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices)

## Installation

1. Clone this repository:

    ```bash
    git clone https://github.com/p0n1/epub-to-audiobook.git
    cd epub-to-audiobook
    ```

2. Create a virtual environment and activate it:

    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3. Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

4. Set the following environment variables with your Azure Text-to-Speech API credentials:

    ```bash
    export MS_TTS_KEY=<your_subscription_key>
    export MS_TTS_REGION=<your_region>
    ```

## Usage

To convert an EPUB ebook to an audiobook, run the following command:

```bash
python epub_to_audiobook.py <input_file> <output_folder> [--voice_name <voice_name>] [--language <language>]
```


- `<input_file>`: Path to the EPUB file.
- `<output_folder>`: Path to the output folder, where the audiobook files will be saved.
- `--voice_name`: (Optional) Voice name for the Text-to-Speech service (default: en-US-GuyNeural). For Chinese ebooks, use zh-CN-YunyeNeural.
- `--language`: (Optional) Language for the Text-to-Speech service (default: en-US).

Example:

```bash
python epub_to_audiobook.py examples/The_Life_and_Adventures_of_Robinson_Crusoe.epub output_folder
```

This command will create a folder called `output_folder` and save the MP3 files for each chapter in the ebook. You can then import the generated audio files into [Audiobookshelf](https://github.com/advplyr/audiobookshelf) or just play with any audio player you like.

## Customization of Voice and Language

You can customize the voice and language used for the Text-to-Speech conversion by passing the `--voice_name` and `--language` options when running the script.

To find the available voices and languages, consult the [Microsoft Azure Text-to-Speech documentation](https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/language-support?tabs=tts#text-to-speech).

For example, if you want to use a British English female voice for the conversion, you can use the following command:

```bash
python epub_to_audiobook.py <input_file> <output_folder> --voice_name en-GB-LibbyNeural --language en-GB
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
