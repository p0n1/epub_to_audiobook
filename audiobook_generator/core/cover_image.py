import dataclasses


@dataclasses.dataclass(frozen=True)
class CoverImage:
    data: bytes
    mime: str
