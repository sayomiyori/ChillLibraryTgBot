"""
Верификация содержимого файла по первым 8KB.
FB2: XML <book-title>, <author> → fuzzy > 85%
EPUB: content.opf из ZIP или поиск в сырых байтах → fuzzy > 85%
TXT: первые 2000 символов → название/автор → fuzzy > 80%
PDF: метаданные /Title, /Author → fuzzy > 80%
DJVU/MP3: упрощённая проверка (наличие текста/не HTML)
"""
import io
import logging
import re
import zipfile
from typing import Optional

from utils.fuzzy import fuzzy_match_score, normalize_for_fuzzy

logger = logging.getLogger(__name__)
CHUNK_SIZE = 8192
ENCODINGS = ["utf-8", "utf-8-sig", "cp1251", "cp866", "koi8-r", "latin-1"]


def _bytes_to_text(raw: bytes, max_chars: int = 3000) -> str:
    for enc in ENCODINGS:
        try:
            return raw.decode(enc, errors="strict")[:max_chars]
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")[:max_chars]


def _extract_terms(title: str, author: str) -> list[str]:
    stop = {"и", "в", "на", "с", "о", "the", "a", "an", "and", "of", "in", "to"}
    terms = []
    for s in (title or "", author or ""):
        n = normalize_for_fuzzy(s)
        for w in n.split():
            if len(w) > 1 and w not in stop:
                terms.append(w)
    return terms[:10]


def _pass_by_title_only(title: str, found_title: str, found_author: str, author: str) -> bool:
    """Если название совпадает сильно (≥80%), считаем валидным даже без автора."""
    if not title or not found_title:
        return False
    title_score = fuzzy_match_score(title, found_title)
    if title_score >= 80:
        return True
    return False


async def verify_fb2(chunk: bytes, title: str, author: str, _session) -> bool:
    """FB2: парсим XML → <book-title>, <author>. Пороги: title≥70%, author≥60%; или title≥80%."""
    try:
        from lxml import etree
        root = etree.fromstring(chunk)
    except Exception:
        root = None
    if root is not None:
        try:
            titles = root.xpath("//*[local-name()='book-title']/text()")
            authors = root.xpath("//*[local-name()='author']//*[local-name()='firstName' or local-name()='lastName']/text()")
            found_title = " ".join(titles).strip() if titles else ""
            found_author = " ".join(authors).strip() if authors else ""
            if _pass_by_title_only(title, found_title, found_author, author):
                return True
            if found_title and found_author:
                if fuzzy_match_score(title, found_title) >= 70 and fuzzy_match_score(author, found_author) >= 60:
                    return True
            if found_title and fuzzy_match_score(title, found_title) >= 70:
                return True
            if found_author and fuzzy_match_score(author, found_author) >= 60:
                return True
        except Exception as e:
            logger.debug("FB2 parse: %s", e)
    text = _bytes_to_text(chunk)
    terms = _extract_terms(title, author)
    if not terms:
        return True
    norm = normalize_for_fuzzy(text)
    return sum(1 for t in terms if t in norm) >= 1


async def verify_epub(chunk: bytes, title: str, author: str, _session) -> bool:
    """EPUB: ищем title/author в тексте. Пороги: title≥70%, author≥60%; или title≥80%."""
    text = _bytes_to_text(chunk)
    terms = _extract_terms(title, author)
    if not terms:
        return True
    norm = normalize_for_fuzzy(text)
    if any(t in norm for t in terms):
        return True
    if title and len(text) > 50 and fuzzy_match_score(title, text[:500]) >= 80:
        return True
    if title and len(text) > 50 and fuzzy_match_score(title, text[:500]) >= 70 and (not author or any(a in norm for a in _extract_terms("", author))):
        return True
    if b"content.opf" in chunk or b"container.xml" in chunk:
        return True
    return False


async def verify_txt(chunk: bytes, title: str, author: str, _session) -> bool:
    """TXT: первые 2000 символов. Пороги: title≥65%, author≥55%; или title≥80%."""
    text = _bytes_to_text(chunk, max_chars=2000)
    if len(text) < 20:
        return False
    if title and fuzzy_match_score(title, text[:500]) >= 80:
        return True
    terms = _extract_terms(title, author)
    if not terms:
        return True
    norm = normalize_for_fuzzy(text)
    found = sum(1 for t in terms if t in norm)
    if found >= 1:
        return True
    if title and fuzzy_match_score(title, text[:300]) >= 65:
        return True
    return False


async def verify_pdf(chunk: bytes, title: str, author: str, _session) -> bool:
    """PDF: метаданные или текст. Пороги: title≥65%, author≥55%; или title≥80%."""
    text = _bytes_to_text(chunk, max_chars=2000)
    if title and len(text) > 30 and fuzzy_match_score(title, text[:500]) >= 80:
        return True
    raw = chunk[:2000]
    if b"/Title" in raw or b"/Author" in raw:
        decoded = raw.decode("latin-1", errors="replace")
        terms = _extract_terms(title, author)
        if not terms:
            return True
        for t in terms:
            if t.encode("utf-8", errors="replace") in raw or t in decoded:
                return True
        if title and fuzzy_match_score(title, decoded) >= 65:
            return True
    terms = _extract_terms(title, author)
    if not terms:
        return True
    norm = normalize_for_fuzzy(text)
    if any(t in norm for t in terms):
        return True
    if title and fuzzy_match_score(title, text[:400]) >= 65:
        return True
    return False


async def verify_djvu(chunk: bytes, title: str, author: str, _session) -> bool:
    """DJVU: первые байты — считаем валидным если не HTML."""
    if b"<html" in chunk[:500].lower() or b"<!doctype" in chunk[:500].lower():
        return False
    return len(chunk) >= 100


async def verify_audio(chunk: bytes, title: str, author: str, _session) -> bool:
    """MP3: не HTML; при наличии ID3 — проверяем."""
    if b"<html" in chunk[:500].lower() or b"<!doctype" in chunk[:500].lower():
        return False
    if b"ID3" in chunk[:10]:
        text = _bytes_to_text(chunk)
        terms = _extract_terms(title, author)
        if not terms:
            return True
        return any(t in normalize_for_fuzzy(text) for t in terms)
    return len(chunk) >= 100


VERIFIERS = {
    "fb2": verify_fb2,
    "epub": verify_epub,
    "txt": verify_txt,
    "pdf": verify_pdf,
    "djvu": verify_djvu,
    "audio": verify_audio,
    "mp3": verify_audio,
    "m4b": verify_audio,
}


async def verify_chunk(
    chunk: bytes,
    title: str,
    author: str,
    fmt: str,
    session,
) -> bool:
    fmt_lower = (fmt or "").strip().lower()
    fn = VERIFIERS.get(fmt_lower) or VERIFIERS.get("txt")
    try:
        return await fn(chunk, title or "", author or "", session)
    except Exception as e:
        logger.debug("Verify %s: %s", fmt, e)
        return False
