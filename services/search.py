"""
Объединённый поиск книги: Google Books + Open Library параллельно.
Fuzzy-дедупликация. search_books — для обложки. search_book — по названию с intitle, RU+EN, фильтр биографий.
"""
import asyncio
import logging
from difflib import SequenceMatcher
from typing import Optional

import aiohttp

from services.models import BookInfo
from services.google_books import search_google_books
from services.open_library import search_open_library
from utils.fuzzy import is_same_book

logger = logging.getLogger(__name__)

TITLE_MATCH_RATIO = 0.6
COVER_TOP_N = 5  # топ результатов при поиске по обложке

EXCLUDED_CATEGORIES = [
    "biography", "биография", "автобиография",
    "criticism", "критика", "исследование",
    "guide", "путеводитель", "companion",
]

BAD_TITLE_MARKERS = [
    "биография", "biography", "unofficial",
    "неофициальная", "создател", "автор серии",
    "companion", "guide to", "путеводитель",
]


def is_relevant_book(book: BookInfo, query: str) -> bool:
    """Отсечь биографии, критические статьи, путеводители по произведениям."""
    title = (book.title or "").lower()
    categories = [c.lower() for c in (book.categories or []) if isinstance(c, str)]
    query_lower = (query or "").strip().lower()
    if not query_lower:
        return True
    query_words = query_lower.split()
    title_has_query = all(w in title for w in query_words if len(w) > 1)
    if not title_has_query:
        return False
    has_bad_category = any(
        exc in cat for exc in EXCLUDED_CATEGORIES for cat in categories
    )
    if has_bad_category:
        return False
    has_bad_marker = any(m in title for m in BAD_TITLE_MARKERS)
    if has_bad_marker:
        return False
    return True


def relevance_score(book: BookInfo, query: str) -> float:
    """Оценка релевантности названия запросу (0..1)."""
    title = (book.title or "").lower()
    q = (query or "").strip().lower()
    if not q or not title:
        return 0.0
    return SequenceMatcher(None, q, title).ratio()


def _ratio(a: str, b: str) -> float:
    """Схожесть строк 0..1 (difflib.SequenceMatcher)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def _merge_dedup(books: list[BookInfo], seen: list[tuple[str, str]]) -> list[BookInfo]:
    """Добавить в seen только не дубликаты, вернуть список новых книг."""
    out = []
    for book in books:
        t, a = (book.title or "").strip(), (book.author or "").strip()
        if not t:
            continue
        if any(is_same_book(t, a, st, sa, threshold=80.0) for st, sa in seen):
            continue
        seen.append((t, a))
        out.append(book)
    return out


async def _fetch_books(session: aiohttp.ClientSession, search_query: str) -> list[BookInfo]:
    """Один запрос: Google Books + Open Library, объединение без дублей."""
    gb_list, ol_list = await asyncio.gather(
        search_google_books(session, search_query, max_results=10),
        search_open_library(session, search_query, limit=10),
    )
    seen: list[tuple[str, str]] = []
    return _merge_dedup(gb_list + ol_list, seen)


async def search_books(
    session: aiohttp.ClientSession,
    query: str,
    title: str = "",
    author: str = "",
    title_en: str = "",
) -> list[dict]:
    """
    Поиск книг для сценария обложки. При title_en — два параллельных запроса (EN и RU),
    объединение без дублей, сначала результаты по английскому запросу, затем по русскому. Топ-5.
    """
    query = (query or "").strip()
    title = (title or "").strip()
    author = (author or "").strip()
    title_en = (title_en or "").strip()
    if not query and not title:
        return []

    if title_en:
        # Два параллельных запроса: по английскому и по оригинальному (русскому) тексту
        query_en = f"{title_en} {author}".strip()
        query_ru = f"{title} {author}".strip()
        list_en, list_ru = await asyncio.gather(
            _fetch_books(session, query_en),
            _fetch_books(session, query_ru),
        )
        seen: list[tuple[str, str]] = []
        merged: list[BookInfo] = _merge_dedup(list_en, seen)
        for book in list_ru:
            t, a = (book.title or "").strip(), (book.author or "").strip()
            if not t or any(is_same_book(t, a, st, sa, threshold=80.0) for st, sa in seen):
                continue
            seen.append((t, a))
            merged.append(book)
        # Скор по совпадению с title или title_en
        scored: list[tuple[float, BookInfo]] = []
        for book in merged:
            t = (book.title or "").strip()
            sc = max(_ratio(title, t), _ratio(title_en, t))
            author_sc = _ratio(author, (book.author or "")) if author else 1.0
            sc = (sc + author_sc) / 2.0 if author else sc
            scored.append((sc, book))
        scored.sort(key=lambda x: -x[0])
        top = scored[:COVER_TOP_N]
    else:
        search_query = query or f"{title} {author}".strip()
        merged = await _fetch_books(session, search_query)
        if not merged:
            return []
        if title:
            scored = []
            for book in merged:
                t, a = (book.title or "").strip(), (book.author or "").strip()
                title_score = _ratio(title, t)
                author_score = _ratio(author, a) if author else 1.0
                score = (title_score + author_score) / 2.0 if author else title_score
                scored.append((score, book))
            scored.sort(key=lambda x: -x[0])
            above = [s for s, b in scored if _ratio(title, (b.title or "")) >= TITLE_MATCH_RATIO]
            if not above and author:
                merged = await _fetch_books(session, title)
                scored = [(_ratio(title, (b.title or "")), b) for b in merged]
                scored.sort(key=lambda x: -x[0])
            top = scored[:COVER_TOP_N]
        else:
            top = [(1.0, b) for b in merged[:COVER_TOP_N]]

    result = []
    for score, book in top:
        d = book.to_dict()
        d["_score"] = round(score, 2)
        result.append(d)
    return result


async def search_book(session: aiohttp.ClientSession, query: str) -> tuple[Optional[BookInfo], list[BookInfo]]:
    """
    Поиск по названию: intitle в Google Books, параллельно EN + RU, фильтр биографий/критики.
    Объединяем с Open Library, дедупликация, сортировка по релевантности.
    Возвращаем (лучшая книга, до 3 похожих).
    """
    if not query or len(query.strip()) < 2:
        return None, []
    q = query.strip()
    # Порядок языков: латиница → EN первым, кириллица → RU первым
    has_latin = any(c.isascii() and c.isalpha() for c in q)
    if has_latin:
        first_lang, second_lang = "en", "ru"
    else:
        first_lang, second_lang = "ru", "en"

    gb_first = search_google_books(session, q, max_results=10, lang=first_lang, use_intitle=True)
    gb_second = search_google_books(session, q, max_results=10, lang=second_lang, use_intitle=True)
    ol_task = search_open_library(session, q, limit=5)
    gb_first_list, gb_second_list, ol_list = await asyncio.gather(gb_first, gb_second, ol_task)

    seen: list[tuple[str, str]] = []
    merged: list[BookInfo] = []
    for book in gb_first_list + gb_second_list + ol_list:
        t, a = (book.title or "").strip(), (book.author or "").strip()
        if not t:
            continue
        if any(is_same_book(t, a, st, sa, threshold=80.0) for st, sa in seen):
            continue
        seen.append((t, a))
        merged.append(book)

    if not merged:
        return None, []

    filtered = [b for b in merged if is_relevant_book(b, q)]
    if not filtered:
        filtered = merged
    sorted_by_score = sorted(filtered, key=lambda b: relevance_score(b, q), reverse=True)
    top = sorted_by_score[:4]
    if not top:
        return None, []
    best = top[0]
    similar = top[1:4]
    # Если лучший результат сомнительный (низкое совпадение с запросом) — отдать топ-3 на выбор
    if relevance_score(best, q) < 0.5 and len(top) > 1:
        return None, top[:3]
    return best, similar
