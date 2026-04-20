import unittest
from unittest.mock import MagicMock

import ebooklib

from audiobook_generator.book_parsers.base_book_parser import get_book_parser
from audiobook_generator.book_parsers.epub_book_parser import EpubBookParser
from audiobook_generator.core.cover_image import CoverImage
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
        self.assertEqual(len(parser.get_chapters("   ")), 24)

    def test_unsupported_file_format(self):
        # Set up a config mock with an unsupported file extension
        config = MagicMock(input_file='book.unsupported')

        # Assert that NotImplementedError is raised for unsupported formats
        with self.assertRaises(NotImplementedError):
            get_book_parser(config)


class TestGetBookCover(unittest.TestCase):

    def setUp(self):
        self.config = get_azure_config()
        self.parser = get_book_parser(self.config)

    def test_cover_extracted_from_real_epub(self):
        cover = self.parser.get_book_cover()
        self.assertIsInstance(cover, CoverImage)
        self.assertGreater(len(cover.data), 0)
        self.assertEqual(cover.mime, 'image/png')

    def test_cover_strategy_item_cover_type(self):
        """Strategy 1: item typed as ITEM_COVER."""
        mock_item = MagicMock()
        mock_item.get_content.return_value = b'cover-bytes'
        mock_item.media_type = 'image/jpeg'

        self.parser.book = MagicMock()
        self.parser.book.get_items_of_type.side_effect = lambda t: [mock_item] if t == ebooklib.ITEM_COVER else []

        cover = self.parser.get_book_cover()
        self.assertEqual(cover, CoverImage(data=b'cover-bytes', mime='image/jpeg'))

    def test_cover_strategy_item_by_id(self):
        """Strategy 2: item with id 'cover' that is an image."""
        self.parser.book = MagicMock()
        self.parser.book.get_items_of_type.return_value = []

        mock_item = MagicMock()
        mock_item.media_type = 'image/jpeg'
        mock_item.get_content.return_value = b'id-cover-bytes'
        self.parser.book.get_item_with_id.return_value = mock_item

        cover = self.parser.get_book_cover()
        self.assertEqual(cover, CoverImage(data=b'id-cover-bytes', mime='image/jpeg'))

    def test_cover_strategy_opf_metadata(self):
        """Strategy 3: OPF <meta name='cover' content='<id>'>."""
        self.parser.book = MagicMock()
        self.parser.book.get_items_of_type.return_value = []

        non_image_item = MagicMock()
        non_image_item.media_type = 'application/xhtml+xml'

        real_cover = MagicMock()
        real_cover.get_content.return_value = b'opf-cover-bytes'
        real_cover.media_type = 'image/png'

        def get_item_by_id(item_id):
            return non_image_item if item_id == 'cover' else real_cover

        self.parser.book.get_item_with_id.side_effect = get_item_by_id
        self.parser.book.get_metadata.return_value = [(None, {'content': 'cover-image-id'})]

        cover = self.parser.get_book_cover()
        self.assertEqual(cover, CoverImage(data=b'opf-cover-bytes', mime='image/png'))

    def test_cover_strategy_filename_contains_cover(self):
        """Strategy 4: first image whose filename contains 'cover'."""
        self.parser.book = MagicMock()

        def get_items_of_type(t):
            if t == ebooklib.ITEM_COVER:
                return []
            if t == ebooklib.ITEM_IMAGE:
                item = MagicMock()
                item.file_name = 'images/cover_art.jpg'
                item.get_content.return_value = b'filename-cover-bytes'
                item.media_type = 'image/jpeg'
                return [item]
            return []

        self.parser.book.get_items_of_type.side_effect = get_items_of_type
        self.parser.book.get_item_with_id.return_value = None
        self.parser.book.get_metadata.return_value = []

        cover = self.parser.get_book_cover()
        self.assertEqual(cover, CoverImage(data=b'filename-cover-bytes', mime='image/jpeg'))

    def test_cover_returns_none_when_not_found(self):
        """All strategies fail → None."""
        self.parser.book = MagicMock()
        self.parser.book.get_items_of_type.return_value = []
        self.parser.book.get_item_with_id.return_value = None
        self.parser.book.get_metadata.return_value = []

        self.assertIsNone(self.parser.get_book_cover())


if __name__ == '__main__':
    unittest.main()
