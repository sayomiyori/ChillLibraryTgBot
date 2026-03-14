"""
Двухуровневый кэш для ссылок на файлы.
L1: dict в памяти (мгновенно)
L2: JSON файл (персистентно)
Ключ: MD5("{title}_{author}_{format}")
TTL: 7 дней
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CACHE_TTL_DAYS

logger = logging.getLogger(__name__)

TTL_SEC = CACHE_TTL_DAYS * 24 * 3600
_L1: dict[str, tuple[str, float]] = {}  # key -> (url, expires_at)


def _cache_key(title: str, author: str, format: str) -> str:
    raw = f"{title}_{author}_{format}".strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _l2_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def get_cached_link(title: str, author: str, format: str) -> Optional[str]:
    key = _cache_key(title, author, format)
    # L1
    if key in _L1:
        url, expires = _L1[key]
        if time.time() < expires:
            return url
        del _L1[key]
    # L2
    path = _l2_path(key)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            expires = data.get("expires", 0)
            if time.time() < expires:
                url = data.get("url")
                # Promote to L1 cache for faster subsequent lookups
                if url:
                    _L1[key] = (url, expires)
                return url
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.debug("Cache read %s: %s", key, e)
    return None


def set_cached_link(title: str, author: str, format: str, url: str) -> None:
    key = _cache_key(title, author, format)
    expires = time.time() + TTL_SEC
    _L1[key] = (url, expires)
    path = _l2_path(key)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"url": url, "expires": expires}, f, ensure_ascii=False)
    except Exception as e:
        logger.debug("Cache write %s: %s", key, e)
