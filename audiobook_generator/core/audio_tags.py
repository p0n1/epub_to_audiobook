import dataclasses
from typing import Optional


@dataclasses.dataclass
class AudioTags:
    title: str  # for TIT2
    author: str  # for TPE1
    book_title: str  # for TALB
    idx: int  # for TRCK
    cover_data: Optional[bytes] = None   # for APIC
    cover_mime: Optional[str] = None     # e.g. "image/jpeg"
