import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import ALLOWED_ORIGINS, MAX_BODY_BYTES


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


class VisionRequestBoundary:
    """Bound streamed JSON before parsing; reject foreign browser origins and parallel images."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self.slot = asyncio.Semaphore(1)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-store")]
            await send(message)

        if scope["method"] != "POST" or scope["path"] != "/api/v1/vision/question":
            await self.app(scope, receive, no_store)
            return
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode("latin-1")
        if origin not in ALLOWED_ORIGINS:
            await error_response(
                "origin_not_allowed", "Use the SolveGuide desktop workspace.", 403
            )(scope, receive, no_store)
            return
        if headers.get(b"content-type", b"").split(b";")[0].strip().lower() != b"application/json":
            await error_response("invalid_request_type", "Send the captured PNG as JSON.", 415)(
                scope, receive, no_store
            )
            return
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            await error_response("invalid_request", "Invalid request size.", 400)(
                scope, receive, no_store
            )
            return
        if length > MAX_BODY_BYTES:
            await error_response("request_too_large", "Request exceeds the 14 MiB limit.", 413)(
                scope, receive, no_store
            )
            return
        if self.slot.locked():
            await error_response(
                "vision_busy", "Another question is being read. Please try again shortly.", 503
            )(scope, receive, no_store)
            return
        async with self.slot:
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > MAX_BODY_BYTES:
                            await error_response(
                                "request_too_large", "Request exceeds the 14 MiB limit.", 413
                            )(scope, receive, no_store)
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await error_response(
                    "request_timeout", "The image upload timed out. Please retry.", 408
                )(scope, receive, no_store)
                return
            delivered = False

            async def bounded_receive() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, no_store)
