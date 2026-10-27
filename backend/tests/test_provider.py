import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.config import Settings
from app.errors import VisionError
from app.images import validate_image
from app.providers import openai as provider_module
from app.schemas import QuestionObservation, VisionRequest


def sdk_response(observation):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "configured-model",
        "status": "completed",
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": json.dumps(observation), "annotations": []}
                ],
            }
        ],
    }


def install_transport(monkeypatch, handler):
    clients = []

    def client_factory(**kwargs):
        assert kwargs["max_retries"] == 0
        assert kwargs["base_url"] == "https://api.openai.com/v1"
        client = AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(provider_module, "AsyncOpenAI", client_factory)
    return clients


def observe(image_payload):
    settings = Settings(
        _env_file=None,
        openai_api_key="test-only-not-a-real-key",
        openai_vision_model="configured-model",
    )
    image = validate_image(VisionRequest.model_validate(image_payload))
    return asyncio.run(provider_module.OpenAIVisionProvider(settings).observe(image))


def test_real_sdk_structured_output_contract(monkeypatch, observation_data, image_payload):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=sdk_response(observation_data))

    clients = install_transport(monkeypatch, handler)
    result = observe(image_payload)
    assert result == QuestionObservation.model_validate(observation_data)
    assert len(requests) == 1 and all(client.is_closed() for client in clients)
    body = json.loads(requests[0].content)
    assert body["model"] == "configured-model" and body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert "NEVER answer" in body["instructions"]
    assert "correct_answer" not in json.dumps(body["text"]["format"]["schema"])


@pytest.mark.parametrize(
    "status,code",
    [(401, "provider_authentication"), (429, "provider_rate_limited"), (500, "provider_error")],
)
def test_provider_http_errors_are_sanitized_no_retries(monkeypatch, image_payload, status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"message": "private provider detail", "type": "error"}}
        )

    install_transport(monkeypatch, handler)
    with pytest.raises(VisionError) as caught:
        observe(image_payload)
    assert caught.value.code == code
    assert "private" not in caught.value.message
    assert len(calls) == 1


def test_provider_timeout_is_structured(monkeypatch, image_payload):
    def handler(request):
        raise httpx.ReadTimeout("private timeout detail", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(VisionError) as caught:
        observe(image_payload)
    assert caught.value.code == "provider_timeout" and caught.value.status == 504


@pytest.mark.parametrize("mode", ["malformed", "refusal", "incomplete"])
def test_invalid_or_refused_output_fails_closed(monkeypatch, image_payload, observation_data, mode):
    body = sdk_response({**observation_data, "correct_answer": "not allowed"})
    if mode == "refusal":
        body["output"][0]["content"] = [{"type": "refusal", "refusal": "Unable to process"}]
    if mode == "incomplete":
        body = sdk_response(observation_data)
        body["status"] = "incomplete"
    install_transport(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(VisionError) as caught:
        observe(image_payload)
    assert caught.value.code == "invalid_provider_response"
