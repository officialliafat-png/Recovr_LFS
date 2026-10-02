from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
fastapi = pytest.importorskip("fastapi")  # noqa: F401
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = np.full((180, 180, 3), 250, dtype=np.uint8)
    cv2.rectangle(image, (35, 45), (145, 135), color, -1)
    cv2.circle(image, (90, 90), 28, (20, 20, 20), 2)
    cv2.imwrite(str(path), image)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("LOSTFOUND_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LOSTFOUND_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("LOSTFOUND_PBKDF2_ITERATIONS", "1000")

    from app.db import initialize_database
    from app.main import app

    initialize_database(tmp_path / "test.db")
    return TestClient(app)


def signup(client: TestClient, email: str = "student@example.com") -> None:
    response = client.post(
        "/api/auth/signup",
        data={
            "display_name": "Student",
            "email": email,
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == email


def submit_item(client: TestClient, image_path: Path, kind: str, title: str):
    with image_path.open("rb") as image_file:
        return client.post(
            "/api/items",
            data={
                "kind": kind,
                "title": title,
                "description": "Test item with visible markings",
                "category": "other",
                "color": "blue",
                "location": "Library",
                "campus_zone": "library",
                "event_date": "2026-08-21",
            },
            files={"image": ("item.png", image_file, "image/png")},
        )


def test_homepage_renders(client: TestClient) -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert "Find what's lost." in response.text
    assert "Create account" in response.text


def test_auth_flow_and_protected_posting(client: TestClient, tmp_path: Path) -> None:
    image_path = tmp_path / "item.png"
    make_image(image_path, (50, 90, 210))

    anonymous_response = submit_item(client, image_path, "lost", "Lost bottle")
    assert anonymous_response.status_code == 401

    signup(client)
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["display_name"] == "Student"

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    login_response = client.post(
        "/api/auth/login",
        data={"email": "student@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200


def test_create_item_and_return_matches(client: TestClient, tmp_path: Path) -> None:
    signup(client)
    lost_image = tmp_path / "lost.png"
    found_image = tmp_path / "found.png"
    make_image(lost_image, (50, 90, 210))
    make_image(found_image, (52, 92, 208))

    found_response = submit_item(client, found_image, "found", "Found bottle")
    assert found_response.status_code == 201

    lost_response = submit_item(client, lost_image, "lost", "Lost bottle")
    assert lost_response.status_code == 201
    payload = lost_response.json()

    assert payload["item"]["kind"] == "lost"
    assert "contact" not in payload["item"]
    assert payload["matches"]
    assert payload["matches"][0]["item"]["title"] == "Found bottle"

    list_response = client.get("/api/v1/listings?type=lost&q=bottle&campus_zone=library")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1


def test_owner_can_update_and_delete_own_items(client: TestClient, tmp_path: Path) -> None:
    signup(client)
    image_path = tmp_path / "item.png"
    make_image(image_path, (50, 90, 210))

    create_response = submit_item(client, image_path, "lost", "Lost bottle")
    assert create_response.status_code == 201
    item_id = create_response.json()["item"]["id"]

    mine_response = client.get("/api/items/mine")
    assert mine_response.status_code == 200
    assert mine_response.json()["items"][0]["id"] == item_id

    update_response = client.patch(
        f"/api/items/{item_id}",
        data={
            "title": "Updated bottle",
            "description": "Updated description",
            "category": "other",
            "color": "black",
            "location": "Student center",
            "campus_zone": "student-center",
            "event_date": "2026-08-22",
            "kind": "lost",
            "status": "resolved",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["item"]["title"] == "Updated bottle"
    assert update_response.json()["item"]["status"] == "resolved"

    list_response = client.get("/api/items")
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    delete_response = client.delete(f"/api/items/{item_id}")
    assert delete_response.status_code == 204
    assert client.get("/api/items/mine").json()["items"] == []


def test_users_cannot_manage_other_users_items(client: TestClient, tmp_path: Path) -> None:
    signup(client, email="owner@example.com")
    image_path = tmp_path / "private.png"
    make_image(image_path, (50, 90, 210))

    create_response = submit_item(client, image_path, "lost", "Owner post")
    item_id = create_response.json()["item"]["id"]
    client.post("/api/auth/logout")

    signup(client, email="other@example.com")
    update_response = client.patch(f"/api/items/{item_id}", data={"title": "Taken over"})
    delete_response = client.delete(f"/api/items/{item_id}")

    assert update_response.status_code == 403
    assert delete_response.status_code == 403
