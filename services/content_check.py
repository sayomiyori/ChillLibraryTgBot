"""
Проверка «начинки» файла: по первым байтам убеждаемся, что это именно та книга (название/автор).
Скачиваем только начало файла (до 100 KB) для скорости.
"""
import re
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/octet-stream,*/*",
}
CHUNK_SIZE = 100 * 1024  # 100 KB для проверки
ENCODINGS = ["utf-8", "utf-8-sig", "cp1251", "cp866", "koi8-r", "latin-1"]


def _normalize_for_search(s: str) -> str:
    """Нормализация для поиска: нижний регистр, только буквы и цифры."""
    if not s:
        return ""
    s = re.sub(r"[^\w\s]", " ", str(s).strip().lower())
    return re.sub(r"\s+", " ", s).strip()


def _extract_search_terms(title: str, author: str) -> list[str]:
    """Ключевые слова для проверки: значимые слова из названия и автора (не предлоги)."""
    stop = {"и", "в", "на", "с", "о", "из", "у", "к", "по", "для", "или", "а", "но", "the", "a", "an", "and", "of", "in", "to"}
    terms = []
    for part in (_normalize_for_search(title), _normalize_for_search(author)):
        for word in (part or "").split():
            if len(word) > 1 and word not in stop:
                terms.append(word)
    return terms[:10]  # не более 10 слов


async def _fetch_first_chunk(url: str) -> Optional[bytes]:
    """Скачать первые CHUNK_SIZE байт по URL (Range для скорости; при 200 берём только начало)."""
    try:
        timeout = aiohttp.ClientTimeout(total=15, connect=8)
        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            async with session.get(url, allow_redirects=True, headers={**HEADERS, "Range": f"bytes=0-{CHUNK_SIZE - 1}"}) as resp:
                if resp.status not in (200, 206):
                    return None
                raw = await resp.content.read(CHUNK_SIZE)
                return raw
    except Exception as e:
        logger.debug("Fetch chunk %s: %s", url[:50], e)
        return None


def _bytes_to_text(raw: bytes) -> str:
    """Декодировать байты в текст (перебор кодировок)."""
    for enc in ENCODINGS:
        try:
            return raw.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


async def validate_file_content(url: str, title: str, author: str, fmt: str) -> bool:
    """
    Проверить, что по ссылке лежит именно эта книга (название/автор встречаются в начале файла).
    Для аудио и бинарных форматов проверка ослаблена (достаточно успешный ответ по URL).
    """
    if not url or not (title or author):
        return False
    terms = _extract_search_terms(title or "", author or "")
    if not terms:
        # Очень короткое название/автор — считаем валидным
        return True

    raw = await _fetch_first_chunk(url)
    if not raw or len(raw) < 50:
        return False

    fmt_lower = (fmt or "").strip().lower()
    if fmt_lower == "audio":
        # Для аудио проверяем только что ответ валидный и не HTML
        if b"<html" in raw[:500].lower() or b"<!doctype" in raw[:500].lower():
            return False
        return True

    text = _bytes_to_text(raw)
    if not text or len(text) < 20:
        return False

    text_norm = _normalize_for_search(text)
    # Хотя бы одно ключевое слово из названия или автора должно встретиться
    found = sum(1 for t in terms if t in text_norm)
    return found >= 1
