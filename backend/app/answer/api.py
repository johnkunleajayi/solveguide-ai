import json
import logging
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from app.answer.errors import AnswerError
from app.answer.schemas import AnswerRecommendation
from app.answer.service import AnswerService
from app.schemas import QuestionObservation

router = APIRouter()
logger = logging.getLogger("solveguide.answer")


def get_answer_service(request: Request) -> AnswerService:
    return request.app.state.answer_service


@router.post("/api/v1/answer", response_model=AnswerRecommendation)
async def suggested_answer(
    observation: QuestionObservation, service: Annotated[AnswerService, Depends(get_answer_service)]
) -> AnswerRecommendation:
    started = time.monotonic()
    outcome = "failed"
    try:
        result = await service.recommend(observation)
        outcome = result.status
        return result
    except AnswerError as error:
        outcome = error.code
        raise
    finally:
        logger.info(
            json.dumps(
                {
                    "event": "answer_request",
                    "request_id": str(uuid4()),
                    "outcome": outcome,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )
