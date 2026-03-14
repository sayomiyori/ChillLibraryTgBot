"""Тесты services.vision: recognize_cover, _get_text_from_image, _parse_title_author_from_text."""
import pytest
from unittest.mock import AsyncMock, patch


def test_parse_title_author_from_text():
    """Эвристика парсинга текста обложки: первая строка — название, вторая — автор."""
    from services.vision import _parse_title_author_from_text

    result = _parse_title_author_from_text("Мастер и Маргарита\nМихаил Булгаков")
    assert result is not None
    assert result["title"] == "Мастер и Маргарита"
    assert result["author"] == "Михаил Булгаков"


def test_parse_title_author_from_text_with_dash():
    """Если в первой строке есть ' — ', разбиваем на title и author."""
    from services.vision import _parse_title_author_from_text

    result = _parse_title_author_from_text("Мастер и Маргарита — Михаил Булгаков")
    assert result is not None
    assert result["title"] == "Мастер и Маргарита"
    assert result["author"] == "Михаил Булгаков"


def test_parse_title_author_from_empty_text():
    """Пустой текст — None."""
    from services.vision import _parse_title_author_from_text

    assert _parse_title_author_from_text("") is None
    assert _parse_title_author_from_text("  ") is None
    assert _parse_title_author_from_text(None) is None


@pytest.mark.asyncio
async def test_get_text_from_image_empty_bytes():
    """Пустое изображение — пустая строка."""
    from services.vision import _get_text_from_image

    result = await _get_text_from_image(b"")
    assert result == ""


@pytest.mark.asyncio
async def test_recognize_cover_returns_none_on_empty_data():
    """Пустые байты — None."""
    from services.vision import recognize_cover

    result = await recognize_cover(b"")
    assert result is None
