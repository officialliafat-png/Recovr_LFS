from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from app.config import get_settings

PASSWORD_ALGORITHM = "pbkdf2_sha256"
SESSION_TOKEN_BYTES = 32


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password) > 256:
        raise ValueError("Password must be 256 characters or fewer.")


def hash_password(password: str) -> str:
    validate_password(password)
    settings = get_settings()
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        settings.pbkdf2_iterations,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(settings.pbkdf2_iterations),
            _encode(salt),
            _encode(digest),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode(salt),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(_encode(digest), expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
