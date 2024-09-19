from dataclasses import dataclass
from typing import List


@dataclass
class Item:
    @property
    def text(self):
        raise NotImplementedError

    def char_count(self):
        """Returns the number of characters in the item"""
        raise NotImplementedError


@dataclass
class Items:
    items: List["Item"]

    @property
    def text(self):
        return "".join((item.text for item in self.items))

    def char_count(self):
        """Returns the number of characters in the item"""
        return sum(map(lambda x: x.char_count(), self.items))


@dataclass
class Chapter(Items):
    title: str


@dataclass
class Text(Item):
    _text: str

    @property
    def text(self):
        return self._text

    def char_count(self):
        return len(self.text)


@dataclass
class Quote(Items):
    pass


@dataclass
class Break(Item):
    @property
    def text(self):
        return ""

    def char_count(self):
        return 0
