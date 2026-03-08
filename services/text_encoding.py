"""Нормализация кодировки текстовых файлов (TXT) в UTF-8 для корректного отображения."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Типичные кодировки для русскоязычных TXT
ENCODINGS = ["utf-8", "utf-8-sig", "cp1251", "cp866", "koi8-r", "latin-1", "iso-8859-1"]


def ensure_utf8_bytes(raw: bytes) -> bytes:
    """
    Преобразует байты текстового файла в UTF-8.
    Пробует типичные кодировки (UTF-8, CP1251, CP866, KOI8-R и др.),
    чтобы избежать кракозябр при открытии в мессенджерах и редакторах.
    """
    if not raw or len(raw) < 2:
        return raw
    # Уже валидный UTF-8
    try:
        raw.decode("utf-8")
        return raw
    except UnicodeDecodeError:
        pass
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc, errors="strict")
            return text.encode("utf-8")
        except (UnicodeDecodeError, LookupError):
            continue
    # Fallback: replace ошибки в cp1251 (часто для русских сайтов)
    try:
        text = raw.decode("cp1251", errors="replace")
        return text.encode("utf-8")
    except Exception:
        pass
    try:
        text = raw.decode("utf-8", errors="replace")
        return text.encode("utf-8")
    except Exception:
        return raw
