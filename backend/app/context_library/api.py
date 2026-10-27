import asyncio
from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.auth.dependencies import required_current_user
from app.auth.models import User
from app.config import ALLOWED_ORIGINS
from app.context_library.schemas import DocumentDetail, DocumentPage, PastedDocument, Title
from app.database import PlatformError

router = APIRouter(
    prefix="/api/v1/context/documents", dependencies=[Depends(required_current_user)]
)
CurrentUser = Annotated[User, Depends(required_current_user)]
TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


def mutation(request):
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise PlatformError("origin_not_allowed", "Use the SolveGuide desktop workspace.", 403)


async def body(request, limit):
    chunks, size = [], 0
    try:
        async with asyncio.timeout(20):
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise PlatformError(
                        "document_too_large",
                        "This document exceeds the configured size limit.",
                        413,
                    )
                chunks.append(chunk)
    except TimeoutError:
        raise PlatformError(
            "request_timeout", "Document transfer timed out. Try again.", 408
        ) from None
    return b"".join(chunks)


async def json_body(request, model, limit):
    mutation(request)
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise PlatformError("invalid_request", "Send document metadata as JSON.", 415)
    from pydantic import ValidationError

    try:
        return model.model_validate_json(await body(request, limit))
    except ValidationError:
        raise PlatformError(
            "invalid_request", "Enter a valid title and text within the configured limits.", 422
        ) from None


@router.get("", response_model=DocumentPage)
async def list_documents(
    request: Request, user: CurrentUser, cursor: str | None = Query(default=None, max_length=150)
):
    return await request.app.state.context_service.list(user.id, cursor)


@router.post("/upload", response_model=DocumentDetail, status_code=201)
async def upload(request: Request, user: CurrentUser):
    mutation(request)
    try:
        filename = unquote(request.headers.get("x-document-filename", ""), errors="strict")
    except UnicodeError:
        raise PlatformError("invalid_document", "Invalid document name.", 422) from None
    if (
        not filename
        or len(filename) > 255
        or any(c in filename for c in "/\\\x00")
        or any(ord(c) < 32 for c in filename)
    ):
        raise PlatformError("invalid_document", "Choose a file with a valid document name.", 422)
    kind = filename.rsplit(".", 1)[-1].lower()
    if (
        kind not in TYPES
        or request.headers.get("content-type", "").split(";")[0].strip() != TYPES[kind]
    ):
        raise PlatformError("unsupported_document", "Choose PDF, DOCX or TXT.", 415)
    data = await body(request, request.app.state.settings.context_upload_bytes)
    if not data:
        raise PlatformError("invalid_document", "The selected file is empty.", 422)
    return await request.app.state.context_service.create(
        user.id, filename[:200], data=data, kind=kind, filename=filename
    )


@router.get("/limits")
async def limits(request: Request, user: CurrentUser):
    settings = request.app.state.settings
    return {
        "upload_bytes": settings.context_upload_bytes,
        "text_characters": settings.context_text_characters,
        "pdf_pages": settings.context_max_pages,
    }


@router.post("/text", response_model=DocumentDetail, status_code=201)
async def paste(request: Request, user: CurrentUser):
    settings = request.app.state.settings
    value = await json_body(request, PastedDocument, settings.context_text_characters * 6 + 4096)
    return await request.app.state.context_service.create(user.id, value.title, pasted=value.text)


@router.get("/{identifier}", response_model=DocumentDetail)
async def detail(identifier: UUID, request: Request, user: CurrentUser):
    return await request.app.state.context_service.detail(user.id, identifier)


@router.patch("/{identifier}", response_model=DocumentDetail)
async def rename(identifier: UUID, request: Request, user: CurrentUser):
    value = await json_body(request, Title, 4096)
    return await request.app.state.context_service.rename(user.id, identifier, value.title)


@router.delete("/{identifier}", status_code=204)
async def delete(identifier: UUID, request: Request, user: CurrentUser):
    mutation(request)
    await request.app.state.context_service.delete(user.id, identifier)
    return Response(status_code=204)
