import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from app.answer.api import router as answer_router
from app.answer.errors import AnswerError
from app.answer.openai import OpenAIAnswerProvider
from app.answer.provider import AnswerProvider
from app.answer.service import AnswerService
from app.api import router
from app.auth.api import router as auth_router
from app.auth.boundary import AuthBoundary, PlatformCORS
from app.auth.google import OpenIDGoogleProvider
from app.config import Settings
from app.context_library.api import router as context_router
from app.context_library.service import ContextService
from app.context_library.storage import LocalDocumentStorage
from app.database import Database, PlatformError
from app.errors import VisionError
from app.middleware import VisionRequestBoundary, error_response
from app.providers.base import VisionProvider
from app.providers.openai import OpenAIVisionProvider
from app.service import VisionService


def create_app(
    settings: Settings | None = None,
    provider: VisionProvider | None = None,
    answer_provider: AnswerProvider | None = None,
) -> FastAPI:
    if settings is None:
        try:
            settings = Settings()
        except ValidationError:
            raise RuntimeError("Invalid backend configuration. Review backend/.env.") from None
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # SDK debug logging may include sensitive request bodies. Never enable it here.
    for name in ("openai", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await database.close()

    app = FastAPI(
        title="SolveGuide AI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.database = database
    app.state.google_provider = OpenIDGoogleProvider(settings)
    app.state.settings = settings
    app.state.context_service = ContextService(
        database, LocalDocumentStorage(settings.context_storage_directory), settings
    )
    app.state.vision_service = VisionService(provider or OpenAIVisionProvider(settings))
    app.state.answer_service = AnswerService(answer_provider or OpenAIAnswerProvider(settings))
    app.add_middleware(AuthBoundary)
    app.add_middleware(VisionRequestBoundary)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", urlsplit(settings.auth_public_base_url).hostname],
    )
    app.add_middleware(PlatformCORS)

    @app.exception_handler(VisionError)
    async def vision_error(_: Request, error: VisionError) -> JSONResponse:
        return error_response(error.code, error.message, error.status)

    @app.exception_handler(PlatformError)
    async def platform_error(_: Request, error: PlatformError) -> JSONResponse:
        response = error_response(error.code, error.message, error.status)
        if error.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(AnswerError)
    async def answer_error(_: Request, error: AnswerError) -> JSONResponse:
        return error_response(error.code, error.message, error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # FastAPI's default includes the invalid input; it could be image data or sensitive text.
        return error_response("invalid_request", "The request is incomplete or invalid.", 422)

    app.include_router(router)
    app.include_router(answer_router)
    app.include_router(auth_router)
    app.include_router(context_router)
    return app


app = create_app()
