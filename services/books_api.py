"""Поиск книг через Google Books API."""
import aiohttp
from typing import Optional

from config import GOOGLE_API_KEY, MAX_SEARCH_RESULTS
from services.genre_ru import genres_to_russian

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


async def search_books(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """
    Поиск книг по названию/автору через Google Books API.
    Возвращает список словарей с полями: id, title, authors, description, thumbnail, rating.
    """
    if not query or not query.strip():
        return []

    params = {
        "q": query.strip(),
        "maxResults": min(max_results, 40),
        "key": GOOGLE_API_KEY,
        "langRestrict": "ru",  # можно убрать для поиска по всем языкам
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(GOOGLE_BOOKS_URL, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except (aiohttp.ClientError, aiohttp.ClientResponseError):
            return []

    items = data.get("items") or []
    result = []

    for item in items:
        vol = item.get("volumeInfo") or {}
        book_id = item.get("id", "")
        title = vol.get("title", "Без названия")
        authors = vol.get("authors") or []
        author = ", ".join(authors) if authors else "Неизвестный автор"
        description = (vol.get("description") or "")[:500]
        if len((vol.get("description") or "")) > 500:
            description += "…"
        image_links = vol.get("imageLinks") or {}
        thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
        rating = vol.get("averageRating")
        if rating is not None:
            try:
                rating = float(rating)
            except (TypeError, ValueError):
                rating = None

        categories = vol.get("categories") or []
        genre = genres_to_russian(categories) if categories else ""

        result.append({
            "id": book_id,
            "title": title,
            "authors": authors,
            "author": author,
            "description": description,
            "thumbnail": thumbnail,
            "rating": rating,
            "genre": genre,
        })

    return result


async def get_book_by_id(book_id: str) -> Optional[dict]:
    """Получить одну книгу по ID (например после распознавания)."""
    if not book_id or not GOOGLE_API_KEY:
        return None

    url = f"{GOOGLE_BOOKS_URL}/{book_id}"
    params = {"key": GOOGLE_API_KEY, "projection": "full"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, aiohttp.ClientResponseError):
            return None

    vol = data.get("volumeInfo") or {}
    authors = vol.get("authors") or []
    author = ", ".join(authors) if authors else "Неизвестный автор"
    description = (vol.get("description") or "")[:500]
    if len((vol.get("description") or "")) > 500:
        description += "…"
    image_links = vol.get("imageLinks") or {}
    thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
    rating = vol.get("averageRating")
    if rating is not None:
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            rating = None

    categories = vol.get("categories") or []
    genre = genres_to_russian(categories) if categories else ""

    # Ссылки на скачивание PDF/EPUB (если доступны)
    access = data.get("accessInfo") or {}
    pdf_link = (access.get("pdf") or {}).get("downloadLink") or (access.get("pdf") or {}).get("acsTokenLink")
    epub_link = (access.get("epub") or {}).get("downloadLink") or (access.get("epub") or {}).get("acsTokenLink")

    return {
        "id": data.get("id", book_id),
        "title": vol.get("title", "Без названия"),
        "authors": authors,
        "author": author,
        "description": description,
        "thumbnail": thumbnail,
        "rating": rating,
        "genre": genre,
        "download_pdf": pdf_link if isinstance(pdf_link, str) and pdf_link.startswith("http") else None,
        "download_epub": epub_link if isinstance(epub_link, str) and epub_link.startswith("http") else None,
    }
