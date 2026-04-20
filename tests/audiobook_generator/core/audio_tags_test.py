import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.audiobook_generator import _ext_for_mime
from audiobook_generator.utils.utils import set_audio_tags


class TestExtForMime(unittest.TestCase):

    def test_jpeg_returns_jpg(self):
        self.assertEqual(_ext_for_mime('image/jpeg'), 'jpg')

    def test_png(self):
        self.assertEqual(_ext_for_mime('image/png'), 'png')

    def test_svg_xml(self):
        self.assertEqual(_ext_for_mime('image/svg+xml'), 'svg')

    def test_none_defaults_to_jpg(self):
        self.assertEqual(_ext_for_mime(None), 'jpg')

    def test_empty_string_defaults_to_jpg(self):
        self.assertEqual(_ext_for_mime(''), 'jpg')

    def test_unknown_mime_defaults_to_jpg(self):
        self.assertEqual(_ext_for_mime('image/x-unknown-format'), 'jpg')


class TestAudioTagsDataclass(unittest.TestCase):

    def test_defaults_no_cover(self):
        tags = AudioTags(title="Ch1", author="Author", book_title="Book", idx=1)
        self.assertIsNone(tags.cover_data)
        self.assertIsNone(tags.cover_mime)

    def test_with_cover(self):
        tags = AudioTags(
            title="Ch1", author="Author", book_title="Book", idx=1,
            cover_data=b'\xff\xd8\xff', cover_mime='image/jpeg',
        )
        self.assertEqual(tags.cover_data, b'\xff\xd8\xff')
        self.assertEqual(tags.cover_mime, 'image/jpeg')


class TestSetAudioTagsCoverEmbedding(unittest.TestCase):
    """Verify that set_audio_tags writes an APIC frame iff cover data is present."""

    def _make_tags(self, **kwargs):
        return AudioTags(title="Ch", author="Auth", book_title="Book", idx=1, **kwargs)

    @patch('audiobook_generator.utils.utils.ID3')
    def test_apic_written_when_cover_present(self, mock_id3_cls):
        mock_tags = MagicMock()
        mock_id3_cls.return_value = mock_tags

        audio_tags = self._make_tags(cover_data=b'imgbytes', cover_mime='image/jpeg')
        set_audio_tags('fake.mp3', audio_tags)

        added_frames = [call.args[0] for call in mock_tags.add.call_args_list]
        frame_types = [type(f).__name__ for f in added_frames]
        self.assertIn('APIC', frame_types)

        apic = next(f for f in added_frames if type(f).__name__ == 'APIC')
        self.assertEqual(apic.data, b'imgbytes')
        self.assertEqual(apic.mime, 'image/jpeg')
        self.assertEqual(apic.type, 3)  # front cover

    @patch('audiobook_generator.utils.utils.ID3')
    def test_apic_not_written_when_no_cover(self, mock_id3_cls):
        mock_tags = MagicMock()
        mock_id3_cls.return_value = mock_tags

        audio_tags = self._make_tags()
        set_audio_tags('fake.mp3', audio_tags)

        added_frames = [call.args[0] for call in mock_tags.add.call_args_list]
        frame_types = [type(f).__name__ for f in added_frames]
        self.assertNotIn('APIC', frame_types)

    @patch('audiobook_generator.utils.utils.ID3')
    def test_standard_tags_always_written(self, mock_id3_cls):
        mock_tags = MagicMock()
        mock_id3_cls.return_value = mock_tags

        audio_tags = self._make_tags()
        set_audio_tags('fake.mp3', audio_tags)

        added_frames = [call.args[0] for call in mock_tags.add.call_args_list]
        frame_types = [type(f).__name__ for f in added_frames]
        for expected in ('TIT2', 'TPE1', 'TALB', 'TRCK'):
            self.assertIn(expected, frame_types)


class TestAudiobookGeneratorCoverSaving(unittest.TestCase):
    """Verify that AudiobookGenerator saves the cover image to the output folder."""

    def _make_config(self, output_folder):
        config = MagicMock()
        config.output_folder = output_folder
        config.chapter_start = 1
        config.chapter_end = -1
        config.no_prompt = True
        config.preview = True  # skip actual TTS
        config.output_text = False
        config.worker_count = 1
        config.log = 'WARNING'
        config.log_file = None
        return config

    def _run_generator(self, output_folder, cover_return):
        config = self._make_config(output_folder)

        mock_parser = MagicMock()
        mock_parser.get_book_title.return_value = "Test Book"
        mock_parser.get_book_author.return_value = "Test Author"
        mock_parser.get_book_cover.return_value = cover_return
        mock_parser.get_chapters.return_value = [("Ch1", "Some text.")]

        mock_tts = MagicMock()
        mock_tts.get_break_string.return_value = ' '
        mock_tts.estimate_cost.return_value = 0.0
        mock_tts.get_output_file_extension.return_value = 'mp3'

        with patch('audiobook_generator.core.audiobook_generator.get_book_parser', return_value=mock_parser), \
             patch('audiobook_generator.core.audiobook_generator.get_tts_provider', return_value=mock_tts), \
             patch('multiprocessing.Pool') as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool.__exit__ = MagicMock(return_value=False)
            mock_pool.imap_unordered.return_value = []
            mock_pool_cls.return_value = mock_pool

            from audiobook_generator.core.audiobook_generator import AudiobookGenerator
            AudiobookGenerator(config).run()

    def test_cover_file_saved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run_generator(tmpdir, (b'pngdata', 'image/png'))

            cover_path = os.path.join(tmpdir, 'cover.png')
            self.assertTrue(os.path.exists(cover_path))
            with open(cover_path, 'rb') as f:
                self.assertEqual(f.read(), b'pngdata')

    def test_no_cover_file_when_epub_has_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run_generator(tmpdir, (None, None))

            cover_files = [f for f in os.listdir(tmpdir) if f.startswith('cover.')]
            self.assertEqual(cover_files, [])


if __name__ == '__main__':
    unittest.main()
