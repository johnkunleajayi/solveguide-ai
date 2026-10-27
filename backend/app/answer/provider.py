from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.rag.schemas import Evidence, GroundedDraft

from app.answer.schemas import AnswerRecommendation
from app.schemas import QuestionObservation


class AnswerProvider(Protocol):
    async def recommend(self, observation: QuestionObservation) -> AnswerRecommendation: ...
    async def recommend_grounded(
        self, observation: QuestionObservation, mode: str, evidence: list["Evidence"]
    ) -> "GroundedDraft": ...
