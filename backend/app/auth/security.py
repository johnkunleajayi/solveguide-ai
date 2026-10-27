import hashlib
import secrets
from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


def secret() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
