"""Shared fixtures: a throwaway SQLite engine per test."""

from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.db.engine import make_engine


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """A fresh file-backed SQLite database with all tables created."""
    return make_engine(f"sqlite:///{tmp_path / 'test.db'}")
