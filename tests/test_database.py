"""Тесты database: init_db, save_query, save_view, get_recent_views."""
import pytest

# Импорт после фикстуры не нужен — фикстура патчит config/database при загрузке теста


def test_init_db_creates_tables(use_temp_db):
    """init_db создаёт таблицы и не падает."""
    import database as db
    db.init_db()
    assert use_temp_db.exists()


def test_save_and_get_views(use_temp_db):
    """save_view сохраняет, get_recent_views возвращает историю (последние первые)."""
    import database as db
    db.init_db()
    db.save_view(user_id=1, book_id="id1", title="Книга 1", author="Автор 1")
    db.save_view(user_id=1, book_id="id2", title="Книга 2", author="Автор 2")
    recent = db.get_recent_views(user_id=1, limit=10)
    assert len(recent) == 2
    book_ids = [r["book_id"] for r in recent]
    assert "id1" in book_ids and "id2" in book_ids
    assert recent[0]["title"] in ("Книга 1", "Книга 2")
    assert recent[1]["title"] in ("Книга 1", "Книга 2")


def test_save_query(use_temp_db):
    """save_query записывает поисковый запрос."""
    import database as db
    db.init_db()
    db.save_query(user_id=1, query="Мастер и Маргарита")
    conn = db.get_connection()
    cur = conn.execute("SELECT query FROM user_queries WHERE user_id = 1")
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "Мастер и Маргарита"


def test_get_recent_views_respects_limit(use_temp_db):
    """get_recent_views ограничивает количество записей."""
    import database as db
    db.init_db()
    for i in range(5):
        db.save_view(user_id=1, book_id=f"id{i}", title=f"Книга {i}", author="Автор")
    recent = db.get_recent_views(user_id=1, limit=2)
    assert len(recent) == 2
