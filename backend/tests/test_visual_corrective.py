"""Synthetic fixture/contract tests. No live visual inference or provider billing."""

import asyncio
import base64
import copy
import json
from io import BytesIO
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError
from test_answer import run_service
from test_provider import install_transport, sdk_response

from app.answer.openai import OpenAIAnswerProvider
from app.answer.prompt import answer_input
from app.answer.schemas import AnswerRecommendation
from app.answer.service import validate_recommendation
from app.answer.visual import compose_editing_response, editing_response, visual_limitation
from app.config import Settings
from app.images import validate_image
from app.providers.openai import OBSERVATION_INSTRUCTIONS, OpenAIVisionProvider
from app.rag.schemas import GroundedDraft, GroundingCheck
from app.schemas import QuestionObservation, VisionRequest


@pytest.fixture
def comparison(observation_data):
    def row(element, prop, before, after, status="changed"):
        return dict(element=element, property=prop, original=before, edited=after, status=status)

    observation_data.update(
        question_type="visual_reasoning",
        question_text="Write an editing prompt.",
        options=[],
        required_selection_count=None,
        visual_task=dict(
            kind="mixed_visual",
            requested_output="editing_prompt",
            direction="established",
            complete=True,
            image_count=2,
            observed_changes=[],
            images=[
                dict(
                    identifier="Original",
                    position="left",
                    role="original",
                    description="Original slide.",
                ),
                dict(
                    identifier="Edited",
                    position="right",
                    role="edited",
                    description="Edited slide.",
                ),
            ],
            comparisons=[
                row("Title", "color", "blue", "green"),
                row("Gap below title", "spacing", "20 units", "40 units"),
                row("Revenue callout", "style", "blue styling", "green styling"),
                row("Second chart bar", "size", "60 units high", "100 units high"),
                row("Confidentiality footer", "presence", "visible", "removed"),
                row("Chart bars", "color", "blue", "blue", "unchanged"),
            ],
        ),
    )
    return observation_data


def proposed(answer_data):
    return {
        **answer_data,
        "question_type": "visual_reasoning",
        "selected_options": [],
        "answer_text": "Recolor every chart bar green.",
        "explanation": "The chart bars changed color.",
        "key_points": ["An unsupported recolor."],
    }


def test_all_five_edits_survive_sdk_schema_serialization_prompt_and_answer(
    monkeypatch, comparison, answer_data
):
    # Two visible slides with five deliberate geometric/textual-style edits.
    image = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(image)
    for offset, edited in [(0, False), (320, True)]:
        color = "green" if edited else "blue"
        draw.text((offset + 10, 5), "Edited" if edited else "Original", fill="black")
        draw.text((offset + 10, 25), "Quarterly Revenue", fill=color)
        title_bottom = draw.textbbox((offset + 10, 25), "Quarterly Revenue")[3]
        callout_top = title_bottom + (40 if edited else 20)
        draw.rectangle((offset + 10, callout_top, offset + 110, callout_top + 10), fill=color)
        draw.rectangle((offset + 30, 120, offset + 50, 200), fill="blue")
        draw.rectangle((offset + 70, 100 if edited else 140, offset + 90, 200), fill="blue")
        if not edited:
            draw.text((offset + 10, 220), "Confidential", fill="black")
    assert image.getpixel((75, 120)) == (255, 255, 255)
    assert image.getpixel((395, 120)) == (0, 0, 255)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    raw = buffer.getvalue()
    validated = validate_image(
        VisionRequest(media_type="image/png", image_base64=base64.b64encode(raw).decode())
    )
    assert base64.b64decode(validated.data_base64) == raw  # No resizing or lossy encode here.
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=sdk_response(comparison))

    install_transport(monkeypatch, handler)
    observed = asyncio.run(
        OpenAIVisionProvider(Settings(_env_file=None, openai_api_key="fake")).observe(validated)
    )
    serialized = QuestionObservation.model_validate_json(observed.model_dump_json())
    assert serialized.visual_task.comparisons == observed.visual_task.comparisons
    prompt = json.loads(answer_input(serialized))
    assert prompt["visual_task"]["comparisons"] == comparison["visual_task"]["comparisons"]
    assert len(calls) == 1
    result, _ = run_service(serialized.model_dump(), proposed(answer_data))
    for label in (
        "Title",
        "Gap below title",
        "Revenue callout",
        "Second chart bar",
        "Confidentiality footer",
    ):
        assert label in result.answer_text
    assert "20 units to 40 units" in result.answer_text
    assert "60 units high to 100 units high" in result.answer_text
    assert "Preserve Chart bars — color: blue" in result.answer_text
    assert "Recolor every chart bar" not in result.answer_text
    assert "chart bars changed color" not in result.explanation
    assert not result.key_points


def test_edit_output_identity_independent_of_mixed_task_kind(comparison, answer_data):
    observed = QuestionObservation.model_validate(comparison)
    assert observed.visual_task.kind == "editing_prompt"
    assert visual_limitation(observed) is None
    assert editing_response(observed) is not None
    comparison["visual_task"]["direction"] = "ambiguous"
    result, provider = run_service(comparison, proposed(answer_data))
    assert result.status == "insufficient_information"
    provider.recommend.assert_not_awaited()


def test_uncertain_properties_never_become_edit_instructions(comparison, answer_data):
    comparison["visual_task"]["comparisons"][3]["status"] = "uncertain"
    result, _ = run_service(comparison, proposed(answer_data))
    assert "Second chart bar" not in result.answer_text
    assert result.status == "uncertain" and result.warnings
    assert (
        compose_editing_response(QuestionObservation.model_validate(comparison), result) == result
    )


def test_conflicting_duplicate_comparisons_are_rejected(comparison):
    data = copy.deepcopy(comparison)
    data["visual_task"]["comparisons"].append(data["visual_task"]["comparisons"][0])
    with pytest.raises(ValidationError):
        QuestionObservation.model_validate(data)
    comparison["visual_task"]["comparisons"][-1]["edited"] = "green"
    with pytest.raises(ValidationError):
        QuestionObservation.model_validate(comparison)


@pytest.mark.parametrize("mode", ["context_guided", "materials_only"])
def test_grounded_visual_formatting_precedes_support_verification(comparison, answer_data, mode):
    observation = QuestionObservation.model_validate(comparison)
    provider = OpenAIAnswerProvider(Settings(_env_file=None))
    draft = GroundedDraft(
        recommendation=AnswerRecommendation.model_validate(proposed(answer_data)),
        sufficient_evidence=True,
        contradictory_evidence=False,
        support=[],
        general_reasoning=[],
    )
    provider._parse = AsyncMock(
        side_effect=[
            draft,
            GroundingCheck(supported=False, contradictory=False, limitation="No material support."),
        ]
    )
    result = asyncio.run(provider.recommend_grounded(observation, mode, []))
    assert "Gap below title" in result.recommendation.answer_text
    validate_recommendation(observation, result.recommendation)
    if mode == "materials_only":
        payload = json.loads(provider._parse.await_args_list[1].args[1])
        assert (
            payload["proposal"]["recommendation"]["answer_text"]
            == result.recommendation.answer_text
        )
        assert not result.sufficient_evidence  # Formatting never overrides a failed support check.
    else:
        assert provider._parse.await_count == 1


def test_visual_prompt_requires_separate_spacing_size_and_color_inspection():
    for phrase in (
        "gap BELOW the title",
        "each chart bar's height",
        "bar COLORS separately",
        "requested_output=editing_prompt",
    ):
        assert phrase in OBSERVATION_INSTRUCTIONS


def test_formatter_cannot_promote_an_answerless_uncertain_result(comparison, answer_data):
    observation = QuestionObservation.model_validate(comparison)
    answer = AnswerRecommendation.model_validate(
        {
            **proposed(answer_data),
            "status": "uncertain",
            "answer_text": None,
            "key_points": [],
            "confidence": 0.0,
            "warnings": ["Cannot recommend safely."],
        }
    )
    assert compose_editing_response(observation, answer) == answer
