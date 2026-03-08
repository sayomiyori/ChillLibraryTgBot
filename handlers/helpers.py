"""Вспомогательные функции: отправка с обработкой флуд-контроля (RetryAfter)."""
import asyncio
import logging
from typing import Any

from aiogram.exceptions import TelegramRetryAfter

logger = logging.getLogger(__name__)


async def safe_answer(target: Any, text: str, **kwargs: Any) -> Any:
    """
    Отправка ответа с одной повторной попыткой при RetryAfter.
    target — объект с методом .answer(text, **kwargs) (Message или callback.message).
    """
    try:
        return await target.answer(text, **kwargs)
    except TelegramRetryAfter as e:
        wait = min(int(e.retry_after), 60)
        logger.warning("RetryAfter %s сек, ждём и повторяем отправку", wait)
        await asyncio.sleep(wait)
        return await target.answer(text, **kwargs)


async def safe_answer_photo(target: Any, photo: str, caption: str | None = None, **kwargs: Any) -> Any:
    """Отправка фото с одной повторной попыткой при RetryAfter."""
    try:
        return await target.answer_photo(photo=photo, caption=caption, **kwargs)
    except TelegramRetryAfter as e:
        wait = min(int(e.retry_after), 60)
        logger.warning("RetryAfter %s сек (photo), ждём и повторяем", wait)
        await asyncio.sleep(wait)
        return await target.answer_photo(photo=photo, caption=caption, **kwargs)
