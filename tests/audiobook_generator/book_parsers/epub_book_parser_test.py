import os
import tempfile
import unittest
from unittest.mock import MagicMock

from ebooklib import epub

from audiobook_generator.book_parsers.base_book_parser import get_book_parser
from audiobook_generator.book_parsers.epub_book_parser import EpubBookParser
from tests.test_utils import get_azure_config


class TestGetBookParser(unittest.TestCase):

    def test_get_epub_book_parser(self):
        # Create a config object with the path to an actual EPUB file
        config = get_azure_config()

        # Call get_book_parser and assert the correct parser is returned
        parser = get_book_parser(config)
        self.assertIsInstance(parser, EpubBookParser)
        self.assertEqual(parser.get_book_author(), "Daniel Defoe")
        self.assertEqual(parser.get_book_title(), "The Life and Adventures of Robinson Crusoe")
        self.assertEqual(parser._sanitize_title(parser.get_book_title(), " @BRK#"), "The_Life_and_Adventures_of_Robinson_Crusoe")
        self.assertEqual(len(parser.get_chapters("   ")), 23)

    def test_chapters_follow_spine_order(self):
        book = epub.EpubBook()
        book.set_identifier("spine-order")
        book.set_title("Order")
        chapter_2 = epub.EpubHtml(uid="b", file_name="b.xhtml", content="<h1>Second</h1><p>Two.</p>")
        chapter_1 = epub.EpubHtml(uid="a", file_name="z.xhtml", content="<h1>First</h1><p>One.</p>")
        # manifest order: second, first; reading order: first, second
        book.add_item(chapter_2)
        book.add_item(chapter_1)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = [chapter_1, chapter_2]

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "order.epub")
            epub.write_epub(path, book)
            config = get_azure_config()
            config.input_file = path
            config.search_and_replace_file = None
            chapters = EpubBookParser(config).get_chapters(" ")

        self.assertEqual([title for title, _ in chapters], ["First", "Second"])

    def test_unsupported_file_format(self):
        # Set up a config mock with an unsupported file extension
        config = MagicMock(input_file='book.unsupported')

        # Assert that NotImplementedError is raised for unsupported formats
        with self.assertRaises(NotImplementedError):
            get_book_parser(config)


if __name__ == '__main__':
    unittest.main()
