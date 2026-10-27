from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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

    @property
    def provider_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.get_secret_value().strip())
