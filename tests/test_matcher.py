from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.services.matcher import ImageMatcher  # noqa: E402


def write_object_image(path: Path, color: tuple[int, int, int], offset: int = 0) -> None:
    image = np.full((220, 220, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (45 + offset, 55), (175 + offset, 165), color, -1)
    cv2.circle(image, (110 + offset, 110), 36, (30, 30, 30), 3)
    cv2.line(image, (65 + offset, 80), (155 + offset, 145), (255, 255, 255), 5)
    cv2.imwrite(str(path), image)


def test_similar_item_images_score_higher_than_different_images(tmp_path: Path) -> None:
    query = tmp_path / "query.png"
    similar = tmp_path / "similar.png"
    different = tmp_path / "different.png"

    write_object_image(query, (40, 80, 210), offset=0)
    write_object_image(similar, (42, 82, 205), offset=3)

    different_image = np.full((220, 220, 3), 235, dtype=np.uint8)
    cv2.circle(different_image, (110, 110), 70, (40, 180, 40), -1)
    cv2.putText(different_image, "ABC", (70, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.imwrite(str(different), different_image)

    matcher = ImageMatcher()
    similar_score = matcher.compare_paths(query, similar)
    different_score = matcher.compare_paths(query, different)

    assert similar_score.score > different_score.score
    assert similar_score.score >= 0.45

