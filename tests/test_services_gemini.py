"""Тесты services.gemini: get_book_from_quote, get_similar_books (мок Gemini)."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_get_book_from_quote_returns_none_without_key():
    """Без GEMINI_API_KEY возвращается None."""
    from services.gemini import get_book_from_quote
    with patch("services.gemini.GEMINI_API_KEY", ""):
        result = await get_book_from_quote("Всё будет хорошо")
        assert result is None


@pytest.mark.asyncio
async def test_get_book_from_quote_parses_response():
    """Парсинг ответа с НАЗВАНИЕ: и АВТОР:."""
    from services.gemini import get_book_from_quote, _get_book_from_quote_sync

    with patch("services.gemini.GEMINI_API_KEY", "test-key"):
        with patch("google.generativeai.GenerativeModel") as MockModel:
            mock_response = MagicMock()
            mock_response.text = "НАЗВАНИЕ: Мастер и Маргарита\nАВТОР: Михаил Булгаков\nГОД: 1967"
            MockModel.return_value.generate_content.return_value = mock_response

            result = _get_book_from_quote_sync("Время не ждёт")
            assert result is not None
            assert result["title"] == "Мастер и Маргарита"
            assert result["author"] == "Михаил Булгаков"


@pytest.mark.asyncio
async def test_get_book_from_quote_not_sure_returns_none():
    """Ответ «НЕ УВЕРЕН» даёт None."""
    from services.gemini import _get_book_from_quote_sync

    with patch("services.gemini.GEMINI_API_KEY", "test-key"):
        with patch("google.generativeai.GenerativeModel") as MockModel:
            mock_response = MagicMock()
            mock_response.text = "НЕ УВЕРЕН в этой цитате."
            MockModel.return_value.generate_content.return_value = mock_response

            result = _get_book_from_quote_sync("какой-то текст")
            assert result is None


@pytest.mark.asyncio
async def test_get_similar_books_parses_lines():
    """get_similar_books парсит строки «Название — Автор»."""
    from services.gemini import _get_similar_books_sync

    with patch("services.gemini.GEMINI_API_KEY", "key"):
        with patch("google.generativeai.GenerativeModel") as MockModel:
            mock_response = MagicMock()
            mock_response.text = """Собачье сердце — Михаил Булгаков
Белая гвардия — Михаил Булгаков
Роковые яйца — Михаил Булгаков"""
            MockModel.return_value.generate_content.return_value = mock_response

            result = _get_similar_books_sync("Мастер и Маргарита", "Булгаков", limit=5)
            assert len(result) == 3
            assert result[0]["title"] == "Собачье сердце"
            assert result[0]["author"] == "Михаил Булгаков"
