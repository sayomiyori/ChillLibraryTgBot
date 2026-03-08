"""
Google Cloud Vision API — распознавание обложки книги.
TEXT_DETECTION, LOGO_DETECTION, LABEL_DETECTION.
При отсутствии результата — fallback на Gemini с изображением.
"""
import base64
import json
import logging
import re
from typing import Optional

import aiohttp

from config import GOOGLE_API_KEY, GOOGLE_VISION_KEY

logger = logging.getLogger(__name__)
VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


def _vision_key() -> str:
    return GOOGLE_VISION_KEY or GOOGLE_API_KEY


async def get_text_from_image(image_bytes: bytes) -> Optional[str]:
    """Распознать текст на изображении (OCR)."""
    key = _vision_key()
    if not key or not image_bytes:
        return None
    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                "features": [
                    {"type": "TEXT_DETECTION", "maxResults": 10},
                    {"type": "LOGO_DETECTION", "maxResults": 5},
                    {"type": "LABEL_DETECTION", "maxResults": 10},
                ],
            }
        ]
    }
    url = f"{VISION_URL}?key={key}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception as e:
        logger.debug("Vision API: %s", e)
        return None
    responses = data.get("responses") or []
    if not responses:
        return None
    first = responses[0]
    if "error" in first:
        return None
    full = first.get("fullTextAnnotation")
    if full and isinstance(full, dict):
        return (full.get("text") or "").strip() or None
    anns = first.get("textAnnotations") or []
    if anns and isinstance(anns[0], dict):
        return (anns[0].get("description") or "").strip() or None
    return None


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


async def recognize_cover(photo_bytes: bytes) -> Optional[dict]:
    """
    1) Vision API → текст с обложки.
    2) Если нет результата → Gemini с фото (JSON: title, author).
    Возвращает {"title": ..., "author": ...} или None.
    """
    text = await get_text_from_image(photo_bytes)
    if text:
        parsed = _parse_title_author_from_text(text)
        if parsed:
            return parsed
    from services.gemini import get_book_from_cover_image
    return await get_book_from_cover_image(photo_bytes)
