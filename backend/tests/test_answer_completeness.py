import asyncio
import json

import httpx
import pytest
from test_answer import install_mock, sdk_result

from app.answer.assessment import question_ids
from app.answer.errors import AnswerError
from app.answer.openai import OpenAIAnswerProvider
from app.config import Settings
from app.rag.prompt import GROUNDED_INSTRUCTIONS
from app.schemas import QuestionObservation


def assessment(data, count):
    return QuestionObservation.model_validate(
        {
            **data,
            "question_type": "mixed",
            "question_text": "Visual Assessment\n"
            + "\n".join(f"Question {i}: Explain the visible task." for i in range(1, count + 1)),
            "options": [],
            "required_selection_count": None,
        }
    )


def run(observation):
    return asyncio.run(
        OpenAIAnswerProvider(Settings(_env_file=None, openai_api_key="test-only")).recommend(
            observation
        )
    )


@pytest.mark.parametrize(
    "count,phrase", [(5, "concise but complete"), (10, "short numbered answers")]
)
def test_assessment_contract_covers_every_question_once(
    monkeypatch, observation_data, answer_data, count, phrase
):
    observation = assessment(observation_data, count)
    result = {
        **answer_data,
        "question_type": "mixed",
        "selected_options": [],
        "answer_text": "\n".join(
            f"Q{i}: Complete response with essential calculation." for i in range(1, count + 1)
        ),
    }

    def handler(request, calls):
        calls.append(1)
        body = json.loads(request.content)
        assert phrase in body["instructions"]
        assert "EVERY ID" in body["instructions"]
        assert "BEFORE optional summaries" in body["instructions"]
        assert body["max_output_tokens"] == 6000
        return httpx.Response(200, json=sdk_result(result))

    calls = install_mock(monkeypatch, handler)
    answer = run(observation)
    for i in range(1, count + 1):
        assert f"Q{i}:" in answer.answer_text
    assert "[[END" not in answer.answer_text
    assert len(calls) == 1
    assert "4-5 questions: concise but complete" in GROUNDED_INSTRUCTIONS


@pytest.mark.parametrize("count", [5, 10])
def test_completed_but_omitted_last_question_is_not_accepted(
    monkeypatch, observation_data, answer_data, count
):
    observation = assessment(observation_data, count)
    result = {
        **answer_data,
        "question_type": "mixed",
        "selected_options": [],
        "answer_text": "\n".join(f"Q{i}: Answer." for i in range(1, count)),
    }

    def handler(request, calls):
        calls.append(1)
        return httpx.Response(200, json=sdk_result(result))

    calls = install_mock(monkeypatch, handler)
    with pytest.raises(AnswerError) as caught:
        run(observation)
    assert caught.value.code == "incomplete_assessment"
    assert len(calls) == 1


@pytest.mark.parametrize("broken_json", [False, True])
def test_token_truncation_detected_before_structured_parsing_without_retry(
    monkeypatch, observation_data, answer_data, broken_json
):
    body = sdk_result(answer_data)
    body["status"] = "incomplete"
    body["incomplete_details"] = {"reason": "max_output_tokens"}
    if broken_json:
        body["output"][1]["content"][0]["text"] = '{"answer_text":"unfinished'

    def handler(request, calls):
        calls.append(1)
        return httpx.Response(200, json=body)

    calls = install_mock(monkeypatch, handler)
    with pytest.raises(AnswerError) as caught:
        run(QuestionObservation.model_validate(observation_data))
    assert caught.value.code == "answer_truncated"
    assert caught.value.status == 502
    assert len(calls) == 1


def test_numbered_options_and_page_position_are_not_question_counts(observation_data):
    for text in [
        "Question 4 of 10: Which option?",
        "1. Option one\n2. Option two",
        "Question 5: Solve this one problem.",
    ]:
        assert (
            question_ids(
                QuestionObservation.model_validate({**observation_data, "question_text": text})
            )
            == []
        )


@pytest.mark.parametrize(
    "kind,question,direct,code",
    [
        (
            "short_answer",
            "How would you improve our brand quality?",
            (
                "I will improve our brand quality by establishing consistent brand guidelines "
                "and standardizing our communication materials."
            ),
            None,
        ),
        (
            "short_answer",
            "Analyze the change from 100 to 120 units.",
            "The increase is 20 units, a 20% rise relative to the initial 100 units.",
            None,
        ),
        (
            "mathematics",
            "Calculate the percentage increase from 100 to 120.",
            "(120 - 100) / 100 × 100 = 20%.",
            None,
        ),
        (
            "code",
            "Write Python code to add two numbers.",
            "The function returns the sum of the two inputs.",
            {"language": "python", "code": "def add(a, b):\n    return a + b"},
        ),
    ],
)
def test_submission_ready_voice_preserves_analysis_calculations_and_code(
    monkeypatch, observation_data, answer_data, kind, question, direct, code
):
    obs = QuestionObservation.model_validate(
        {
            **observation_data,
            "question_type": kind,
            "question_text": question,
            "options": [],
            "required_selection_count": None,
        }
    )
    result = {
        **answer_data,
        "question_type": kind,
        "selected_options": [],
        "answer_text": direct,
        "code_answer": code,
    }

    def handler(request, calls):
        calls.append(1)
        instructions = json.loads(request.content)["instructions"]
        assert "submission-ready" in instructions and "first person" in instructions
        assert "Do not\ninvent personal experience" in instructions
        return httpx.Response(200, json=sdk_result(result))

    calls = install_mock(monkeypatch, handler)
    answer = run(obs)
    assert answer.answer_text == direct
    assert "You should explain" not in answer.answer_text
    if code:
        assert answer.code_answer.code == code["code"]
    assert len(calls) == 1


@pytest.mark.parametrize(
    "detail", ["", "Q1: Explanation.\nQ2: Explanation.\nQ3: Explanation.\nQ4: I would improve by"]
)
def test_restored_provider_displays_useful_partial_assessment_without_end_markers(
    monkeypatch, observation_data, answer_data, detail
):
    obs = assessment(observation_data, 5).model_copy(
        update={
            "question_text": "Assessment\n"
            + "\n".join(f"{i}. Explain the task." for i in range(1, 6))
        }
    )
    text = (
        "Q1: A useful response.\nQ2: A useful response.\n"
        "Q3: A useful response.\nQ4: I will improve by"
    )
    result = {
        **answer_data,
        "question_type": "mixed",
        "selected_options": [],
        "answer_text": text,
        "explanation": detail or "A useful explanation.",
    }

    def handler(request, calls):
        calls.append(1)
        assert "[[END" not in json.loads(request.content)["instructions"]
        return httpx.Response(200, json=sdk_result(result))

    calls = install_mock(monkeypatch, handler)
    answer = run(obs)
    assert answer.answer_text == text
    assert answer.status == "answered"
    assert len(calls) == 1
