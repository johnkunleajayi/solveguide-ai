from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import required_current_user
from app.auth.models import User
from app.context_library.api import json_body
from app.learning.schemas import (
    DraftInput,
    PreparationState,
    Revision,
    SessionLiveness,
    SessionView,
    StartInput,
)

router = APIRouter(prefix="/api/v1/learning", dependencies=[Depends(required_current_user)])
CurrentUser = Annotated[User, Depends(required_current_user)]


@router.get("/preparation", response_model=PreparationState)
async def current(request: Request, user: CurrentUser):
    return await request.app.state.learning_service.read(user.id)


@router.put("/preparation", response_model=SessionView)
async def save(request: Request, user: CurrentUser):
    return await request.app.state.learning_service.save(
        user.id, await json_body(request, DraftInput, 16384)
    )


@router.post("/preparation/{identifier}/ready", response_model=SessionView)
async def ready(identifier: UUID, request: Request, user: CurrentUser):
    value = await json_body(request, Revision, 1024)
    return await request.app.state.learning_service.ready(user.id, identifier, value.revision)


@router.post("/sessions/start", response_model=SessionView)
async def start(request: Request, user: CurrentUser):
    return await request.app.state.learning_service.start(
        user.id, await json_body(request, StartInput, 2048)
    )


@router.get("/sessions/active", response_model=SessionView | None)
async def active(request: Request, user: CurrentUser):
    return await request.app.state.learning_service.active(user.id)


@router.post("/sessions/{identifier}/end", response_model=SessionView)
async def end(identifier: UUID, request: Request, user: CurrentUser):
    value = await json_body(request, Revision, 1024)
    return await request.app.state.learning_service.end(user.id, identifier, value.revision)


@router.post("/sessions/{identifier}/validate", response_model=SessionLiveness)
async def validate(identifier: UUID, request: Request, user: CurrentUser):
    value = await json_body(request, Revision, 1024)
    return await request.app.state.learning_service.liveness(user.id, identifier, value.revision)
