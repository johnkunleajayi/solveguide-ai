from typing import Annotated, Literal, Self

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
        return self


class VisionRequest(StrictModel):
    media_type: Annotated[str, Field(min_length=1, max_length=64)]
    image_base64: Annotated[str, Field(min_length=1, repr=False)]
