"""Conservative formatting/coverage checks; no local question solving or provider calls."""

import re

from app.answer.errors import AnswerError
from app.schemas import QuestionObservation

QUESTION = re.compile(r"(?im)^\s*(?:#{1,3}\s*)?(?:question|q)\s*(\d{1,3})\b(?!\s+of\s+\d)")


def question_ids(observation: QuestionObservation) -> list[int]:
    text = "\n".join([observation.question_text or "", *observation.visible_context])
    ids = sorted({int(m.group(1)) for m in QUESTION.finditer(text) if 0 < int(m.group(1)) <= 100})
    # A lone "Question 4" describes one question, not four questions.
    if len(ids) >= 2:
        return ids
    return []


def response_plan(observation: QuestionObservation) -> str:
    ids = question_ids(observation)
    if not ids:
        return ""
    count = len(ids)
    style = (
        "detailed"
        if count <= 3
        else "concise but complete (about 120 words per question, excluding essential code)"
        if count <= 5
        else "short numbered answers (about 60 words per question, excluding essential code)"
        if count <= 10
        else "minimal numbered coverage of all questions before any optional detail"
    )
    return (
        f"Visible question IDs: {', '.join(map(str, ids))}. Response style: {style}. "
        "Put a direct response for EVERY ID in answer_text, each on a new line labelled Q<ID>:. "
        "Preserve essential calculations, code and question-specific instructions. "
        "If a prompt is unreadable or unsupported, say so for that ID; never invent it. "
        "Complete every numbered response before optional explanations or summaries."
    )


def require_coverage(observation: QuestionObservation, answer) -> None:
    ids = question_ids(observation)
    if len(ids) < 4 or answer.status not in ("answered", "uncertain"):
        return
    covered = {int(m.group(1)) for m in QUESTION.finditer(answer.answer_text or "")}
    if not set(ids).issubset(covered):
        raise AnswerError(
            "incomplete_assessment",
            "The response omitted one or more detected questions. "
            "Retry explicitly with fewer questions.",
            502,
        )
