from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fastapi import UploadFile

from app.config import get_settings

SAFE_EXTENSION = re.compile(r"[^a-zA-Z0-9.]")


@dataclass(frozen=True)
class StoredImage:
    path: Path
    url: str = ""


async def save_upload(upload: UploadFile) -> StoredImage:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = upload.filename or "image.jpg"
    suffix = Path(SAFE_EXTENSION.sub("", original_name)).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"

    object_name = f"{uuid.uuid4()}{suffix}"
    destination = settings.upload_dir / object_name
    contents = await upload.read()
    if not contents:
        raise ValueError("Image upload is empty.")

    destination.write_bytes(contents)
    image_url = ""
    if settings.storage_backend == "supabase":
        image_url = upload_to_supabase_storage(
            object_name=object_name,
            contents=contents,
            content_type=upload.content_type or "image/jpeg",
        )

    return StoredImage(path=destination, url=image_url)


def ensure_local_image(item: dict) -> Path:
    image_path = Path(item["image_path"])
    if image_path.exists():
        return image_path

    image_url = item.get("image_url")
    if not image_url:
        raise ValueError(f"Unable to read image: {image_path}")

    image_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(image_url, timeout=15) as response:
            image_path.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"Unable to download image: {image_url}") from exc

    return image_path


def upload_to_supabase_storage(
    object_name: str,
    contents: bytes,
    content_type: str,
) -> str:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError(
            "Supabase storage is enabled, but LOSTFOUND_SUPABASE_URL or "
            "LOSTFOUND_SUPABASE_SERVICE_ROLE_KEY is missing."
        )

    bucket = settings.supabase_storage_bucket
    object_path = quote(object_name)
    upload_url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{object_path}"
    request = urllib.request.Request(
        upload_url,
        data=contents,
        method="POST",
        headers={
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": content_type,
            "x-upsert": "false",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
            detail = payload.get("message", detail)
        except json.JSONDecodeError:
            pass
        raise ValueError(f"Supabase image upload failed: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Supabase image upload failed: {exc.reason}") from exc

    return f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{object_path}"
