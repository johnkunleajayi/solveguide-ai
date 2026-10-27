from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    email: str
    email_verified: bool
    display_name: str
    avatar_url: str | None


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    secret: str = Field(min_length=43, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
