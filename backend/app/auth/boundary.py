import asyncio

from starlette.middleware.cors import CORSMiddleware

from app.config import ALLOWED_ORIGINS
from app.middleware import error_response


class PlatformCORS:
    """Cookies are enabled only for auth routes; AI transport stays credential-free."""

    def __init__(self, app):
        options = dict(
            allow_origins=list(ALLOWED_ORIGINS),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            max_age=600,
        )
        self.auth = CORSMiddleware(app, allow_credentials=True, **options)
        self.public = CORSMiddleware(app, allow_credentials=False, **options)

    async def __call__(self, scope, receive, send):
        target = self.auth if scope.get("path", "").startswith("/api/v1/auth/") else self.public
        await target(scope, receive, send)


class AuthBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not scope["path"].startswith("/api/v1/auth/")
            or scope["method"] != "POST"
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if headers.get(b"origin", b"").decode("latin-1") not in ALLOWED_ORIGINS:
            await error_response("origin_not_allowed", "Use the SolveGuide workspace.", 403)(
                scope, receive, send
            )
            return
        if headers.get(b"content-type", b"").split(b";")[0] != b"application/json":
            await error_response("invalid_request_type", "Send JSON.", 415)(scope, receive, send)
            return
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 4096:
                        await error_response(
                            "request_too_large", "Authentication request is too large.", 413
                        )(scope, receive, send)
                        return
                    if not message.get("more_body"):
                        break
        except TimeoutError:
            await error_response("request_timeout", "Sign-in request timed out.", 408)(
                scope, receive, send
            )
            return
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
