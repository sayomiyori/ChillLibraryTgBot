"""Распознавание по обложке (/scan) и по цитате (/quote). Флоу: OCR/цитата → подтверждение → show_book_variants (мультиязычный список)."""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from messages import (
    RECOGNIZE_PHOTO_PROMPT,
    RECOGNIZE_QUOTE_PROMPT,
    QUOTE_NOT_FOUND,
    QUOTE_LOW_CONFIDENCE,
    COVER_NOT_RECOGNIZED,
    COVER_LOW_QUALITY,
    SEARCH_EMPTY,
    SEARCH_TYPING,
    BTN_SCAN_COVER,
    BTN_QUOTE,
    BTN_BACK,
    ERR_NO_API_KEY,
    COVER_EXTRACTED,
    COVER_LOW_CONFIDENCE,
)
from keyboards import (
    main_menu,
    back_only,
    cover_confirm_keyboard,
    manual_input_keyboard,
    cancel_keyboard,
    retry_or_accept_keyboard,
)
from config import GOOGLE_API_KEY, GROQ_API_KEY
from main import get_session
from services.vision import recognize_cover
from services.quote_service import find_by_quote
from handlers.search import show_book_variants

router = Router()
logger = logging.getLogger(__name__)


class RecognizeStates(StatesGroup):
    waiting_cover = State()
    waiting_cover_confirm = State()  # data: cover_title, cover_author
    waiting_manual_after_cover = State()
    waiting_quote = State()
    waiting_quote_confirm = State()  # data: quote_pending_result (title, author)


@router.message(Command("scan"))
@router.message(F.text == BTN_SCAN_COVER)
async def start_scan(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RecognizeStates.waiting_cover)
    await message.answer(RECOGNIZE_PHOTO_PROMPT, reply_markup=main_menu())


@router.message(RecognizeStates.waiting_cover, F.photo)
async def process_cover(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buf = await message.bot.download_file(file.file_path)
    if not buf:
        await state.set_state(RecognizeStates.waiting_cover)
        await message.answer(COVER_NOT_RECOGNIZED, reply_markup=manual_input_keyboard())
        return
    data = buf.read() if hasattr(buf, "read") else b""
    if not data:
        await state.set_state(RecognizeStates.waiting_cover)
        await message.answer(COVER_NOT_RECOGNIZED, reply_markup=manual_input_keyboard())
        return

    info = await recognize_cover(data)

    if not info:
        await state.set_state(RecognizeStates.waiting_cover)
        await message.answer(COVER_NOT_RECOGNIZED, reply_markup=manual_input_keyboard())
        return

    title = info.get("title", "").strip()
    author = info.get("author", "").strip()
    title_en = info.get("title_en", "").strip()
    if not title:
        await state.set_state(RecognizeStates.waiting_cover)
        await message.answer(COVER_LOW_QUALITY, reply_markup=manual_input_keyboard())
        return

    await state.update_data(cover_title=title, cover_author=author, cover_title_en=title_en)
    await state.set_state(RecognizeStates.waiting_cover_confirm)
    text = COVER_EXTRACTED.format(title=title, author=author or "—")
    await message.answer(
        text,
        reply_markup=cover_confirm_keyboard(title, author),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "cover_yes")
async def cover_confirm_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    title = (data.get("cover_title") or "").strip()

    if not title:
        await state.clear()
        await callback.message.answer(COVER_NOT_RECOGNIZED, reply_markup=manual_input_keyboard())
        return

    if not get_session():
        await state.clear()
        await callback.message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return

    await callback.message.answer(SEARCH_TYPING)
    await show_book_variants(callback.message, state, title, source="cover")


@router.callback_query(F.data == "cover_no")
async def cover_confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(RecognizeStates.waiting_manual_after_cover)
    await callback.message.answer(COVER_LOW_CONFIDENCE, reply_markup=back_only())


@router.message(RecognizeStates.waiting_manual_after_cover, F.text)
async def process_manual_after_cover(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer(COVER_LOW_CONFIDENCE, reply_markup=back_only())
        return
    if query == BTN_BACK:
        await state.clear()
        await message.answer(RECOGNIZE_PHOTO_PROMPT, reply_markup=main_menu())
        return
    if not GOOGLE_API_KEY:
        await message.answer(ERR_NO_API_KEY, reply_markup=main_menu())
        await state.clear()
        return
    await message.answer(SEARCH_TYPING)
    await show_book_variants(message, state, query, source="cover")


# ——— Цитата ———

@router.message(Command("quote"))
@router.message(F.text == BTN_QUOTE)
async def start_quote(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RecognizeStates.waiting_quote)
    await message.answer(RECOGNIZE_QUOTE_PROMPT, reply_markup=main_menu())


@router.message(RecognizeStates.waiting_quote, F.text)
@router.message(RecognizeStates.waiting_quote_confirm, F.text)
async def process_quote(message: Message, state: FSMContext) -> None:
    if not GROQ_API_KEY:
        await state.clear()
        await message.answer(ERR_NO_API_KEY, reply_markup=main_menu())
        return
    quote = (message.text or "").strip()
    if not quote:
        await message.answer(RECOGNIZE_QUOTE_PROMPT, reply_markup=main_menu())
        return
    info = await find_by_quote(quote)
    if not info:
        await state.set_state(RecognizeStates.waiting_quote)
        await message.answer(QUOTE_NOT_FOUND, reply_markup=cancel_keyboard())
        return
    confidence = info.get("confidence", 100)
    title = info.get("title", "")
    author = info.get("author", "")
    if confidence < 70:
        await state.update_data(quote_pending_result=info)
        await state.set_state(RecognizeStates.waiting_quote_confirm)
        await message.answer(QUOTE_LOW_CONFIDENCE, reply_markup=retry_or_accept_keyboard(info))
        return
    await message.answer(SEARCH_TYPING)
    await show_book_variants(message, state, title, source="quote")


@router.callback_query(F.data == "cancel_search")
async def cancel_search_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена поиска по цитате — главное меню."""
    await callback.answer()
    await state.clear()
    await callback.message.answer("Поиск отменён.", reply_markup=main_menu())


@router.callback_query(F.data == "retry_quote")
async def retry_quote_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Попробовать другую цитату."""
    await callback.answer()
    await state.set_state(RecognizeStates.waiting_quote)
    await callback.message.answer(RECOGNIZE_QUOTE_PROMPT, reply_markup=cancel_keyboard())


@router.callback_query(F.data == "accept_quote_result")
async def accept_quote_result_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь принял вариант книги при низкой уверенности по цитате."""
    await callback.answer()
    data = await state.get_data()
    info = data.get("quote_pending_result")
    if not info:
        await state.clear()
        await callback.message.answer(SEARCH_EMPTY, reply_markup=main_menu())
        return
    title = info.get("title", "")
    await callback.message.answer(SEARCH_TYPING)
    await show_book_variants(callback.message, state, title, source="quote")


@router.callback_query(F.data == "manual_title_input")
async def manual_title_input_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Ввести название книги вручную после неудачной обложки."""
    await callback.answer()
    await state.set_state(RecognizeStates.waiting_manual_after_cover)
    await callback.message.answer(COVER_LOW_CONFIDENCE, reply_markup=back_only())


@router.callback_query(F.data == "retry_cover")
async def retry_cover_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Сделать другое фото обложки."""
    await callback.answer()
    await state.set_state(RecognizeStates.waiting_cover)
    await callback.message.answer(RECOGNIZE_PHOTO_PROMPT, reply_markup=main_menu())
