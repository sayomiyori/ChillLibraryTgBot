"""Кнопки и меню бота."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from messages import (
    BTN_FIND_BOOK,
    BTN_AUDIO_BOOKS,
    BTN_SCAN_COVER,
    BTN_QUOTE,
    BTN_BACK,
    BTN_BACK_TO_BOOK,
    BTN_AUDIO,
    BTN_READ,
    BTN_BUY,
    BTN_SIMILAR,
    BTN_SHOW_MORE,
    BTN_FB2,
    BTN_EPUB,
    BTN_TXT,
    BTN_PDF,
    BTN_DJVU,
    COVER_CONFIRM_YES,
    COVER_CONFIRM_NO,
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


def book_card_how_read(book_id: str, has_long_description: bool = False) -> InlineKeyboardMarkup:
    """Карточка книги. При длинном описании — первая строка «Показать ещё», затем [Аудио][Читать][Купить][Похожие]."""
    buttons = []
    if has_long_description:
        buttons.append([
            InlineKeyboardButton(text=BTN_SHOW_MORE, callback_data=f"fulldesc:{book_id}"),
        ])
    buttons.append([
        InlineKeyboardButton(text=BTN_AUDIO, callback_data=f"how:audio:{book_id}"),
        InlineKeyboardButton(text=BTN_READ, callback_data=f"how:read:{book_id}"),
    ])
    buttons.append([
        InlineKeyboardButton(text=BTN_BUY, callback_data=f"how:buy:{book_id}"),
        InlineKeyboardButton(text=BTN_SIMILAR, callback_data=f"similar:{book_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def manual_input_keyboard() -> InlineKeyboardMarkup:
    """После неудачного распознавания обложки: ввести название вручную или другое фото."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Ввести название вручную", callback_data="manual_title_input"),
            InlineKeyboardButton(text="📷 Другое фото", callback_data="retry_cover"),
        ],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Отмена поиска по цитате — вернуться в главное меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")],
    ])


def retry_or_accept_keyboard(result: dict) -> InlineKeyboardMarkup:
    """Низкая уверенность по цитате: принять вариант или ввести другую цитату."""
    title = (result.get("title") or result.get("book") or "книга")[:30]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Да, это «{title}»", callback_data="accept_quote_result")],
        [InlineKeyboardButton(text="✏️ Попробовать другую цитату", callback_data="retry_quote")],
    ])


def back_to_book_keyboard(book_id: str) -> InlineKeyboardMarkup:
    """Кнопка «Назад к книге» — вернуть карточку книги с Аудио/Читать/Купить."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=BTN_BACK_TO_BOOK, callback_data=f"back_to_book:{book_id}"),
    )
    return builder.as_markup()


def book_card_formats(book_id: str, formats: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    """
    Выбор формата для скачивания.
    Если formats не задан — показываем все кнопки (FB2, EPUB, TXT, PDF, DJVU).
    Если задан — показываем только доступные форматы.
    """
    builder = InlineKeyboardBuilder()
    fmts = {k.lower() for k in (formats or {}).keys()}

    def _has(fmt: str) -> bool:
        return not formats or fmt.lower() in fmts

    row1: list[InlineKeyboardButton] = []
    if _has("fb2"):
        row1.append(InlineKeyboardButton(text=BTN_FB2, callback_data=f"fmt:fb2:{book_id}"))
    if _has("epub"):
        row1.append(InlineKeyboardButton(text=BTN_EPUB, callback_data=f"fmt:epub:{book_id}"))
    if _has("txt"):
        row1.append(InlineKeyboardButton(text=BTN_TXT, callback_data=f"fmt:txt:{book_id}"))
    if row1:
        builder.row(*row1)

    row2: list[InlineKeyboardButton] = []
    if _has("pdf"):
        row2.append(InlineKeyboardButton(text=BTN_PDF, callback_data=f"fmt:pdf:{book_id}"))
    if _has("djvu"):
        row2.append(InlineKeyboardButton(text=BTN_DJVU, callback_data=f"fmt:djvu:{book_id}"))
    if row2:
        builder.row(*row2)

    return builder.as_markup()


def buy_links_keyboard(links: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Inline кнопки магазинов (название, url)."""
    builder = InlineKeyboardBuilder()
    for name, url in links[:5]:
        builder.row(InlineKeyboardButton(text=f"🛒 {name}", url=url))
    return builder.as_markup()


def cover_confirm_keyboard(title: str, author: str) -> InlineKeyboardMarkup:
    """Кнопки подтверждения после распознавания обложки: [Да, искать] [Нет, введу сам]."""
    # callback_data до 64 байт — храним в state, кнопки только триггеры
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=COVER_CONFIRM_YES, callback_data="cover_yes"),
        InlineKeyboardButton(text=COVER_CONFIRM_NO, callback_data="cover_no"),
    )
    return builder.as_markup()


def book_choice_keyboard(books: list[dict], callback_prefix: str = "cover_book") -> InlineKeyboardMarkup:
    """Список книг на выбор (одна кнопка на книгу). callback_prefix: cover_book или search_book."""
    builder = InlineKeyboardBuilder()
    for book in books[:5]:
        bid = (book.get("id") or "").strip()
        title = (book.get("title") or "Без названия")[:40]
        author = (book.get("author") or "")[:30]
        text = f"{title} — {author}" if author else title
        if bid:
            builder.row(InlineKeyboardButton(text=text, callback_data=f"{callback_prefix}:{bid}"))
    return builder.as_markup()


def book_variants_keyboard(books: list[dict]) -> InlineKeyboardMarkup:
    """Список языковых вариантов книги: флаг + название — автор, select_book:id, кнопка Отмена."""
    buttons = []
    for book in books[:5]:
        bid = (book.get("id") or "").strip()
        title = (book.get("title") or "Без названия")[:35]
        author = (book.get("author") or "")[:20]
        flag = book.get("flag", "\U0001f30d")
        text = f"{flag} {title} — {author}" if author else f"{flag} {title}"
        if bid:
            buttons.append([InlineKeyboardButton(text=text, callback_data=f"select_book:{bid}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
