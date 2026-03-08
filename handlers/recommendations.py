"""Похожие книги: Gemini → поиск по каждой → карусель карточек. И открытие книги по «Открыть»."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from messages import RECOMMEND_HEADING, RECOMMEND_ERROR, RECOMMEND_EMPTY, HOW_READ
from keyboards import main_menu, book_card_short, book_card_how_read
from config import MAX_RECOMMENDATIONS
from main import get_session
from services.gemini import get_similar_books
from services.search import search_book
from services.google_books import get_book_by_id
from handlers.search import BOOK_CACHE, _format_card

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("similar:"))
async def similar_books(callback: CallbackQuery) -> None:
    """Кнопка «Похожие книги»: Gemini даёт список → поиск каждой → карточки."""
    book_id = callback.data.removeprefix("similar:").strip()
    await callback.answer()
    title, author = BOOK_CACHE.get(book_id, ("", ""))
    if not title and not author:
        await callback.message.answer(RECOMMEND_EMPTY, reply_markup=main_menu())
        return
    similar_list = await get_similar_books(title, author, limit=MAX_RECOMMENDATIONS)
    if not similar_list:
        await callback.message.answer(RECOMMEND_EMPTY, reply_markup=main_menu())
        return
    session = get_session()
    if not session:
        await callback.message.answer(RECOMMEND_ERROR, reply_markup=main_menu())
        return
    await callback.message.answer(RECOMMEND_HEADING, reply_markup=main_menu())
    for item in similar_list:
        t = item.get("title", "")
        a = item.get("author", "")
        if not t:
            continue
        best, _ = await search_book(session, f"{t} {a}")
        if not best:
            await callback.message.answer(f"📖 {t} — {a}\n(не найдено в каталоге)")
            continue
        bid = best.id or ""
        BOOK_CACHE[bid] = (best.title, best.author)
        text = _format_card(best)
        try:
            if best.cover_url:
                await callback.message.answer_photo(
                    photo=best.cover_url,
                    caption=text,
                    reply_markup=book_card_short(bid, best.title, best.author),
                )
            else:
                await callback.message.answer(
                    text,
                    reply_markup=book_card_short(bid, best.title, best.author),
                )
        except Exception:
            await callback.message.answer(
                text,
                reply_markup=book_card_short(bid, best.title, best.author),
            )


@router.callback_query(F.data.startswith("open:"))
async def open_book(callback: CallbackQuery) -> None:
    """Открыть полную карточку книги (из рекомендаций)."""
    book_id = callback.data.removeprefix("open:").strip()
    await callback.answer()
    session = get_session()
    if not session:
        return
    book = await get_book_by_id(session, book_id)
    if not book:
        await callback.message.answer(RECOMMEND_EMPTY, reply_markup=main_menu())
        return
    BOOK_CACHE[book_id] = (book.title, book.author)
    text = _format_card(book)
    try:
        if book.cover_url:
            await callback.message.answer_photo(
                photo=book.cover_url,
                caption=text,
                reply_markup=book_card_how_read(book_id),
            )
        else:
            await callback.message.answer(text, reply_markup=book_card_how_read(book_id))
    except Exception:
        await callback.message.answer(text, reply_markup=book_card_how_read(book_id))
    await callback.message.answer(HOW_READ, reply_markup=main_menu())
