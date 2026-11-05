"""Private parent-pipe bootstrap for the desktop-owned localhost server."""

import hmac
import json
import socket
import sys
import threading

import uvicorn
from starlette.responses import JSONResponse


class InstanceBoundary:
    def __init__(self, app, instance_id, token):
        self.app, self.instance_id, self.token = app, instance_id, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        health = scope["method"] == "GET" and scope["path"] == "/api/health"
        # Browser OAuth callback retains state/nonce protection and cannot supply native headers.
        callback = scope["method"] == "GET" and scope["path"] == "/api/v1/auth/google/callback"
        supplied = dict(scope["headers"]).get(b"x-solveguide-instance", b"")
        if not health and not callback and not hmac.compare_digest(supplied, self.token.encode()):
            return await JSONResponse(
                {
                    "error": {
                        "code": "backend_instance_required",
                        "message": "Use the owning desktop application.",
                    }
                },
                status_code=403,
            )(scope, receive, send)

        async def tagged(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-solveguide-instance-id", self.instance_id.encode()),
                ]
            await send(message)

        await self.app(scope, receive, tagged)


def serve(*, personal_desktop=False):
    # No application import/listen before receiving bootstrap through the private stdin pipe.
    # EOF covers parent failure before Windows job assignment/bootstrap.
    raw = sys.stdin.readline(4097)
    if not raw or len(raw) > 4096:
        raise RuntimeError("Managed backend bootstrap unavailable")
    values = json.loads(raw)
    if set(values) != {"protocol", "instance_id", "token"} or values["protocol"] != 1:
        raise RuntimeError("Invalid managed backend protocol")
    import re

    if any(
        not isinstance(values[k], str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", values[k])
        for k in ("instance_id", "token")
    ):
        raise RuntimeError("Invalid managed backend identity")
    from app.main import app

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # Personal desktop uses the already registered Google loopback callback.
        try:
            listener.bind(("127.0.0.1", 8000 if personal_desktop else 0))
        except OSError:
            if personal_desktop:
                raise RuntimeError("Personal desktop requires available localhost port 8000") from None
            raise
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                InstanceBoundary(app, values["instance_id"], values["token"]),
                host="127.0.0.1",
                port=port,
                loop="app.runtime:event_loop",
                http="h11",
                ws="none",
                access_log=False,
                timeout_graceful_shutdown=3,
            )
        )

        def control():
            # Native parent owns this pipe. EOF is also an explicit shutdown request.
            sys.stdin.readline(128)
            server.should_exit = True

        threading.Thread(target=control, daemon=True).start()
        print(
            json.dumps({"protocol": 1, "port": port, "instance_id": values["instance_id"]}),
            flush=True,
        )
        server.run(sockets=[listener])
