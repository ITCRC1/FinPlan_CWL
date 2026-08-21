"""Tests for DATABASE_URL normalization (managed-provider compatibility)."""
from app.db import normalize_database_url


def test_postgresql_scheme_gets_asyncpg():
    assert normalize_database_url("postgresql://u:p@host:5432/db") == \
        "postgresql+asyncpg://u:p@host:5432/db"


def test_postgres_scheme_gets_asyncpg():
    assert normalize_database_url("postgres://u:p@host/db") == \
        "postgresql+asyncpg://u:p@host/db"


def test_already_asyncpg_unchanged():
    url = "postgresql+asyncpg://u:p@host/db"
    assert normalize_database_url(url) == url


def test_empty_unchanged():
    assert normalize_database_url("") == ""
