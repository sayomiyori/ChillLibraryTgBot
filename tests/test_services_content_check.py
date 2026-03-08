"""Тесты services.content_check: проверка начинки файла по первым байтам."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_validate_file_content_true_when_title_in_chunk():
    """Если в начале файла есть название книги — валидация проходит."""
    from services.content_check import validate_file_content

    with patch("services.content_check._fetch_first_chunk", new_callable=AsyncMock) as m:
        m.return_value = "Здесь текст книги. Муму. Тургенев.".encode("utf-8")
        result = await validate_file_content("https://example.com/book.txt", "Муму", "Тургенев", "txt")
    assert result is True


@pytest.mark.asyncio
async def test_validate_file_content_false_when_chunk_is_html():
    """Если по ссылке пришла HTML-страница — не считаем файлом книги."""
    from services.content_check import validate_file_content

    with patch("services.content_check._fetch_first_chunk", new_callable=AsyncMock) as m:
        m.return_value = b"<!DOCTYPE html><html><body>Not a book</body></html>"
        result = await validate_file_content("https://example.com/page", "Муму", "Тургенев", "txt")
    assert result is False


@pytest.mark.asyncio
async def test_validate_file_content_false_when_empty_or_no_match():
    """Пустой ответ или без названия/автора — False."""
    from services.content_check import validate_file_content

    with patch("services.content_check._fetch_first_chunk", new_callable=AsyncMock) as m:
        m.return_value = b"Some random content without book title."
        result = await validate_file_content("https://example.com/f", "Муму", "Тургенев", "txt")
    assert result is False
