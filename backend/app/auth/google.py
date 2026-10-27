import hmac
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oidc.core import CodeIDToken
from joserfc import jwt
from joserfc.jwk import KeySet
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.database import PlatformError

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


class GoogleIdentity(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    subject: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    email_verified: bool
    display_name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2048)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        if "@" not in value or any(c.isspace() for c in value.strip()):
            raise ValueError("Invalid email")
        return value.strip().lower()

    @field_validator("avatar_url")
    @classmethod
    def safe_avatar(cls, value):
        if value:
            url = urlsplit(value)
            if (
                url.scheme != "https"
                or url.hostname != "lh3.googleusercontent.com"
                or url.username
                or url.password
            ):
                return None
        return value


class GoogleProvider(Protocol):
    async def identity(self, code: str, verifier: str, nonce: str) -> GoogleIdentity: ...


def authorization_url(settings: Settings, state: str, nonce: str, challenge: str) -> str:
    return (
        AUTHORIZATION_URL
        + "?"
        + urlencode(
            {
                "client_id": settings.google_client_id,
                "redirect_uri": settings.google_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "online",
                "prompt": "select_account",
            }
        )
    )


def validate_identity(
    id_token: str, keys: dict, settings: Settings, nonce: str, access_token: str
) -> GoogleIdentity:
    token = jwt.decode(id_token, KeySet.import_key_set(keys), algorithms=["RS256"])
    if not isinstance(token.claims.get("nonce"), str) or not hmac.compare_digest(
        token.claims["nonce"], nonce
    ):
        raise ValueError("Invalid nonce")
    claims = CodeIDToken(
        token.claims,
        token.header,
        options={
            "iss": {
                "essential": True,
                "values": ["https://accounts.google.com", "accounts.google.com"],
            },
            "aud": {"essential": True, "value": settings.google_client_id},
            "exp": {"essential": True},
            "iat": {"essential": True},
            "sub": {"essential": True},
        },
        params={
            "nonce": nonce,
            "client_id": settings.google_client_id,
            "access_token": access_token,
        },
    )
    claims.validate(leeway=30)
    identity = GoogleIdentity(
        subject=claims["sub"],
        email=claims["email"],
        email_verified=claims["email_verified"],
        display_name=claims.get("name") or claims["email"],
        avatar_url=claims.get("picture"),
    )
    if not identity.email_verified:
        raise ValueError("Verified email required")
    return identity


class OpenIDGoogleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def identity(self, code: str, verifier: str, nonce: str) -> GoogleIdentity:
        try:
            async with AsyncOAuth2Client(
                self.settings.google_client_id,
                self.settings.google_client_secret.get_secret_value(),
                redirect_uri=self.settings.google_redirect_uri,
                timeout=15,
                token_endpoint_auth_method="client_secret_post",
                trust_env=False,
            ) as client:
                token = await client.fetch_token(TOKEN_URL, code=code, code_verifier=verifier)
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get(JWKS_URL)
                response.raise_for_status()
            return validate_identity(
                token["id_token"], response.json(), self.settings, nonce, token["access_token"]
            )
        except Exception:
            # No SDK/provider exception, token or identity payload reaches logs/client.
            raise PlatformError(
                "google_identity_failed", "Google sign-in could not be verified. Start again.", 401
            ) from None
