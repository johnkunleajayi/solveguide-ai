import asyncio
import math
from typing import Protocol

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from app.database import PlatformError
from app.diagnostics import span


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def validate_vectors(vectors, count, dimensions):
    if len(vectors) != count or any(
        len(v) != dimensions
        or not all(isinstance(x, (float, int)) and math.isfinite(x) for x in v)
        or sum(x * x for x in v) <= 0
        for v in vectors
    ):
        raise PlatformError(
            "embedding_invalid", "The embedding provider returned an invalid response."
        )
    return vectors


class OpenAIEmbeddingProvider:
    def __init__(self, settings):
        self.settings = settings

    @span("embedding_provider")
    async def embed(self, texts):
        s = self.settings
        if not s.provider_configured:
            raise PlatformError(
                "embedding_not_configured", "Configure the backend embedding provider."
            )
        if (
            not texts
            or len(texts) > 16
            or any(not t.strip() or len(t.encode()) > 6400 for t in texts)
        ):
            raise PlatformError(
                "embedding_input", "Embedding input exceeds its bounded batch.", 422
            )
        try:
            async with (
                AsyncOpenAI(
                    api_key=s.openai_api_key.get_secret_value(),
                    base_url="https://api.openai.com/v1",
                    max_retries=0,
                    timeout=httpx.Timeout(s.embedding_timeout_seconds, connect=5),
                ) as client,
                asyncio.timeout(s.embedding_timeout_seconds),
            ):
                response = await client.embeddings.create(
                    model=s.openai_embedding_model,
                    dimensions=s.embedding_dimensions,
                    input=texts,
                    encoding_format="float",
                )
            rows = sorted(response.data, key=lambda row: row.index)
            if [row.index for row in rows] != list(range(len(texts))):
                raise ValueError
            return validate_vectors(
                [row.embedding for row in rows], len(texts), s.embedding_dimensions
            )
        except PlatformError:
            raise
        except (TimeoutError, APITimeoutError):
            raise PlatformError(
                "embedding_timeout", "Indexing timed out. Retry explicitly.", 504
            ) from None
        except AuthenticationError:
            raise PlatformError(
                "embedding_authentication", "Review backend provider credentials."
            ) from None
        except RateLimitError:
            raise PlatformError(
                "embedding_rate_limited", "The embedding provider is busy. Retry later."
            ) from None
        except (APIConnectionError, APIStatusError):
            raise PlatformError(
                "embedding_unavailable", "The embedding provider is unavailable."
            ) from None
        except Exception:
            raise PlatformError(
                "embedding_invalid", "The embedding response could not be validated."
            ) from None
