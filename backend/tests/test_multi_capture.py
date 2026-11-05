import asyncio
import base64
import json
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from test_provider import install_transport, sdk_response

from app.config import Settings
from app.errors import VisionError
from app.images import validate_image
from app.main import create_app
from app.providers.openai import OpenAIVisionProvider, observation_content
from app.schemas import QuestionObservation, VisionRequest


def capture(color):
    buffer = BytesIO()
    Image.new("RGB", (24, 16), color).save(buffer, format="PNG")
    return {"media_type": "image/png", "image_base64": base64.b64encode(buffer.getvalue()).decode()}


def test_ordered_captures_use_one_provider_call(monkeypatch, observation_data):
    captures = [capture(color) for color in ["red", "green", "blue", "white", "black"]]
    image = validate_image(VisionRequest(**captures[0], additional_images=captures[1:]))
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=sdk_response(observation_data))

    install_transport(monkeypatch, handler)
    settings = Settings(_env_file=None, openai_api_key="test-only")
    observation = asyncio.run(OpenAIVisionProvider(settings).observe(image))
    assert observation == QuestionObservation.model_validate(observation_data)
    assert len(requests) == 1
    content = requests[0]["input"][0]["content"]
    assert [item["image_url"] for item in content if item["type"] == "input_image"] == [
        f"data:image/png;base64,{c['image_base64']}" for c in captures
    ]
    assert "ONE question" in content[0]["text"]
    assert requests[0]["store"] is False
    assert captures[0]["image_base64"] not in repr(image)


def test_invalid_second_capture_never_reaches_provider(api_factory, image_payload):
    class Provider:
        calls = 0

        async def observe(self, image):
            self.calls += 1
            raise AssertionError("Must not execute")

    provider = Provider()
    response = api_factory(provider).post(
        "/api/v1/vision/question",
        json={
            **image_payload,
            "additional_images": [{"media_type": "image/png", "image_base64": "not-png"}],
        },
    )
    assert response.status_code == 422
    assert provider.calls == 0
    assert "not-png" not in response.text


def test_aggregate_limits_and_count(monkeypatch, image_payload):
    from app import images

    with pytest.raises(ValidationError):
        VisionRequest(**image_payload, additional_images=[image_payload] * 5)
    request = VisionRequest(**image_payload, additional_images=[image_payload])
    monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 600)
    with pytest.raises(VisionError) as caught:
        validate_image(request)
    assert caught.value.code == "image_too_large"
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 1)
    with pytest.raises(VisionError) as caught:
        validate_image(request)
    assert caught.value.code == "image_too_large"


def test_multi_capture_remains_authenticated(image_payload):
    class Provider:
        calls = 0

        async def observe(self, image):
            self.calls += 1
            raise AssertionError("Must not execute")

    provider = Provider()
    app = create_app(Settings(_env_file=None, openai_api_key=None), provider)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/v1/vision/question",
            json={**image_payload, "additional_images": [image_payload]},
            headers={"Origin": "http://127.0.0.1:1420"},
        )
    assert response.status_code == 401
    assert provider.calls == 0


def test_single_capture_behavior_is_unchanged(image_payload):
    image = validate_image(VisionRequest(**image_payload))
    assert not image.additional
    content = observation_content(image)
    assert len(content) == 2
    assert content[0]["text"] == "Observe this captured question. Do not answer it."
