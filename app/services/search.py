from __future__ import annotations

from app.config import get_settings
from app.models import MatchResult
from app.repository import get_item, list_items
from app.services.image_store import ensure_local_image
from app.services.matcher import ImageMatcher


def find_matches_for_item(item_id: str, limit: int = 5) -> list[MatchResult]:
    item = get_item(item_id)
    if not item:
        return []
    target_kind = "found" if item["kind"] == "lost" else "lost"
    matcher = ImageMatcher()
    query_signature = matcher.signature(matcher.load_image(ensure_local_image(item)))
    return _rank_candidates(
        matcher, query_signature, target_kind, item_id, limit, query_item=item,
        org_id=item.get("org_id", ""),
    )


def find_matches_for_image(
    image,
    target_kind: str | None = None,
    limit: int = 5,
) -> list[MatchResult]:
    matcher = ImageMatcher()
    query_signature = matcher.signature(image)
    return _rank_candidates(matcher, query_signature, target_kind, None, limit, query_item=None)


def _rank_candidates(
    matcher: ImageMatcher,
    query_signature,
    target_kind: str | None,
    excluded_item_id: str | None,
    limit: int,
    query_item: dict | None,
    org_id: str = "",
) -> list[MatchResult]:
    settings = get_settings()
    candidates = list_items(kind=target_kind, limit=100, org_id=org_id)
    results = []

    for candidate in candidates:
        if candidate["id"] == excluded_item_id:
            continue
        try:
            score = matcher.compare(
                query_signature,
                matcher.signature(matcher.load_image(ensure_local_image(candidate))),
            )
        except ValueError:
            continue

        combined_score = _combined_score(query_item, candidate, score.score)
        if combined_score >= settings.match_threshold:
            explanation = f"{score.explanation}, metadata={combined_score - score.score:+.2f}"
            results.append(
                MatchResult(
                    item=candidate,
                    score=combined_score,
                    explanation=explanation,
                )
            )

    return sorted(results, key=lambda result: result.score, reverse=True)[:limit]


def _combined_score(query_item: dict | None, candidate: dict, image_score: float) -> float:
    if not query_item:
        return image_score

    metadata_bonus = 0.0
    if query_item.get("category") == candidate.get("category"):
        metadata_bonus += 0.08
    if query_item.get("campus_zone") == candidate.get("campus_zone"):
        metadata_bonus += 0.05
    if query_item.get("event_date") and query_item.get("event_date") == candidate.get("event_date"):
        metadata_bonus += 0.04
    return round(min(1.0, image_score + metadata_bonus), 4)
