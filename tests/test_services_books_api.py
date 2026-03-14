"""Тесты services.google_books: search_google_books, get_book_by_id (с моком aiohttp)."""
import re
import pytest
from aioresponses import aioresponses


@pytest.fixture
def mock_google_key(monkeypatch):
    """Подмена API-ключа в модуле google_books."""
    import services.google_books as gb
    monkeypatch.setattr(gb, "GOOGLE_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_search_google_books_empty_query():
    """Пустой запрос возвращает пустой список."""
    import aiohttp
    from services.google_books import search_google_books
    async with aiohttp.ClientSession() as session:
        result = await search_google_books(session, "")
    assert result == []


@pytest.mark.asyncio
async def test_search_google_books_returns_parsed_results(mock_google_key):
    """search_google_books парсит ответ API и возвращает список BookInfo."""
    import aiohttp
    from services.google_books import search_google_books

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
        m.get(
            re.compile(r"^https://www\.googleapis\.com/books/v1/volumes\?"),
            payload=mock_response,
        )
        async with aiohttp.ClientSession() as session:
            result = await search_google_books(session, "булгаков", max_results=5)
    assert len(result) == 1
    assert result[0].id == "abc123"
    assert result[0].title == "Мастер и Маргарита"
    assert result[0].author == "Михаил Булгаков"
    assert result[0].rating == 4.8
    assert result[0].cover_url == "http://example.com/cover.jpg"


@pytest.mark.asyncio
async def test_search_google_books_empty_response(mock_google_key):
    """При отсутствии items возвращается пустой список."""
    import aiohttp
    from services.google_books import search_google_books
    with aioresponses() as m:
        m.get(re.compile(r"^https://www\.googleapis\.com/books/v1/volumes\?"), payload={})
        async with aiohttp.ClientSession() as session:
            result = await search_google_books(session, "нет такой книги", max_results=5)
    assert result == []


@pytest.mark.asyncio
async def test_get_book_by_id_returns_none_without_key(monkeypatch):
    """Без API-ключа get_book_by_id возвращает None."""
    import aiohttp
    import services.google_books as gb
    monkeypatch.setattr(gb, "GOOGLE_API_KEY", "")
    async with aiohttp.ClientSession() as session:
        result = await gb.get_book_by_id(session, "some-id")
    assert result is None


@pytest.mark.asyncio
async def test_get_book_by_id_parses_volume(mock_google_key):
    """get_book_by_id возвращает BookInfo."""
    import aiohttp
    from services.google_books import get_book_by_id

    mock_response = {
        "id": "vol123",
        "volumeInfo": {
            "title": "Собачье сердце",
            "authors": ["Михаил Булгаков"],
            "description": "Повесть.",
        },
    }
    with aioresponses() as m:
        m.get(
            re.compile(r"^https://www\.googleapis\.com/books/v1/volumes/vol123"),
            payload=mock_response,
        )
        async with aiohttp.ClientSession() as session:
            result = await get_book_by_id(session, "vol123")
    assert result is not None
    assert result.id == "vol123"
    assert result.title == "Собачье сердце"
    assert result.author == "Михаил Булгаков"
