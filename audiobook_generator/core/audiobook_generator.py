import logging
import os
import shutil

from audiobook_generator.book_parsers.base_book_parser import get_book_parser
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider

logger = logging.getLogger(__name__)


def confirm_conversion():
    print("Do you want to continue? (y/n)")
    answer = input()
    if answer.lower() != "y":
        print("Aborted.")
        exit(0)


def get_total_chars(chapters):
    total_characters = 0
    for title, text in chapters:
        total_characters += len(text)
    return total_characters


class AudiobookGenerator:
    def __init__(self, config: GeneralConfig):
        self.config = config
        self.temp_folder = None
        self.working_dir = None

    def __str__(self) -> str:
        return f"{self.config}"

    def setup_directories(self, book_title):
        """Setup output and temp directories"""
        if self.config.temp_dir:
            # Create temp dir if it doesn't exist
            os.makedirs(self.config.temp_dir, exist_ok=True)
            # Create book-specific subfolder in temp dir
            safe_title = "".join(c for c in book_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            self.temp_folder = os.path.join(self.config.temp_dir, safe_title)
            os.makedirs(self.temp_folder, exist_ok=True)
            self.working_dir = self.temp_folder
        else:
            # If not using temp dir, create output folder immediately
            os.makedirs(self.config.output_folder, exist_ok=True)
            self.working_dir = self.config.output_folder

    def cleanup_temp_folder(self):
        """Clean up temporary directory after successful move"""
        if self.temp_folder and os.path.exists(self.temp_folder):
            shutil.rmtree(self.temp_folder)
            logger.info(f"Cleaned up temporary directory: {self.temp_folder}")

    def move_files_to_output(self):
        """Copy all files from temp folder to output folder, then clean up temp"""
        if not self.temp_folder:
            return

        # Create output folder just before copying files
        os.makedirs(self.config.output_folder, exist_ok=True)
        
        logger.info("Copying files from temp folder to output folder...")
        try:
            for filename in os.listdir(self.temp_folder):
                src = os.path.join(self.temp_folder, filename)
                dst = os.path.join(self.config.output_folder, filename)
                shutil.copy2(src, dst)  # copy2 preserves metadata
            logger.info("Successfully copied all files to output folder")
            
            # Only clean up temp folder after successful copy
            self.cleanup_temp_folder()
        except Exception as e:
            logger.error(f"Error copying files to output folder: {e}")
            raise

    def run(self):
        try:
            book_parser = get_book_parser(self.config)
            tts_provider = get_tts_provider(self.config)
            
            chapters = book_parser.get_chapters(tts_provider.get_break_string())
            # Filter out empty or very short chapters
            chapters = [(title, text) for title, text in chapters if text.strip()]

            logger.info(f"Chapters count: {len(chapters)}.")

            # Check chapter start and end args
            if self.config.chapter_start < 1 or self.config.chapter_start > len(chapters):
                raise ValueError(
                    f"Chapter start index {self.config.chapter_start} is out of range. Check your input."
                )
            if self.config.chapter_end < -1 or self.config.chapter_end > len(chapters):
                raise ValueError(
                    f"Chapter end index {self.config.chapter_end} is out of range. Check your input."
                )
            if self.config.chapter_end == -1:
                self.config.chapter_end = len(chapters)
            if self.config.chapter_start > self.config.chapter_end:
                raise ValueError(
                    f"Chapter start index {self.config.chapter_start} is larger than chapter end index {self.config.chapter_end}. Check your input."
                )

            logger.info(f"Converting chapters from {self.config.chapter_start} to {self.config.chapter_end}.")

            # Initialize total_characters to 0
            total_characters = get_total_chars(chapters[self.config.chapter_start - 1:self.config.chapter_end])
            logger.info(f"✨ Total characters in selected book chapters: {total_characters} ✨")
            rough_price = tts_provider.estimate_cost(total_characters)
            print(f"Estimate book voiceover would cost you roughly: ${rough_price:.2f}\n")

            # Prompt user to continue if not in preview mode
            if self.config.no_prompt:
                logger.info(f"Skipping prompt as passed parameter no_prompt")
            elif self.config.preview:
                logger.info(f"Skipping prompt as in preview mode")
            else:
                confirm_conversion()

            # Setup directories using book title
            self.setup_directories(book_parser.get_book_title())

            # Loop through each chapter and convert it to speech using the provided TTS provider
            for idx, (title, text) in enumerate(chapters, start=1):
                if idx < self.config.chapter_start:
                    continue
                if idx > self.config.chapter_end:
                    break
                logger.info(
                    f"Converting chapter {idx}/{len(chapters)}: {title}, characters: {len(text)}"
                )

                if self.config.output_text:
                    text_file = os.path.join(self.working_dir, f"{idx:04d}_{title}.txt")
                    with open(text_file, "w", encoding='utf-8') as file:
                        file.write(text)

                if self.config.preview:
                    continue

                output_file = os.path.join(self.working_dir,
                                         f"{idx:04d}_{title}.{tts_provider.get_output_file_extension()}")

                audio_tags = AudioTags(title, book_parser.get_book_author(), book_parser.get_book_title(), idx)
                tts_provider.text_to_speech(
                    text,
                    output_file,
                    audio_tags,
                )
                logger.info(
                    f"✅ Converted chapter {idx}/{len(chapters)}: {title}"
                )

            logger.info("All chapters converted. 🎉🎉🎉")
            
            # Move files from temp to output if using temp dir
            if self.temp_folder:
                self.move_files_to_output()
                self.cleanup_temp_folder()

        except KeyboardInterrupt:
            logger.info("Job stopped by user.")
            exit()
