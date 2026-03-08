"""SQLite — история запросов и просмотров пользователя."""
import sqlite3
from pathlib import Path
from typing import Optional

from config import DB_PATH


def ensure_db_dir() -> None:
    """Создать директорию для БД при необходимости."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Подключение к SQLite."""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создать таблицы при первом запуске."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id TEXT NOT NULL,
                title TEXT,
                author TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_views_user ON user_views(user_id);
            CREATE INDEX IF NOT EXISTS idx_queries_user ON user_queries(user_id);
        """)
        conn.commit()
    finally:
        conn.close()


def save_query(user_id: int, query: str) -> None:
    """Сохранить поисковый запрос пользователя."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO user_queries (user_id, query) VALUES (?, ?)",
            (user_id, query.strip()),
        )
        conn.commit()
    finally:
        conn.close()


def save_view(user_id: int, book_id: str, title: str = "", author: str = "") -> None:
    """Сохранить просмотр книги пользователем."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO user_views (user_id, book_id, title, author)
               VALUES (?, ?, ?, ?)""",
            (user_id, book_id, title or "", author or ""),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_views(user_id: int, limit: int = 20) -> list[dict]:
    """Последние просмотренные книги пользователя."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT book_id, title, author FROM user_views
               WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
