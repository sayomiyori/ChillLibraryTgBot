"""
Объединённый поиск книги: Google Books + Open Library параллельно.
Fuzzy-дедупликация, возврат лучшего результата + топ-3 похожих.
"""
import asyncio
import logging
from typing import Optional

import aiohttp

from services.models import BookInfo
from services.google_books import search_google_books
from services.open_library import search_open_library
from utils.fuzzy import is_same_book

logger = logging.getLogger(__name__)


async def search_book(session: aiohttp.ClientSession, query: str) -> tuple[Optional[BookInfo], list[BookInfo]]:
    """
    Параллельный запрос к Google Books и Open Library.
    Объединяем результаты, убираем дубликаты по fuzzy match.
    Возвращаем (лучшая книга, до 3 похожих).
    """
    if not query or len(query.strip()) < 2:
        return None, []
    q = query.strip()
    gb_task = search_google_books(session, q, max_results=5)
    ol_task = search_open_library(session, q, limit=5)
    gb_list, ol_list = await asyncio.gather(gb_task, ol_task)
    merged: list[BookInfo] = []
    seen: list[tuple[str, str]] = []
    for book in gb_list + ol_list:
        t, a = (book.title or "").strip(), (book.author or "").strip()
        if not t:
            continue
        duplicate = False
        for st, sa in seen:
            if is_same_book(t, a, st, sa, threshold=80.0):
                duplicate = True
                break
        if not duplicate:
            seen.append((t, a))
            merged.append(book)
    if not merged:
        return None, []
    best = merged[0]
    similar = merged[1:4]
    return best, similar
