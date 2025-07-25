import unittest
from unittest.mock import MagicMock

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.tts_providers.edge_tts_provider import CommWithPauses


def get_edge_config():
    """Helper function to create a basic EdgeTTS config for testing"""
    args = MagicMock(
        input_file='../../../examples/The_Life_and_Adventures_of_Robinson_Crusoe.epub',
        output_folder='output',
        preview=False,
        output_text=False,
        log='INFO',
        newline_mode='double',
        chapter_start=1,
        chapter_end=-1,
        remove_endnotes=False,
        tts='edge',
        language='en-US',
        voice_name='en-US-GuyNeural',
        output_format='audio-24khz-48kbitrate-mono-mp3',
        model_name='',
        break_duration='1250'
    )
    return GeneralConfig(args)


class TestEdgeTtsProvider(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures"""
        self.comm_with_pauses = CommWithPauses(
            text="Test text",
            voice_name="en-US-GuyNeural",
            break_string=" @BRK#".strip(),
            break_duration=1250,
            output_format_ext="mp3"
        )

    def test_is_meaningful_text_empty_strings(self):
        """Test that empty strings are filtered out"""
        self.assertFalse(self.comm_with_pauses._is_meaningful_text(""))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("   "))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("\t"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("\n"))

    def test_is_meaningful_text_single_letters(self):
        """Test that single letters are kept"""
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("A"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("B"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("C"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("I"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("a"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("1"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("0"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("的"))

    def test_is_meaningful_text_single_punctuation(self):
        """Test that single punctuation marks are filtered out"""
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("'"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("."))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text(","))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("!"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("?"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text(":"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text(";"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("。"))

    def test_is_meaningful_text_short_mixed_content(self):
        """Test short text with mixed content (letters + punctuation)"""
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("A."))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("B,"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("C!"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("I?"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("a:"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("1;"))

    def test_is_meaningful_text_short_punctuation_only(self):
        """Test short sequences of punctuation (should be filtered for 5 chars or less)"""
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("--"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("..."))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("!!!"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("????"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("-----"))

    def test_is_meaningful_text_longer_punctuation(self):
        """Test longer punctuation sequences (should be filtered for 6+ chars)"""
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("......"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("------"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("!!!!!!"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("???????"))

    def test_is_meaningful_text_words(self):
        """Test that regular words are always kept"""
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("Hello"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("world"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("test123"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("Hello!"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("Hello, world!"))

    def test_is_meaningful_text_whitespace_handling(self):
        """Test that whitespace is properly stripped"""
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("  A  "))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("\tHello\t"))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("\n1\n"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("  '  "))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("\t.\t"))

    def test_is_meaningful_text_more_cases(self):
        """Test more mixed cases"""
        # Exactly 5 characters - punctuation only (should be filtered)
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("'...'"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text(",,,,,"))
        
        # Exactly 5 characters - with alphanumeric (should be kept)
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("A...."))
        self.assertTrue(self.comm_with_pauses._is_meaningful_text("1,,,,"))
        
        # Exactly 6 characters - punctuation only (should be filtered)
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("''''''"))
        self.assertFalse(self.comm_with_pauses._is_meaningful_text("......"))

        self.assertTrue(self.comm_with_pauses._is_meaningful_text(".............你好世界"))

    def test_parse_text_filters_meaningless_chunks(self):
        """Test that parse_text properly filters out meaningless chunks"""
        # Create a CommWithPauses instance with text that contains meaningless chunks
        comm = CommWithPauses(
            text="Hello @BRK# ' @BRK# world @BRK# ... @BRK# A @BRK# ------ @BRK# end",
            voice_name="en-US-GuyNeural",
            break_string=" @BRK#".strip(),
            break_duration=1250,
            output_format_ext="mp3"
        )
        
        parsed = comm.parsed
        
        # Should keep: "Hello", "world", "A", "end"
        # Should filter: "'" (single punctuation), "..." (3 chars punctuation only), "------" (6 chars punctuation only)
        expected_chunks = ["Hello", "world", "A", "end"]
        self.assertEqual(parsed, expected_chunks)

    def test_parse_text_no_break_string(self):
        """Test that parse_text handles text without break strings"""
        comm = CommWithPauses(
            text="This is a test without breaks",
            voice_name="en-US-GuyNeural",
            break_string=" @BRK#".strip(),
            break_duration=1250,
            output_format_ext="mp3"
        )
        
        parsed = comm.parsed
        self.assertEqual(parsed, ["This is a test without breaks"])


if __name__ == '__main__':
    unittest.main() 