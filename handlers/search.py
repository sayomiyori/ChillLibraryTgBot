"""Поиск книги: запрос → карточка → Как хочешь читать? [Аудио] [Читать]."""
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from messages import (
    WELCOME,
    HELP,
    SEARCH_PROMPT,
    SEARCH_NO_QUERY,
    SEARCH_EMPTY,
    SEARCH_TYPING,
    CARD_RATING,
    CARD_YEAR,
    CARD_GENRE,
    CARD_DESC,
    BTN_FIND_BOOK,
    BTN_AUDIO_BOOKS,
    BTN_BACK,
    ERR_NO_API_KEY,
    MULTIPLE_RESULTS,
    MULTIPLE_EDITIONS,
    BOOK_NOT_FOUND,
)
from keyboards import main_menu, back_only, book_card_how_read, book_choice_keyboard, book_variants_keyboard
from config import GOOGLE_API_KEY
from main import get_session
from services.google_books import get_book_by_id, search_books_multilang
from services.models import BookInfo
from services.book_display import enrich_libgen_book
from handlers.helpers import safe_answer, safe_answer_photo

SEARCH_TIMEOUT = 60.0

router = Router()
logger = logging.getLogger(__name__)

DESCRIPTION_LIMIT = 200  # в карточке показываем первые 200 символов; обрезка по границе слова

# Кэш последней показанной книги по book_id (для callback Аудио/Читать)
BOOK_CACHE: dict[str, tuple[str, str]] = {}
# Кэш полного словаря LibGen-книг (для использования available_formats без повторного запроса)
LIBGEN_BOOK_CACHE: dict[str, dict] = {}


class SearchStates(StatesGroup):
    waiting_query = State()


def _format_card(book: BookInfo, description_limit: int | None = DESCRIPTION_LIMIT) -> str:
    """Форматирование карточки из BookInfo. description_limit=None — полное описание (для раскрытия)."""
    lines = [
        f"📖 {book.title}",
        f"✍️ {book.author}",
        "",
    ]
    if book.rating > 0:
        lines.append(CARD_RATING.format(book.rating))
    if book.year:
        lines.append(CARD_YEAR.format(book.year))
    if book.categories:
        lines.append(CARD_GENRE.format(", ".join(book.categories)))
    lines.append("")
    if book.description:
        raw = book.description
        if description_limit is not None and len(raw) > description_limit:
            truncated = raw[:description_limit]
            # Обрезка по границе слова (если есть пробел)
            if " " in truncated:
                truncated = truncated.rsplit(" ", 1)[0]
            short = truncated + "..."
        else:
            short = raw
        lines.append(CARD_DESC.format(short))
    return "\n".join(lines)


def book_from_dict(book: dict) -> BookInfo:
    """Собрать BookInfo из словаря (например, из search_books)."""
    cats = book.get("categories")
    if not cats and book.get("genre"):
        cats = [book["genre"]] if isinstance(book.get("genre"), str) else []
    return BookInfo(
        id=book.get("id"),
        title=book.get("title", "Без названия"),
        author=book.get("author", "Неизвестный автор"),
        description=book.get("description", ""),
        rating=float(book.get("rating") or 0),
        cover_url=book.get("cover_url") or book.get("thumbnail", ""),
        categories=cats or [],
        year=int(book.get("year") or 0),
        preview_link=book.get("preview_link"),
    )


def format_book_card(book: dict) -> str:
    """Форматирование карточки из словаря (для совместимости и тестов)."""
    return _format_card(book_from_dict(book))


async def show_book_card(message: Message, book: dict) -> None:
    """Показать одну карточку книги (по словарю из search_books_multilang или get_book_by_id)."""
    book_id = (book.get("id") or "").strip()
    if book.get("source") == "libgen":
        session = get_session()
        if session:
            book = await enrich_libgen_book(session, book)
        if book_id and book.get("available_formats"):
            LIBGEN_BOOK_CACHE[book_id] = book
    info = book_from_dict(book)
    if book_id:
        BOOK_CACHE[book_id] = (info.title, info.author)
    text = _format_card(info)
    has_long = len(info.description or "") > DESCRIPTION_LIMIT
    try:
        if info.cover_url:
            await safe_answer_photo(
                message,
                photo=info.cover_url,
                caption=text,
                reply_markup=book_card_how_read(book_id, has_long_description=has_long),
            )
        else:
            await safe_answer(message, text, reply_markup=book_card_how_read(book_id, has_long_description=has_long))
    except Exception:
        await safe_answer(message, text, reply_markup=book_card_how_read(book_id, has_long_description=has_long))


async def show_book_variants(
    message: Message,
    state: FSMContext,
    title: str,
    source: str,  # "title" | "cover" | "quote"
) -> None:
    """
    Единая точка для всех способов поиска: по названию, обложке, цитате.
    Ищет 3–5 языковых вариантов, показывает список или одну карточку.
    """
    session = get_session()
    if not session:
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return
    try:
        books = await asyncio.wait_for(search_books_multilang(session, title), timeout=SEARCH_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("search_books_multilang timeout")
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return
    except Exception as e:
        logger.error("search_books_multilang: %s", e)
        await message.answer(BOOK_NOT_FOUND, reply_markup=main_menu())
        return

    if not books:
        await message.answer(BOOK_NOT_FOUND, reply_markup=main_menu())
        return

    if len(books) == 1:
        await show_book_card(message, books[0])
        return

    await state.update_data(search_results={b["id"]: b for b in books})
    await message.answer(
        MULTIPLE_EDITIONS,
        reply_markup=book_variants_keyboard(books),
    )


def _safe_filename(title: str, fmt: str) -> str:
    """Имя файла без недопустимых символов (для тестов и возможной отправки файла)."""
    ext = (fmt or "txt").lower()
    safe = "".join(c for c in (title or "book") if c.isalnum() or c in " _-.")[:80]
    return (safe.strip() or "book") + "." + ext


@router.message(Command("start"))
@router.message(F.text == BTN_BACK)
async def cmd_start_or_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu())


@router.message(Command("search"))
@router.message(F.text.in_([BTN_FIND_BOOK, BTN_AUDIO_BOOKS]))
async def start_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_query)
    await message.answer(SEARCH_PROMPT, reply_markup=back_only())


@router.message(SearchStates.waiting_query, F.text)
async def process_search(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer(SEARCH_NO_QUERY)
        return
    if not GOOGLE_API_KEY:
        await message.answer(ERR_NO_API_KEY, reply_markup=main_menu())
        await state.clear()
        return
    await message.answer(SEARCH_TYPING)
    await show_book_variants(message, state, query, source="title")


@router.callback_query(F.data.startswith("select_book:"))
async def on_book_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор издания из списка языковых вариантов (поиск по названию, обложке, цитате)."""
    book_id = (callback.data.removeprefix("select_book:") or "").strip()
    await callback.answer()
    if not book_id:
        return
    data = await state.get_data()
    book = data.get("search_results", {}).get(book_id)
    if not book:
        session = get_session()
        if session:
            bi = await get_book_by_id(session, book_id)
            book = bi.to_dict() if bi else None
    if not book:
        await callback.message.answer(BOOK_NOT_FOUND, reply_markup=main_menu())
        await state.clear()
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await state.clear()
    await show_book_card(callback.message, book)


@router.callback_query(F.data.startswith("fulldesc:"))
async def show_full_description(callback: CallbackQuery) -> None:
    """Раскрыть описание: редактируем то же сообщение, подставляем полный текст, убираем кнопку «Показать ещё»."""
    book_id = (callback.data.removeprefix("fulldesc:") or "").strip()
    await callback.answer()
    if not book_id:
        return
    session = get_session()
    if not session:
        return
    book = await get_book_by_id(session, book_id)
    if not book:
        return
    full_text = _format_card(book, description_limit=None)
    reply_markup = book_card_how_read(book_id, has_long_description=False)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=full_text, reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text=full_text, reply_markup=reply_markup)
    except Exception:
        pass