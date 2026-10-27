from app.answer.errors import AnswerError
from app.answer.provider import AnswerProvider
from app.answer.schemas import AnswerRecommendation
from app.schemas import QuestionObservation


def abstain(observation: QuestionObservation, status: str, message: str) -> AnswerRecommendation:
    return AnswerRecommendation.model_validate(
        {
            "status": status,
            "question_type": observation.question_type,
            "selected_options": [],
            "answer_text": None,
            "true_false_answer": None,
            "code_answer": None,
            "explanation": message,
            "key_points": [],
            "confidence": 0.0,
            "warnings": [message],
        }
    )


def validate_recommendation(
    observation: QuestionObservation, answer: AnswerRecommendation
) -> AnswerRecommendation:
    if answer.question_type != observation.question_type:
        raise AnswerError(
            "answer_type_mismatch", "The recommendation did not match the question type. Try again."
        )
    labels = {option.label: option.text for option in observation.options}
    if any(label not in labels for label in answer.selected_options):
        raise AnswerError(
            "invalid_option_selection",
            "The provider selected an option that was not observed. Try again.",
        )
    has_answer = (
        answer.answer_text is not None
        or answer.code_answer is not None
        or answer.true_false_answer is not None
    )
    if answer.status == "uncertain" and not has_answer:
        if answer.selected_options or answer.confidence != 0 or answer.key_points:
            raise AnswerError(
                "invalid_answer_response",
                "The uncertain result contained an inconsistent recommendation.",
            )
        return answer
    if answer.status in ("insufficient_information", "unsupported"):
        return answer
    if observation.question_type != "true_false" and answer.true_false_answer is not None:
        raise AnswerError(
            "invalid_answer_response", "The provider returned an unexpected true/false response."
        )
    if observation.question_type == "true_false" and answer.true_false_answer is None:
        raise AnswerError(
            "invalid_answer_response", "The provider did not supply a clear true/false response."
        )
    if labels or observation.question_type in ("multiple_choice", "multiple_select"):
        expected = observation.required_selection_count
        if observation.question_type in ("multiple_choice", "true_false"):
            expected = 1
        if not answer.selected_options or (
            expected is not None and len(answer.selected_options) != expected
        ):
            raise AnswerError(
                "selection_count_mismatch",
                "The provider returned the wrong number of options. Try again.",
            )
        if observation.question_type == "true_false":
            chosen = labels[answer.selected_options[0]].strip().casefold().rstrip(".")
            if chosen in ("true", "false") and (chosen == "true") != answer.true_false_answer:
                raise AnswerError(
                    "invalid_answer_response", "The true/false recommendation was inconsistent."
                )
    elif answer.selected_options:
        raise AnswerError(
            "invalid_option_selection", "This question does not have selectable options."
        )
    return answer


class AnswerService:
    def __init__(self, provider: AnswerProvider):
        self.provider = provider

    async def recommend(self, observation: QuestionObservation) -> AnswerRecommendation:
        if (
            observation.status != "detected"
            or not observation.question_text
            or not observation.question_text.strip()
        ):
            return abstain(
                observation,
                "insufficient_information",
                "Read a complete, clear question first. Retake unclear content.",
            )
        if observation.question_type in (
            "multiple_choice",
            "true_false",
        ) and observation.required_selection_count not in (None, 1):
            return abstain(
                observation,
                "insufficient_information",
                "The question type conflicts with its selection instructions. Retake or review it.",
            )
        if observation.question_type == "unknown":
            return abstain(
                observation,
                "unsupported",
                "The question type is unknown. Retake or clarify the visible question.",
            )
        if observation.question_type in ("multiple_choice", "multiple_select") and (
            not observation.options
            or (
                observation.required_selection_count is not None
                and observation.required_selection_count > len(observation.options)
            )
        ):
            return abstain(
                observation,
                "insufficient_information",
                "There are not enough visible options to recommend an answer.",
            )
        try:
            result = await self.provider.recommend(observation)
            result = AnswerRecommendation.model_validate(result.model_dump())
            return validate_recommendation(observation, result)
        except AnswerError:
            raise
        except Exception:
            raise AnswerError(
                "invalid_answer_response",
                "The answer recommendation could not be validated. Please try again.",
            ) from None
