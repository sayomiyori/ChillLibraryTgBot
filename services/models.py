"""Модели данных: BookInfo."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class BookInfo:
    title: str
    author: str
    description: str
    rating: float
    cover_url: str
    categories: list
    year: int
    id: Optional[str] = None  # Google Books volume id или Open Library key
    preview_link: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id or "",
            "title": self.title,
            "author": self.author,
            "description": self.description,
            "rating": self.rating,
            "cover_url": self.cover_url,
            "thumbnail": self.cover_url,
            "categories": self.categories,
            "genre": ", ".join(self.categories) if self.categories else "",
            "year": self.year,
        }
