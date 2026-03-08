"""Фикстуры pytest: временная БД, моки API-ключей."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_db_path(tmp_path: Path):
    """Временная директория и путь к тестовой БД."""
    return tmp_path / "test_library.db"


@pytest.fixture
def use_temp_db(temp_db_path, monkeypatch):
    """Подмена пути к БД на временный перед импортом database."""
    import config
    monkeypatch.setattr(config, "DB_PATH", temp_db_path)
    # database импортирует DB_PATH при загрузке — подменяем в модуле database
    import database as db
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)
    return temp_db_path
