from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ItemCreate:
    kind: str
    title: str
    description: str
    category: str
    color: str
    location: str
    campus_zone: str
    event_date: str
    owner_id: str
    owner_name: str
    contact: str
    image_path: str
    image_url: str = ""


@dataclass(frozen=True)
class MatchResult:
    item: dict
    score: float
    explanation: str
