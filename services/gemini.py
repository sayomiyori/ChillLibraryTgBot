"""Gemini API — цитата, обложка (fallback), рекомендации."""
import asyncio
import json
import logging
import re
from typing import Optional

from config import GEMINI_API_KEY, MAX_RECOMMENDATIONS

logger = logging.getLogger(__name__)

COVER_IMAGE_PROMPT = """На этой обложке книги определи:
1) Название книги
2) Автора
Ответь строго в JSON: {"title": "...", "author": "..."}"""

QUOTE_JSON_PROMPT = """Пользователь прислал цитату из книги:
"{text}"

Определи: 1. Название книги 2. Автора 3. Уверенность (0-100%)
Ответь строго в JSON:
{{"title": "...", "author": "...", "confidence": 95, "context": "краткое объяснение"}}"""

QUOTE_PROMPT = """Определи книгу по этой цитате. Верни только в таком формате:
НАЗВАНИЕ: название книги
АВТОР: имя автора
ГОД: год издания (если известен, иначе —)

Если не уверен в книге — напиши одной строкой: НЕ УВЕРЕН

Цитата:
"""


def _get_book_from_quote_sync(quote: str) -> Optional[dict]:
    """Синхронный вызов Gemini. Возвращает title, author, confidence (0-100), context."""
    if not quote or not quote.strip() or not GEMINI_API_KEY:
        logger.warning("quote: нет текста или нет GEMINI_API_KEY")
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = QUOTE_JSON_PROMPT.format(text=quote.strip())
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
        logger.info("Gemini raw response: %s", text)
        if not text or "НЕ УВЕРЕН" in text.upper():
            return None
        text_clean = re.sub(r"^```\w*\s*", "", text).strip()
        text_clean = re.sub(r"\s*```\s*$", "", text_clean).strip()
        try:
            data = json.loads(text_clean)
            title = (data.get("title") or "").strip()
            author = (data.get("author") or "").strip()
            confidence = data.get("confidence")
            if confidence is not None:
                confidence = int(confidence)
            else:
                confidence = 80
            result = {"title": title, "author": author or "Неизвестный автор", "confidence": confidence, "context": data.get("context", "")}
            logger.info("Gemini result: %s", result)
            return result
        except (json.JSONDecodeError, TypeError):
            pass
        title = None
        author = None
        for line in text.split("\n"):
            line = line.strip()
            if line.upper().startswith("НАЗВАНИЕ:"):
                title = line.split(":", 1)[-1].strip()
            elif line.upper().startswith("АВТОР:"):
                author = line.split(":", 1)[-1].strip()
        if title or author:
            result = {"title": title or "", "author": author or "Неизвестный автор", "confidence": 75, "context": ""}
            logger.info("Gemini result: %s", result)
            return result
        if " — " in text:
            parts = text.split(" — ", 1)
            if len(parts) == 2:
                result = {"title": parts[0].strip(), "author": parts[1].strip(), "confidence": 70, "context": ""}
                logger.info("Gemini result: %s", result)
                return result
        return None
    except Exception as e:
        logger.warning("Gemini quote recognition failed: %s", e)
        return None


async def get_book_from_quote(quote: str) -> Optional[dict]:
    """
    По цитате вернуть название и автора книги.
    Возвращает dict с ключами title, author, confidence, context или None.
    Если confidence < 70% — вызывающий код может показать «Не уверен».
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _get_book_from_quote_sync(quote))


def _get_book_from_cover_image_sync(photo_bytes: bytes) -> Optional[dict]:
    """Gemini по фото обложки → JSON title, author."""
    if not photo_bytes or not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        image_part = {"mime_type": "image/jpeg", "data": photo_bytes}
        response = model.generate_content([image_part, COVER_IMAGE_PROMPT])
        text = (response.text or "").strip()
        if not text:
            return None
        text = re.sub(r"^```\w*\s*", "", text).strip()
        text = re.sub(r"\s*```\s*$", "", text).strip()
        data = json.loads(text)
        title = (data.get("title") or "").strip()
        author = (data.get("author") or "").strip()
        if title:
            return {"title": title, "author": author or "Неизвестный автор"}
        return None
    except Exception as e:
        logger.debug("Gemini cover image: %s", e)
        return None


async def get_book_from_cover_image(photo_bytes: bytes) -> Optional[dict]:
    """По фото обложки вернуть title, author через Gemini."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _get_book_from_cover_image_sync(photo_bytes))


SIMILAR_PROMPT = """Пользователь прочитал книгу: «{title}», автор: {author}.{genre_block}
Порекомендуй ровно {limit} похожих книг. Обязательно подбирай книги того же жанра и стиля.
Верни только список, по одной книге на строку, в формате: Название — Автор
Без нумерации, без лишнего текста, только строки вида "Название — Автор".
"""


def _get_similar_books_sync(title: str, author: str, limit: int, genre: str = "") -> list[dict]:
    """Синхронный вызов Gemini для списка похожих книг (с учётом жанра)."""
    if not title and not author or not GEMINI_API_KEY:
        return []
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        genre_block = f"\nЖанр книги: {genre}." if (genre and genre.strip()) else ""
        prompt = SIMILAR_PROMPT.format(
            title=title or "неизвестно",
            author=author or "неизвестен",
            limit=limit,
            genre_block=genre_block,
        )
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
        if not text:
            return []
        result = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Убрать нумерацию "1. " или "1) "
            line = re.sub(r"^\d+[.)]\s*", "", line).strip()
            # "Название — Автор" или "Название - Автор" или "Название, Автор"
            for sep in (" — ", " - ", ", "):
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        t, a = parts[0].strip(), parts[1].strip()
                        if t and a and len(result) < limit:
                            result.append({"title": t, "author": a})
                    break
        return result[:limit]
    except Exception as e:
        logger.warning("Gemini similar books failed: %s", e)
        return []


async def get_similar_books(
    title: str,
    author: str,
    limit: int = MAX_RECOMMENDATIONS,
    genre: Optional[str] = None,
) -> list[dict]:
    """
    Рекомендации похожих книг через Gemini (с приоритетом по жанру).
    Каждый элемент — dict с title, author.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _get_similar_books_sync(title or "", author or "", limit, genre or ""),
    )
