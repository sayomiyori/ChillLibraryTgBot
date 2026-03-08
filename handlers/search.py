"""Поиск книги: запрос → карточка → Как хочешь читать? [Аудио] [Читать]."""
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message
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
    HOW_READ,
    CARD_RATING,
    CARD_YEAR,
    CARD_GENRE,
    CARD_DESC,
    BTN_FIND_BOOK,
    BTN_AUDIO_BOOKS,
    BTN_BACK,
    ERR_NO_API_KEY,
)
from keyboards import main_menu, back_only, book_card_how_read
from config import GOOGLE_API_KEY
from main import get_session
from services.search import search_book
from services.models import BookInfo
from handlers.helpers import safe_answer, safe_answer_photo

SEARCH_TIMEOUT = 30.0

router = Router()
logger = logging.getLogger(__name__)

# Кэш последней показанной книги по book_id (для callback Аудио/Читать)
BOOK_CACHE: dict[str, tuple[str, str]] = {}


class SearchStates(StatesGroup):
    waiting_query = State()


def _format_card(book: BookInfo) -> str:
    """Форматирование карточки из BookInfo."""
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
        desc = (book.description[:300] + "…") if len(book.description) > 300 else book.description
        lines.append(CARD_DESC.format(desc))
    return "\n".join(lines)


def format_book_card(book: dict) -> str:
    """Форматирование карточки из словаря (для совместимости и тестов)."""
    cats = book.get("categories")
    if not cats and book.get("genre"):
        cats = [book["genre"]]
    b = BookInfo(
        title=book.get("title", "Без названия"),
        author=book.get("author", "Неизвестный автор"),
        description=book.get("description", ""),
        rating=float(book.get("rating") or 0),
        cover_url=book.get("cover_url") or book.get("thumbnail", ""),
        categories=cats or [],
        year=int(book.get("year") or 0),
    )
    return _format_card(b)


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
    session = get_session()
    if not session:
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        await state.clear()
        return

    try:
        best, _similar = await asyncio.wait_for(
            search_book(session, query),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("search_book timeout %.0fs", SEARCH_TIMEOUT)
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        await state.clear()
        return

    if not best:
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        await state.clear()
        return

    book_id = best.id or ""
    BOOK_CACHE[book_id] = (best.title, best.author)
    text = _format_card(best)

    try:
        if best.cover_url:
            await safe_answer_photo(
                message,
                photo=best.cover_url,
                caption=text,
                reply_markup=book_card_how_read(book_id),
            )
        else:
            await safe_answer(message, text, reply_markup=book_card_how_read(book_id))
    except Exception:
        await safe_answer(message, text, reply_markup=book_card_how_read(book_id))

    await safe_answer(message, HOW_READ, reply_markup=main_menu())
    await state.clear()
