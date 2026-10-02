from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db import connect, execute
from app.models import ItemCreate
from app.security import hash_session_token, new_session_token, normalize_email


def _normalize_row(row) -> dict:
    return dict(row)


def create_item(item: ItemCreate) -> dict:
    item_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        execute(
            connection,
            """
            INSERT INTO items (
                id, owner_id, kind, title, description, category, color, location,
                campus_zone, event_date, owner_name, contact, status, image_path,
                image_url, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                item_id,
                item.owner_id,
                item.kind,
                item.title,
                item.description,
                item.category,
                item.color,
                item.location,
                item.campus_zone,
                item.event_date,
                item.owner_name,
                item.contact,
                item.image_path,
                item.image_url,
                created_at,
            ),
        )
        row = execute(connection, "SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _normalize_row(row)


def create_user(email: str, display_name: str, password_hash: str) -> dict:
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        execute(
            connection,
            """
            INSERT INTO users (id, email, display_name, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                normalize_email(email),
                display_name.strip(),
                password_hash,
                created_at,
            ),
        )
        row = execute(connection, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _normalize_row(row)


def get_user_by_email(email: str) -> dict | None:
    with connect() as connection:
        row = execute(
            connection,
            "SELECT * FROM users WHERE email = ?",
            (normalize_email(email),),
        ).fetchone()
    return _normalize_row(row) if row else None


def get_user_by_session(token: str) -> dict | None:
    token_hash = hash_session_token(token)
    now = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        execute(connection, "DELETE FROM sessions WHERE expires_at <= ?", (now,))
        row = execute(
            connection,
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    return _normalize_row(row) if row else None


def create_session(user_id: str) -> tuple[str, dict]:
    settings = get_settings()
    token = new_session_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.session_days)
    with connect() as connection:
        execute(
            connection,
            """
            INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                hash_session_token(token),
                user_id,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        row = execute(
            connection,
            "SELECT * FROM sessions WHERE token_hash = ?",
            (hash_session_token(token),),
        ).fetchone()
    return token, _normalize_row(row)


def delete_session(token: str) -> None:
    with connect() as connection:
        execute(
            connection,
            "DELETE FROM sessions WHERE token_hash = ?",
            (hash_session_token(token),),
        )


def list_items(
    kind: str | None = None,
    status: str | None = "open",
    owner_id: str | None = None,
    category: str | None = None,
    q: str | None = None,
    campus_zone: str | None = None,
    cursor: str | None = None,
    limit: int = 25,
    org_id: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM items WHERE 1 = 1"
    params = []
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    if status:
        query += " AND status = ?"
        params.append(status)
    if owner_id:
        query += " AND owner_id = ?"
        params.append(owner_id)
    if category:
        query += " AND category = ?"
        params.append(category)
    if campus_zone:
        query += " AND campus_zone = ?"
        params.append(campus_zone)
    if q:
        query += " AND (lower(title) LIKE ? OR lower(description) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like])
    if org_id is not None:
        query += " AND org_id = ?"
        params.append(org_id)
    if cursor:
        query += " AND created_at < ?"
        params.append(cursor)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 100)))

    with connect() as connection:
        rows = execute(connection, query, tuple(params)).fetchall()
    return [_normalize_row(row) for row in rows]


def get_item(item_id: str) -> dict | None:
    with connect() as connection:
        row = execute(connection, "SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _normalize_row(row) if row else None


def resolve_item(item_id: str) -> dict | None:
    with connect() as connection:
        execute(connection, "UPDATE items SET status = 'resolved' WHERE id = ?", (item_id,))
        row = execute(connection, "SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _normalize_row(row) if row else None


def update_item(item_id: str, owner_id: str, updates: dict) -> dict | None:
    allowed_fields = {
        "kind",
        "title",
        "description",
        "category",
        "color",
        "location",
        "campus_zone",
        "event_date",
        "status",
    }
    clean_updates = {
        field: value
        for field, value in updates.items()
        if field in allowed_fields and value is not None
    }
    if not clean_updates:
        return get_item(item_id)

    assignments = ", ".join(f"{field} = ?" for field in clean_updates)
    params = tuple(clean_updates.values()) + (item_id, owner_id)
    with connect() as connection:
        execute(
            connection,
            f"UPDATE items SET {assignments} WHERE id = ? AND owner_id = ?",
            params,
        )
        row = execute(
            connection,
            "SELECT * FROM items WHERE id = ? AND owner_id = ?",
            (item_id, owner_id),
        ).fetchone()
    return _normalize_row(row) if row else None


def delete_item(item_id: str, owner_id: str) -> bool:
    with connect() as connection:
        cursor = execute(
            connection,
            "DELETE FROM items WHERE id = ? AND owner_id = ?",
            (item_id, owner_id),
        )
    return cursor.rowcount > 0
