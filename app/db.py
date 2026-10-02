from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL CHECK(kind IN ('lost', 'found')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    color TEXT NOT NULL,
    location TEXT NOT NULL,
    campus_zone TEXT NOT NULL DEFAULT 'other',
    event_date TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL,
    contact TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resolved')),
    image_path TEXT NOT NULL,
    image_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, zones TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('admin', 'staff', 'user')),
    PRIMARY KEY (user_id, org_id)
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY, item_id TEXT NOT NULL, org_id TEXT NOT NULL, claimant_id TEXT NOT NULL,
    answer TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, decided_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, message TEXT NOT NULL,
    item_id TEXT NOT NULL DEFAULT '', is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY, org_id TEXT NOT NULL, user_id TEXT NOT NULL DEFAULT '', action TEXT NOT NULL,
    item_id TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_org ON claims(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_items_kind_status ON items(kind, status);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_location ON items(location);
CREATE INDEX IF NOT EXISTS idx_items_event_date ON items(event_date);
"""


def connect(db_path: Path | None = None):
    settings = get_settings()
    if settings.database_url and db_path is None:
        return _connect_postgres(settings.database_url)

    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def execute(connection, query: str, params: tuple[Any, ...] = ()):
    if _is_postgres(connection):
        query = query.replace("?", "%s")
    return connection.execute(query, params)


def initialize_database(db_path: Path | None = None) -> None:
    with connect(db_path) as connection:
        for statement in _schema_statements():
            execute(connection, statement)
        _ensure_column(connection, "items", "owner_id", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "items", "campus_zone", "TEXT NOT NULL DEFAULT 'other'")
        _ensure_column(connection, "items", "event_date", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "items", "image_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "organizations", "join_code", "TEXT NOT NULL DEFAULT ''")
        for col, default in (("org_id", "''"), ("lifecycle", "'reported'"), ("private_detail", "''"),
                             ("storage_location", "''"), ("returned_at", "''")):
            _ensure_column(connection, "items", col, f"TEXT NOT NULL DEFAULT {default}")


def _connect_postgres(database_url: str):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - only hit in cloud config without psycopg
        raise RuntimeError(
            "DATABASE_URL is set, but psycopg is not installed. "
            "Install the project dependencies with `pip install -e .`."
        ) from exc

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return psycopg.connect(database_url, row_factory=dict_row, prepare_threshold=None)


def _ensure_column(connection, table: str, column: str, definition: str) -> None:
    if _is_postgres(connection):
        row = execute(
            connection,
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = ? AND column_name = ?
            """,
            (table, column),
        ).fetchone()
    else:
        row = next(
            (
                existing
                for existing in execute(connection, f"PRAGMA table_info({table})").fetchall()
                if existing["name"] == column
            ),
            None,
        )

    if not row:
        execute(connection, f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _is_postgres(connection) -> bool:
    return connection.__class__.__module__.startswith("psycopg")


def _schema_statements() -> list[str]:
    return [statement.strip() for statement in SCHEMA.split(";") if statement.strip()]
