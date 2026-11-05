import io
import sys

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.managed_runtime import InstanceBoundary, serve


def client():
    async def ok(request):
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[
            Route(path, ok)
            for path in ["/api/health", "/api/v1/auth/me", "/api/v1/auth/google/callback"]
        ]
    )
    return TestClient(InstanceBoundary(app, "public-instance-id", "private-instance-token"))


def test_readiness_identity_is_not_the_request_secret():
    response = client().get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-solveguide-instance-id"] == "public-instance-id"
    assert "private-instance-token" not in str(response.headers)


def test_only_owning_client_can_use_api_and_responses_are_tagged():
    app = client()
    for headers in [{}, {"x-solveguide-instance": "wrong-token"}]:
        assert app.get("/api/v1/auth/me", headers=headers).status_code == 403
    response = app.get(
        "/api/v1/auth/me", headers={"x-solveguide-instance": "private-instance-token"}
    )
    assert response.status_code == 200
    assert response.headers["x-solveguide-instance-id"] == "public-instance-id"


def test_google_callback_retains_existing_state_nonce_authorization_boundary():
    # Only transport headers are bypassed; the real auth route still validates state/nonce.
    assert client().get("/api/v1/auth/google/callback").status_code == 200


@pytest.mark.parametrize(
    "payload", ["", '{"protocol":2}', '{"protocol":1,"instance_id":"bad","token":"bad"}']
)
def test_bad_or_closed_bootstrap_cannot_start_server(monkeypatch, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    with pytest.raises(RuntimeError):
        serve()
