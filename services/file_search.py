"""
Поиск ссылки на файл книги: рабочие источники по форматам, верификация 8KB, кэш.
Алгоритм: параллельный поиск по источникам формата → fallback Google CSE → верификация.
"""
import asyncio
import logging
import time
from typing import Optional

import aiohttp

from config import CONNECT_TIMEOUT, FILE_CHUNK_VERIFY, READ_TIMEOUT
from services.file_sources import (
    BROWSER_HEADERS,
    SAFE_SOURCES,
    _query_ru,
    _query_en,
    google_fallback_search,
)
from services.verifier import verify_chunk
from utils.cache import get_cached_link, set_cached_link

logger = logging.getLogger(__name__)

async def _fetch_first_chunk(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    try:
        timeout = aiohttp.ClientTimeout(connect=CONNECT_TIMEOUT, total=READ_TIMEOUT + 1)
        headers = {**BROWSER_HEADERS, "Range": f"bytes=0-{FILE_CHUNK_VERIFY - 1}"}
        async with session.get(
            url,
            allow_redirects=True,
            headers=headers,
            timeout=timeout,
        ) as resp:
            if resp.status not in (200, 206):
                return None
            return await resp.content.read(FILE_CHUNK_VERIFY)
    except Exception as e:
        logger.debug("Fetch chunk %s: %s", url[:50], e)
        return None


async def _validate_content(
    url: str,
    title: str,
    author: str,
    fmt: str,
    session: aiohttp.ClientSession,
) -> bool:
    logger.info("[VERIFY] качаем 8KB → проверяем метаданные...")
    chunk = await _fetch_first_chunk(session, url)
    if not chunk or len(chunk) < 50:
        logger.warning("[VERIFY] ❌ не удалось прочитать начало файла")
        return False
    ok = await verify_chunk(chunk, title, author, fmt, session)
    if ok:
        logger.info("[VERIFY] ✅ содержимое совпадает (title/author)")
    else:
        logger.warning("[VERIFY] ❌ содержимое не совпадает")
    return ok


async def find_file_link(
    session: aiohttp.ClientSession,
    title: str,
    author: str,
    format: str,
) -> Optional[tuple[str, str]]:
    """
    Найти ссылку на файл: кэш → параллельный поиск по источникам формата →
    при неудаче Google CSE fallback → верификация первых 8KB.
    Возвращает (url, source_name) или None.
    """
    fmt = (format or "").strip().lower()
    if not fmt or not (title or author):
        return None

    cached = get_cached_link(title, author, fmt)
    if cached:
        logger.info("[DONE] ссылка из кэша")
        return (cached, "cache")

    start = time.perf_counter()
    query_ru = _query_ru(title, author)
    query_en = _query_en(title, author)
    from services.file_sources import search_archive_org
    sources = SAFE_SOURCES.get(fmt)
    if not sources:
        sources = [("archive.org", lambda s, q: search_archive_org(s, q, fmt.upper()))]

    async def run_source(src_name: str, src_fn, q: str) -> tuple[Optional[str], str]:
        try:
            url = await src_fn(session, q)
            return (url, src_name)
        except Exception as e:
            logger.warning("[%s] %s → ❌ %s", fmt.upper(), src_name, e)
            return (None, src_name)

    all_tasks = [
        asyncio.create_task(run_source(name, fn, query_ru)) for name, fn in sources
    ] + [
        asyncio.create_task(run_source(name, fn, query_en)) for name, fn in sources
    ]

    candidates: list[tuple[str, str]] = []
    try:
        for coro in asyncio.as_completed(all_tasks):
            try:
                url, name = await coro
                if url and url.startswith("http"):
                    candidates.append((url, name))
                    if len(candidates) >= 3:
                        break
            except Exception:
                continue
    finally:
        for t in all_tasks:
            if not t.done():
                t.cancel()

    if not candidates:
        logger.info("[%s] Прямые источники не дали результата → Google fallback", fmt.upper())
        fallback_urls = await google_fallback_search(session, title, author, fmt)
        candidates = [(u, "Google") for u in fallback_urls]

    for url, source_name in candidates:
        try:
            if await _validate_content(url, title, author, fmt, session):
                set_cached_link(title, author, fmt, url)
                elapsed = time.perf_counter() - start
                logger.info("[DONE] ссылка отдана за %.1f сек (источник: %s)", elapsed, source_name)
                return (url, source_name)
        except Exception as e:
            logger.debug("Verify %s: %s", source_name, e)
            continue

    elapsed = time.perf_counter() - start
    logger.warning("[DONE] подходящая ссылка не найдена за %.1f сек", elapsed)
    return None
