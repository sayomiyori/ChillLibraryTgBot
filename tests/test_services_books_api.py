"""Тесты services.books_api: search_books, get_book_by_id (с моком aiohttp)."""
import re
import pytest
from aioresponses import aioresponses


@pytest.fixture
def mock_google_key(monkeypatch):
    """Подмена API-ключа в модуле books_api (уже импортирован из config)."""
    import services.books_api as api
    monkeypatch.setattr(api, "GOOGLE_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_search_books_empty_query():
    """Пустой запрос возвращает пустой список."""
    from services.books_api import search_books
    result = await search_books("")
    assert result == []
    result = await search_books("   ")
    assert result == []


@pytest.mark.asyncio
async def test_search_books_returns_parsed_results(mock_google_key):
    """search_books парсит ответ API и возвращает список книг."""
    from services.books_api import search_books, GOOGLE_BOOKS_URL

    mock_response = {
        "items": [
            {
                "id": "abc123",
                "volumeInfo": {
                    "title": "Мастер и Маргарита",
                    "authors": ["Михаил Булгаков"],
                    "description": "Роман.",
                    "imageLinks": {"thumbnail": "http://example.com/cover.jpg"},
                    "averageRating": 4.8,
                },
            }
        ]
    }
    with aioresponses() as m:
        # URL с query: .../volumes?q=...&maxResults=...&key=...
        m.get(
            re.compile(r"^https://www\.googleapis\.com/books/v1/volumes\?"),
            payload=mock_response,
        )
        result = await search_books("булгаков", max_results=5)
    assert len(result) == 1
    assert result[0]["id"] == "abc123"
    assert result[0]["title"] == "Мастер и Маргарита"
    assert result[0]["author"] == "Михаил Булгаков"
    assert result[0]["rating"] == 4.8
    assert result[0]["thumbnail"] == "http://example.com/cover.jpg"


@pytest.mark.asyncio
async def test_search_books_empty_response(mock_google_key):
    """При отсутствии items возвращается пустой список."""
    from services.books_api import search_books, GOOGLE_BOOKS_URL
    with aioresponses() as m:
        m.get(re.compile(r"^https://www\.googleapis\.com/books/v1/volumes\?"), payload={})
        result = await search_books("нет такой книги", max_results=5)
    assert result == []


@pytest.mark.asyncio
async def test_get_book_by_id_returns_none_without_key(monkeypatch):
    """Без API-ключа get_book_by_id возвращает None."""
    import services.books_api as api
    monkeypatch.setattr(api, "GOOGLE_API_KEY", "")
    result = await api.get_book_by_id("some-id")
    assert result is None


@pytest.mark.asyncio
async def test_get_book_by_id_parses_volume(mock_google_key):
    """get_book_by_id возвращает словарь книги."""
    from services.books_api import get_book_by_id, GOOGLE_BOOKS_URL

    mock_response = {
        "id": "vol123",
        "volumeInfo": {
            "title": "Собачье сердце",
            "authors": ["Михаил Булгаков"],
            "description": "Повесть.",
        },
    }
    with aioresponses() as m:
        # URL: .../volumes/vol123?key=...
        m.get(
            re.compile(r"^https://www\.googleapis\.com/books/v1/volumes/vol123"),
            payload=mock_response,
        )
        result = await get_book_by_id("vol123")
    assert result is not None
    assert result["id"] == "vol123"
    assert result["title"] == "Собачье сердце"
    assert result["author"] == "Михаил Булгаков"
