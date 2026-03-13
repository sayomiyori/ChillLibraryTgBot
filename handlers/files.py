"""Поиск файла по формату: Аудио / Читать (FB2, EPUB, …) → скачивание → отправка файла или ссылка."""
import asyncio
import logging
import re
import time
from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile

from handlers.helpers import safe_answer
from messages import (
    FILE_SEARCHING,
    FILE_NOT_FOUND,
    FILE_FOUND,
    FILE_TRY_OTHER,
    CHOOSE_FORMAT,
    FORMATS_SEARCHING,
    DOWNLOADING,
    DOWNLOAD_FAILED,
)
from keyboards import main_menu, book_card_formats, book_card_how_read, back_to_book_keyboard, buy_links_keyboard
from main import get_session
from services.file_search import find_file_link
from services.libgen_service import get_download_formats, download_book
from services.buy_links import get_buy_links
from services.google_books import get_book_by_id
from handlers.search import BOOK_CACHE, LIBGEN_BOOK_CACHE

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


def _get_card_text(msg) -> str:
    """Текст/подпись карточки книги из сообщения (фото или текст)."""
    return (msg.caption or msg.text or "").strip()


async def _edit_card_message(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    """Редактировать то же сообщение карточки (фото или текст)."""
    msg = callback.message
    if msg.photo:
        await msg.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        await msg.edit_text(text=text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("how:read:"))
async def how_read(callback: CallbackQuery) -> None:
    """Читать → редактируем карточку: «Ищу форматы», затем кнопки форматов или FILE_NOT_FOUND."""
    book_id = callback.data.removeprefix("how:read:").strip()
    await callback.answer()
    title, author = await _get_title_author(callback, book_id)
    if not title and not author:
        await safe_answer(callback.message, FILE_NOT_FOUND, reply_markup=main_menu())
        return
    card_text = _get_card_text(callback.message)
    await callback.bot.send_chat_action(callback.message.chat.id, "typing")
    try:
        await _edit_card_message(
            callback,
            card_text + "\n\n" + FORMATS_SEARCHING,
            reply_markup=None,
        )
    except Exception:
        pass
    libgen_book = LIBGEN_BOOK_CACHE.get(book_id) if book_id else None
    if libgen_book and libgen_book.get("source") == "libgen" and libgen_book.get("available_formats"):
        formats = libgen_book["available_formats"]
    else:
        formats = await get_download_formats(title, author)
    try:
        if formats:
            # Всегда показываем все форматы в карточке, даже если заранее
            # знаем только часть доступных. Реальная проверка наличия формата
            # происходит в send_format при вызове get_download_formats().
            await _edit_card_message(
                callback,
                card_text + "\n\n" + CHOOSE_FORMAT,
                reply_markup=book_card_formats(book_id),
            )
        else:
            await _edit_card_message(
                callback,
                card_text + "\n\n" + FILE_NOT_FOUND + "\n\n" + FILE_TRY_OTHER,
                reply_markup=back_to_book_keyboard(book_id),
            )
    except Exception:
        if formats:
            await safe_answer(
                callback.message,
                card_text + "\n\n" + CHOOSE_FORMAT,
                reply_markup=book_card_formats(book_id),
            )
        else:
            await safe_answer(
                callback.message,
                card_text + "\n\n" + FILE_NOT_FOUND + "\n\n" + FILE_TRY_OTHER,
                reply_markup=back_to_book_keyboard(book_id),
            )


@router.callback_query(F.data.startswith("back_to_book:"))
async def back_to_book(callback: CallbackQuery) -> None:
    """Вернуть карточку книги с кнопками Аудио/Читать/Купить/Похожие (текст уже в сообщении)."""
    book_id = callback.data.removeprefix("back_to_book:").strip()
    await callback.answer()
    current = _get_card_text(callback.message)
    for sep in ("\n\n" + FILE_NOT_FOUND, "\n\n" + CHOOSE_FORMAT, "\n\n" + FORMATS_SEARCHING):
        if sep in current:
            current = current.split(sep)[0].strip()
            break
    try:
        await _edit_card_message(callback, current, reply_markup=book_card_how_read(book_id))
    except Exception:
        await safe_answer(callback.message, current, reply_markup=book_card_how_read(book_id))


@router.callback_query(F.data.startswith("how:buy:"))
async def how_buy(callback: CallbackQuery) -> None:
    """Показать ссылки на магазины."""
    book_id = callback.data.removeprefix("how:buy:").strip()
    await callback.answer()
    title, author = await _get_title_author(callback, book_id)
    links = get_buy_links(title, author)
    await safe_answer(callback.message, "🛒 Где купить:", reply_markup=buy_links_keyboard(links))


def _safe_filename(name: str) -> str:
    """Убрать символы, недопустимые в имени файла."""
    return re.sub(r'[\\/*?:"<>|]', "_", (name or "").strip()).strip() or "book"


@router.callback_query(F.data.startswith("fmt:"))
async def send_format(callback: CallbackQuery) -> None:
    """Выбран формат → скачиваем файл и отправляем в чат; при ошибке — ссылка или FILE_NOT_FOUND."""
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer()
        return
    _, fmt, book_id = parts
    fmt = (fmt or "").strip().lower()
    book_id = (book_id or "").strip()
    await callback.answer()
    title, author = await _get_title_author(callback, book_id)
    if not title and not author:
        await callback.message.answer(FILE_NOT_FOUND, reply_markup=main_menu())
        return

    chat_id = callback.message.chat.id
    status_msg = await callback.message.answer(DOWNLOADING)
    await callback.bot.send_chat_action(chat_id, "upload_document")

    libgen_book = LIBGEN_BOOK_CACHE.get(book_id) if book_id else None
    if libgen_book and libgen_book.get("source") == "libgen" and libgen_book.get("available_formats"):
        formats = libgen_book["available_formats"]
    else:
        formats = await get_download_formats(title, author)
    url = formats.get(fmt) or formats.get(fmt.lower()) or formats.get(fmt.upper())

    if not url:
        # Формат не найден: сообщаем об этом, но не дублируем клавиатуру форматов.
        # Пользователь выберет другой формат из основной карточки книги.
        await status_msg.edit_text(FILE_NOT_FOUND)
        return

    session = get_session()
    result = await download_book(session, url)

    if not result:
        await status_msg.edit_text(DOWNLOAD_FAILED.format(url=url))
        return

    file_bytes, filename = result
    if not filename.lower().endswith(f".{fmt}"):
        filename = f"{_safe_filename(title)}_{_safe_filename(author)}.{fmt}"
    else:
        filename = _safe_filename(filename)

    await status_msg.delete()
    await callback.bot.send_document(
        chat_id,
        document=BufferedInputFile(file_bytes, filename=filename),
        caption=f"📖 {title}\n✍️ {author}\n📄 Формат: {fmt.upper()}",
        reply_markup=main_menu(),
    )
