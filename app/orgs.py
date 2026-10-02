"""Multi-tenant helpers: roles, audit log, notifications, match recording."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db import connect, execute

STAFF = ("admin", "staff")
ALL_ROLES = ("admin", "staff", "user")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def audit(conn, org_id, user_id, action, item_id="", detail="") -> None:
    execute(conn, "INSERT INTO audit_logs (id, org_id, user_id, action, item_id, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)", (new_id(), org_id, user_id, action, item_id, detail, now()))


def notify(conn, user_id, message, item_id="") -> None:
    execute(conn, "INSERT INTO notifications (id, user_id, message, item_id, is_read, created_at)"
            " VALUES (?, ?, ?, ?, 0, ?)", (new_id(), user_id, message, item_id, now()))


def role_of(conn, user_id, org_id):
    row = execute(conn, "SELECT role FROM memberships WHERE user_id = ? AND org_id = ?",
                  (user_id, org_id)).fetchone()
    return row["role"] if row else None


def require_role(conn, user, org_id, roles=ALL_ROLES) -> str:
    role = role_of(conn, user["id"], org_id)
    if role not in roles:
        raise HTTPException(status_code=403, detail="You do not have access to this institution.")
    return role


def record_matches(item: dict, matches) -> None:
    """Audit + notify + advance lifecycle for each candidate match (same institution only)."""
    with connect() as c:
        audit(c, item["org_id"], item["owner_id"], "item_created", item["id"], item["title"])
        for m in matches:
            other = m.item
            audit(c, item["org_id"], "", "match_generated", item["id"],
                  f"{item['title']} ~ {other['title']} (score {m.score:.2f})")
            for it in (item, other):
                execute(c, "UPDATE items SET lifecycle = 'potential_match' WHERE id = ?"
                        " AND lifecycle = 'reported'", (it["id"],))
            lost = item if item["kind"] == "lost" else other
            notify(c, lost["owner_id"],
                   f"You may have a match for your lost item: {lost['title']}", lost["id"])
