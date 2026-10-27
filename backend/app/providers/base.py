from typing import Protocol

from app.images import ValidatedImage
from app.schemas import QuestionObservation


class VisionProvider(Protocol):
    async def observe(self, image: ValidatedImage) -> QuestionObservation: ...
