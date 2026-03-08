"""Распознавание по обложке (/scan) и по цитате (/quote)."""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from messages import (
    RECOGNIZE_PHOTO_PROMPT,
    RECOGNIZE_QUOTE_PROMPT,
    RECOGNIZE_ERROR,
    RECOGNIZE_NOT_SURE,
    RECOGNIZED_BOOK,
    HOW_READ,
    SEARCH_EMPTY,
    BTN_SCAN_COVER,
    BTN_QUOTE,
    ERR_NO_API_KEY,
)
from keyboards import main_menu, book_card_how_read
from config import GEMINI_API_KEY
from main import get_session
from services.vision import recognize_cover
from services.gemini import get_book_from_quote
from services.search import search_book
from handlers.search import BOOK_CACHE, _format_card

router = Router()
logger = logging.getLogger(__name__)


class RecognizeStates(StatesGroup):
    waiting_cover = State()
    waiting_quote = State()


@router.message(Command("scan"))
@router.message(F.text == BTN_SCAN_COVER)
async def start_scan(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RecognizeStates.waiting_cover)
    await message.answer(RECOGNIZE_PHOTO_PROMPT, reply_markup=main_menu())


@router.message(RecognizeStates.waiting_cover, F.photo)
async def process_cover(message: Message, state: FSMContext) -> None:
    await state.clear()
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buf = await message.bot.download_file(file.file_path)
    if not buf:
        await message.answer(RECOGNIZE_ERROR, reply_markup=main_menu())
        return
    data = buf.read() if hasattr(buf, "read") else b""
    if not data:
        await message.answer(RECOGNIZE_ERROR, reply_markup=main_menu())
        return
    info = await recognize_cover(data)
    if not info:
        await message.answer(RECOGNIZE_ERROR, reply_markup=main_menu())
        return
    title, author = info.get("title", ""), info.get("author", "")
    await message.answer(RECOGNIZED_BOOK.format(title, author))
    session = get_session()
    if not session:
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return
    best, _ = await search_book(session, f"{title} {author}")
    if not best:
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return
    book_id = best.id or ""
    BOOK_CACHE[book_id] = (best.title, best.author)
    text = _format_card(best)
    try:
        if best.cover_url:
            await message.answer_photo(
                photo=best.cover_url,
                caption=text,
                reply_markup=book_card_how_read(book_id),
            )
        else:
            await message.answer(text, reply_markup=book_card_how_read(book_id))
    except Exception:
        await message.answer(text, reply_markup=book_card_how_read(book_id))
    await message.answer(HOW_READ, reply_markup=main_menu())


@router.message(Command("quote"))
@router.message(F.text == BTN_QUOTE)
async def start_quote(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RecognizeStates.waiting_quote)
    await message.answer(RECOGNIZE_QUOTE_PROMPT, reply_markup=main_menu())


@router.message(RecognizeStates.waiting_quote, F.text)
async def process_quote(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not GEMINI_API_KEY:
        await message.answer(ERR_NO_API_KEY, reply_markup=main_menu())
        return
    quote = (message.text or "").strip()
    if not quote:
        await message.answer(RECOGNIZE_QUOTE_PROMPT, reply_markup=main_menu())
        return
    info = await get_book_from_quote(quote)
    if not info:
        await message.answer(RECOGNIZE_ERROR, reply_markup=main_menu())
        return
    confidence = info.get("confidence", 100)
    title = info.get("title", "")
    author = info.get("author", "")
    if confidence < 70:
        await message.answer(RECOGNIZE_NOT_SURE.format(title or "эта книга"), reply_markup=main_menu())
        return
    session = get_session()
    if not session:
        await message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return
    best, _ = await search_book(session, f"{title} {author}")
    if not best:
        await message.answer(RECOGNIZE_NOT_SURE.format(title or "эта книга"), reply_markup=main_menu())
        return
    book_id = best.id or ""
    BOOK_CACHE[book_id] = (best.title, best.author)
    text = _format_card(best)
    try:
        if best.cover_url:
            await message.answer_photo(
                photo=best.cover_url,
                caption=text,
                reply_markup=book_card_how_read(book_id),
            )
        else:
            await message.answer(text, reply_markup=book_card_how_read(book_id))
    except Exception:
        await message.answer(text, reply_markup=book_card_how_read(book_id))
    await message.answer(HOW_READ, reply_markup=main_menu())
