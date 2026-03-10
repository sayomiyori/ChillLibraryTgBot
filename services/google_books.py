"""
Google Books API.
GET https://www.googleapis.com/books/v1/volumes?q={query}&key={API_KEY}&langRestrict=ru&maxResults=5
"""
import asyncio
import logging
from difflib import SequenceMatcher
from typing import Optional

import aiohttp

from config import GOOGLE_API_KEY
from services.models import BookInfo
from services.genre_ru import genres_to_russian

logger = logging.getLogger(__name__)
URL = "https://www.googleapis.com/books/v1/volumes"

# Языки для мультиязычного поиска (только Google Books). RU берём из LibGen.
SEARCH_LANGUAGES = [
    ("en", "EN", "\U0001f1ec\U0001f1e7"),   # English
    ("de", "DE", "\U0001f1e9\U0001f1ea"),   # Deutsch
    ("fr", "FR", "\U0001f1eb\U0001f1f7"),   # Français
    ("es", "ES", "\U0001f1ea\U0001f1f8"),   # Español
]

MULTILANG_TIMEOUT = 5.0


def _relevance_score(book: BookInfo, query: str) -> float:
    """Оценка релевантности книги запросу (0.0–1.0)."""
    if not query:
        return 1.0
    q = query.lower().strip()
    t = (book.title or "").lower()
    return SequenceMatcher(None, q, t).ratio()


async def search_google_books(
    session: aiohttp.ClientSession,
    query: str,
    max_results: int = 5,
    lang: str = "ru",
    use_intitle: bool = False,
) -> list[BookInfo]:
    if not query or not GOOGLE_API_KEY:
        return []
    q = query.strip()
    if use_intitle:
        q = f'intitle:"{q}"'
    params = {
        "q": q,
        "key": GOOGLE_API_KEY,
        "langRestrict": lang,
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


async def _search_google_books_multilang(
    session: aiohttp.ClientSession,
    title: str,
) -> list[dict]:
    """Поиск по Google Books только EN/DE/FR/ES. Возвращает список dict с zone, flag."""
    if not title or not GOOGLE_API_KEY:
        return []
    title = title.strip()
    query = f'intitle:"{title}"'

    async def _search_one(lang_code: str) -> list[BookInfo]:
        try:
            return await asyncio.wait_for(
                search_google_books(session, query, max_results=5, lang=lang_code, use_intitle=False),
                timeout=MULTILANG_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Google Books %s: timeout", lang_code)
            return []
        except Exception as e:
            logger.warning("Google Books %s: %s", lang_code, e)
            return []

    results_per_lang = await asyncio.gather(
        *[_search_one(lang_code) for lang_code, _, _ in SEARCH_LANGUAGES],
        return_exceptions=True,
    )

    best_per_lang: list[dict] = []
    for i, raw in enumerate(results_per_lang):
        if isinstance(raw, Exception):
            continue
        results: list[BookInfo] = raw or []
        if not results:
            continue
        lang_code, zone, flag = SEARCH_LANGUAGES[i]
        scored = sorted(results, key=lambda b: _relevance_score(b, title), reverse=True)
        best = scored[0]
        d = best.to_dict()
        d["zone"] = zone
        d["flag"] = flag
        d["lang_code"] = lang_code
        if best.preview_link:
            d["preview_link"] = best.preview_link
        best_per_lang.append(d)

    seen: set[str] = set()
    unique: list[dict] = []
    for book in best_per_lang:
        key = (book.get("title") or "").lower()[:30]
        if key not in seen:
            seen.add(key)
            unique.append(book)
    return unique


async def search_books_multilang(
    session: aiohttp.ClientSession,
    title: str,
) -> list[dict]:
    """
    Мультиязычный поиск: RU из LibGen (fallback Open Library), EN/DE/FR/ES из Google Books.
    RU всегда первый в списке.
    """
    if not title:
        return []
    title = title.strip()

    from services.libgen_service import search_libgen_ru, search_open_library_ru

    google_task = _search_google_books_multilang(session, title)
    libgen_task = search_libgen_ru(session, title)

    google_results: list[dict] = []
    libgen_ru: Optional[dict] = None

    try:
        g_res, l_res = await asyncio.gather(google_task, libgen_task, return_exceptions=True)
        if not isinstance(g_res, Exception):
            google_results = g_res or []
        if not isinstance(l_res, Exception) and l_res is not None:
            libgen_ru = l_res
    except Exception as e:
        logger.warning("search_books_multilang gather: %s", e)

    final: list[dict] = []
    if libgen_ru:
        final.append(libgen_ru)
    final.extend(google_results)

    ru_found = any(b.get("zone") == "RU" for b in final)
    if not ru_found:
        try:
            ol_ru = await search_open_library_ru(session, title)
            if ol_ru:
                final.insert(0, ol_ru)
        except Exception as e:
            logger.warning("Open Library RU fallback: %s", e)

    seen = set()
    unique = []
    for book in final:
        key = (book.get("title") or "").lower()[:30]
        if key not in seen:
            seen.add(key)
            unique.append(book)
    return unique[:5]
