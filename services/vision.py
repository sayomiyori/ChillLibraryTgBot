"""Распознавание обложки книги: chrome-lens-py (OCR) → Groq (извлечение title/author).

1) OCR через chrome-lens-py.
2) Извлечение структурированных данных через Groq (title, author, confidence).
3) confidence < 0.5 → None (хендлер попросит ввести вручную).
4) При отсутствии OCR/ключа — fallback на Gemini по изображению.
"""
import json
import logging
import re
import tempfile
from typing import Any, Optional

try:
    from chrome_lens_py import LensAPI
    _LENS_AVAILABLE = True
except ImportError:
    LensAPI = None  # type: ignore[misc, assignment]
    _LENS_AVAILABLE = False

logger = logging.getLogger(__name__)
CONFIDENCE_THRESHOLD = 0.5


async def _get_text_from_image(image_bytes: bytes) -> str:
    """Распознать текст на изображении (OCR) через chrome-lens-py.

    Возвращает распознанный текст или пустую строку при ошибке/отсутствии пакета.
    """
    if not image_bytes:
        return ""
    if not _LENS_AVAILABLE:
        logger.debug("chrome_lens_py не установлен, OCR по обложке пропущен")
        return ""

    tmp_path = None
    try:
        # На Windows NamedTemporaryFile с delete=True держит открытый дескриптор
        # и внешняя библиотека не может открыть файл повторно → PermissionError.
        # Поэтому создаём файл с delete=False, закрываем, а потом удаляем вручную.
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        try:
            tmp.write(image_bytes)
            tmp.flush()
            tmp_path = tmp.name
        finally:
            tmp.close()

        api = LensAPI()
        result = await api.process_image(
            image_path=tmp_path,
            output_format="full_text",
        )

        text = (result.get("ocr_text") or "").strip()
        return text
    except Exception:
        logger.exception("Failed to perform OCR with chrome-lens-py")
        return ""
    finally:
        if tmp_path:
            try:
                import os

                os.remove(tmp_path)
            except OSError:
                # Не критично, файл в %TEMP% со временем удалится системой.
                pass


def _parse_title_author_from_text(text: str) -> Optional[dict]:
    """Из текста обложки вытащить название и автора (эвристика)."""
    if not text or len(text.strip()) < 2:
        return None
    lines = [l.strip() for l in text.split("\n") if l.strip()][:5]
    if not lines:
        return None
    title = lines[0]
    author = lines[1] if len(lines) > 1 else ""
    if not author and " — " in title:
        title, author = title.split(" — ", 1)
    return {"title": title.strip(), "author": author.strip() or "Неизвестный автор"}


async def _extract_book_from_ocr_groq(ocr_text: str) -> Optional[dict[str, Any]]:
    """
    Извлечь название книги и автора из сырого OCR через Groq.
    Возвращает {"title": str, "author": str, "confidence": float, "raw_ocr": str} или None.
    """
    from config import GROQ_API_KEY

    if not GROQ_API_KEY or not ocr_text or len(ocr_text.strip()) < 2:
        return None

    prompt = (
        "Извлеки название книги и автора из текста на обложке. "
        "Если название на русском — добавь оригинальное английское название книги, если знаешь. "
        "Верни ТОЛЬКО валидный JSON: "
        "{\"title\": \"...\", \"author\": \"...\", \"title_en\": \"...\", \"confidence\": 0.0-1.0}. "
        "Поле title_en оставь пустой строкой, если не знаешь оригинал. "
        "Если не можешь уверенно определить название — поставь confidence ниже 0.5. "
        f"Текст с обложки:\n{ocr_text[:2000]}"
    )

    try:
        import asyncio
        from groq import AsyncGroq

        client = AsyncGroq(api_key=GROQ_API_KEY)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100,
            ),
            timeout=10.0,
        )
        content = (response.choices[0].message.content or "").strip()
        # Вытащить JSON из ответа (могут быть markdown-блоки или пояснения)
        start = content.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        content = content[start : i + 1]
                        break
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.debug("Groq response is not valid JSON: %s", content[:200])
            return None
        title = (data.get("title") or "").strip() or "Без названия"
        author = (data.get("author") or "").strip() or "Неизвестный автор"
        title_en = (data.get("title_en") or "").strip()
        confidence = float(data.get("confidence", 0.0))
        return {
            "title": title,
            "author": author,
            "title_en": title_en,
            "confidence": max(0.0, min(1.0, confidence)),
            "raw_ocr": ocr_text,
        }
    except Exception as e:
        logger.warning("Groq extract from OCR failed: %s", e)
        return None


async def recognize_cover(photo_bytes: bytes) -> Optional[dict[str, Any]]:
    """
    1) chrome-lens-py → OCR текст.
    2) Groq → извлечь title, author, confidence.
    3) confidence < 0.5 → None.
    4) Иначе вернуть {"title", "author", "confidence", "raw_ocr"}.
    5) Если OCR пустой или Groq недоступен — fallback Gemini по фото.
    """
    text = await _get_text_from_image(photo_bytes)

    if text:
        extracted = await _extract_book_from_ocr_groq(text)
        if extracted is not None:
            if extracted["confidence"] >= CONFIDENCE_THRESHOLD:
                return extracted
            # Низкая уверенность — возвращаем None, хендлер попросит ввести вручную
            logger.info("Cover OCR confidence %.2f < %.2f, returning None", extracted["confidence"], CONFIDENCE_THRESHOLD)
            return None
        # Groq не сработал — пробуем эвристику по первой строке (без confidence)
        parsed = _parse_title_author_from_text(text)
        if parsed:
            parsed["confidence"] = 0.6  # эвристика — средняя уверенность
            parsed["raw_ocr"] = text
            parsed.setdefault("title_en", "")
            return parsed

    try:
        from services.gemini import get_book_from_cover_image
    except Exception:
        logger.exception("Failed to import Gemini fallback for cover recognition")
        return None

    try:
        gemini_result = await get_book_from_cover_image(photo_bytes)
        if gemini_result and isinstance(gemini_result, dict):
            gemini_result.setdefault("confidence", 0.7)
            gemini_result.setdefault("raw_ocr", "")
            gemini_result.setdefault("title_en", "")
            return gemini_result
        return gemini_result
    except Exception:
        logger.exception("Gemini fallback for cover recognition failed")
        return None
