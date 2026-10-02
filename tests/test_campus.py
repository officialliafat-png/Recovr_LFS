from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTFOUND_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("LOSTFOUND_UPLOAD_DIR", str(tmp_path / "up"))
    monkeypatch.setenv("LOSTFOUND_PBKDF2_ITERATIONS", "1000")
    from app.db import initialize_database
    from app.main import app
    initialize_database(tmp_path / "t.db")
    return app, tmp_path


def user(app, email):
    c = TestClient(app)
    r = c.post("/api/auth/signup", data={"display_name": email, "email": email, "password": "correct-horse-1"})
    assert r.status_code == 201
    return c


def img(path: Path, color):
    a = np.full((180, 180, 3), 250, np.uint8)
    cv2.rectangle(a, (35, 45), (145, 135), color, -1)
    cv2.circle(a, (90, 90), 28, (20, 20, 20), 2)
    cv2.imwrite(str(path), a)


def post(c, path, **data):
    base = {"description": "d", "category": "bags", "color": "blue", "location": "Library",
            "campus_zone": "library", "event_date": "2026-08-21"}
    with path.open("rb") as f:
        return c.post("/api/items", data={**base, **data}, files={"image": ("i.png", f, "image/png")})


def test_full_workflow_and_tenant_isolation(app_env):
    app, tmp = app_env
    admin, student, outsider = user(app, "a@x.test"), user(app, "s@x.test"), user(app, "o@x.test")
    org = admin.post("/api/orgs", data={"name": "Uni A", "zones": "library"}).json()["id"]
    assert admin.post(f"/api/orgs/{org}/members", data={"email": "s@x.test", "role": "user"}).status_code == 201
    other = outsider.post("/api/orgs", data={"name": "Uni B"}).json()["id"]
    img(tmp / "a.png", (200, 80, 40))
    lost = post(student, tmp / "a.png", kind="lost", title="Blue bag", org_id=org).json()["item"]
    # students may not file found reports; staff may
    assert post(student, tmp / "a.png", kind="found", title="x", org_id=org).status_code == 403
    found = post(admin, tmp / "a.png", kind="found", title="Blue bag found", org_id=org,
                 private_detail="yellow keychain", storage_location="Cabinet B").json()
    assert found["matches"] and "features=" in found["matches"][0]["explanation"]
    assert "private_detail" not in found["item"] and "storage_location" not in found["item"]
    notes = student.get("/api/notifications").json()["notifications"]
    assert any("may have a match" in n["message"] for n in notes)
    fid = found["item"]["id"]
    assert student.post(f"/api/items/{fid}/claims", data={"answer": "yellow keychain"}).status_code == 201
    assert student.get("/api/claims/mine").json()["claims"][0].get("storage_location") is None
    claim = admin.get(f"/api/orgs/{org}/claims").json()["claims"][0]
    assert claim["private_detail"] == "yellow keychain" and claim["status"] == "pending"
    assert student.post(f"/api/claims/{claim['id']}/decision", data={"decision": "approved"}).status_code == 403
    assert admin.post(f"/api/claims/{claim['id']}/decision", data={"decision": "approved"}).status_code == 200
    assert student.get("/api/claims/mine").json()["claims"][0]["storage_location"] == "Cabinet B"
    d = admin.get(f"/api/orgs/{org}/dashboard").json()
    assert d["returned_items"] == 1 and d["return_rate"] == 1.0 and d["pending_claims"] == 0
    actions = {e["action"] for e in admin.get(f"/api/orgs/{org}/audit").json()["events"]}
    assert {"claim_submitted", "claim_approved", "item_returned", "match_generated"} <= actions
    # tenant isolation + unauthenticated access
    assert outsider.get(f"/api/items/{fid}").status_code == 403
    assert outsider.get(f"/api/orgs/{org}/dashboard").status_code == 403
    assert outsider.get(f"/api/items?org_id={org}").status_code == 403
    assert TestClient(app).get(f"/api/items/{lost['id']}").status_code == 401
    assert outsider.post(f"/api/items/{fid}/claims", data={"answer": "x"}).status_code in (400, 403)
    assert other != org


def test_rejects_bad_uploads(app_env):
    app, tmp = app_env
    c = user(app, "u@x.test")
    (tmp / "bad.txt").write_text("not an image")
    with (tmp / "bad.txt").open("rb") as f:
        r = c.post("/api/items", data={"kind": "lost", "title": "t", "description": "d", "category": "bags",
                   "color": "blue", "location": "l", "event_date": "2026-08-21"},
                   files={"image": ("bad.txt", f, "text/plain")})
    assert r.status_code == 400


def test_matching_prefers_similar_images(app_env):
    from app.services.matcher import ImageMatcher
    _, tmp = app_env
    img(tmp / "x.png", (200, 80, 40)); img(tmp / "y.png", (200, 80, 40)); img(tmp / "z.png", (30, 200, 30))
    m = ImageMatcher()
    assert m.compare_paths(tmp / "x.png", tmp / "y.png").score > m.compare_paths(tmp / "x.png", tmp / "z.png").score


def test_pages_render(app_env):
    app, _ = app_env
    c = TestClient(app)
    assert "Lost less" in c.get("/").text and "Demo pricing" in c.get("/").text
    for path in ("/portal", "/staff", "/app", "/static/recovr.css"):
        assert c.get(path).status_code == 200


def test_signup_duplicate_join_and_admin_powers(app_env):
    app, tmp = app_env
    admin = user(app, "boss@x.test")
    dup = TestClient(app).post("/api/auth/signup", data={"display_name": "x", "email": "boss@x.test", "password": "correct-horse-1"})
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]
    org = admin.post("/api/orgs", data={"name": "Uni", "zones": "library"}).json()
    student = user(app, "stu@x.test")
    assert student.post("/api/orgs/join", data={"code": "ZZZZZZ"}).status_code == 404
    assert student.post("/api/orgs/join", data={"code": org["join_code"].lower()}).status_code == 201
    assert student.post("/api/orgs/join", data={"code": org["join_code"]}).status_code == 409
    mine = student.get("/api/orgs/mine").json()["orgs"][0]
    assert mine["role"] == "user" and "join_code" not in mine
    assert student.get(f"/api/orgs/{org['id']}/members").status_code == 403
    members = admin.get(f"/api/orgs/{org['id']}/members").json()["members"]
    sid = next(m["id"] for m in members if m["email"] == "stu@x.test")
    assert admin.post(f"/api/orgs/{org['id']}/members/{sid}/role", data={"role": "staff"}).status_code == 200
    assert student.get(f"/api/orgs/{org['id']}/dashboard").status_code == 200
    assert student.post(f"/api/orgs/{org['id']}/zones", data={"zones": "x"}).status_code == 403
    img(tmp / "a.png", (200, 80, 40))
    item = post(admin, tmp / "a.png", kind="found", title="Bag", org_id=org["id"]).json()["item"]
    assert student.delete(f"/api/orgs/{org['id']}/items/{item['id']}").status_code == 403
    assert admin.delete(f"/api/orgs/{org['id']}/items/{item['id']}").status_code == 200
    assert admin.delete(f"/api/orgs/{org['id']}/items/{item['id']}").status_code == 404


def test_error_pages(app_env):
    app, _ = app_env
    c = TestClient(app)
    r = c.get("/nothing-here")
    assert r.status_code == 404 and "couldn't find that page" in r.text
    assert c.get("/api/nothing").json()["detail"]
    assert all(c.get(p).status_code == 200 for p in ("/admin", "/guide"))
