import json
import logging
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.errors import VisionError
from app.images import validate_image
from app.schemas import QuestionObservation, VisionRequest
from app.service import VisionService

router = APIRouter()
logger = logging.getLogger("solveguide.vision")


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


@router.post("/api/v1/vision/question", response_model=QuestionObservation)
async def observe_question(
    payload: VisionRequest, service: Annotated[VisionService, Depends(get_service)]
) -> QuestionObservation:
    started = time.monotonic()
    request_id = str(uuid4())
    status = "failed"
    try:
        image = await run_in_threadpool(validate_image, payload)
        observation = await service.observe(image)
        status = observation.status
        return observation
    except VisionError as error:
        status = error.code
        raise
    finally:
        # Whitelist log fields. Never include payloads, observations, exception text or credentials.
        logger.info(
            json.dumps(
                {
                    "event": "vision_request",
                    "request_id": request_id,
                    "outcome": status,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )
