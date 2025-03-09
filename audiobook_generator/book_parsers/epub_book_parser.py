import logging
import os
import re
from typing import List, Tuple
import shutil
import zipfile

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from audiobook_generator.book_parsers.base_book_parser import BaseBookParser
from audiobook_generator.config.general_config import GeneralConfig

logger = logging.getLogger(__name__)


def read_epub_safely(epub_path):
    """
    Safely read an EPUB file, attempting to fix common issues if needed.
    """
    common_missing_files = [
        'page_styles.css',
        'stylesheet.css',
        'style.css',
        'styles.css'
    ]

    # Add all potentially missing files
    try:
        with zipfile.ZipFile(epub_path, 'a') as epub_zip:
            existing_files = set(epub_zip.namelist())

            for css_file in common_missing_files:
                if css_file not in existing_files:
                    logger.info(f"Adding missing {css_file} to EPUB file...")
                    epub_zip.writestr(css_file, '/* Empty CSS file */')
    except Exception as e:
        logger.warning(f"Could not preemptively fix EPUB file: {e}")
        # Continue anyway, we'll try to read the file as is

    # Now try to read the EPUB
    try:
        return epub.read_epub(epub_path, {'ignore_ncx': True})
    except KeyError as e:
        # Extract the missing file name from the error
        missing_file_match = re.search(r"'([^']*)'", str(e))
        if missing_file_match:
            missing_file = missing_file_match.group(1)
            logger.warning(f"EPUB file is missing '{missing_file}'. Attempting to fix...")

            try:
                # Try to add the specific missing file
                with zipfile.ZipFile(epub_path, 'a') as epub_zip:
                    epub_zip.writestr(missing_file, '/* Empty file */')
                logger.info(f"Added missing file: {missing_file}. Trying to read EPUB again...")
                return epub.read_epub(epub_path, {'ignore_ncx': True})
            except Exception as fix_error:
                logger.error(f"Error while fixing EPUB: {fix_error}")
                # If we still can't read it, try a more drastic approach
                try:
                    logger.info("Attempting to extract and repackage the EPUB...")
                    import tempfile

                    # Create a temporary directory
                    temp_dir = tempfile.mkdtemp()
                    try:
                        # Extract the EPUB
                        with zipfile.ZipFile(epub_path, 'r') as epub_zip:
                            epub_zip.extractall(temp_dir)

                        # Create all missing CSS files
                        for css_file in common_missing_files:
                            css_path = os.path.join(temp_dir, css_file)
                            if not os.path.exists(css_path):
                                with open(css_path, 'w') as f:
                                    f.write('/* Empty CSS file */')

                        # Create a new EPUB file
                        temp_epub = epub_path + '.fixed'
                        with zipfile.ZipFile(temp_epub, 'w') as new_epub:
                            for root, _, files in os.walk(temp_dir):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, temp_dir)
                                    new_epub.write(file_path, arcname)

                        # Replace the original with the fixed version
                        shutil.move(temp_epub, epub_path)
                        logger.info("EPUB file has been repackaged. Trying to read again...")

                        return epub.read_epub(epub_path, {'ignore_ncx': True})
                    finally:
                        # Clean up the temporary directory
                        shutil.rmtree(temp_dir)
                except Exception as repackage_error:
                    logger.error(f"Error while repackaging EPUB: {repackage_error}")
                    raise e
        else:
            # For other KeyError issues, just raise the original error
            raise
    except Exception as e:
        logger.error(f"Error reading EPUB file: {e}")
        raise

class EpubBookParser(BaseBookParser):
    def __init__(self, config: GeneralConfig):
        super().__init__(config)
        self.book = read_epub_safely(self.config.input_file)

    def __str__(self) -> str:
        return super().__str__()

    def validate_config(self):
        if self.config.input_file is None:
            raise ValueError("Epub Parser: Input file cannot be empty")
        if not self.config.input_file.endswith(".epub"):
            raise ValueError(f"Epub Parser: Unsupported file format: {self.config.input_file}")

    def get_book(self):
        return self.book

    def get_book_title(self) -> str:
        if self.book.get_metadata('DC', 'title'):
            return self.book.get_metadata("DC", "title")[0][0]
        return "Untitled"

    def get_book_author(self) -> str:
        if self.book.get_metadata('DC', 'creator'):
            return self.book.get_metadata("DC", "creator")[0][0]
        return "Unknown"

    def get_chapters(self, break_string) -> List[Tuple[str, str]]:
        chapters = []
        search_and_replaces = self.get_search_and_replaces()
        for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            soup = BeautifulSoup(content, "lxml-xml")
            raw = soup.get_text(strip=False)
            logger.debug(f"Raw text: <{raw[:]}>")

            # Replace excessive whitespaces and newline characters based on the mode
            if self.config.newline_mode == "single":
                cleaned_text = re.sub(r"[\n]+", break_string, raw.strip())
            elif self.config.newline_mode == "double":
                cleaned_text = re.sub(r"[\n]{2,}", break_string, raw.strip())
            elif self.config.newline_mode == "none":
                cleaned_text = re.sub(r"[\n]+", " ", raw.strip())
            else:
                raise ValueError(f"Invalid newline mode: {self.config.newline_mode}")

            logger.debug(f"Cleaned text step 1: <{cleaned_text[:]}>")
            cleaned_text = re.sub(r"\s+", " ", cleaned_text)
            logger.debug(f"Cleaned text step 2: <{cleaned_text[:100]}>")

            # Removes end-note numbers
            if self.config.remove_endnotes:
                cleaned_text = re.sub(r'(?<=[a-zA-Z.,!?;”")])\d+', "", cleaned_text)
                logger.debug(f"Cleaned text step 4: <{cleaned_text[:100]}>")

            # Does user defined search and replaces
            for search_and_replace in search_and_replaces:
                cleaned_text = re.sub(search_and_replace['search'], search_and_replace['replace'], cleaned_text)
            logger.debug(f"Cleaned text step 5: <{cleaned_text[:100]}>")

            # Get proper chapter title
            if self.config.title_mode == "auto":
                title = ""
                title_levels = ['title', 'h1', 'h2', 'h3']
                for level in title_levels:
                    if soup.find(level):
                        title = soup.find(level).text
                        break
                if title == "" or re.match(r'^\d{1,3}$',title) is not None:
                    title = cleaned_text[:60]
            elif self.config.title_mode == "tag_text":
                title = ""
                title_levels = ['title', 'h1', 'h2', 'h3']
                for level in title_levels:
                    if soup.find(level):
                        title = soup.find(level).text
                        break
                if title == "":
                    title = "<blank>"
            elif self.config.title_mode == "first_few":
                title = cleaned_text[:60]
            else:
                raise ValueError("Unsupported title_mode")
            logger.debug(f"Raw title: <{title}>")
            title = self._sanitize_title(title, break_string)
            logger.debug(f"Sanitized title: <{title}>")

            chapters.append((title, cleaned_text))
            soup.decompose()
        return chapters

    def get_search_and_replaces(self):
        search_and_replaces = []
        if self.config.search_and_replace_file:
            with open(self.config.search_and_replace_file) as fp:
                search_and_replace_content = fp.readlines()
                for search_and_replace in search_and_replace_content:
                    if '==' in search_and_replace and not search_and_replace.startswith('==') and not search_and_replace.endswith('==') and not search_and_replace.startswith('#'):
                        search_and_replaces = search_and_replaces + [ {'search': r"{}".format(search_and_replace.split('==')[0]), 'replace': r"{}".format(search_and_replace.split('==')[1][:-1])} ]
        return search_and_replaces

    @staticmethod
    def _sanitize_title(title, break_string) -> str:
        # replace MAGIC_BREAK_STRING with a blank space
        # strip incase leading bank is missing
        title = title.replace(break_string, " ")
        sanitized_title = re.sub(r"[^\w\s]", "", title, flags=re.UNICODE)
        sanitized_title = re.sub(r"\s+", "_", sanitized_title.strip())
        return sanitized_title
