import asyncio
import json

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import ValidationError

from app.answer.assessment import require_coverage, response_plan
from app.answer.context import LearningContext
from app.answer.errors import AnswerError
from app.answer.prompt import ANSWER_INSTRUCTIONS, answer_input
from app.answer.schemas import AnswerRecommendation
from app.answer.visual import compose_editing_response
from app.config import Settings
from app.diagnostics import emit, span
from app.performance import Timing, provider_role
from app.providers.client import lease
from app.rag.prompt import GROUNDED_INSTRUCTIONS, VERIFY_INSTRUCTIONS
from app.rag.schemas import GroundedDraft, GroundingCheck
from app.schemas import QuestionObservation


class OpenAIAnswerProvider:
    def __init__(self, settings: Settings, clients=None):
        self.settings = settings
        self.clients = clients

    async def recommend(
        self, observation: QuestionObservation, context: LearningContext | None = None
    ) -> AnswerRecommendation:
        result = await self._parse(
            ANSWER_INSTRUCTIONS + "\n" + response_plan(observation),
            answer_input(observation, context),
            AnswerRecommendation,
        )
        with Timing("answer_formatting"):
            result = compose_editing_response(observation, result)
            require_coverage(observation, result)
            return result

    async def recommend_grounded(
        self, observation, mode, evidence, context: LearningContext | None = None
    ):
        payload = dict(
            reasoning_mode=mode,
            observation=observation.model_dump(),
            retrieved_evidence=[e.model_dump() for e in evidence],
        )
        if context is not None:
            payload["learning_context"] = context.model_dump()
        try:
            async with asyncio.timeout(self.settings.answer_timeout_seconds):
                draft = await self._parse(
                    GROUNDED_INSTRUCTIONS + "\n" + response_plan(observation),
                    json.dumps(payload, ensure_ascii=False),
                    GroundedDraft,
                )
                # Format before Materials Only's independent support check, never after it.
                with Timing("answer_formatting"):
                    prepared = compose_editing_response(observation, draft.recommendation)
                if prepared != draft.recommendation:
                    draft.recommendation = prepared
                    draft.support = [s for s in draft.support if s.target != "key_point"]
                require_coverage(observation, draft.recommendation)
                if (
                    mode == "materials_only"
                    and draft.sufficient_evidence
                    and not draft.contradictory_evidence
                ):
                    check = await self._parse(
                        VERIFY_INSTRUCTIONS,
                        json.dumps(
                            dict(
                                observation=payload["observation"],
                                evidence=payload["retrieved_evidence"],
                                proposal=draft.model_dump(),
                            ),
                            ensure_ascii=False,
                        ),
                        GroundingCheck,
                    )
                    emit(
                        "support_verification",
                        outcome="supported"
                        if check.supported and not check.contradictory
                        else "rejected",
                        reason="contradictory_evidence"
                        if check.contradictory
                        else "support_verified"
                        if check.supported
                        else "support_verification_failed",
                    )
                    if not check.supported or check.contradictory:
                        draft.sufficient_evidence = False
                        draft.contradictory_evidence = check.contradictory
                        draft.limitation = check.limitation
                return draft
        except TimeoutError:
            raise AnswerError(
                "answer_timeout", "Grounding verification timed out. Try again.", 504
            ) from None

    @span("answer_provider")
    async def _parse(self, instructions, task_input, schema):
        if not self.settings.provider_configured:
            raise AnswerError(
                "answer_not_configured",
                "Set OPENAI_API_KEY in backend/.env, then restart the backend.",
                503,
            )
        try:
            async with (
                lease(
                    self.clients,
                    AsyncOpenAI,
                    api_key=self.settings.openai_api_key.get_secret_value(),
                    base_url="https://api.openai.com/v1",
                    max_retries=0,
                    timeout=httpx.Timeout(self.settings.answer_timeout_seconds, connect=5),
                ) as client,
                asyncio.timeout(self.settings.answer_timeout_seconds),
            ):
                with Timing(
                    "provider_sdk",
                    provider="openai",
                    role=provider_role.get()
                    or (
                        "verification"
                        if schema is GroundingCheck
                        else "grounded_draft"
                        if schema is GroundedDraft
                        else "answer"
                    ),
                    model=self.settings.openai_answer_model,
                ):
                    raw = await client.responses.with_raw_response.parse(
                        model=self.settings.openai_answer_model,
                        instructions=instructions,
                        input=[
                            {
                                "role": "user",
                                "content": [{"type": "input_text", "text": task_input}],
                            }
                        ],
                        text_format=schema,
                        reasoning={"effort": self.settings.answer_reasoning_effort},
                        max_output_tokens=self.settings.answer_max_output_tokens,
                        store=False,
                    )
                # Inspect completion metadata BEFORE the SDK parses potentially cut-off JSON.
                # This is the same HTTP response, not an additional provider request.
                metadata = raw.http_response.json()
                if (metadata.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
                    raise AnswerError(
                        "answer_truncated",
                        "The provider reached its output limit before completing the answer. "
                        "Retry explicitly with fewer questions.",
                        502,
                    )
                if metadata.get("status") != "completed":
                    raise AnswerError(
                        "invalid_answer_response",
                        "The provider did not complete the response. Please retry explicitly.",
                    )
                response = raw.parse()
            if response.status != "completed" or response.output_parsed is None:
                raise AnswerError(
                    "invalid_answer_response",
                    "The provider did not return a complete recommendation. Please try again.",
                )
            # Return only validated public output, never response reasoning items or metadata.
            with Timing("answer_validation"):
                return schema.model_validate(response.output_parsed.model_dump())
        except AnswerError:
            raise
        except (APITimeoutError, TimeoutError):
            raise AnswerError(
                "answer_timeout", "The suggested answer timed out. Please try again.", 504
            ) from None
        except AuthenticationError:
            raise AnswerError(
                "answer_authentication",
                "The provider rejected backend credentials. Review backend configuration.",
                503,
            ) from None
        except RateLimitError:
            raise AnswerError(
                "answer_rate_limited",
                "The answer provider is busy or its quota is unavailable. Try again later.",
                503,
            ) from None
        except APIConnectionError:
            raise AnswerError(
                "answer_unavailable",
                "The backend could not reach the answer provider. Please try again.",
                503,
            ) from None
        except APIStatusError:
            raise AnswerError(
                "answer_provider_error",
                "The answer provider could not process this observation. Please try again.",
            ) from None
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise AnswerError(
                "invalid_answer_response",
                "The answer provider returned an invalid recommendation. Please try again.",
            ) from None
