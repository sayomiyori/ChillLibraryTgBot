"""
Open Library API (бесплатно, без ключа).
GET https://openlibrary.org/search.json?q={query}&limit=5
"""
import logging
from typing import Optional

import aiohttp

from services.models import BookInfo

logger = logging.getLogger(__name__)
URL = "https://openlibrary.org/search.json"


async def search_open_library(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 5,
) -> list[BookInfo]:
    if not query or not query.strip():
        return []
    params = {"q": query.strip(), "limit": min(limit, 20)}
    try:
        async with session.get(URL, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception as e:
        logger.debug("Open Library: %s", e)
        return []
    docs = data.get("docs") or []
    result = []
    for doc in docs:
        title = doc.get("title", "Без названия")
        author_list = doc.get("author_name")
        if isinstance(author_list, list):
            author = ", ".join(str(a) for a in author_list[:3])
        else:
            author = str(author_list or "Неизвестный автор")
        year = 0
        fp = doc.get("first_publish_year")
        if fp is not None:
            try:
                year = int(fp)
            except (TypeError, ValueError):
                pass
        rating = doc.get("ratings_average")
        if rating is not None:
            try:
                rating = float(rating)
            except (TypeError, ValueError):
                rating = 0.0
        else:
            rating = 0.0
        cover_id = doc.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""
        key = doc.get("key", "")
        olid = key.replace("/works/", "").replace("/books/", "") if key else ""
        result.append(
            BookInfo(
                id=olid or None,
                title=title,
                author=author,
                description="",
                rating=rating,
                cover_url=cover_url,
                categories=[],
                year=year,
                preview_link=None,
            )
        )
    return result
