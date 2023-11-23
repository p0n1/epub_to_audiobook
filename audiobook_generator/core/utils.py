import logging
from typing import List
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
            print(tags)
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