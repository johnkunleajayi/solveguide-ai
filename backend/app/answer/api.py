import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.answer.errors import AnswerError
from app.answer.schemas import AnswerRecommendation
from app.answer.service import AnswerService
from app.auth.dependencies import credential, required_current_user
from app.auth.models import User
from app.auth.service import read_identity
from app.diagnostics import emit, outcome
from app.learning.schemas import SessionAnswerRequest
from app.rag.schemas import GroundedAnswer, ReasoningRequest
from app.schemas import QuestionObservation

router = APIRouter()


def get_answer_service(request: Request) -> AnswerService:
    return request.app.state.answer_service


@router.post(
    "/api/v1/answer",
    response_model=AnswerRecommendation | GroundedAnswer,
    dependencies=[Depends(required_current_user)],
)
async def suggested_answer(
    observation: QuestionObservation | ReasoningRequest | SessionAnswerRequest,
    service: Annotated[AnswerService, Depends(get_answer_service)],
    request: Request,
    user: Annotated[User, Depends(required_current_user)],
) -> AnswerRecommendation | GroundedAnswer:
    try:
        metadata = (
            observation if isinstance(observation, QuestionObservation) else observation.observation
        )
        emit("question_metadata", level=logging.DEBUG, question_type=metadata.question_type)
        learning = request.app.state.learning_service
        if isinstance(observation, SessionAnswerRequest):
            token = credential(request)

            async def reauthorize(db):
                identity = await read_identity(db, token or "", touch=False)
                if identity.id != user.id:
                    from app.database import PlatformError

                    raise PlatformError("invalid_session", "Sign in again.", 401)

            result = await learning.recommend(
                user.id,
                observation,
                service,
                request.app.state.rag_service,
                reauthorize=reauthorize,
            )
        else:
            await learning.guard_legacy(user.id)
            result = (
                await request.app.state.rag_service.recommend(user.id, observation)
                if isinstance(observation, ReasoningRequest)
                else await service.recommend(observation)
            )
            await learning.guard_legacy(user.id)
        outcome(result.status)
        return result
    except AnswerError as error:
        outcome(error.code, error=True)
        raise
