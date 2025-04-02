import logging
from typing import List, Tuple
import tempfile
import os
import io
from pydub import AudioSegment
from mutagen.id3._frames import TIT2, TPE1, TALB, TRCK
from mutagen.id3 import ID3, ID3NoHeaderError

logger = logging.getLogger(__name__)


def split_text(text: str, max_chars: int, language: str) -> List[str]:
    chunks = []
    current_chunk = ""

    if language.startswith("zh"):  # Chinese
        for char in text:
            if len(current_chunk) + 1 <= max_chars or is_special_char(char):
                current_chunk += char
            else:
                chunks.append(current_chunk)
                current_chunk = char

        if current_chunk:
            chunks.append(current_chunk)

    else:
        words = text.split()

        for word in words:
            if len(current_chunk) + len(word) + 1 <= max_chars:
                current_chunk += (" " if current_chunk else "") + word
            else:
                chunks.append(current_chunk)
                current_chunk = word

        if current_chunk:
            chunks.append(current_chunk)

    logger.info(f"Split text into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks, 1):
        first_100 = chunk[:100]
        last_100 = chunk[-100:] if len(chunk) > 100 else ""
        logger.info(
            f"Chunk {i}: Length={len(chunk)}, Start={first_100}..., End={last_100}"
        )

    return chunks


def set_audio_tags(output_file, audio_tags):
    try:
        try:
            tags = ID3(output_file)
            logger.debug(f"tags: {tags}")
        except ID3NoHeaderError:
            logger.debug(f"handling ID3NoHeaderError: {output_file}")
            tags = ID3()
        tags.add(TIT2(encoding=3, text=audio_tags.title))
        tags.add(TPE1(encoding=3, text=audio_tags.author))
        tags.add(TALB(encoding=3, text=audio_tags.book_title))
        tags.add(TRCK(encoding=3, text=str(audio_tags.idx)))
        tags.save(output_file)
    except Exception as e:
        logger.error(f"Error while setting audio tags: {e}, {output_file}")
        raise e  # TODO: use this raise to catch unknown errors for now


def is_special_char(char: str) -> bool:
    # Check if the character is a English letter, number or punctuation or a punctuation in Chinese, never split these characters.
    ord_char = ord(char)
    result = (
        (ord_char >= 33 and ord_char <= 126)
        or (char in "。，、？！：；“”‘’（）《》【】…—～·「」『』〈〉〖〗〔〕")
        or (char in "∶")
    )  # special unicode punctuation
    logger.debug(f"is_special_char> char={char}, ord={ord_char}, result={result}")
    return result


def save_segment_tmp(segment: io.BytesIO, output_format: str, prefix: str = None) -> str:
    """
    Save audio segment to a temporary file
    
    Args:
        segment: Audio segment (io.BytesIO)
        output_format: Audio file format
        prefix: Optional prefix for the temporary filename
        
    Returns:
        Path to the temporary file
    """
    kwargs = {"delete": False, "suffix": f".{output_format}"}
    if prefix:
        kwargs["prefix"] = f"{prefix}_"
        
    with tempfile.NamedTemporaryFile(**kwargs) as tmp_file:
        segment.seek(0)
        tmp_file.write(segment.read())
        logger.debug(f"Audio segment written to temporary file: {tmp_file.name}")
        return tmp_file.name


def pydub_merge_audio_segments(tmp_files: List[str], output_file: str, output_format: str) -> None:
    """
    Merge multiple audio segments into one and set audio tags
    
    Args:
        tmp_files: List of temporary file paths
        output_file: Path to the final output file
        output_format: Audio file format
    """
    if not tmp_files:
        logger.warning("No temporary files to merge")
        return
        
    combined = AudioSegment.empty()
    for tmp_file in tmp_files:
        logger.debug(f"Loading chunk from temporary file: {tmp_file}")
        segment = AudioSegment.from_file(tmp_file)
        combined += segment
        
    # Export to final output file
    logger.debug(f"Exporting to final output file: {output_file}")
    combined.export(output_file, format=output_format)
    logger.debug(f"Final output file exported: {output_file}")

    # Delete the temporary files
    for tmp_file in tmp_files:
        os.remove(tmp_file)
    logger.debug(f"Temporary files deleted: {tmp_files}")


def direct_merge_audio_segments(audio_segments: List[io.BytesIO], output_file: str) -> None:
    """
    Directly write multiple audio segments into one file without using pydub
    
    Args:
        audio_segments: List of audio segments in memory
        output_file: Path to the final output file
    """
    if not audio_segments:
        logger.warning("No audio segments to write")
        return
        
    logger.debug(f"Writing audio segments directly to file: {output_file}")
    with open(output_file, "wb") as outfile:
        for segment in audio_segments:
            segment.seek(0)
            outfile.write(segment.read())
    logger.debug(f"Direct writing completed: {output_file}")


def merge_audio_segments(audio_segments: List[io.BytesIO], output_file: str, output_format: str, 
                          chunk_ids: List[str], use_pydub_merge: bool) -> None:
    """
    Merge audio segments using either pydub or direct write method based on configuration
    
    Args:
        audio_segments: List of audio segments (BytesIO objects)
        output_file: Path to the final output file
        output_format: Audio file format
        chunk_ids: List of IDs for each audio chunk
        use_pydub_merge: Whether to use pydub for merging (True) or direct write (False)
    """
    if use_pydub_merge:
        logger.info(f"Using pydub to merge audio segments: {chunk_ids}")
        tmp_files = []
        for i, segment in enumerate(audio_segments):
            tmp_file_path = save_segment_tmp(segment, output_format, chunk_ids[i])
            tmp_files.append(tmp_file_path)

        # Merge all audio chunks with pydub and create the final output file
        pydub_merge_audio_segments(tmp_files, output_file, output_format)
    else:
        logger.info(f"Using direct write to merge audio segments: {chunk_ids}")
        # Direct write audio segments to output file
        direct_merge_audio_segments(audio_segments, output_file)