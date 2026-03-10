"""Дополнение метаданных книг (описание, обложка) из внешних источников."""
import logging
from typing import Any, Dict

import aiohttp

from services.google_books import search_google_books

logger = logging.getLogger(__name__)


async def enrich_libgen_book(
    session: aiohttp.ClientSession,
    book: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Дополняет LibGen-книгу описанием и обложкой из Google Books.
    Остальные поля (title, author, available_formats, source) остаются из LibGen.
    """
    if book.get("source") != "libgen":
        return book

    title = (book.get("title") or "").strip()
    author = (book.get("author") or "").strip()
    if not title:
        return book

    query = f'intitle:"{title}"'
    if author:
        query += f' inauthor:"{author}"'

    try:
        gb_results = await search_google_books(
            session,
            query,
            max_results=1,
            lang="ru",
            use_intitle=False,
        )
    except Exception as e:
        logger.debug("enrich_libgen_book Google Books: %s", e)
        return book

    if not gb_results:
        return book

    gb = gb_results[0]
    book["description"] = gb.description or book.get("description") or ""
    book["cover_url"] = gb.cover_url or book.get("cover_url") or ""
    book["year"] = getattr(gb, "year", 0) or book.get("year", 0)
    book["categories"] = getattr(gb, "categories", []) or book.get("categories") or []
    book["rating"] = getattr(gb, "rating", 0.0) or book.get("rating", 0.0)
    return book
