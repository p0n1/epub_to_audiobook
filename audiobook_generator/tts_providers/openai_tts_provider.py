import io
import logging
import math
import tempfile
import os
from pydub import AudioSegment

from openai import OpenAI

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.utils.utils import split_text, set_audio_tags, merge_audio_segments, split_mixed_language_text
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from sentencex import segment


logger = logging.getLogger(__name__)


def get_openai_supported_output_formats():
    return ["mp3", "aac", "flac", "opus", "wav"]

def get_openai_supported_voices():
    return ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"]

def get_openai_supported_models():
    return ["gpt-4o-mini-tts", "tts-1", "tts-1-hd"]

def get_openai_instructions_example():
    return """Voice Affect: Calm, composed, and reassuring. Competent and in control, instilling trust.
Tone: Sincere, empathetic, with genuine concern for the customer and understanding of the situation.
Pacing: Slower during the apology to allow for clarity and processing. Faster when offering solutions to signal action and resolution.
Emotions: Calm reassurance, empathy, and gratitude.
Pronunciation: Clear, precise: Ensures clarity, especially with key details. Focus on key words like 'refund' and 'patience.' 
Pauses: Before and after the apology to give space for processing the apology."""

def get_price(model):
    # https://platform.openai.com/docs/pricing#transcription-and-speech-generation
    if model == "tts-1": # $15 per 1 mil chars
        return 0.015
    elif model == "tts-1-hd": # $30 per 1 mil chars
        return 0.03
    elif model == "gpt-4o-mini-tts": # $12 per 1 mil tokens (not chars, as 1 token is ~4 chars)
        return 0.003 # TODO: this could be very wrong for Chinese. Not sure how openai calculates the audio token count.
    else:
        logger.warning(f"OpenAI: Unsupported model name: {model}, unable to retrieve the price")
        return 0.0


class OpenAITTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.model_name = config.model_name or "gpt-4o-mini-tts" # default to this model as it's the cheapest
        config.voice_name = config.voice_name or "alloy"
        config.speed = config.speed or 1.0
        config.instructions = config.instructions or None
        config.output_format = config.output_format or "mp3"
        
        # Secondary voice for English text in mixed Chinese-English content
        config.english_voice_name = getattr(config, 'english_voice_name', None) or "alloy"

        self.price = get_price(config.model_name)
        super().__init__(config)

        self.client = OpenAI(max_retries=4)  # User should set OPENAI_API_KEY environment variable

    def __str__(self) -> str:
        return super().__str__()

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        max_chars = 1800
        break_marker = self.get_break_string().strip()  # "@PBRK#"
        sentence_interval = int(getattr(self.config, 'sentence_interval', 0) or 0)
        paragraph_interval = int(getattr(self.config, 'paragraph_interval', 1250) or 1250)

        has_english_voice = (self.config.english_voice_name and
                            self.config.english_voice_name != self.config.voice_name and
                            self._has_mixed_languages(text))

        if has_english_voice:
            logger.info(f"Using dual-voice mode: primary={self.config.voice_name}, english={self.config.english_voice_name}")

        # Build chunk list: (text, voice, break_type_before)
        # break_type_before: None | 'sentence' | 'paragraph'
        chunks = self._build_chunks(text, max_chars, break_marker, sentence_interval, has_english_voice)

        logger.info(f"Total chunks: {len(chunks)} (sentence_interval={sentence_interval}ms, paragraph_interval={paragraph_interval}ms)")

        audio_segments = []
        chunk_ids = []

        # Pre-generate silence segments
        silence_sentence = self._generate_silence(sentence_interval) if sentence_interval > 0 else None
        silence_paragraph = self._generate_silence(paragraph_interval) if paragraph_interval > 0 else None

        for i, (chunk, voice, break_type) in enumerate(chunks, 1):
            # Insert silence before chunk based on break type
            if break_type == 'paragraph' and silence_paragraph:
                sid = f"chapter-{audio_tags.idx}_{audio_tags.title}_silence_p{i}"
                audio_segments.append(silence_paragraph)
                chunk_ids.append(sid)
            elif break_type == 'sentence' and silence_sentence:
                sid = f"chapter-{audio_tags.idx}_{audio_tags.title}_silence_s{i}"
                audio_segments.append(silence_sentence)
                chunk_ids.append(sid)

            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(chunks)}"
            logger.info(f"Processing {chunk_id}, length={len(chunk)}, voice={voice}")
            logger.debug(f"Processing {chunk_id}, length={len(chunk)}, voice={voice}, text=[{chunk}]")

            response = self.client.audio.speech.create(
                model=self.config.model_name,
                voice=voice,
                speed=self.config.speed,
                instructions=self.config.instructions,
                input=chunk,
                response_format=self.config.output_format,
            )

            logger.debug(f"Remote server response: status_code={response.response.status_code}, "
                         f"size={len(response.content)} bytes")

            # Validate response: a valid mp3 should be at least a few hundred bytes
            # and start with an MPEG sync word (0xFF 0xFB/0xFF 0xF3/0xFF 0xFA etc.)
            if len(response.content) < 100:
                logger.warning(
                    f"TTS response for {chunk_id} is suspiciously small ({len(response.content)} bytes), "
                    f"text=[{chunk[:50]}...]. Skipping this chunk."
                )
                continue

            audio_segments.append(io.BytesIO(response.content))
            chunk_ids.append(chunk_id)

        merge_audio_segments(audio_segments, output_file, self.config.output_format, chunk_ids, self.config.use_pydub_merge)
        set_audio_tags(output_file, audio_tags)

    def _build_chunks(self, text: str, max_chars: int, paragraph_marker: str,
                      sentence_interval: int, has_english_voice: bool):
        """
        Build a flat list of TTS chunks from text.
        Hierarchy: paragraph → sentence → language segment → max_chars split.
        Each chunk is (text, voice, break_type_before).

        To avoid excessive TTS API calls, consecutive same-voice sentences are
        batched into chunks up to max_chars. Silence is inserted between paragraphs
        and between consecutive batches of different voices.
        """
        english_voice = self.config.english_voice_name
        primary_voice = self.config.voice_name
        language = self.config.language
        min_lang_switch_chars = 10

        chunks = []
        paragraphs = text.split(paragraph_marker)

        for p_idx, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            first_in_paragraph = (p_idx > 0)

            # Level 2: split each paragraph into sentences (only if sentence_interval > 0)
            if sentence_interval > 0:
                sentences = list(segment(language, para))
            else:
                sentences = [para]

            # Build per-sentence language segments
            sentence_segments = []  # list of (text, voice, is_first_in_paragraph, is_first_in_sentence)
            for s_idx, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if has_english_voice:
                    lang_segments = split_mixed_language_text(sentence)
                    lang_segments = self._merge_short_segments(lang_segments, min_lang_switch_chars)
                else:
                    lang_segments = [(sentence, 'zh')]

                for seg_text, lang in lang_segments:
                    if not seg_text.strip():
                        continue
                    voice = english_voice if lang == 'en' else primary_voice
                    sentence_segments.append((
                        seg_text, voice,
                        first_in_paragraph and s_idx == 0 and len(sentence_segments) == 0,
                        s_idx > 0,
                    ))

            # Batch consecutive same-voice segments into max_chars chunks
            current_batch = ""
            current_voice = None
            batch_break_type = None

            for seg_text, voice, is_first_para, is_first_sent in sentence_segments:
                if current_voice is None:
                    # Start first batch
                    current_batch = seg_text
                    current_voice = voice
                    if is_first_para:
                        batch_break_type = 'paragraph'
                    elif is_first_sent and sentence_interval > 0:
                        batch_break_type = 'sentence'
                    else:
                        batch_break_type = None
                elif voice == current_voice and len(current_batch) + len(seg_text) + 1 <= max_chars:
                    # Same voice, fits in batch → append
                    current_batch += seg_text
                else:
                    # Different voice or batch full → flush and start new
                    if len(current_batch) > max_chars:
                        sub_chunks = split_text(current_batch, max_chars, language)
                        for j, sub in enumerate(sub_chunks):
                            chunks.append((sub, current_voice, batch_break_type if j == 0 else None))
                    else:
                        chunks.append((current_batch, current_voice, batch_break_type))
                    current_batch = seg_text
                    current_voice = voice
                    if is_first_para:
                        batch_break_type = 'paragraph'
                    elif is_first_sent and sentence_interval > 0:
                        batch_break_type = 'sentence'
                    else:
                        batch_break_type = None

            # Flush last batch in paragraph
            if current_batch.strip():
                if len(current_batch) > max_chars:
                    # Split oversized batch into max_chars sub-chunks
                    sub_chunks = split_text(current_batch, max_chars, language)
                    for j, sub in enumerate(sub_chunks):
                        chunks.append((sub, current_voice, batch_break_type if j == 0 else None))
                else:
                    chunks.append((current_batch, current_voice, batch_break_type))

        # Post-processing: merge very short chunks (<5 chars) into the previous chunk
        if len(chunks) > 1:
            merged = [chunks[0]]
            for chunk_text, voice, break_type in chunks[1:]:
                if len(chunk_text.strip()) < 5 and merged:
                    prev_text, prev_voice, prev_break = merged[-1]
                    merged[-1] = (prev_text + chunk_text, prev_voice, prev_break)
                else:
                    merged.append((chunk_text, voice, break_type))
            chunks = merged

        logger.debug(f"Built {len(chunks)} chunks")
        for i, (c, v, bt) in enumerate(chunks):
            logger.debug(f"  [{i+1}] voice={v}, break={bt}, len={len(c)}, preview={c[:50]}")

        return chunks

    @staticmethod
    def _merge_short_segments(lang_segments, min_chars):
        """
        Re-merge foreign-language segments shorter than min_chars into adjacent
        primary-language segments. This prevents excessive voice switching for
        short inline English words (names, abbreviations) in Chinese text.
        """
        if len(lang_segments) <= 1:
            return lang_segments

        # Find the dominant language (primary)
        lang_counts = {}
        for _, lang in lang_segments:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        primary_lang = max(lang_counts, key=lang_counts.get)

        result = []
        for seg_text, lang in lang_segments:
            if lang != primary_lang and len(seg_text.strip()) < min_chars:
                # Short foreign segment - merge into previous or next primary segment
                if result:
                    prev_text, prev_lang = result[-1]
                    result[-1] = (prev_text + seg_text, prev_lang)
                else:
                    # No previous segment, prepend to next (will be handled in loop)
                    result.append((seg_text, primary_lang))
            else:
                if result and result[-1][1] == lang:
                    # Same language as previous, merge
                    prev_text, prev_lang = result[-1]
                    result[-1] = (prev_text + seg_text, prev_lang)
                else:
                    result.append((seg_text, lang))

        # Final pass: merge consecutive same-language segments
        if len(result) <= 1:
            return result
        final = [result[0]]
        for seg_text, lang in result[1:]:
            prev_text, prev_lang = final[-1]
            if prev_lang == lang:
                final[-1] = (prev_text + seg_text, prev_lang)
            else:
                final.append((seg_text, lang))

        return final

    def _generate_silence(self, duration_ms: int):
        """Generate a silent audio segment of the specified duration."""
        if duration_ms <= 0:
            return None
        try:
            silence = AudioSegment.silent(duration=duration_ms)
            buf = io.BytesIO()
            fmt = self.config.output_format or "mp3"
            silence.export(buf, format=fmt)
            buf.seek(0)
            return buf
        except Exception as e:
            logger.warning(f"Could not generate silence segment: {e}")
            return None

    def _has_mixed_languages(self, text: str) -> bool:
        """Check if text contains both Chinese and English characters."""
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
        has_english = any(char.isalpha() and char.isascii() for char in text)
        return has_chinese and has_english

    def get_break_string(self):
        return " @PBRK# "

    def get_output_file_extension(self):
        return self.config.output_format

    def validate_config(self):
        if self.config.output_format not in get_openai_supported_output_formats():
            raise ValueError(f"OpenAI: Unsupported output format: {self.config.output_format}")
        if self.config.speed < 0.25 or self.config.speed > 4.0:
            raise ValueError(f"OpenAI: Unsupported speed: {self.config.speed}")
        if self.config.instructions and len(self.config.instructions) > 0 and self.config.model_name != "gpt-4o-mini-tts":
            raise ValueError(f"OpenAI: Instructions are only supported for 'gpt-4o-mini-tts' model")

    def estimate_cost(self, total_chars):
        return math.ceil(total_chars / 1000) * self.price
