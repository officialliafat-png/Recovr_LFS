from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    db_path: Path
    upload_dir: Path
    match_threshold: float
    session_cookie_name: str
    session_days: int
    pbkdf2_iterations: int
    cookie_secure: bool
    storage_backend: str
    supabase_url: str
    supabase_service_role_key: str
    supabase_storage_bucket: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL") or None,
        db_path=Path(os.getenv("LOSTFOUND_DB_PATH", "data/lost_found.db")),
        upload_dir=Path(os.getenv("LOSTFOUND_UPLOAD_DIR", "data/uploads")),
        match_threshold=float(os.getenv("LOSTFOUND_MATCH_THRESHOLD", "0.42")),
        session_cookie_name=os.getenv("LOSTFOUND_SESSION_COOKIE", "recovr_session"),
        session_days=int(os.getenv("LOSTFOUND_SESSION_DAYS", "7")),
        pbkdf2_iterations=int(os.getenv("LOSTFOUND_PBKDF2_ITERATIONS", "600000")),
        cookie_secure=os.getenv("LOSTFOUND_COOKIE_SECURE", "false").lower() == "true",
        storage_backend=os.getenv("LOSTFOUND_STORAGE_BACKEND", "local").lower(),
        supabase_url=os.getenv("LOSTFOUND_SUPABASE_URL", "").rstrip("/"),
        supabase_service_role_key=os.getenv("LOSTFOUND_SUPABASE_SERVICE_ROLE_KEY", ""),
        supabase_storage_bucket=os.getenv("LOSTFOUND_SUPABASE_STORAGE_BUCKET", "recovr-items"),
    )
