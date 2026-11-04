import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import required_current_user
from app.auth.models import User
from app.diagnostics import emit, outcome
from app.errors import VisionError
from app.images import validate_image
from app.performance import Timing
from app.schemas import QuestionObservation, VisionRequest
from app.service import VisionService

router = APIRouter()


def get_service(request: Request) -> VisionService:
    return request.app.state.vision_service


@router.get("/api/health")
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "vision": {
            "provider": "openai",
            "configured": request.app.state.settings.provider_configured,
        },
        "database": {"configured": request.app.state.settings.database_configured},
        "authentication": {"configured": request.app.state.settings.auth_configured},
    }


@router.post(
    "/api/v1/vision/question",
    response_model=QuestionObservation,
    dependencies=[Depends(required_current_user)],
)
async def observe_question(
    payload: VisionRequest,
    service: Annotated[VisionService, Depends(get_service)],
    request: Request,
    user: Annotated[User, Depends(required_current_user)],
) -> QuestionObservation:
    try:
        if payload.session_id is not None:
            await request.app.state.learning_service.liveness(
                user.id, UUID(payload.session_id), payload.session_revision
            )
        with Timing("image_validation_worker"):
            image = await run_in_threadpool(validate_image, payload)
        observation = await service.observe(image)
        emit("question_metadata", level=logging.DEBUG, question_type=observation.question_type)
        outcome(observation.status)
        return observation
    except VisionError as error:
        outcome(error.code, error=True)
        raise
