from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionType = Literal[
    "multiple_choice",
    "multiple_select",
    "true_false",
    "short_answer",
    "essay",
    "mathematics",
    "code",
    "mixed",
    "visual_reasoning",
    "unknown",
]
Text = Annotated[str, Field(min_length=1, max_length=20000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class QuestionOption(StrictModel):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    text: Text


class VisualElement(StrictModel):
    kind: Literal[
        "chart", "diagram", "table", "screenshot", "illustration", "formula", "code", "other"
    ]
    description: Annotated[str, Field(min_length=1, max_length=4000)]
    text: Text | None
    language: Annotated[str, Field(min_length=1, max_length=80)] | None


class VisualImage(StrictModel):
    identifier: Annotated[str, Field(min_length=1, max_length=40)]
    position: Annotated[str, Field(min_length=1, max_length=120)]
    role: Literal["original", "edited", "option", "sequence", "comparison", "unknown"]
    description: Annotated[str, Field(min_length=1, max_length=4000)]


class VisualComparison(StrictModel):
    element: Annotated[str, Field(min_length=1, max_length=160)]
    property: Literal["text", "color", "spacing", "size", "position", "presence", "style"]
    original: Annotated[str, Field(min_length=1, max_length=500)]
    edited: Annotated[str, Field(min_length=1, max_length=500)]
    status: Literal["changed", "unchanged", "uncertain"]


class VisualTask(StrictModel):
    kind: Literal["editing_prompt", "odd_one_out", "sequence", "spot_difference", "mixed_visual"]
    images: Annotated[list[VisualImage], Field(min_length=1, max_length=20)]
    image_count: Annotated[int, Field(ge=1, le=20)]
    complete: bool
    direction: Literal["established", "ambiguous", "not_applicable"]
    # Neutral, visible facts only; no recommended selection or inferred rule.
    observed_changes: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=1200)]], Field(max_length=30)
    ]
    requested_output: Literal["editing_prompt", "selection", "explanation"] | None = None
    comparisons: Annotated[list[VisualComparison], Field(max_length=40)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def consistent_images(self) -> Self:
        if self.kind == "mixed_visual" and self.requested_output == "editing_prompt":
            self.kind = "editing_prompt"
        ids = [image.identifier for image in self.images]
        if len(ids) != len(set(ids)) or self.image_count != len(self.images):
            raise ValueError("Visual image identifiers and counts must be consistent")
        properties = [(row.element.casefold().strip(), row.property) for row in self.comparisons]
        if len(properties) != len(set(properties)):
            raise ValueError("Comparison properties must not be duplicated")
        if any(
            row.status == "unchanged" and row.original != row.edited for row in self.comparisons
        ):
            raise ValueError("Unchanged properties must have equal values")
        if (
            self.kind == "editing_prompt" or self.requested_output == "editing_prompt"
        ) and self.direction == "established":
            roles = [image.role for image in self.images]
            if roles.count("original") != 1 or roles.count("edited") != 1:
                raise ValueError("An established edit requires one original and one edited image")
        return self


class QuestionObservation(StrictModel):
    status: Literal["detected", "unclear", "no_question"]
    question_type: QuestionType
    question_text: Text | None
    options: Annotated[list[QuestionOption], Field(max_length=100)]
    instructions: Annotated[list[Text], Field(max_length=30)]
    required_selection_count: Annotated[int, Field(ge=1, le=100)] | None
    visible_context: Annotated[list[Text], Field(max_length=30)]
    visual_elements: Annotated[list[VisualElement], Field(max_length=40)]
    extraction_confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    warnings: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=2000)]], Field(max_length=30)
    ]
    # Default preserves old clients/fixtures; new provider output includes this nullable field.
    visual_task: VisualTask | None = None

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "detected" and not self.question_text:
            raise ValueError("A detected question requires visible question text")
        if self.status == "no_question" and (
            self.question_text is not None
            or self.options
            or self.required_selection_count is not None
            or self.question_type != "unknown"
        ):
            raise ValueError("No-question observations cannot claim a detected question")
        if self.status == "unclear" and not self.warnings:
            raise ValueError("Unclear observations require an uncertainty warning")
        labels = [option.label for option in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("Option labels must be unique")
        if self.visual_task:
            task = self.visual_task
            if self.status == "no_question":
                raise ValueError("No-question observations cannot contain a visual task")
            if task.kind in ("odd_one_out", "sequence"):
                choices = {image.identifier for image in task.images if image.role == "option"}
                if choices != set(labels) or (task.kind == "odd_one_out" and len(choices) < 2):
                    raise ValueError("Visual choices must match the observed option labels")
        return self


class VisionRequest(StrictModel):
    media_type: Annotated[str, Field(min_length=1, max_length=64)]
    image_base64: Annotated[str, Field(min_length=1, repr=False)]
    session_id: (
        Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")]
        | None
    ) = None
    session_revision: Annotated[int, Field(ge=1, le=2147483646)] | None = None

    @model_validator(mode="after")
    def session_pair(self) -> Self:
        if (self.session_id is None) != (self.session_revision is None):
            raise ValueError("Session ID and revision must be supplied together")
        if self.session_id is not None:
            self.session_id = str(UUID(self.session_id))
        return self
