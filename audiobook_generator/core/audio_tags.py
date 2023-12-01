import dataclasses


@dataclasses.dataclass
class AudioTags:
    title: str  # for TIT2
    author: str  # for TPE1
    book_title: str  # for TALB
    idx: int  # for TRCK
