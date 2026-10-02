"""Populate a labelled DEMO institution. Run: python seed_demo.py  (demo credentials only)."""
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import initialize_database
from app.main import app

PASSWORD = "demo-pass-123"
ZONES = "library,cafeteria,engineering,student_centre,sports_complex"


def photo(path, body, mark, shift=0, seed=0):
    img = np.full((220, 220, 3), 245, np.uint8)
    cv2.rectangle(img, (70 + shift, 60), (150 + shift, 190), body, -1)
    cv2.rectangle(img, (88 + shift, 35), (132 + shift, 60), (60, 60, 60), -1)
    cv2.circle(img, (110 + shift, 170), 9, mark, -1)
    noise = np.random.default_rng(seed).integers(-6, 7, img.shape)
    cv2.imwrite(str(path), np.clip(img + noise, 0, 255).astype(np.uint8))


def main():
    initialize_database()
    tmp = Path(tempfile.mkdtemp())
    users = {"admin": "Demo Admin", "staff": "Demo Security Officer", "student": "Demo Student",
             "student2": "Demo Student 2"}
    clients = {}
    for key, name in users.items():
        c = TestClient(app)
        r = c.post("/api/auth/signup", data={"display_name": name, "email": f"{key}@demo.test",
                                             "password": PASSWORD})
        if r.status_code == 409:
            c.post("/api/auth/login", data={"email": f"{key}@demo.test", "password": PASSWORD})
        clients[key] = c
    org = clients["admin"].post("/api/orgs", data={"name": "University of Lahore (DEMO)",
                                                   "zones": ZONES}).json()["id"]
    for key, role in (("staff", "staff"), ("student", "user"), ("student2", "user")):
        clients["admin"].post(f"/api/orgs/{org}/members", data={"email": f"{key}@demo.test", "role": role})

    def post(who, kind, title, cat, color, zone, body, mark, shift=0, seed=0, private="", storage=""):
        path = tmp / f"{seed}-{title[:6]}.png"
        photo(path, body, mark, shift, seed)
        with path.open("rb") as f:
            r = clients[who].post("/api/items", data={
                "kind": kind, "title": f"[DEMO] {title}", "description": f"Demo {kind} item",
                "category": cat, "color": color, "location": zone.title(), "campus_zone": zone,
                "event_date": datetime.now(timezone.utc).date().isoformat(), "org_id": org,
                "private_detail": private, "storage_location": storage},
                files={"image": ("item.png", f, "image/png")})
        r.raise_for_status()
        return r.json()["item"]["id"]

    black, blue, red = (30, 30, 30), (170, 80, 30), (40, 40, 200)
    post("student", "lost", "Black Hydro Flask bottle", "other", "black", "library", black, (255, 255, 255), seed=1)
    post("staff", "found", "Black water bottle", "other", "black", "library", black, (255, 255, 255), 3, 2,
         "Small white sticker near the bottom", "Security Office, Cabinet B, Shelf 3")
    post("student2", "lost", "Blue backpack", "bags", "blue", "engineering", blue, (0, 200, 255), seed=3)
    back = post("staff", "found", "Blue backpack", "bags", "blue", "engineering", blue, (0, 200, 255), 2, 4,
                "Yellow keychain inside front pocket", "Security Office, Cabinet A")
    post("staff", "found", "Red umbrella", "other", "red", "cafeteria", red, (255, 255, 255), seed=5,
         storage="Reception desk")
    clients["student2"].post(f"/api/items/{back}/claims", data={"answer": "Yellow keychain in front pocket"})
    cid = clients["staff"].get(f"/api/orgs/{org}/claims").json()["claims"][0]["id"]
    clients["staff"].post(f"/api/claims/{cid}/decision", data={"decision": "approved"})
    # back-date the returned item so recovery-time analytics are not zero (demo data only)
    past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with sqlite3.connect(get_settings().db_path) as db:
        db.execute("UPDATE items SET created_at = ? WHERE id = ?", (past, back))
    code = clients["admin"].get("/api/orgs/mine").json()["orgs"][0]["join_code"]
    print("Institution join code:", code)
    print("Demo ready. Logins (demo only), password:", PASSWORD)
    print("  admin@demo.test  staff@demo.test  student@demo.test  student2@demo.test")


if __name__ == "__main__":
    main()
