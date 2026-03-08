"""
Точка входа — Telegram-бот библиотеки.
Один aiohttp.ClientSession на всё приложение; trust_env=True для системного прокси (WARP/Zapret).
"""
import asyncio
import logging
import ssl
import sys
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import aiohttp
from aiohttp import ClientSession, TCPConnector
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.backoff import BackoffConfig

from config import BOT_TOKEN

# Ограничиваем backoff при флуд-контроле: макс. задержка 60 сек, не бесконечный рост
POLLING_BACKOFF = BackoffConfig(min_delay=1.0, max_delay=60.0, factor=1.5, jitter=0.1)
from database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Общая сессия aiohttp для всех запросов (устанавливается в on_startup)
_app_session: Optional[ClientSession] = None


def get_session() -> Optional[ClientSession]:
    """Вернуть общую aiohttp-сессию (для обработчиков)."""
    return _app_session


async def check_connectivity() -> None:
    """Проверка доступности сайтов (не блокирует старт)."""
    try:
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_ctx = True
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with ClientSession(connector=TCPConnector(ssl=ssl_ctx), trust_env=True) as session:
            for url in ("https://archive.org", "https://httpbin.org/ip"):
                try:
                    async with session.get(url, timeout=timeout) as r:
                        logger.info("%s -> %s", url, r.status)
                except Exception as e:
                    logger.debug("%s -> %s", url, e)
    except Exception as e:
        logger.debug("check_connectivity: %s", e)


async def on_startup(bot: Bot) -> None:
    global _app_session
    try:
        import certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_context = True
    connector = TCPConnector(
        ssl=ssl_context,
        limit=100,
        limit_per_host=10,
        use_dns_cache=True,
        ttl_dns_cache=300,
        force_close=False,
    )
    _app_session = ClientSession(connector=connector, trust_env=True)
    asyncio.create_task(check_connectivity())


async def on_shutdown(bot: Bot) -> None:
    global _app_session
    if _app_session and not _app_session.closed:
        await _app_session.close()
        _app_session = None


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан.")
        sys.exit(1)
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    from handlers import search, files as files_handler, recognize, recommendations
    dp.include_router(search.router)
    dp.include_router(files_handler.router)
    dp.include_router(recognize.router)
    dp.include_router(recommendations.router)

    logger.info("Бот запущен.")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        handle_signals=True,
        backoff_config=POLLING_BACKOFF,
    )


if __name__ == "__main__":
    asyncio.run(main())
