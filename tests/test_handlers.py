"""Тесты логики обработчиков: форматирование карточки, имя файла."""
import pytest


def test_format_book_card():
    """format_book_card формирует текст с названием, автором, описанием, рейтингом."""
    from handlers.search import format_book_card

    book = {
        "title": "Мастер и Маргарита",
        "author": "Михаил Булгаков",
        "description": "Роман о дьяволе.",
        "rating": 4.8,
    }
    text = format_book_card(book)
    assert "Мастер и Маргарита" in text
    assert "Михаил Булгаков" in text
    assert "Роман о дьяволе" in text
    assert "4.8" in text
    assert "📖" in text and "✍️" in text


def test_format_book_card_minimal():
    """При отсутствии описания и рейтинга выводятся только название и автор."""
    from handlers.search import format_book_card

    book = {"title": "Книга", "author": "Автор"}
    text = format_book_card(book)
    assert "Книга" in text
    assert "Автор" in text


def test_safe_filename():
    """_safe_filename убирает недопустимые символы и добавляет расширение."""
    from handlers.search import _safe_filename

    assert _safe_filename("Мастер и Маргарита", "epub") == "Мастер и Маргарита.epub"
    assert _safe_filename("Book Title", "fb2") == "Book Title.fb2"
    assert _safe_filename("", "pdf") == "book.pdf"


def test_keyboard_main_menu_has_buttons():
    """Главное меню содержит кнопки Найти книгу, Аудиокниги, Сканировать обложку, Ввести цитату."""
    from keyboards import main_menu
    from messages import BTN_FIND_BOOK, BTN_AUDIO_BOOKS, BTN_SCAN_COVER, BTN_QUOTE

    kb = main_menu()
    assert kb.keyboard
    flat = [btn.text for row in kb.keyboard for btn in row]
    assert BTN_FIND_BOOK in flat
    assert BTN_AUDIO_BOOKS in flat
    assert BTN_SCAN_COVER in flat
    assert BTN_QUOTE in flat


def test_book_card_short_has_open_button():
    """Короткая карточка содержит кнопку Открыть."""
    from keyboards import book_card_short

    kb = book_card_short("book-id", "Title", "Author")
    inline = kb.inline_keyboard
    assert inline
    open_btn = [b for row in inline for b in row if b.callback_data == "open:book-id"]
    assert len(open_btn) == 1
