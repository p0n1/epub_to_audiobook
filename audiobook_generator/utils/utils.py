import logging
from typing import List
import tempfile
import os
import io
from pydub import AudioSegment
from mutagen.id3._frames import TIT2, TPE1, TALB, TRCK
from mutagen.id3 import ID3, ID3NoHeaderError
from typing import List
from sentencex import segment
import os

logger = logging.getLogger(__name__)


def split_text(text: str, max_chars: int, language: str) -> List[str]:
    """
    Split text into chunks, where each chunk is as close to max_chars as possible.
    
    Args:
        text: The text to split
        max_chars: The maximum number of characters per chunk
        language: The language of the text
    
    Returns:
        A list of text chunks
    """
    # Edge cases
    if not text:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    
    # Use sentencex to get all sentences
    sentences = list(segment(language, text))
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # Add a space between sentences if current_chunk is not empty
        space = " " if current_chunk else ""
        # Check if adding the sentence would exceed max_chars
        if len(current_chunk) + len(space) + len(sentence) <= max_chars:
            current_chunk += space + sentence
        # If the sentence itself is longer than max_chars, split it
        elif len(sentence) > max_chars:
            # Add the current chunk if it's not empty
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            # Split the long sentence
            sentence_chunks = split_long_sentence(sentence, max_chars)
            
            # Add all chunks except the last one
            chunks.extend(sentence_chunks[:-1])
            
            # Start a new chunk with the last sentence chunk
            current_chunk = sentence_chunks[-1]
        # Otherwise, start a new chunk with this sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    # For DEBUG only
    # # Assert that no chunk exceeds max_chars
    # for i, chunk in enumerate(chunks):
    #     assert len(chunk) <= max_chars, f"Chunk {i} length {len(chunk)} exceeds max_chars {max_chars}"
    
    # # Assert that no content is lost (loose check)
    # original_sans_whitespace = ''.join(c for c in text if not c.isspace())
    # chunks_sans_whitespace = ''.join(c for c in ''.join(chunks) if not c.isspace())
    
    # # The lengths should be the same
    # assert len(chunks_sans_whitespace) == len(original_sans_whitespace), "Content might be lost during splitting"
    
    return chunks

def split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    """
    Split a long sentence into smaller parts based on punctuation and spaces.
    
    Args:
        sentence: The sentence to split
        max_chars: The maximum number of characters per part
    
    Returns:
        A list of sentence parts
    """
    # If max_chars is extremely small, split by character
    if max_chars < 5:
        return [sentence[i:i+max_chars] for i in range(0, len(sentence), max_chars)]
    
    # Define punctuation marks in order of priority
    punctuations = [
        '。', '！', '？',  # Chinese end-of-sentence
        '. ', '! ', '? ',  # English end-of-sentence with space
        '；', ';',  # Semicolons
        '，', ',',  # Commas
        '：', ':',  # Colons
        '）', ')', ']', '】', '}', '」', '』',  # Closing parentheses and brackets
        '、',  # Chinese enumeration comma
        '—', '-', '–',  # Dashes
        ' ',  # Spaces as last resort
    ]
    
    parts = []
    remaining = sentence
    
    while remaining:
        if len(remaining) <= max_chars:
            parts.append(remaining)
            break
        
        # Try to find the best split point based on punctuation marks
        best_split_idx = -1
        
        for punctuation in punctuations:
            # Find the rightmost occurrence of the punctuation within max_chars
            split_idx = remaining[:max_chars].rfind(punctuation)
            
            if split_idx != -1:
                # For punctuation marks that are not spaces, include them in the current chunk
                if punctuation != ' ':
                    split_idx += len(punctuation)
                else:
                    # For spaces, exclude them from both chunks
                    split_idx += 1
                
                best_split_idx = split_idx
                break
        
        # If no punctuation is found, split at max_chars
        if best_split_idx == -1:
            best_split_idx = max_chars
        
        parts.append(remaining[:best_split_idx])
        remaining = remaining[best_split_idx:]
    
    return parts


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