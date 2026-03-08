"""Поиск файла по формату: Аудио / Читать (FB2, EPUB, …) → верификация → ссылка."""
import asyncio
import logging
import time
from aiogram import Router, F
from aiogram.types import CallbackQuery

from handlers.helpers import safe_answer
from messages import (
    FILE_SEARCHING,
    FILE_NOT_FOUND,
    FILE_FOUND,
    FILE_TRY_OTHER,
    CHOOSE_FORMAT,
)
from keyboards import main_menu, book_card_formats, buy_links_keyboard
from main import get_session
from services.file_search import find_file_link
from services.buy_links import get_buy_links
from services.google_books import get_book_by_id
from handlers.search import BOOK_CACHE

router = Router()
logger = logging.getLogger(__name__)
FILE_SEARCH_TIMEOUT = 30.0


async def _get_title_author(callback: CallbackQuery, book_id: str) -> tuple[str, str]:
    """Достать title, author по book_id из кэша или API."""
    if book_id in BOOK_CACHE:
        return BOOK_CACHE[book_id]
    session = get_session()
    if session:
        book = await get_book_by_id(session, book_id)
        if book:
            return book.title, book.author
    return "", ""


@router.callback_query(F.data.startswith("how:audio:"))
async def how_audio(callback: CallbackQuery) -> None:
    """Пользователь выбрал Аудио → ищем аудиокнигу, кидаем ссылку."""
    book_id = callback.data.removeprefix("how:audio:").strip()
    await callback.answer(FILE_SEARCHING)
    title, author = await _get_title_author(callback, book_id)
    if not title and not author:
        await callback.message.answer(FILE_NOT_FOUND, reply_markup=main_menu())
        return
    session = get_session()
    if not session:
        await callback.message.answer(FILE_NOT_FOUND, reply_markup=main_menu())
        return
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            find_file_link(session, title, author, "audio"),
            timeout=FILE_SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("find_file_link (audio) timeout %.0fs", FILE_SEARCH_TIMEOUT)
        result = None
    elapsed = time.perf_counter() - start
    if result:
        url, _ = result
        text = FILE_FOUND.format(elapsed, title, author, "Аудио", url)
        await safe_answer(callback.message, text, reply_markup=main_menu())
    else:
        await safe_answer(
            callback.message,
            FILE_NOT_FOUND + "\n\n" + FILE_TRY_OTHER,
            reply_markup=book_card_formats(book_id),
        )


@router.callback_query(F.data.startswith("how:read:"))
async def how_read(callback: CallbackQuery) -> None:
    """Пользователь выбрал Читать → спрашиваем формат."""
    book_id = callback.data.removeprefix("how:read:").strip()
    await callback.answer()
    await safe_answer(callback.message, CHOOSE_FORMAT, reply_markup=book_card_formats(book_id))


@router.callback_query(F.data.startswith("how:buy:"))
async def how_buy(callback: CallbackQuery) -> None:
    """Показать ссылки на магазины."""
    book_id = callback.data.removeprefix("how:buy:").strip()
    await callback.answer()
    title, author = await _get_title_author(callback, book_id)
    links = get_buy_links(title, author)
    await safe_answer(callback.message, "🛒 Где купить:", reply_markup=buy_links_keyboard(links))


@router.callback_query(F.data.startswith("fmt:"))
async def send_format(callback: CallbackQuery) -> None:
    """Выбран формат (FB2, EPUB, TXT, PDF, DJVU) → ищем ссылку, верифицируем, отправляем."""
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer()
        return
    _, fmt, book_id = parts
    fmt = (fmt or "").strip().lower()
    book_id = (book_id or "").strip()
    await callback.answer(FILE_SEARCHING)
    title, author = await _get_title_author(callback, book_id)
    if not title and not author:
        await callback.message.answer(FILE_NOT_FOUND, reply_markup=main_menu())
        return
    session = get_session()
    if not session:
        await callback.message.answer(FILE_NOT_FOUND, reply_markup=main_menu())
        return
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            find_file_link(session, title, author, fmt),
            timeout=FILE_SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("find_file_link (%s) timeout %.0fs", fmt, FILE_SEARCH_TIMEOUT)
        result = None
    elapsed = time.perf_counter() - start
    if result:
        url, _ = result
        text = FILE_FOUND.format(elapsed, title, author, fmt.upper(), url)
        await safe_answer(callback.message, text, reply_markup=main_menu())
    else:
        await safe_answer(
            callback.message,
            FILE_NOT_FOUND + "\n\n" + FILE_TRY_OTHER,
            reply_markup=book_card_formats(book_id),
        )
