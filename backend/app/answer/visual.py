"""Deterministic visual sufficiency checks; no separate reasoning/provider path."""

from app.answer.errors import AnswerError
from app.schemas import QuestionObservation


def editing_task(observation: QuestionObservation) -> bool:
    task = observation.visual_task
    return bool(
        task
        and task.requested_output != "selection"
        and (task.kind == "editing_prompt" or task.requested_output == "editing_prompt")
    )


def editing_response(observation: QuestionObservation) -> tuple[str, str] | None:
    """Format observed facts, never infer edits. No extra model or image transmission.

    Grounded providers must compose this BEFORE support verification, not afterwards.
    Uncertain properties never become transformation instructions.
    """
    task = observation.visual_task
    if not editing_task(observation) or not task.comparisons or visual_limitation(observation):
        return None
    changed = [row for row in task.comparisons if row.status == "changed"]
    original = next(image for image in task.images if image.role == "original")
    edited = next(image for image in task.images if image.role == "edited")
    lines = [
        f"Transform {original.identifier} ({original.position}) "
        f"into {edited.identifier} ({edited.position})."
    ]
    for row in changed:
        lines.append(f"- {row.element} — {row.property}: change {row.original} to {row.edited}.")
    for row in task.comparisons:
        if row.status == "unchanged":
            lines.append(f"- Preserve {row.element} — {row.property}: {row.original}.")
    uncertain = any(row.status == "uncertain" for row in task.comparisons)
    lines.append(
        "Preserve explicitly unchanged properties. "
        "Do not infer edits for uncertain or unlisted properties."
        if uncertain
        else "Preserve all other elements. Do not infer additional edits."
    )
    explanation = (
        "The prompt lists the structured observed changes "
        "and preserves explicitly unchanged properties."
    )
    if uncertain:
        explanation += " Uncertain comparisons were omitted; review the original images before use."
    prompt = "\n".join(lines)
    if len(prompt) > 8000:
        raise AnswerError(
            "invalid_answer_response",
            "The visual comparison exceeds the response limit. Show a simpler comparison.",
        )
    return prompt, explanation


def compose_editing_response(observation, answer):
    """Only format a successful recommendation; never turn abstention into an answer."""
    if (
        answer.status not in ("answered", "uncertain")
        or answer.answer_text is None
        or answer.code_answer is not None
        or answer.true_false_answer is not None
    ):
        return answer
    response = editing_response(observation)
    if response:
        answer = answer.model_copy(deep=True)
        answer.answer_text, answer.explanation = response
        answer.key_points = []
        if any(row.status == "uncertain" for row in observation.visual_task.comparisons):
            answer.status = "uncertain"
            notice = "Uncertain visual properties are excluded from the prompt."
            if notice not in answer.warnings:
                answer.warnings = [notice, *answer.warnings][:30]
    return answer


def visual_limitation(observation: QuestionObservation) -> str | None:
    task = observation.visual_task
    if observation.question_type == "visual_reasoning" and task is None:
        return "The visual task was not described reliably. Capture the complete task again."
    if task is None:
        return None
    if not task.complete:
        return "Important image details or choices are incomplete or unreadable. Retake the task."
    if editing_task(observation) and task.direction != "established":
        return "Original-to-edited direction is ambiguous. Include visible labels or instructions."
    if (editing_task(observation) or task.kind == "spot_difference") and task.image_count < 2:
        return "Both comparison images must be visible before recommending a response."
    return None
