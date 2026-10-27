from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import required_current_user
from app.auth.models import User
from app.context_library.api import json_body

router = APIRouter(
    prefix="/api/v1/context/documents", dependencies=[Depends(required_current_user)]
)
CurrentUser = Annotated[User, Depends(required_current_user)]


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    method: Literal["semantic_pgvector", "lexical"]
    consent: bool = False
    force: bool = False


@router.get("/indexes")
async def indexes(
    request: Request,
    user: CurrentUser,
    cursor: Annotated[UUID | None, Query()] = None,
    selected: Annotated[list[UUID] | None, Query(max_length=5)] = None,
):
    service = request.app.state.rag_service
    result = await service.repository.catalog(user.id, cursor, selected)
    result["semantic_available"] = await service.repository.vector_available()
    return result


@router.post("/{identifier}/index")
async def index(identifier: UUID, request: Request, user: CurrentUser):
    value = await json_body(request, IndexRequest, 4096)
    return await request.app.state.rag_service.index(
        user.id, identifier, value.method, value.consent, value.force
    )
