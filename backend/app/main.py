import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from app.api import router
from app.config import ALLOWED_ORIGINS, Settings
from app.errors import VisionError
from app.middleware import VisionRequestBoundary, error_response
from app.providers.base import VisionProvider
from app.providers.openai import OpenAIVisionProvider
from app.service import VisionService


def create_app(settings: Settings | None = None, provider: VisionProvider | None = None) -> FastAPI:
    if settings is None:
        try:
            settings = Settings()
        except ValidationError:
            raise RuntimeError("Invalid backend configuration. Review backend/.env.") from None
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # SDK debug logging may include sensitive request bodies. Never enable it here.
    for name in ("openai", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    app = FastAPI(
        title="SolveGuide Question Observation", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.settings = settings
    app.state.vision_service = VisionService(provider or OpenAIVisionProvider(settings))
    app.add_middleware(VisionRequestBoundary)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        max_age=600,
    )

    @app.exception_handler(VisionError)
    async def vision_error(_: Request, error: VisionError) -> JSONResponse:
        return error_response(error.code, error.message, error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # FastAPI's default includes the invalid input; it could be image data or sensitive text.
        return error_response("invalid_request", "The image request is incomplete or invalid.", 422)

    app.include_router(router)
    return app


app = create_app()
