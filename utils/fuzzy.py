"""Нечёткое сравнение строк для дедупликации и верификации (rapidfuzz)."""
from typing import Optional

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


def normalize_for_fuzzy(s: str) -> str:
    """Нормализация для сравнения: нижний регистр, без лишних пробелов."""
    if not s:
        return ""
    return " ".join(str(s).strip().lower().split())


def fuzzy_match_score(s1: str, s2: str) -> float:
    """
    Возвращает оценку совпадения 0–100.
    Если rapidfuzz не установлен — простое сравнение нормализованных строк.
    """
    n1 = normalize_for_fuzzy(s1)
    n2 = normalize_for_fuzzy(s2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 100.0
    if fuzz:
        return float(fuzz.token_set_ratio(n1, n2))
    return 100.0 if n1 in n2 or n2 in n1 else 0.0


def is_same_book(title1: str, author1: str, title2: str, author2: str, threshold: float = 85.0) -> bool:
    """Проверка, что две книги совпадают (по названию и автору)."""
    t = fuzzy_match_score(title1, title2)
    a = fuzzy_match_score(author1, author2)
    return t >= threshold and a >= threshold
