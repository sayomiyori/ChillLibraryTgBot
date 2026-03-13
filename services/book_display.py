"""Дополнение метаданных книг (описание, обложка) из внешних источников."""
import logging
from difflib import SequenceMatcher
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

    # 1. Пытаемся найти русское издание (описание и жанры сразу будут на русском)
    try:
        gb_results = await search_google_books(
            session,
            title,
            max_results=5,
            lang="ru",
            use_intitle=False,
        )
    except Exception as e:
        logger.debug("enrich_libgen_book Google Books: %s", e)
        return book

    # Слова-маркеры НЕ-художественной литературы — такие книги не используем
    SKIP_WORDS = {
        "биограф", "биография", "неофициальн", "путеводитель",
        "энциклопедия", "справочник", "раскраска", "комикс",
        "кулинар", "рецепт",
        "лексическ", "грамматик", "языкознание",
        "учебник", "пособие", "курс", "практикум",
        "перевод с английского", "перевод с французского",
    }

    ru_candidate = None
    if gb_results:
        base_title = title.lower()
        for cand in gb_results:
            cand_title = (cand.title or "").strip()
            cand_lower = cand_title.lower()
            # Берём только если в названии есть кириллица и нет маркеров
            # учебных пособий / биографий и т.п.
            has_cyrillic = any("\u0400" <= c <= "\u04FF" for c in cand_title)
            is_skip = any(w in cand_lower for w in SKIP_WORDS)
            if not has_cyrillic or is_skip:
                continue
            # Дополнительная защита: название должно быть похоже на libgen‑название
            score = SequenceMatcher(None, base_title, cand_lower).ratio()
            if score < 0.5:
                logger.info(
                    "enrich_libgen_book: отклонён кандидат '%s' (score=%.2f)",
                    cand_title[:60],
                    score,
                )
                continue
            ru_candidate = cand
            break

    # 2. Если русское издание не найдено — пробуем английское как fallback
    en_candidate = None
    if not ru_candidate:
        try:
            gb_en = await search_google_books(
                session,
                title,
                max_results=3,
                lang="en",
                use_intitle=False,
            )
            if gb_en:
                en_candidate = gb_en[0]
        except Exception as e:
            logger.debug("enrich_libgen_book Google Books EN: %s", e)

    gb = ru_candidate or en_candidate
    if not gb:
        return book

    book["description"] = gb.description or book.get("description") or ""
    book["cover_url"] = gb.cover_url or book.get("cover_url") or ""
    book["year"] = getattr(gb, "year", 0) or book.get("year", 0)
    book["categories"] = getattr(gb, "categories", []) or book.get("categories") or []
    book["rating"] = getattr(gb, "rating", 0.0) or book.get("rating", 0.0)
    return book
