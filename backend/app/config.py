from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_BODY_BYTES = 14 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_ORIGINS = ("http://127.0.0.1:1420", "http://tauri.localhost")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    openai_api_key: SecretStr | None = None
    openai_vision_model: str = Field(default="gpt-4.1-mini", min_length=1, max_length=100)
    vision_timeout_seconds: float = Field(default=45, ge=1, le=90)
    vision_max_output_tokens: int = Field(default=4096, ge=512, le=8192)

    openai_answer_model: str = Field(default="gpt-5.4", min_length=1, max_length=100)
    answer_timeout_seconds: float = Field(default=60, ge=1, le=90)
    answer_max_output_tokens: int = Field(default=6000, ge=1024, le=12000)
    answer_reasoning_effort: Literal["none", "low", "medium", "high"] = "medium"

    database_url: SecretStr | None = None
    google_client_id: str = Field(default="", max_length=300)
    google_client_secret: SecretStr | None = None
    auth_state_encryption_key: SecretStr | None = None
    auth_public_base_url: str = "http://127.0.0.1:8000"
    auth_cookie_secure: bool = False
    auth_session_hours: int = Field(default=168, ge=1, le=720)

    context_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    context_text_characters: int = Field(default=500_000, ge=1000, le=1_000_000)
    context_max_pages: int = Field(default=200, ge=1, le=500)
    context_max_blocks: int = Field(default=5000, ge=200, le=10000)
    context_expanded_bytes: int = Field(default=32 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    context_storage_directory: Path = BACKEND_ROOT.parent / ".cache" / "context-library"

    @model_validator(mode="after")
    def platform_configuration(self):
        from cryptography.fernet import Fernet
        from sqlalchemy.engine import make_url

        if self.database_url and self.database_url.get_secret_value().strip():
            try:
                url = make_url(self.database_url.get_secret_value())
                if (
                    url.drivername not in ("postgresql", "postgresql+psycopg")
                    or not url.host
                    or not url.database
                ):
                    raise ValueError
            except Exception:
                raise ValueError("DATABASE_URL must be a PostgreSQL URL") from None
        from urllib.parse import urlsplit

        base = urlsplit(self.auth_public_base_url)
        if (
            base.path
            or base.query
            or base.fragment
            or base.username
            or base.password
            or not base.hostname
            or (base.scheme != "https" and self.auth_public_base_url != "http://127.0.0.1:8000")
        ):
            raise ValueError("Invalid AUTH_PUBLIC_BASE_URL")
        if base.scheme == "https" and not self.auth_cookie_secure:
            raise ValueError("HTTPS requires AUTH_COOKIE_SECURE=true")
        if (
            self.auth_state_encryption_key
            and self.auth_state_encryption_key.get_secret_value().strip()
        ):
            try:
                Fernet(self.auth_state_encryption_key.get_secret_value().encode())
            except Exception:
                raise ValueError("Invalid AUTH_STATE_ENCRYPTION_KEY") from None
        else:
            self.auth_state_encryption_key = None
        return self

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url and self.database_url.get_secret_value().strip())

    @property
    def auth_configured(self) -> bool:
        return bool(
            self.database_configured
            and self.google_client_id
            and self.google_client_secret
            and self.google_client_secret.get_secret_value().strip()
            and self.auth_state_encryption_key
        )

    @property
    def google_redirect_uri(self) -> str:
        return self.auth_public_base_url + "/api/v1/auth/google/callback"

    @property
    def provider_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.get_secret_value().strip())
