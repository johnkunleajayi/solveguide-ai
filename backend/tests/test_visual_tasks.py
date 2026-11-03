"""Offline visual contracts and orchestration, not a model-accuracy benchmark."""

import asyncio
import base64
import copy
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError
from test_answer import client, run_service
from test_provider import install_transport, sdk_response

from app.answer.errors import AnswerError
from app.answer.prompt import ANSWER_INSTRUCTIONS, answer_input
from app.answer.schemas import AnswerRecommendation
from app.answer.service import AnswerService
from app.config import Settings
from app.images import validate_image
from app.providers.openai import OBSERVATION_INSTRUCTIONS, OpenAIVisionProvider
from app.rag.prompt import GROUNDED_INSTRUCTIONS, VERIFY_INSTRUCTIONS
from app.rag.retrieval import Retrieved
from app.rag.schemas import ReasoningRequest
from app.rag.service import RagService
from app.schemas import QuestionObservation, VisionRequest


@pytest.fixture
def visual(observation_data):
    observation_data.update(
        question_type="visual_reasoning",
        question_text="Describe the edit from Original to Edited.",
        options=[],
        required_selection_count=None,
        instructions=["Preserve unchanged elements."],
        visual_task={
            "kind": "editing_prompt",
            "image_count": 2,
            "complete": True,
            "direction": "established",
            "images": [
                {
                    "identifier": "Original",
                    "position": "right",
                    "role": "original",
                    "description": "White slide; green title 'Study'; small circle at top-left.",
                },
                {
                    "identifier": "Edited",
                    "position": "left",
                    "role": "edited",
                    "description": "White slide; mint title 'Research'; circle shifted right.",
                },
            ],
            "observed_changes": [
                "Title changes from Study to Research.",
                "Title changes from green to mint.",
                "Circle moves right; white background remains unchanged.",
            ],
        },
    )
    return observation_data


def response(answer_data, observation):
    return {
        **answer_data,
        "question_type": observation["question_type"],
        "selected_options": [],
        "answer_text": "Change Study to Research, recolor the title mint and move the circle "
        "right. Preserve the white background and all other elements.",
    }


def test_edit_prompt_keeps_reverse_layout_direction_and_complete_observed_changes(
    visual, answer_data
):
    observation = QuestionObservation.model_validate(visual)
    payload = json.loads(answer_input(observation))
    assert payload["visual_task"]["images"][0]["position"] == "right"
    assert payload["visual_task"]["observed_changes"] == visual["visual_task"]["observed_changes"]
    answer, provider = run_service(visual, response(answer_data, visual))
    assert all(word in answer.answer_text for word in ("Research", "mint", "right", "Preserve"))
    assert provider.recommend.await_args.args[0].visual_task.direction == "established"


@pytest.mark.parametrize("kind", ["odd_one_out", "sequence"])
def test_five_visual_choices_preserve_labels_positions_and_selection(visual, answer_data, kind):
    visual["visual_task"].update(
        kind=kind,
        direction="not_applicable",
        image_count=5,
        images=[
            dict(identifier=label, position=f"row 1 column {i}", role="option", description=shape)
            for i, (label, shape) in enumerate(
                zip("ABCDE", ["circle", "circle", "square", "circle", "circle"], strict=True), 1
            )
        ],
        observed_changes=[],
    )
    visual["options"] = [
        dict(label=image["identifier"], text=image["description"])
        for image in visual["visual_task"]["images"]
    ]
    result, _ = run_service(visual, {**response(answer_data, visual), "selected_options": ["C"]})
    assert result.selected_options == ["C"]
    with pytest.raises(AnswerError):
        run_service(visual, {**response(answer_data, visual), "selected_options": ["Z"]})
    if kind == "odd_one_out":
        with pytest.raises(AnswerError):
            run_service(visual, {**response(answer_data, visual), "selected_options": ["A", "C"]})
    visual["visual_task"]["images"][0]["identifier"] = "invented"
    with pytest.raises(ValidationError):
        QuestionObservation.model_validate(visual)


@pytest.mark.parametrize("case", ["incomplete", "direction", "missing_image", "missing_task"])
def test_ambiguous_visuals_abstain_before_answer_provider(visual, answer_data, case):
    task = visual["visual_task"]
    if case == "incomplete":
        task["complete"] = False
    elif case == "direction":
        task["direction"] = "ambiguous"
    elif case == "missing_image":
        task.update(kind="spot_difference", direction="not_applicable", image_count=1)
        task["images"] = task["images"][:1]
    else:
        visual["visual_task"] = None
    result, provider = run_service(visual, response(answer_data, visual))
    assert result.status == "insufficient_information" and result.confidence == 0
    provider.recommend.assert_not_awaited()


def test_visual_schema_rejects_invented_direction_counts_and_hidden_answers(visual):
    for patch in (
        {"image_count": 5},
        {"correct_option": "A"},
        {"images": [visual["visual_task"]["images"][0]] * 2},
    ):
        data = copy.deepcopy(visual)
        data["visual_task"].update(patch)
        with pytest.raises(ValidationError):
            QuestionObservation.model_validate(data)


def test_sequence_without_choices_can_describe_next_pattern(visual, answer_data):
    visual["visual_task"].update(kind="sequence", direction="not_applicable")
    for image in visual["visual_task"]["images"]:
        image["role"] = "sequence"
    result, _ = run_service(visual, response(answer_data, visual))
    assert result.status == "answered" and result.selected_options == []


def test_legacy_observation_without_visual_field_remains_readable(observation_data):
    observation_data.pop("visual_task")
    assert QuestionObservation.model_validate(observation_data).visual_task is None


def test_editing_task_requires_plain_copyable_prompt_not_a_code_response(visual, answer_data):
    with pytest.raises(AnswerError, match="invalid_answer_response"):
        run_service(
            visual,
            {
                **response(answer_data, visual),
                "answer_text": None,
                "code_answer": {"language": None, "code": "not an editing prompt"},
            },
        )


@pytest.mark.parametrize("mode", ["general", "context_guided", "materials_only"])
def test_visual_modes_preserve_fallback_and_materials_abstention(visual, answer_data, mode):
    owner, doc = uuid4(), uuid4()
    repository = SimpleNamespace(selection=AsyncMock(), validate=AsyncMock())
    provider = SimpleNamespace(
        recommend=AsyncMock(
            return_value=AnswerRecommendation.model_validate(response(answer_data, visual))
        )
    )
    service = RagService(repository, None, AnswerService(provider), Settings(_env_file=None))
    service.retriever.retrieve = AsyncMock(return_value=Retrieved([], "lexical", {}))
    request = ReasoningRequest(
        observation=QuestionObservation.model_validate(visual),
        mode=mode,
        document_ids=[str(doc)],
        allow_context_transmission=True,
    )
    result = asyncio.run(service.recommend(owner, request))
    if mode == "materials_only":
        assert result.status == "insufficient_information" and not result.citations
        provider.recommend.assert_not_awaited()
    else:
        assert result.status == "answered"
        provider.recommend.assert_awaited_once()
        if mode == "context_guided":
            assert result.grounding_status == "general_reasoning" and not result.citations
        else:
            repository.selection.assert_not_awaited()
            service.retriever.retrieve.assert_not_awaited()


def test_visual_sdk_accepts_synthetic_two_slide_image_without_another_provider_call(
    monkeypatch, visual
):
    # Actual SDK parsing against a local HTTP transport double. No model inference.
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=sdk_response(visual))

    install_transport(monkeypatch, handler)
    image = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 10), "Edited", fill="black")
    draw.text((340, 10), "Original", fill="black")
    draw.text((20, 60), "Research", fill="#A3FFCF")
    draw.text((340, 60), "Study", fill="#55E6A5")
    draw.ellipse((50, 100, 70, 120), fill="black")
    draw.ellipse((340, 100, 360, 120), fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    payload = VisionRequest(
        media_type="image/png", image_base64=base64.b64encode(buffer.getvalue()).decode()
    )
    validated = validate_image(payload)
    observed = asyncio.run(
        OpenAIVisionProvider(Settings(_env_file=None, openai_api_key="test-only")).observe(
            validated
        )
    )
    assert observed.visual_task.image_count == 2 and len(calls) == 1
    assert calls[0]["store"] is False
    assert "visual_task" in calls[0]["text"]["format"]["schema"]["properties"]


def test_visual_answer_route_has_no_image_payload_and_sanitizes_logs(visual, answer_data, caplog):
    provider = SimpleNamespace(
        recommend=AsyncMock(
            return_value=AnswerRecommendation.model_validate(response(answer_data, visual))
        )
    )
    with caplog.at_level("INFO"):
        result = client(provider).post("/api/v1/answer", json=visual)
    assert result.status_code == 200
    assert "Research" not in caplog.text and "Study" not in caplog.text
    assert "image_base64" not in answer_input(QuestionObservation.model_validate(visual))


def test_visual_prompts_keep_observation_separate_from_answer_and_document_support():
    assert "NEVER answer" in OBSERVATION_INSTRUCTIONS
    assert "EVERY visible task image" in OBSERVATION_INSTRUCTIONS
    assert "preserve unchanged" in ANSWER_INSTRUCTIONS
    assert "Materials Only" in GROUNDED_INSTRUCTIONS
    assert "not document evidence" in VERIFY_INSTRUCTIONS
