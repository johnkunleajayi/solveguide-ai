"""Own request work through disconnect/timeout; no orphaned provider or validation task."""

import asyncio
import re
import time

from starlette.responses import JSONResponse

from app.diagnostics import outcome

SESSION_VALIDATION_SECONDS = 10
NO_STORE = {
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
}


async def run_connected(app, scope, receive, send, body, *, deadline=None):
    delivered = False
    disconnected = asyncio.Event()
    began = False
    response_finished = False

    async def replay():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def tracked_send(message):
        nonlocal began, response_finished
        if message["type"] == "http.response.start":
            began = True
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            response_finished = True
        await send(message)

    async def watch():
        while True:
            if (await receive())["type"] == "http.disconnect":
                disconnected.set()
                return

    work = asyncio.create_task(app(scope, replay, tracked_send))
    watcher = asyncio.create_task(watch())
    try:
        done, _ = await asyncio.wait(
            {work, watcher}, timeout=deadline, return_when=asyncio.FIRST_COMPLETED
        )
        if work in done:
            await work
        elif watcher in done:
            await watcher
            if response_finished:
                await work
            else:
                outcome("request_cancelled", error=True)
        else:
            outcome("session_validation_timeout", error=True)
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
            if not began:
                await JSONResponse(
                    {
                        "error": {
                            "code": "session_validation_timeout",
                            "message": "Session check timed out. Check diagnostics and retry.",
                        }
                    },
                    status_code=504,
                    headers=NO_STORE,
                )(scope, replay, send)
    finally:
        for task in (work, watcher):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


class SessionRequestBoundary:
    """Whole validation budget below the unchanged native 12-second deadline."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not re.fullmatch(
                r"/api/v1/learning/sessions/[0-9a-fA-F-]{36}/validate", scope["path"]
            )
        ):
            return await self.app(scope, receive, send)
        body = bytearray()
        started = time.monotonic()
        try:
            async with asyncio.timeout(SESSION_VALIDATION_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        outcome("request_cancelled", error=True)
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 1024:
                        return await JSONResponse(
                            {
                                "error": {
                                    "code": "request_too_large",
                                    "message": "Session validation request is too large.",
                                }
                            },
                            status_code=413,
                            headers=NO_STORE,
                        )(scope, receive, send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse(
                {
                    "error": {
                        "code": "request_timeout",
                        "message": "Session request upload timed out.",
                    }
                },
                status_code=408,
                headers=NO_STORE,
            )(scope, receive, send)
        await run_connected(
            self.app,
            scope,
            receive,
            send,
            bytes(body),
            deadline=max(0, SESSION_VALIDATION_SECONDS - (time.monotonic() - started)),
        )
