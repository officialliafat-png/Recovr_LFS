"""Institution (tenant) features: orgs, staff views, claims, notifications, analytics."""
from __future__ import annotations

import secrets
from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, HTTPException

from app.api import CurrentUser
from app.db import connect, execute
from app.orgs import STAFF, audit, new_id, notify, now, require_role, role_of
from app.repository import get_item, get_user_by_email, list_items

router = APIRouter()
PRIVATE = ("owner_id",)


@router.post("/orgs", status_code=201)
def create_org(user: CurrentUser, name: str = Form(...), zones: str = Form("")) -> dict:
    if not name.strip():
        raise HTTPException(status_code=400, detail="Institution name is required.")
    org_id = new_id()
    with connect() as c:
        code = secrets.token_hex(3).upper()
        execute(c, "INSERT INTO organizations (id, name, zones, join_code, created_at) VALUES (?, ?, ?, ?, ?)",
                (org_id, name.strip(), zones.strip(), code, now()))
        execute(c, "INSERT INTO memberships (user_id, org_id, role) VALUES (?, ?, 'admin')",
                (user["id"], org_id))
        audit(c, org_id, user["id"], "org_created", detail=name.strip())
    return {"id": org_id, "name": name.strip(), "join_code": code, "zones": [z.strip() for z in zones.split(",") if z.strip()]}


@router.get("/orgs/mine")
def my_orgs(user: CurrentUser) -> dict:
    with connect() as c:
        rows = execute(c, "SELECT o.id, o.name, o.zones, o.join_code, m.role FROM memberships m JOIN"
                       " organizations o ON o.id = m.org_id WHERE m.user_id = ?", (user["id"],)).fetchall()
    orgs = [dict(r) for r in rows]
    for o in orgs:  # only admins may see the join code
        if o["role"] != "admin":
            o.pop("join_code")
    return {"orgs": orgs}


@router.post("/orgs/join", status_code=201)
def join_org(user: CurrentUser, code: str = Form(...)) -> dict:
    with connect() as c:
        org = execute(c, "SELECT id, name FROM organizations WHERE join_code = ? AND join_code != ''",
                      (code.strip().upper(),)).fetchone()
        if not org:
            raise HTTPException(status_code=404, detail="That join code was not found. Ask your institution for the right one.")
        if role_of(c, user["id"], org["id"]):
            raise HTTPException(status_code=409, detail="You are already a member of this institution.")
        execute(c, "INSERT INTO memberships (user_id, org_id, role) VALUES (?, ?, 'user')", (user["id"], org["id"]))
        audit(c, org["id"], user["id"], "member_joined", detail=user["email"])
    return {"id": org["id"], "name": org["name"]}


@router.post("/orgs/{org_id}/members", status_code=201)
def add_member(org_id: str, user: CurrentUser, email: str = Form(...), role: str = Form("user")) -> dict:
    if role not in {"staff", "user", "admin"}:
        raise HTTPException(status_code=400, detail="role must be admin, staff or user")
    target = get_user_by_email(email)
    if not target:
        raise HTTPException(status_code=404, detail="That person must create an account first.")
    with connect() as c:
        require_role(c, user, org_id, ("admin",))
        execute(c, "DELETE FROM memberships WHERE user_id = ? AND org_id = ?", (target["id"], org_id))
        execute(c, "INSERT INTO memberships (user_id, org_id, role) VALUES (?, ?, ?)",
                (target["id"], org_id, role))
        audit(c, org_id, user["id"], "member_added", detail=f"{target['email']} as {role}")
    return {"status": "ok"}


@router.get("/orgs/{org_id}/items")
def staff_items(org_id: str, user: CurrentUser, kind: Optional[str] = None,
                lifecycle: Optional[str] = None, category: Optional[str] = None,
                q: Optional[str] = None, campus_zone: Optional[str] = None) -> dict:
    with connect() as c:
        require_role(c, user, org_id, STAFF)
    items = list_items(kind=kind, status=None, category=category, q=q, campus_zone=campus_zone,
                       org_id=org_id, limit=100)
    if lifecycle:
        items = [i for i in items if i["lifecycle"] == lifecycle]
    return {"items": [{k: v for k, v in i.items() if k not in PRIVATE} for i in items]}


@router.post("/items/{item_id}/claims", status_code=201)
def submit_claim(item_id: str, user: CurrentUser, answer: str = Form(...)) -> dict:
    item = get_item(item_id)
    if not item or not item.get("org_id"):
        raise HTTPException(status_code=404, detail="Item not found")
    if not answer.strip():
        raise HTTPException(status_code=400, detail="Describe a private detail only the owner knows.")
    with connect() as c:
        require_role(c, user, item["org_id"])
        if item["kind"] != "found" or item["lifecycle"] == "returned":
            raise HTTPException(status_code=400, detail="Only unreturned found items can be claimed.")
        if item["owner_id"] == user["id"]:
            raise HTTPException(status_code=400, detail="You cannot claim your own found report.")
        claim_id = new_id()
        execute(c, "INSERT INTO claims (id, item_id, org_id, claimant_id, answer, status, note, created_at,"
                " decided_at) VALUES (?, ?, ?, ?, ?, 'pending', '', ?, '')",
                (claim_id, item_id, item["org_id"], user["id"], answer.strip(), now()))
        execute(c, "UPDATE items SET lifecycle = 'claim_submitted' WHERE id = ?", (item_id,))
        audit(c, item["org_id"], user["id"], "claim_submitted", item_id, item["title"])
        for s in execute(c, "SELECT user_id FROM memberships WHERE org_id = ? AND role IN ('admin','staff')",
                         (item["org_id"],)).fetchall():
            notify(c, s["user_id"], f"New claim needs verification: {item['title']}", item_id)
    return {"id": claim_id, "status": "pending"}


@router.get("/orgs/{org_id}/claims")
def org_claims(org_id: str, user: CurrentUser) -> dict:
    with connect() as c:
        require_role(c, user, org_id, STAFF)
        rows = execute(c, "SELECT cl.*, i.title, i.private_detail, u.display_name AS claimant FROM claims cl"
                       " JOIN items i ON i.id = cl.item_id JOIN users u ON u.id = cl.claimant_id"
                       " WHERE cl.org_id = ? ORDER BY cl.created_at DESC", (org_id,)).fetchall()
    return {"claims": [dict(r) for r in rows]}


@router.get("/claims/mine")
def my_claims(user: CurrentUser) -> dict:
    with connect() as c:
        rows = execute(c, "SELECT cl.id, cl.status, cl.note, cl.created_at, i.title, i.storage_location"
                       " FROM claims cl JOIN items i ON i.id = cl.item_id WHERE cl.claimant_id = ?"
                       " ORDER BY cl.created_at DESC", (user["id"],)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["status"] != "approved":  # pickup details only released after approval
            d.pop("storage_location")
        out.append(d)
    return {"claims": out}


@router.post("/claims/{claim_id}/decision")
def decide_claim(claim_id: str, user: CurrentUser, decision: str = Form(...), note: str = Form("")) -> dict:
    if decision not in {"approved", "rejected", "needs_info"}:
        raise HTTPException(status_code=400, detail="decision must be approved, rejected or needs_info")
    with connect() as c:
        claim = execute(c, "SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        require_role(c, user, claim["org_id"], STAFF)
        item = get_item(claim["item_id"])
        execute(c, "UPDATE claims SET status = ?, note = ?, decided_at = ? WHERE id = ?",
                (decision, note.strip(), now(), claim_id))
        if decision == "approved":
            execute(c, "UPDATE items SET lifecycle = 'returned', status = 'resolved', returned_at = ?"
                    " WHERE id = ?", (now(), item["id"]))
            notify(c, claim["claimant_id"], f"Your claim was approved: {item['title']}. Pickup details are in My claims.", item["id"])
            audit(c, claim["org_id"], user["id"], "claim_approved", item["id"], item["title"])
            audit(c, claim["org_id"], user["id"], "item_returned", item["id"], item["title"])
        else:
            if decision == "rejected":
                execute(c, "UPDATE items SET lifecycle = 'reported' WHERE id = ?", (item["id"],))
            text = "was rejected" if decision == "rejected" else "requires more verification"
            notify(c, claim["claimant_id"], f"Your claim {text}: {item['title']}. {note.strip()}", item["id"])
            audit(c, claim["org_id"], user["id"], f"claim_{decision}", item["id"], note.strip())
    return {"id": claim_id, "status": decision}


@router.get("/notifications")
def notifications(user: CurrentUser) -> dict:
    with connect() as c:
        rows = execute(c, "SELECT id, message, item_id, is_read, created_at FROM notifications"
                       " WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user["id"],)).fetchall()
    return {"notifications": [dict(r) for r in rows]}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, user: CurrentUser) -> dict:
    with connect() as c:
        execute(c, "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
                (notification_id, user["id"]))
    return {"status": "ok"}


@router.get("/orgs/{org_id}/audit")
def audit_log(org_id: str, user: CurrentUser) -> dict:
    with connect() as c:
        require_role(c, user, org_id, STAFF)
        rows = execute(c, "SELECT action, item_id, detail, created_at FROM audit_logs WHERE org_id = ?"
                       " ORDER BY created_at DESC LIMIT 50", (org_id,)).fetchall()
    return {"events": [dict(r) for r in rows]}


@router.get("/orgs/{org_id}/dashboard")
def dashboard(org_id: str, user: CurrentUser) -> dict:
    with connect() as c:
        require_role(c, user, org_id, STAFF)
        items = [dict(r) for r in execute(c, "SELECT kind, category, campus_zone, lifecycle, created_at,"
                 " returned_at FROM items WHERE org_id = ?", (org_id,)).fetchall()]
        pending = execute(c, "SELECT COUNT(*) AS n FROM claims WHERE org_id = ? AND status IN"
                          " ('pending','needs_info')", (org_id,)).fetchone()["n"]
        events = [dict(r) for r in execute(c, "SELECT action, detail, created_at FROM audit_logs"
                  " WHERE org_id = ? ORDER BY created_at DESC LIMIT 8", (org_id,)).fetchall()]
    found = [i for i in items if i["kind"] == "found"]
    returned = [i for i in found if i["lifecycle"] == "returned"]
    days = [(datetime.fromisoformat(i["returned_at"]) - datetime.fromisoformat(i["created_at"])).total_seconds()
            / 86400 for i in returned if i["returned_at"]]
    return {
        "lost_reports": sum(i["kind"] == "lost" for i in items),
        "found_items": len(found),
        "possible_matches": sum(i["lifecycle"] == "potential_match" for i in items),
        "pending_claims": pending,
        "returned_items": len(returned),
        "unclaimed_items": len(found) - len(returned),
        "return_rate": round(len(returned) / len(found), 3) if found else 0.0,
        "avg_recovery_days": round(sum(days) / len(days), 2) if days else None,
        "by_category": Counter(i["category"] for i in items).most_common(),
        "by_zone": Counter(i["campus_zone"] for i in items).most_common(),
        "recent_activity": events,
    }


@router.get("/orgs/{org_id}/members")
def members(org_id: str, user: CurrentUser) -> dict:
    with connect() as c:
        require_role(c, user, org_id, ("admin",))
        rows = execute(c, "SELECT u.id, u.display_name, u.email, m.role FROM memberships m JOIN users u"
                       " ON u.id = m.user_id WHERE m.org_id = ? ORDER BY m.role, u.display_name", (org_id,)).fetchall()
    return {"members": [dict(r) for r in rows]}


@router.post("/orgs/{org_id}/members/{member_id}/role")
def set_role(org_id: str, member_id: str, user: CurrentUser, role: str = Form(...)) -> dict:
    if role not in {"admin", "staff", "user"}:
        raise HTTPException(status_code=400, detail="role must be admin, staff or user")
    if member_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")
    with connect() as c:
        require_role(c, user, org_id, ("admin",))
        if not role_of(c, member_id, org_id):
            raise HTTPException(status_code=404, detail="Member not found")
        execute(c, "UPDATE memberships SET role = ? WHERE user_id = ? AND org_id = ?", (role, member_id, org_id))
        audit(c, org_id, user["id"], "role_changed", detail=f"{member_id} -> {role}")
    return {"status": "ok"}


@router.delete("/orgs/{org_id}/members/{member_id}")
def remove_member(org_id: str, member_id: str, user: CurrentUser) -> dict:
    if member_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot remove yourself.")
    with connect() as c:
        require_role(c, user, org_id, ("admin",))
        execute(c, "DELETE FROM memberships WHERE user_id = ? AND org_id = ?", (member_id, org_id))
        audit(c, org_id, user["id"], "member_removed", detail=member_id)
    return {"status": "ok"}


@router.post("/orgs/{org_id}/zones")
def set_zones(org_id: str, user: CurrentUser, zones: str = Form("")) -> dict:
    with connect() as c:
        require_role(c, user, org_id, ("admin",))
        execute(c, "UPDATE organizations SET zones = ? WHERE id = ?", (zones.strip(), org_id))
        audit(c, org_id, user["id"], "zones_updated", detail=zones.strip())
    return {"status": "ok"}


@router.delete("/orgs/{org_id}/items/{item_id}")
def delete_org_item(org_id: str, item_id: str, user: CurrentUser) -> dict:
    with connect() as c:
        require_role(c, user, org_id, ("admin",))
        item = execute(c, "SELECT title FROM items WHERE id = ? AND org_id = ?", (item_id, org_id)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        execute(c, "DELETE FROM claims WHERE item_id = ?", (item_id,))
        execute(c, "DELETE FROM items WHERE id = ?", (item_id,))
        audit(c, org_id, user["id"], "item_deleted", item_id, item["title"])
    return {"status": "ok"}
