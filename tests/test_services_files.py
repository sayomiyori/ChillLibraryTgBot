"""Тесты services.files: find_download_link (поиск ссылки + проверка начинки)."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_find_download_link_returns_none_for_unknown_format():
    """Неизвестный формат — None."""
    from services.files import find_download_link
    result = await find_download_link("Книга", "Автор", "unknown_format")
    assert result is None


@pytest.mark.asyncio
async def test_find_download_link_returns_none_for_short_query():
    """Запрос короче 2 символов (например только один символ) — None."""
    from services.files import find_download_link
    result = await find_download_link("А", "", "epub")
    assert result is None


@pytest.mark.asyncio
async def test_find_download_link_returns_none_when_no_source_returns_url():
    """Ни один источник не вернул ссылку — None."""
    from services.files import find_download_link

    with patch("services.files.find_link_any_source", new_callable=AsyncMock, return_value=None):
        result = await find_download_link("Очень редкая книга xyz", "Неизвестный", "pdf")
    assert result is None
