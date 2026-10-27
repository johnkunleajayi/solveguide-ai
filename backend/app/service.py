from pydantic import ValidationError

from app.errors import VisionError
from app.images import ValidatedImage
from app.providers.base import VisionProvider
from app.schemas import QuestionObservation


class VisionService:
    def __init__(self, provider: VisionProvider):
        self.provider = provider

    async def observe(self, image: ValidatedImage) -> QuestionObservation:
        try:
            observation = await self.provider.observe(image)
            return QuestionObservation.model_validate(observation.model_dump())
        except VisionError:
            raise
        except (ValidationError, ValueError, AttributeError, TypeError):
            raise VisionError(
                "invalid_provider_response", "The vision response was invalid. Retake or retry."
            ) from None
        except Exception:
            # Do not leak third-party exception messages, image bytes or extracted text.
            raise VisionError(
                "vision_unavailable",
                "Question reading is temporarily unavailable. Please retry.",
                503,
            ) from None
