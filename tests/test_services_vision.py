"""Тесты services.vision: get_text_from_image (мок Vision API)."""
import base64
import pytest
from aioresponses import aioresponses


@pytest.fixture
def mock_google_key(monkeypatch):
    import services.vision as vision
    monkeypatch.setattr(vision, "GOOGLE_API_KEY", "test-vision-key")


@pytest.mark.asyncio
async def test_get_text_from_image_returns_none_without_key(monkeypatch):
    """Без API-ключа возвращается None."""
    import services.vision as vision
    monkeypatch.setattr(vision, "GOOGLE_API_KEY", "")
    result = await vision.get_text_from_image(b"\x00\x01")
    assert result is None


@pytest.mark.asyncio
async def test_get_text_from_image_parses_full_text_annotation(mock_google_key):
    """Парсинг fullTextAnnotation.text."""
    from services.vision import get_text_from_image, VISION_URL

    mock_response = {
        "responses": [
            {
                "fullTextAnnotation": {
                    "text": "Мастер и Маргарита\nМихаил Булгаков",
                }
            }
        ]
    }
    with aioresponses() as m:
        m.post(
            f"{VISION_URL}?key=test-vision-key",
            payload=mock_response,
        )
        result = await get_text_from_image(b"fake image bytes")
    assert result == "Мастер и Маргарита\nМихаил Булгаков"


@pytest.mark.asyncio
async def test_get_text_from_image_empty_bytes_returns_none(mock_google_key):
    """Пустое изображение — None."""
    from services.vision import get_text_from_image
    result = await get_text_from_image(b"")
    assert result is None
