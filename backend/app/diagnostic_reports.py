"""Bounded metadata only. Repeated/overlapping spans report maxima, never additive totals."""

STAGES = frozenset(
    "authentication session_liveness active_session_lookup database_setup database_query "
    "image_validation_worker vision_service vision_validation answer_service "
    "answer_validation answer_formatting answer_validation_formatting grounded_answer "
    "session_configuration_before session_configuration_after retrieval reference_selection "
    "reference_ranking".split()
)
ROLES = frozenset(
    "vision answer grounded_draft verification answer_supplement query_embedding embedding".split()
)
QUESTION_TYPES = frozenset(
    (
        "multiple_choice multiple_select true_false short_answer essay mathematics "
        "code mixed unknown visual_reasoning"
    ).split()
)


def resolve_mode(explicit=None, legacy="INFO"):
    if explicit is not None:
        if explicit not in {"NORMAL", "PERFORMANCE", "DEBUG"}:
            raise ValueError("Invalid diagnostic mode")
        return explicit
    return "DEBUG" if legacy == "DEBUG" else "NORMAL"


class Metrics:
    """One HTTP request; finite stage vocabulary, no raw events retained."""

    def __init__(self):
        self.stages = {}
        self.question_type = None

    def observe(self, stage, duration, role=None):
        if stage == "provider_sdk" and isinstance(role, str) and role in ROLES:
            stage = f"provider_{role}"
        elif not isinstance(stage, str) or stage not in STAGES:
            return
        if type(duration) is not int or not 0 <= duration <= 86_400_000:
            return
        row = self.stages.setdefault(stage, {"count": 0, "max_single_span_ms": 0})
        row["count"] += 1
        row["max_single_span_ms"] = max(row["max_single_span_ms"], duration)

    def view(self):
        # Null means not measured, never an inferred zero.
        keys = STAGES | {f"provider_{role}" for role in ROLES}
        return {key: self.stages.get(key) for key in sorted(keys)}
