from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Response, UploadFile

from app.config import get_settings
from app.db import connect, execute
from app.models import ItemCreate
from app.orgs import record_matches, require_role
from app.repository import (
    create_item,
    create_session,
    create_user,
    delete_item,
    delete_session,
    get_item,
    get_user_by_email,
    get_user_by_session,
    list_items,
    resolve_item,
    update_item,
)
from app.security import hash_password, normalize_email, verify_password
from app.services.image_store import save_upload
from app.services.matcher import ImageMatcher, VisionDependencyError
from app.services.search import find_matches_for_image, find_matches_for_item

CATEGORIES = {"electronics", "clothing", "id_cards", "keys", "bags", "jewelry", "other"}
IMAGE_UPLOAD = File(...)
OPTIONAL_TARGET_KIND = Form(None)

router = APIRouter()
SESSION_COOKIE_NAME = get_settings().session_cookie_name
SessionCookie = Annotated[Optional[str], Cookie(alias=SESSION_COOKIE_NAME)]


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "created_at": user["created_at"],
    }


def public_item(item: dict) -> dict:
    hidden = dict(item)
    hidden.pop("owner_id", None)
    hidden.pop("contact", None)
    hidden.pop("private_detail", None)
    hidden.pop("storage_location", None)
    if hidden.get("image_url"):
        hidden["image_url"] = hidden["image_url"]
    elif hidden.get("image_path"):
        hidden["image_url"] = f"/uploads/{Path(hidden['image_path']).name}"
    hidden["contact_policy"] = "hidden_until_match_confirmation"
    return hidden


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=get_settings().session_cookie_name,
        path="/",
        samesite="strict",
    )


def current_user(session_token: SessionCookie = None) -> dict:
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = get_user_by_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


CurrentUser = Annotated[dict, Depends(current_user)]


def _require_member(token, org_id: str, roles=("admin", "staff", "user")) -> dict:
    user = current_user(token)
    with connect() as c:
        require_role(c, user, org_id, roles)
    return user


def public_matches(matches) -> list[dict]:
    return [
        {
            "item": public_item(match.item),
            "score": match.score,
            "explanation": match.explanation,
        }
        for match in matches
    ]


def ensure_owner(item_id: str, user: dict) -> dict:
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.get("owner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the reporter can manage this item")
    return item


def validate_item_fields(updates: dict) -> dict:
    if updates.get("kind") is not None and updates["kind"] not in {"lost", "found"}:
        raise HTTPException(status_code=400, detail="kind must be lost or found")
    if updates.get("status") is not None and updates["status"] not in {"open", "resolved"}:
        raise HTTPException(status_code=400, detail="status must be open or resolved")
    if updates.get("category") is not None and updates["category"] not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CATEGORIES)}")
    if updates.get("event_date"):
        try:
            date.fromisoformat(updates["event_date"])
        except ValueError as exc:
            detail = "event_date must use YYYY-MM-DD format"
            raise HTTPException(status_code=400, detail=detail) from exc
    return updates


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/auth/signup", status_code=201)
def api_signup(
    response: Response,
    display_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
) -> dict:
    normalized_email = normalize_email(email)
    if "@" not in normalized_email or "." not in normalized_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if not display_name.strip():
        raise HTTPException(status_code=400, detail="Display name is required.")

    try:
        user = create_user(normalized_email, display_name, hash_password(password))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        detail = "An account with this email already exists."
        raise HTTPException(status_code=409, detail=detail) from exc
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            detail = "An account with this email already exists."
            raise HTTPException(status_code=409, detail=detail) from exc
        raise

    token, _ = create_session(user["id"])
    set_session_cookie(response, token)
    return {"user": public_user(user)}


@router.post("/auth/login")
def api_login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
) -> dict:
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token, _ = create_session(user["id"])
    set_session_cookie(response, token)
    return {"user": public_user(user)}


@router.post("/auth/logout")
def api_logout(
    response: Response,
    session_token: SessionCookie = None,
) -> dict:
    if session_token:
        delete_session(session_token)
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/auth/me")
def api_me(user: CurrentUser) -> dict:
    return {"user": public_user(user)}


@router.get("/items/mine")
@router.get("/listings/mine")
def api_my_items(
    user: CurrentUser,
    status: Optional[str] = None,
) -> dict:
    if status not in {None, "open", "resolved"}:
        raise HTTPException(status_code=400, detail="status must be open or resolved")
    items = list_items(owner_id=user["id"], status=status, limit=100)
    return {"items": [public_item(item) for item in items]}


@router.get("/items")
@router.get("/listings")
def api_list_items(
    kind: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    campus_zone: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 25,
    org_id: Optional[str] = None,
    session_token: SessionCookie = None,
) -> dict:
    kind = kind or type
    if org_id:
        _require_member(session_token, org_id)
    if kind not in {None, "lost", "found"}:
        raise HTTPException(status_code=400, detail="kind must be lost or found")
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CATEGORIES)}")
    items = list_items(
        kind=kind,
        category=category,
        q=q,
        campus_zone=campus_zone,
        cursor=cursor,
        limit=limit,
        org_id=org_id or "",
    )
    next_cursor = items[-1]["created_at"] if len(items) == min(max(limit, 1), 100) else None
    return {"items": [public_item(item) for item in items], "next_cursor": next_cursor}


@router.get("/items/{item_id}")
@router.get("/listings/{item_id}")
def api_get_item(item_id: str, session_token: SessionCookie = None) -> dict:
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.get("org_id"):
        _require_member(session_token, item["org_id"])
    return public_item(item)


@router.post("/items", status_code=201)
@router.post("/listings", status_code=201)
async def api_create_item(
    user: CurrentUser,
    kind: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    color: str = Form(...),
    location: str = Form(...),
    campus_zone: str = Form("other"),
    event_date: str = Form(...),
    owner_name: Optional[str] = Form(None),
    contact: Optional[str] = Form(None),
    org_id: str = Form(""),
    private_detail: str = Form(""),
    storage_location: str = Form(""),
    image: UploadFile = IMAGE_UPLOAD,
) -> dict:
    if kind not in {"lost", "found"}:
        raise HTTPException(status_code=400, detail="kind must be lost or found")
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CATEGORIES)}")
    try:
        date.fromisoformat(event_date)
    except ValueError as exc:
        detail = "event_date must use YYYY-MM-DD format"
        raise HTTPException(status_code=400, detail=detail) from exc

    org_id = org_id.strip()
    if org_id:  # staff report found items; any member may report lost ones
        with connect() as c:
            require_role(c, user, org_id, ("admin", "staff") if kind == "found" else ("admin", "staff", "user"))
    try:
        stored_image = await save_upload(image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        ImageMatcher().load_image(stored_image.path)
    except VisionDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = create_item(
        ItemCreate(
            kind=kind,
            title=title.strip(),
            description=description.strip(),
            category=category.strip().lower(),
            color=color.strip().lower(),
            location=location.strip(),
            campus_zone=campus_zone.strip().lower() or "other",
            event_date=event_date,
            owner_id=user["id"],
            owner_name=(owner_name or user["display_name"]).strip(),
            contact=(contact or user["email"]).strip(),
            image_path=str(stored_image.path),
            image_url=stored_image.url,
        )
    )
    if org_id:
        with connect() as c:
            execute(c, "UPDATE items SET org_id = ?, private_detail = ?, storage_location = ? WHERE id = ?",
                    (org_id, private_detail.strip(), storage_location.strip(), item["id"]))
        item = get_item(item["id"])
    matches = find_matches_for_item(item["id"])
    if org_id:
        record_matches(item, matches)
    return {"item": public_item(item), "matches": public_matches(matches)}


@router.patch("/items/{item_id}")
@router.patch("/listings/{item_id}")
def api_update_item(
    item_id: str,
    user: CurrentUser,
    kind: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    campus_zone: Optional[str] = Form(None),
    event_date: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
) -> dict:
    ensure_owner(item_id, user)
    updates = validate_item_fields(
        {
            "kind": kind.strip() if kind else None,
            "title": title.strip() if title else None,
            "description": description.strip() if description else None,
            "category": category.strip().lower() if category else None,
            "color": color.strip().lower() if color else None,
            "location": location.strip() if location else None,
            "campus_zone": campus_zone.strip().lower() if campus_zone else None,
            "event_date": event_date,
            "status": status.strip().lower() if status else None,
        }
    )
    item = update_item(item_id, user["id"], updates)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": public_item(item)}


@router.delete("/items/{item_id}", status_code=204)
@router.delete("/listings/{item_id}", status_code=204)
def api_delete_item(item_id: str, user: CurrentUser) -> Response:
    ensure_owner(item_id, user)
    if not delete_item(item_id, user["id"]):
        raise HTTPException(status_code=404, detail="Item not found")
    return Response(status_code=204)


@router.post("/items/{item_id}/resolve")
@router.post("/listings/{item_id}/resolve")
def api_resolve_item(item_id: str, user: CurrentUser) -> dict:
    ensure_owner(item_id, user)

    item = resolve_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return public_item(item)


@router.get("/items/{item_id}/matches")
@router.get("/listings/{item_id}/matches")
def api_item_matches(item_id: str, session_token: SessionCookie = None) -> list[dict]:
    existing = get_item(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    if existing.get("org_id"):
        _require_member(session_token, existing["org_id"])
    try:
        matches = find_matches_for_item(item_id)
    except VisionDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return public_matches(matches)


@router.post("/search/image")
async def api_search_image(
    target_kind: Optional[str] = OPTIONAL_TARGET_KIND,
    image: UploadFile = IMAGE_UPLOAD,
) -> list[dict]:
    if target_kind not in {None, "lost", "found"}:
        raise HTTPException(status_code=400, detail="target_kind must be lost or found")

    contents = await image.read()
    try:
        query_image = ImageMatcher().image_from_bytes(contents)
        matches = find_matches_for_image(query_image, target_kind=target_kind)
    except VisionDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return public_matches(matches)
