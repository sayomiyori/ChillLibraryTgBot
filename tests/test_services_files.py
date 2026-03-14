"""Тесты services.file_search: find_file_link (поиск ссылки + верификация)."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_find_file_link_returns_none_for_empty_format():
    """Пустой формат — None."""
    import aiohttp
    from services.file_search import find_file_link
    async with aiohttp.ClientSession() as session:
        result = await find_file_link(session, "Книга", "Автор", "")
    assert result is None


@pytest.mark.asyncio
async def test_find_file_link_returns_none_for_no_title_and_author():
    """Без title и author — None."""
    import aiohttp
    from services.file_search import find_file_link
    async with aiohttp.ClientSession() as session:
        result = await find_file_link(session, "", "", "epub")
    assert result is None


@pytest.mark.asyncio
async def test_find_file_link_returns_cached_link():
    """При наличии в кэше — возвращает ссылку из кэша."""
    import aiohttp
    from services.file_search import find_file_link

    with patch("services.file_search.get_cached_link", return_value="http://cached.example.com/book.epub"):
        async with aiohttp.ClientSession() as session:
            result = await find_file_link(session, "Книга", "Автор", "epub")
    assert result is not None
    assert result[0] == "http://cached.example.com/book.epub"
    assert result[1] == "cache"
