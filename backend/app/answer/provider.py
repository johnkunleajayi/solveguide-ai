from typing import Protocol

from app.answer.schemas import AnswerRecommendation
from app.schemas import QuestionObservation


class AnswerProvider(Protocol):
    async def recommend(self, observation: QuestionObservation) -> AnswerRecommendation: ...
