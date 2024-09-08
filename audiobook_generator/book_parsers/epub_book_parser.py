import logging
import re
from typing import List

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from audiobook_generator.book_parsers.base_book_parser import BaseBookParser
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.book_parsers import ast

logger = logging.getLogger(__name__)


def _split_by_break(item: ast.Text) -> List[ast.Item]:
    parts = item.text.split("\n")
    return [elem for x in parts for elem in (ast.Text(x + " "), ast.Break()) if x][:-1]


def _merge_item(item: ast.Item, new_items: List[ast.Item]):
    if isinstance(item, ast.Break):
        if new_items and isinstance(new_items[-1], ast.Break):
            return
        else:
            # add break
            new_items.append(item)
    elif isinstance(item, ast.Text):
        if new_items and isinstance(new_items[-1], ast.Text):
            new_items[-1]._text += item.text
        else:
            # add new text
            new_items.append(item)
    elif isinstance(item, ast.Items):
        item.items = _split_and_merge(item.items)
        new_items.append(item)
    else:
        new_items.append(item)


def _split_and_merge(items: List[ast.Item]) -> List[ast.Item]:
    # split text by breaks
    new_items = []
    for item in items:
        if isinstance(item, ast.Text):
            new_items += _split_by_break(item)
        else:
            new_items.append(item)

    # merge items together
    items = []
    for item in new_items:
        _merge_item(item, items)

    return items


def _parse(soup: BeautifulSoup) -> List[ast.Item]:
    items = []
    for item in soup:
        if isinstance(item, str):
            items.append(ast.Text(_text=item))
        elif item.name == "blockquote":
            items.append(ast.Quote(items=_parse(item)))
        else:
            items += _parse(item)
    return items


class EpubBookParser(BaseBookParser):
    def __init__(self, config: GeneralConfig):
        super().__init__(config)
        self.book = epub.read_epub(self.config.input_file, {"ignore_ncx": True})

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

    def get_chapters(self, break_string) -> List[ast.Chapter]:
        chapters = []
        search_and_replaces = []#self.get_search_and_replaces()
        for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            soup = BeautifulSoup(content, "lxml-xml")
            raw = _split_and_merge(_parse(soup))

            # Get proper chapter title
            if self.config.title_mode == "auto":
                title = ""
                title_levels = ['title', 'h1', 'h2', 'h3']
                for level in title_levels:
                    if soup.find(level):
                        title = soup.find(level).text
                        break
                if title == "" or re.match(r'^\d{1,3}$',title) is not None:
                    title = soup.get_text(strip=True)[:60]
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
                title = soup.get_text(strip=True)[:60]
            else:
                raise ValueError("Unsupported title_mode")
            logger.debug(f"Raw title: <{title}>")
            title = self._sanitize_title(title, break_string)
            logger.debug(f"Sanitized title: <{title}>")

            chapters.append(ast.Chapter(title=title, items=raw))
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
