from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas import QuestionType, StrictModel

AnswerText = Annotated[str, Field(min_length=1, max_length=8000)]


class CodeAnswer(StrictModel):
    language: Annotated[str, Field(min_length=1, max_length=80)] | None
    code: Annotated[str, Field(min_length=1, max_length=12000)]


class AnswerRecommendation(StrictModel):
    status: Literal["answered", "uncertain", "insufficient_information", "unsupported"]
    question_type: QuestionType
    selected_options: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(max_length=100)
    ]
    answer_text: AnswerText | None
    true_false_answer: bool | None
    code_answer: CodeAnswer | None
    explanation: AnswerText
    key_points: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=1200)]], Field(max_length=8)
    ]
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    warnings: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=2000)]], Field(max_length=30)
    ]

    @model_validator(mode="after")
    def honest_status(self) -> Self:
        if len(self.selected_options) != len(set(self.selected_options)):
            raise ValueError("Duplicate selections are not allowed")
        if not self.explanation.strip() or (
            self.answer_text is not None and not self.answer_text.strip()
        ):
            raise ValueError("Response text must not be blank")
        if self.status in ("insufficient_information", "unsupported"):
            if (
                self.selected_options
                or self.answer_text is not None
                or self.code_answer is not None
                or self.true_false_answer is not None
                or self.key_points
                or self.confidence != 0
            ):
                raise ValueError("Abstentions cannot contain an answer or answer confidence")
        if self.status != "answered" and not self.warnings:
            raise ValueError("Non-definitive recommendations require a warning")
        if (
            self.status == "answered"
            and self.answer_text is None
            and self.code_answer is None
            and self.true_false_answer is None
        ):
            raise ValueError("An answered result needs a direct response")
        return self
