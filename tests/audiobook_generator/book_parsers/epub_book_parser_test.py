import unittest
from unittest.mock import MagicMock

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
        self.assertEqual(parser._sanitize_title("   "), "The_Life_and_Adventures_of_Robinson_Crusoe")
        self.assertEqual(len(parser.get_chapters("   ")), 24)

    def test_unsupported_file_format(self):
        # Set up a config mock with an unsupported file extension
        config = MagicMock(input_file='book.unsupported')

        # Assert that NotImplementedError is raised for unsupported formats
        with self.assertRaises(NotImplementedError):
            get_book_parser(config)


if __name__ == '__main__':
    unittest.main()
