import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.answer import openai as provider_module
from app.answer.errors import AnswerError
from app.answer.schemas import AnswerRecommendation
from app.answer.service import AnswerService
from app.config import Settings
from app.main import create_app
from app.schemas import QuestionObservation


@pytest.fixture
def answer_data():
    return {
        "status": "answered",
        "question_type": "multiple_choice",
        "selected_options": ["A"],
        "answer_text": "A circle.",
        "true_false_answer": None,
        "code_answer": None,
        "explanation": "The observed figure is round without corners.",
        "key_points": [],
        "confidence": 0.88,
        "warnings": [],
    }


def run_service(observation_data, answer_data):
    provider = type(
        "Fake",
        (),
        {"recommend": AsyncMock(return_value=AnswerRecommendation.model_validate(answer_data))},
    )()
    result = asyncio.run(
        AnswerService(provider).recommend(QuestionObservation.model_validate(observation_data))
    )
    return result, provider


def test_mcq_valid_recommendation_and_distinct_confidence(observation_data, answer_data):
    result, provider = run_service(observation_data, answer_data)
    assert (
        result.selected_options == ["A"]
        and result.confidence != observation_data["extraction_confidence"]
    )
    provider.recommend.assert_awaited_once()


@pytest.mark.parametrize(
    "labels,code",
    [
        (["A", "B"], "selection_count_mismatch"),
        (["Z"], "invalid_option_selection"),
        ([], "selection_count_mismatch"),
    ],
)
def test_mcq_invalid_selection_fails_closed(observation_data, answer_data, labels, code):
    answer_data["selected_options"] = labels
    with pytest.raises(AnswerError) as caught:
        run_service(observation_data, answer_data)
    assert caught.value.code == code


def test_duplicate_labels_and_extra_reasoning_fields_rejected(answer_data):
    for patch in (
        {"selected_options": ["A", "A"]},
        {"chain_of_thought": "private"},
        {"confidence": 2.0},
        {"unexpected": "extra"},
    ):
        with pytest.raises(ValidationError):
            AnswerRecommendation.model_validate({**answer_data, **patch})


@pytest.mark.parametrize("labels,valid", [(["A", "B"], True), (["A"], False)])
def test_multiple_select_count(observation_data, answer_data, labels, valid):
    observation_data.update(question_type="multiple_select", required_selection_count=2)
    answer_data.update(question_type="multiple_select", selected_options=labels)
    if valid:
        assert run_service(observation_data, answer_data)[0].selected_options == labels
    else:
        with pytest.raises(AnswerError, match="selection_count_mismatch"):
            run_service(observation_data, answer_data)


def test_multiple_select_unknown_count_is_not_invented(observation_data, answer_data):
    observation_data.update(question_type="multiple_select", required_selection_count=None)
    answer_data.update(question_type="multiple_select", selected_options=["A", "B"])
    assert len(run_service(observation_data, answer_data)[0].selected_options) == 2


def test_true_false_without_artificial_options(observation_data, answer_data):
    observation_data.update(
        question_type="true_false", question_text="A square has four sides.", options=[]
    )
    answer_data.update(
        question_type="true_false", selected_options=[], true_false_answer=True, answer_text="True."
    )
    assert run_service(observation_data, answer_data)[0].true_false_answer is True


def test_true_false_option_must_match_boolean(observation_data, answer_data):
    observation_data.update(
        question_type="true_false",
        options=[{"label": "T", "text": "True"}, {"label": "F", "text": "False"}],
    )
    answer_data.update(question_type="true_false", selected_options=["F"], true_false_answer=True)
    with pytest.raises(AnswerError, match="invalid_answer_response"):
        run_service(observation_data, answer_data)


@pytest.mark.parametrize("kind", ["short_answer", "essay", "mathematics", "code", "mixed"])
def test_non_choice_educational_answers(observation_data, answer_data, kind):
    prompts = {
        "short_answer": "Name a renewable energy source.",
        "essay": "Compare solar and wind power.",
        "mathematics": "Solve 2x + 1 = 7.",
        "code": "Write a Python function that adds two numbers.",
        "mixed": "Use the supplied table and equation to describe the trend.",
    }
    observation_data.update(
        question_type=kind, question_text=prompts[kind], options=[], required_selection_count=None
    )
    answer_data.update(
        question_type=kind,
        selected_options=[],
        answer_text="A concise direct response.",
        explanation="A brief educational explanation.",
        key_points=["One relevant public explanation point."],
    )
    if kind == "mathematics":
        answer_data.update(answer_text="x = 3", key_points=["2x = 6", "x = 3"])
    if kind == "code":
        answer_data.update(
            code_answer={"language": "python", "code": "def add(a, b):\n    return a + b"}
        )
    result, _ = run_service(observation_data, answer_data)
    assert result.question_type == kind and not result.selected_options
    assert result.answer_text == answer_data["answer_text"]
    if kind == "code":
        assert result.code_answer.code.endswith("\n    return a + b")


def test_uncertain_and_provider_abstentions(observation_data, answer_data):
    answer_data.update(status="uncertain", confidence=0.4, warnings=["Two choices are plausible."])
    assert run_service(observation_data, answer_data)[0].status == "uncertain"
    for status in ("insufficient_information", "unsupported"):
        answer_data.update(
            status=status,
            selected_options=[],
            answer_text=None,
            confidence=0.0,
            warnings=["Required context is missing."],
        )
        assert run_service(observation_data, answer_data)[0].status == status


@pytest.mark.parametrize(
    "patch,status",
    [
        ({"status": "unclear", "warnings": ["Cropped prompt."]}, "insufficient_information"),
        ({"question_type": "unknown"}, "unsupported"),
        ({"required_selection_count": 2}, "insufficient_information"),
    ],
)
def test_inadequate_input_does_not_spend_credits(observation_data, patch, status):
    observation_data.update(patch)
    provider = type("Fake", (), {"recommend": AsyncMock()})()
    result = asyncio.run(
        AnswerService(provider).recommend(QuestionObservation.model_validate(observation_data))
    )
    assert result.status == status and result.answer_text is None
    provider.recommend.assert_not_awaited()


def client(provider=None, configured=False):
    return TestClient(
        create_app(
            Settings(_env_file=None, openai_api_key="test-only" if configured else None),
            answer_provider=provider,
        ),
        base_url="http://127.0.0.1",
        headers={"Origin": "http://127.0.0.1:1420"},
    )


def test_route_accepts_observation_without_screenshot(observation_data, answer_data):
    provider = type(
        "Fake",
        (),
        {"recommend": AsyncMock(return_value=AnswerRecommendation.model_validate(answer_data))},
    )()
    response = client(provider).post("/api/v1/answer", json=observation_data)
    assert response.status_code == 200 and response.json()["selected_options"] == ["A"]
    assert response.headers["cache-control"] == "no-store"
    for patch in ({"image_base64": "sensitive-image"}, {"answer_text": "preloaded answer"}):
        invalid = client(provider).post("/api/v1/answer", json={**observation_data, **patch})
        assert invalid.status_code == 422 and "sensitive-image" not in invalid.text


def test_missing_credentials(observation_data):
    response = client().post("/api/v1/answer", json=observation_data)
    assert (
        response.status_code == 503 and response.json()["error"]["code"] == "answer_not_configured"
    )


def test_answer_route_has_request_and_origin_bounds(observation_data):
    api = client()
    assert (
        api.post(
            "/api/v1/answer", json=observation_data, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        api.post(
            "/api/v1/answer",
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": str(256 * 1024 + 1)},
        ).status_code
        == 413
    )
    invalid = api.post("/api/v1/answer", json={**observation_data, "question_type": "invalid"})
    assert invalid.status_code == 422


def test_answer_logging_does_not_contain_payloads(observation_data, answer_data, caplog):
    provider = type(
        "Fake",
        (),
        {"recommend": AsyncMock(return_value=AnswerRecommendation.model_validate(answer_data))},
    )()
    with caplog.at_level("INFO", logger="solveguide.answer"):
        assert client(provider).post("/api/v1/answer", json=observation_data).status_code == 200
    assert (
        observation_data["question_text"] not in caplog.text
        and answer_data["answer_text"] not in caplog.text
    )
    assert json.loads(caplog.records[-1].message)["outcome"] == "answered"


def install_mock(monkeypatch, handler):
    calls = []

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: handler(request, calls)),
                trust_env=False,
            ),
        )

    monkeypatch.setattr(provider_module, "AsyncOpenAI", factory)
    return calls


def sdk_result(data):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "test-answer-model",
        "status": "completed",
        "tools": [],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "output": [
            {"type": "reasoning", "id": "rs_test", "summary": []},
            {
                "type": "message",
                "id": "msg_test",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(data), "annotations": []}],
            },
        ],
    }


def recommend(observation_data):
    return asyncio.run(
        provider_module.OpenAIAnswerProvider(
            Settings(
                _env_file=None, openai_api_key="test-only", openai_answer_model="test-answer-model"
            )
        ).recommend(QuestionObservation.model_validate(observation_data))
    )


def test_official_sdk_contract_is_text_only_structured_and_stateless(
    monkeypatch, observation_data, answer_data
):
    def handler(request, calls):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=sdk_result(answer_data))

    calls = install_mock(monkeypatch, handler)
    result = recommend(observation_data)
    body = calls[0]
    assert len(calls) == 1 and body["model"] == "test-answer-model" and body["store"] is False
    assert body["reasoning"] == {"effort": "medium"}
    assert body["text"]["format"]["strict"] is True
    assert body["input"][0]["content"][0]["type"] == "input_text"
    assert json.loads(body["input"][0]["content"][0]["text"]) == observation_data
    assert "input_image" not in json.dumps(body) and "data:image" not in json.dumps(body)
    assert "chain_of_thought" not in result.model_dump() and "reasoning" not in result.model_dump()


@pytest.mark.parametrize(
    "status,code",
    [(401, "answer_authentication"), (429, "answer_rate_limited"), (500, "answer_provider_error")],
)
def test_sdk_errors_are_sanitized_and_not_retried(monkeypatch, observation_data, status, code):
    def handler(request, calls):
        calls.append(1)
        return httpx.Response(
            status, json={"error": {"message": "secret provider details", "type": "error"}}
        )

    calls = install_mock(monkeypatch, handler)
    with pytest.raises(AnswerError) as caught:
        recommend(observation_data)
    assert caught.value.code == code and "secret" not in caught.value.message and len(calls) == 1


def test_sdk_timeout(monkeypatch, observation_data):
    def handler(request, calls):
        raise httpx.ReadTimeout("private detail", request=request)

    install_mock(monkeypatch, handler)
    with pytest.raises(AnswerError, match="answer_timeout"):
        recommend(observation_data)


@pytest.mark.parametrize("mode", ["malformed", "incomplete", "refusal"])
def test_sdk_invalid_results_fail_closed(monkeypatch, observation_data, answer_data, mode):
    body = sdk_result({**answer_data, "private_reasoning": "not allowed"})
    if mode == "incomplete":
        body["status"] = "incomplete"
    if mode == "refusal":
        body["output"] = [
            {
                "type": "message",
                "id": "msg",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "refusal", "refusal": "Cannot comply"}],
            }
        ]
    install_mock(monkeypatch, lambda request, calls: httpx.Response(200, json=body))
    with pytest.raises(AnswerError, match="invalid_answer_response"):
        recommend(observation_data)
