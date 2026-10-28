import dataclasses
from typing import Optional

from audiobook_generator.core.cover_image import CoverImage


@dataclasses.dataclass
class AudioTags:
    title: str       # for TIT2
    author: str      # for TPE1
    book_title: str  # for TALB
    idx: int         # for TRCK
    cover: Optional[CoverImage] = None  # for APIC
