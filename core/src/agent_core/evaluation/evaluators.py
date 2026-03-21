"""Built-in evaluator constants and resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.schemas.evaluation_config import EvaluatorLevel


@dataclass(frozen=True)
class EvaluatorInfo:
    """Metadata for a built-in evaluator."""

    name: str
    category: str
    level: EvaluatorLevel
    description: str


BUILTIN_EVALUATORS: dict[str, EvaluatorInfo] = {
    # Response Quality — TRACE level
    "Builtin.Correctness": EvaluatorInfo(
        name="Builtin.Correctness",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="Factual accuracy of agent responses.",
    ),
    "Builtin.Completeness": EvaluatorInfo(
        name="Builtin.Completeness",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="Whether the response fully addresses the request.",
    ),
    "Builtin.Faithfulness": EvaluatorInfo(
        name="Builtin.Faithfulness",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="Whether the response is grounded in retrieved context.",
    ),
    "Builtin.Helpfulness": EvaluatorInfo(
        name="Builtin.Helpfulness",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="How useful the response is to the user.",
    ),
    "Builtin.Harmlessness": EvaluatorInfo(
        name="Builtin.Harmlessness",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="Whether the response avoids harmful content.",
    ),
    "Builtin.Coherence": EvaluatorInfo(
        name="Builtin.Coherence",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="Logical consistency and flow of the response.",
    ),
    "Builtin.Relevance": EvaluatorInfo(
        name="Builtin.Relevance",
        category="response_quality",
        level=EvaluatorLevel.TRACE,
        description="How relevant the response is to the query.",
    ),
    # Task Completion — SESSION level
    "Builtin.GoalSuccessRate": EvaluatorInfo(
        name="Builtin.GoalSuccessRate",
        category="task_completion",
        level=EvaluatorLevel.SESSION,
        description="Whether the agent achieved the stated goal.",
    ),
    # Tool Usage — SPAN level
    "Builtin.ToolSelectionAccuracy": EvaluatorInfo(
        name="Builtin.ToolSelectionAccuracy",
        category="tool_usage",
        level=EvaluatorLevel.SPAN,
        description="Whether the agent chose the right tools.",
    ),
    "Builtin.ToolParameterAccuracy": EvaluatorInfo(
        name="Builtin.ToolParameterAccuracy",
        category="tool_usage",
        level=EvaluatorLevel.SPAN,
        description="Whether the agent passed correct parameters to tools.",
    ),
    # Safety — TRACE level
    "Builtin.Harmfulness": EvaluatorInfo(
        name="Builtin.Harmfulness",
        category="safety",
        level=EvaluatorLevel.TRACE,
        description="Detection of harmful or dangerous content.",
    ),
    "Builtin.Stereotyping": EvaluatorInfo(
        name="Builtin.Stereotyping",
        category="safety",
        level=EvaluatorLevel.TRACE,
        description="Detection of stereotyping or biased content.",
    ),
}


def resolve_evaluator_ids(names: list[str]) -> list[str]:
    """Validate and resolve evaluator identifiers.

    Accepts a mix of ``Builtin.*`` names and custom evaluator IDs.
    Raises ``ValueError`` for unknown builtin names.

    Parameters
    ----------
    names:
        List of evaluator identifiers.

    Returns
    -------
    The same list, validated.
    """
    for name in names:
        if name.startswith("Builtin.") and name not in BUILTIN_EVALUATORS:
            known = ", ".join(sorted(BUILTIN_EVALUATORS.keys()))
            raise ValueError(f"Unknown builtin evaluator: {name}. Known: {known}")
    return names
