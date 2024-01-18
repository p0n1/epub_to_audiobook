import argparse
import logging

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audiobook_generator import AudiobookGenerator
from audiobook_generator.tts_providers.base_tts_provider import get_supported_tts_providers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def handle_args():
    parser = argparse.ArgumentParser(description="Convert text book to audiobook")
    parser.add_argument("input_file", help="Path to the EPUB file")
    parser.add_argument("output_folder", help="Path to the output folder")
    parser.add_argument(
        "--tts",
        choices=get_supported_tts_providers(),
        default=get_supported_tts_providers()[0],
        help="Choose TTS provider (default: azure). azure: Azure Cognitive Services, openai: OpenAI TTS API. When using azure, environment variables MS_TTS_KEY and MS_TTS_REGION must be set. When using openai, environment variable OPENAI_API_KEY must be set.",
    )
    parser.add_argument(
        "--log",
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default="INFO",
        help="Log level (default: INFO), can be DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Enable preview mode. In preview mode, the script will not convert the text to speech. Instead, it will print the chapter index, titles, and character counts.",
    )
    parser.add_argument(
        "--no_prompt",
        action="store_true",
        help="Don't ask the user if they wish to continue after estimating the cloud cost for TTS. Useful for scripting.",
    )
    parser.add_argument(
        "--language",
        default="en-US",
        help="Language for the text-to-speech service (default: en-US). For Azure TTS (--tts=azure), check https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts#text-to-speech for supported languages. For OpenAI TTS (--tts=openai), their API detects the language automatically. But setting this will also help on splitting the text into chunks with different strategies in this tool, especially for Chinese characters. For Chinese books, use zh-CN, zh-TW, or zh-HK.",
    )
    parser.add_argument(
        "--newline_mode",
        choices=["single", "double"],
        default="double",
        help="Choose the mode of detecting new paragraphs: 'single' or 'double'. 'single' means a single newline character, while 'double' means two consecutive newline characters. (default: double, works for most ebooks but will detect less paragraphs for some ebooks)",
    )
    parser.add_argument(
        "--chapter_start",
        default=1,
        type=int,
        help="Chapter start index (default: 1, starting from 1)",
    )
    parser.add_argument(
        "--chapter_end",
        default=-1,
        type=int,
        help="Chapter end index (default: -1, meaning to the last chapter)",
    )
    parser.add_argument(
        "--output_text",
        action="store_true",
        help="Enable Output Text. This will export a plain text file for each chapter specified and write the files to the output folder specified.",
    )
    parser.add_argument(
        "--remove_endnotes",
        action="store_true",
        help="This will remove endnote numbers from the end or middle of sentences. This is useful for academic books.",
    )

    parser.add_argument(
        "--voice_name",
        help="Various TTS providers has different voice names, look up for your provider settings.",
    )

    parser.add_argument(
        "--output_format",
        help="Output format for the text-to-speech service. Supported format depends on selected TTS provider",
    )

    parser.add_argument(
        "--model_name",
        help="Various TTS providers has different neural model names",
    )

    edge_tts_group = parser.add_argument_group(title="edge specific")
    edge_tts_group.add_argument(
        "--voice_rate",
        help='''
            Speaking rate of the text. Valid relative values range from -50%%(--xxx='-50%%') to +100%%. 
            For negative value use format --arg=value,
        '''
    )

    edge_tts_group.add_argument(
        "--voice_volume",
        help='''
            Volume level of the speaking voice. Valid relative values floor to -100%%.
            For negative value use format --arg=value,
        '''
    )

    edge_tts_group.add_argument(
        "--voice_pitch",
        help='''
            Baseline pitch for the text.Valid relative values like -80Hz,+50Hz, pitch changes should be within 0.5 to 1.5 times the original audio.
            For negative value use format --arg=value,
        '''
    )

    edge_tts_group.add_argument(
        "--proxy",
        help="Proxy server for the TTS provider. Format: http://[username:password@]proxy.server:port",
    )

    azure_tts_group = parser.add_argument_group(title="azure specific")
    azure_tts_group.add_argument(
        "--break_duration",
        default="1250",
        help="Break duration in milliseconds for the different paragraphs or sections (default: 1250). Valid values range from 0 to 5000 milliseconds.",
    )

    args = parser.parse_args()
    return GeneralConfig(args)


def main():
    config = handle_args()
    logger.setLevel(config.log)
    AudiobookGenerator(config).run()


if __name__ == "__main__":
    main()
