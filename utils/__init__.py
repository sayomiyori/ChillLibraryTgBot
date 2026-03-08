"""Утилиты: кэш, нечёткий поиск, нормализация."""
from utils.cache import get_cached_link, set_cached_link
from utils.fuzzy import fuzzy_match_score, normalize_for_fuzzy
from utils.normalize import normalize_query

__all__ = [
    "get_cached_link",
    "set_cached_link",
    "fuzzy_match_score",
    "normalize_for_fuzzy",
    "normalize_query",
]
