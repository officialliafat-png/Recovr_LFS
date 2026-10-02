from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - exercised when optional deps are absent locally
    cv2 = None
    np = None


class VisionDependencyError(RuntimeError):
    """Raised when OpenCV or NumPy is not installed."""


@dataclass(frozen=True)
class ImageSignature:
    average_hash: int
    histogram: object
    descriptors: object
    keypoint_count: int


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    feature_score: float
    hash_score: float
    color_score: float
    explanation: str


class ImageMatcher:
    def __init__(self) -> None:
        if cv2 is None or np is None:
            raise VisionDependencyError("Install opencv-python-headless and numpy to use matching.")
        self._orb = cv2.ORB_create(nfeatures=800)

    def load_image(self, path: str | Path):
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Unable to read image: {path}")
        return self._resize_for_matching(image)

    def image_from_bytes(self, contents: bytes):
        buffer = np.frombuffer(contents, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Upload is not a readable image.")
        return self._resize_for_matching(image)

    def signature(self, image) -> ImageSignature:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        average_hash = self._average_hash(gray)
        histogram = self._color_histogram(image)
        keypoints, descriptors = self._orb.detectAndCompute(gray, None)
        keypoint_count = len(keypoints) if keypoints is not None else 0
        return ImageSignature(average_hash, histogram, descriptors, keypoint_count)

    def compare(self, left: ImageSignature, right: ImageSignature) -> ScoreBreakdown:
        feature_score = self._feature_score(left.descriptors, right.descriptors)
        hash_score = self._hash_similarity(left.average_hash, right.average_hash)
        color_score = float(cv2.compareHist(left.histogram, right.histogram, cv2.HISTCMP_CORREL))
        color_score = max(0.0, min(1.0, color_score))

        score = (feature_score * 0.50) + (hash_score * 0.25) + (color_score * 0.25)
        explanation = (
            f"features={feature_score:.2f}, shape={hash_score:.2f}, color={color_score:.2f}"
        )
        return ScoreBreakdown(
            score=round(score, 4),
            feature_score=round(feature_score, 4),
            hash_score=round(hash_score, 4),
            color_score=round(color_score, 4),
            explanation=explanation,
        )

    def compare_paths(self, left_path: str | Path, right_path: str | Path) -> ScoreBreakdown:
        return self.compare(
            self.signature(self.load_image(left_path)),
            self.signature(self.load_image(right_path)),
        )

    def compare_image_to_path(self, image, candidate_path: str | Path) -> ScoreBreakdown:
        return self.compare(self.signature(image), self.signature(self.load_image(candidate_path)))

    def _resize_for_matching(self, image):
        height, width = image.shape[:2]
        longest_side = max(height, width)
        if longest_side <= 900:
            return image
        scale = 900 / longest_side
        return cv2.resize(image, (int(width * scale), int(height * scale)))

    def _average_hash(self, gray) -> int:
        small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
        mean = small.mean()
        bits = (small > mean).flatten()
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return value

    def _color_histogram(self, image):
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        return hist.flatten()

    def _feature_score(self, left, right) -> float:
        if left is None or right is None or len(left) < 2 or len(right) < 2:
            return 0.0

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        raw_matches = matcher.knnMatch(left, right, k=2)
        good_matches = []
        for pair in raw_matches:
            if len(pair) != 2:
                continue
            first, second = pair
            if first.distance < 0.75 * second.distance:
                good_matches.append(first)

        normalizer = max(12, min(len(left), len(right)))
        return min(1.0, len(good_matches) / normalizer)

    def _hash_similarity(self, left_hash: int, right_hash: int) -> float:
        distance = bin(int(left_hash ^ right_hash)).count("1")
        return 1.0 - (distance / 64.0)
