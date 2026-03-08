"""
Google Books API.
GET https://www.googleapis.com/books/v1/volumes?q={query}&key={API_KEY}&langRestrict=ru&maxResults=5
"""
import logging
from typing import Optional

import aiohttp

from config import GOOGLE_API_KEY
from services.models import BookInfo
from services.genre_ru import genres_to_russian

logger = logging.getLogger(__name__)
URL = "https://www.googleapis.com/books/v1/volumes"


async def search_google_books(
    session: aiohttp.ClientSession,
    query: str,
    max_results: int = 5,
) -> list[BookInfo]:
    if not query or not GOOGLE_API_KEY:
        return []
    params = {
        "q": query.strip(),
        "key": GOOGLE_API_KEY,
        "langRestrict": "ru",
        "maxResults": min(max_results, 40),
    }
    try:
        async with session.get(URL, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception as e:
        logger.debug("Google Books: %s", e)
        return []
    items = data.get("items") or []
    result = []
    for item in items:
        vol = item.get("volumeInfo") or {}
        book_id = item.get("id", "")
        title = vol.get("title", "Без названия")
        authors_list = vol.get("authors") or []
        author = ", ".join(authors_list) if authors_list else "Неизвестный автор"
        desc = (vol.get("description") or "")[:500]
        if len(vol.get("description") or "") > 500:
            desc += "…"
        image_links = vol.get("imageLinks") or {}
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
        rating = vol.get("averageRating")
        if rating is not None:
            try:
                rating = float(rating)
            except (TypeError, ValueError):
                rating = 0.0
        else:
            rating = 0.0
        categories_raw = vol.get("categories") or []
        categories = [genres_to_russian([c]).strip() or c for c in categories_raw[:5]]
        year = 0
        pub = vol.get("publishedDate") or ""
        if pub:
            try:
                year = int(pub[:4])
            except (ValueError, TypeError):
                pass
        preview = vol.get("previewLink") or ""
        result.append(
            BookInfo(
                id=book_id,
                title=title,
                author=author,
                description=desc,
                rating=rating,
                cover_url=cover_url,
                categories=categories,
                year=year,
                preview_link=preview or None,
            )
        )
    return result


async def get_book_by_id(
    session: aiohttp.ClientSession,
    book_id: str,
) -> Optional[BookInfo]:
    if not book_id or not GOOGLE_API_KEY:
        return None
    url = f"{URL}/{book_id}"
    params = {"key": GOOGLE_API_KEY, "projection": "full"}
    try:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception as e:
        logger.debug("Google Books get %s: %s", book_id, e)
        return None
    vol = data.get("volumeInfo") or {}
    authors_list = vol.get("authors") or []
    author = ", ".join(authors_list) if authors_list else "Неизвестный автор"
    desc = (vol.get("description") or "")[:500]
    if len(vol.get("description") or "") > 500:
        desc += "…"
    image_links = vol.get("imageLinks") or {}
    cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
    rating = vol.get("averageRating")
    if rating is not None:
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            rating = 0.0
    else:
        rating = 0.0
    categories_raw = vol.get("categories") or []
    categories = [genres_to_russian([c]).strip() or c for c in categories_raw[:5]]
    year = 0
    pub = vol.get("publishedDate") or ""
    if pub:
        try:
            year = int(pub[:4])
        except (ValueError, TypeError):
            pass
    return BookInfo(
        id=data.get("id", book_id),
        title=vol.get("title", "Без названия"),
        author=author,
        description=desc,
        rating=rating,
        cover_url=cover_url,
        categories=categories,
        year=year,
        preview_link=vol.get("previewLink") or None,
    )
