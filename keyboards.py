"""Кнопки и меню бота."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from messages import (
    BTN_FIND_BOOK,
    BTN_AUDIO_BOOKS,
    BTN_SCAN_COVER,
    BTN_QUOTE,
    BTN_BACK,
    BTN_AUDIO,
    BTN_READ,
    BTN_BUY,
    BTN_SIMILAR,
    BTN_FB2,
    BTN_EPUB,
    BTN_TXT,
    BTN_PDF,
    BTN_DJVU,
)


def main_menu() -> ReplyKeyboardMarkup:
    """Главное меню: Найти книгу, Аудиокниги, Сканировать, Цитата."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=BTN_FIND_BOOK),
        KeyboardButton(text=BTN_AUDIO_BOOKS),
    )
    builder.row(
        KeyboardButton(text=BTN_SCAN_COVER),
        KeyboardButton(text=BTN_QUOTE),
    )
    return builder.as_markup(resize_keyboard=True)


def back_only() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_BACK))
    return builder.as_markup(resize_keyboard=True)


def book_card_how_read(book_id: str) -> InlineKeyboardMarkup:
    """После карточки: Как хочешь читать? [🎧 Аудио] [📖 Читать] [🛒 Купить] [📚 Похожие]"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=BTN_AUDIO, callback_data=f"how:audio:{book_id}"),
        InlineKeyboardButton(text=BTN_READ, callback_data=f"how:read:{book_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=BTN_BUY, callback_data=f"how:buy:{book_id}"),
        InlineKeyboardButton(text=BTN_SIMILAR, callback_data=f"similar:{book_id}"),
    )
    return builder.as_markup()


def book_card_formats(book_id: str) -> InlineKeyboardMarkup:
    """Выбор формата: [FB2] [EPUB] [TXT] [PDF] [DJVU]"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=BTN_FB2, callback_data=f"fmt:fb2:{book_id}"),
        InlineKeyboardButton(text=BTN_EPUB, callback_data=f"fmt:epub:{book_id}"),
        InlineKeyboardButton(text=BTN_TXT, callback_data=f"fmt:txt:{book_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=BTN_PDF, callback_data=f"fmt:pdf:{book_id}"),
        InlineKeyboardButton(text=BTN_DJVU, callback_data=f"fmt:djvu:{book_id}"),
    )
    return builder.as_markup()


def buy_links_keyboard(links: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Inline кнопки магазинов (название, url)."""
    builder = InlineKeyboardBuilder()
    for name, url in links[:5]:
        builder.row(InlineKeyboardButton(text=f"🛒 {name}", url=url))
    return builder.as_markup()


def book_card_short(book_id: str, title: str, author: str) -> InlineKeyboardMarkup:
    """Короткая карточка для рекомендаций — Открыть + магазины."""
    from urllib.parse import quote_plus
    q = quote_plus(f"{title} {author}".strip())
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Открыть", callback_data=f"open:{book_id}"),
        InlineKeyboardButton(text="Ozon", url=f"https://www.ozon.ru/search/?text={q}"),
        InlineKeyboardButton(text="Litres", url=f"https://www.litres.ru/search/?q={q}"),
    )
    return builder.as_markup()
