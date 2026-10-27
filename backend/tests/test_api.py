import asyncio
import base64
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from conftest import authorized_test_app
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import MAX_BODY_BYTES, MAX_IMAGE_BYTES, Settings
from app.errors import VisionError
from app.main import create_app
from app.schemas import QuestionObservation

PATH = "/api/v1/vision/question"


def test_health_has_no_secret():
    client = TestClient(
        create_app(Settings(_env_file=None, openai_api_key=None)), base_url="http://127.0.0.1"
    )
    response = client.get("/api/health")
    assert response.json() == {
        "status": "ok",
        "vision": {"provider": "openai", "configured": False},
        "database": {"configured": False},
        "authentication": {"configured": False},
    }
    assert response.headers["cache-control"] == "no-store"


def test_missing_key_is_graceful(image_payload):
    client = TestClient(
        authorized_test_app(create_app(Settings(_env_file=None, openai_api_key=None))),
        base_url="http://127.0.0.1",
    )
    response = client.post(PATH, json=image_payload, headers={"Origin": "http://127.0.0.1:1420"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


@pytest.mark.parametrize(
    "kind,count",
    [
        ("multiple_choice", 1),
        ("multiple_select", 2),
        ("essay", None),
        ("short_answer", None),
        ("true_false", 1),
        ("mathematics", None),
        ("code", None),
        ("mixed", None),
        ("unknown", None),
    ],
)
def test_question_types(api_factory, image_payload, observation_data, kind, count):
    observation_data["question_type"] = kind
    observation_data["required_selection_count"] = count
    if kind not in ("multiple_choice", "multiple_select", "true_false"):
        observation_data["options"] = []
        observation_data["instructions"] = []
    if kind == "multiple_select":
        observation_data["question_text"] = "Which shapes have three sides?"
        observation_data["instructions"] = ["Select two options."]
        observation_data["options"] = [
            {"label": "A", "text": "Equilateral triangle"},
            {"label": "B", "text": "Square"},
            {"label": "C", "text": "Right triangle"},
            {"label": "D", "text": "Circle"},
        ]
    if kind == "essay":
        observation_data["question_text"] = (
            "Compare two renewable energy sources.\n"
            "Discuss their advantages and limitations in separate paragraphs."
        )
        observation_data["instructions"] = ["Write three paragraphs."]
    if kind == "short_answer":
        observation_data["question_text"] = (
            "Name the process by which plants convert light into energy."
        )
        observation_data["instructions"] = ["Write one sentence."]
    if kind == "true_false":
        observation_data["question_text"] = "True or false: a square has four equal sides."
        observation_data["options"] = [
            {"label": "T", "text": "True"},
            {"label": "F", "text": "False"},
        ]
    if kind == "mathematics":
        observation_data["question_text"] = (
            "Evaluate \u222b\u2080\u00b9 x\u00b2 dx. Preserve x \u2260 0."
        )
        observation_data["visual_elements"] = [
            {
                "kind": "formula",
                "description": "An integral with lower and upper bounds.",
                "text": "\u222b\u2080\u00b9 x\u00b2 dx",
                "language": None,
            }
        ]
    if kind == "code":
        observation_data["question_text"] = "What is the type of x?"
        observation_data["visual_elements"] = [
            {
                "kind": "code",
                "description": "A conditional Python assignment.",
                "text": "if flag:\n    x = [1, 2]",
                "language": "python",
            }
        ]
    response = api_factory().post(PATH, json=image_payload)
    assert response.status_code == 200
    assert response.json() == observation_data
    assert "answer" not in response.json() and "reasoning" not in response.json()
    assert response.headers["cache-control"] == "no-store"


def test_no_question_and_ambiguity_are_observations(api_factory, image_payload, observation_data):
    observation_data.update(
        status="no_question",
        question_type="unknown",
        question_text=None,
        options=[],
        required_selection_count=None,
        extraction_confidence=0.0,
        warnings=["No visible question."],
    )
    assert api_factory().post(PATH, json=image_payload).json()["status"] == "no_question"
    observation_data.update(
        status="unclear",
        question_text="Partial prompt [unclear]",
        warnings=["Question text is cropped."],
    )
    assert api_factory().post(PATH, json=image_payload).json()["warnings"] == [
        "Question text is cropped."
    ]


def test_selection_count_can_remain_unknown(api_factory, image_payload, observation_data):
    observation_data.update(
        question_type="multiple_select",
        required_selection_count=None,
        instructions=["Choose all that apply."],
    )
    assert api_factory().post(PATH, json=image_payload).json()["required_selection_count"] is None


@pytest.mark.parametrize(
    "patch",
    [
        {"correct_answer": "A"},
        {"extraction_confidence": 1.2},
        {"question_type": "made_up"},
        {"question_text": None},
        {"status": "unclear", "warnings": []},
    ],
)
def test_strict_schema_rejects_invented_or_inconsistent_fields(observation_data, patch):
    with pytest.raises(ValidationError):
        QuestionObservation.model_validate({**observation_data, **patch})


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"media_type": "image/jpeg", "image_base64": "abcd"}, "invalid_image_type"),
        ({"media_type": "image/png", "image_base64": "not base64!"}, "invalid_image"),
        (
            {"media_type": "image/png", "image_base64": base64.b64encode(b"not a png").decode()},
            "invalid_image",
        ),
        (
            {
                "media_type": "image/png",
                "image_base64": "A" * (((MAX_IMAGE_BYTES + 2) // 3) * 4 + 4),
            },
            "image_too_large",
        ),
    ],
)
def test_invalid_images_never_reach_provider(api_factory, payload, expected):
    provider = type("Fake", (), {"observe": AsyncMock()})()
    response = api_factory(provider).post(PATH, json=payload)
    assert response.status_code in (413, 415, 422)
    assert response.json()["error"]["code"] == expected
    provider.observe.assert_not_awaited()


def test_validation_errors_do_not_echo_input(api_factory):
    marker = "sensitive-image-data"
    response = api_factory().post(
        PATH, json={"media_type": "image/png", "image_base64": marker, "path": "D:/secret"}
    )
    assert response.status_code == 422
    assert marker not in response.text and "secret" not in response.text


def test_oversized_declared_body(api_factory):
    response = api_factory().post(
        PATH,
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)},
    )
    assert response.status_code == 413


def test_streamed_body_is_bounded_without_content_length(api_factory):
    app = api_factory().app

    async def run():
        async def chunks():
            for _ in range(15):
                yield b"x" * 1024 * 1024

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            return await client.post(
                PATH,
                content=chunks(),
                headers={"Origin": "http://127.0.0.1:1420", "Content-Type": "application/json"},
            )

    assert asyncio.run(run()).status_code == 413


@pytest.mark.parametrize(
    "origin", ["https://untrusted.example", "null", "http://localhost:1420", ""]
)
def test_foreign_or_missing_origin_rejected(api_factory, image_payload, origin):
    response = api_factory().post(PATH, json=image_payload, headers={"Origin": origin})
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_only_expected_desktop_origins_are_allowed(api_factory, image_payload):
    client = api_factory()
    response = client.options(
        PATH,
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "access-control-allow-credentials" not in response.headers
    assert (
        client.post(
            PATH, json=image_payload, headers={"Origin": "http://tauri.localhost"}
        ).status_code
        == 200
    )


def test_provider_abstraction_errors_and_logs_are_sanitized(api_factory, image_payload, caplog):
    async def fail(_):
        raise RuntimeError("sensitive provider details")

    provider = type("Fake", (), {"observe": staticmethod(fail)})()
    with caplog.at_level("INFO", logger="solveguide.vision"):
        response = api_factory(provider).post(PATH, json=image_payload)
    assert response.status_code == 503
    assert "sensitive" not in response.text
    assert image_payload["image_base64"] not in caplog.text
    assert "sensitive" not in caplog.text
    assert json.loads(caplog.records[-1].message)["outcome"] == "vision_unavailable"


def test_busy_request_is_rejected_without_second_provider_call(api_factory, image_payload):
    async def run():
        started = asyncio.Event()
        finish = asyncio.Event()

        async def observe(_):
            started.set()
            await finish.wait()
            raise VisionError("provider_timeout", "Timed out.", 504)

        provider = type("Fake", (), {"observe": staticmethod(observe)})()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_factory(provider).app),
            base_url="http://127.0.0.1",
            headers={"Origin": "http://127.0.0.1:1420"},
        ) as client:
            first = asyncio.create_task(client.post(PATH, json=image_payload))
            await started.wait()
            second = await client.post(PATH, json=image_payload)
            finish.set()
            await first
            return second

    assert asyncio.run(run()).json()["error"]["code"] == "vision_busy"
