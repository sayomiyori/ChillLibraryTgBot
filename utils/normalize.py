"""Нормализация поисковых запросов и имён."""
import re
from typing import Optional


def normalize_query(q: str, max_len: int = 200) -> str:
    """Нормализация запроса: обрезка пробелов, схлопывание пробелов, лимит длины."""
    if not q or not isinstance(q, str):
        return ""
    s = re.sub(r"\s+", " ", q.strip())
    return s[:max_len] if max_len else s
