"""Конфигурация бота — токены и настройки."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "data" / "cache"
DB_PATH = DATA_DIR / "library_bot.db"

# Токены
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")       # Google Books API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")      # Gemini — рекомендации, цитаты, обложки
GOOGLE_VISION_KEY = os.getenv("GOOGLE_VISION_KEY", "")  # Vision API — распознавание обложек
GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX", "")  # Google Custom Search Engine ID (fallback поиска файлов)

MAX_SEARCH_RESULTS = 10
MAX_RECOMMENDATIONS = 5

# Кэш файлов: TTL 7 дней
CACHE_TTL_DAYS = 7
FILE_CHUNK_VERIFY = 8192  # 8 KB для верификации
CONNECT_TIMEOUT = 1.0
READ_TIMEOUT = 3.0
