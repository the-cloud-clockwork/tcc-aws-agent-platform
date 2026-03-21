"""AgentCore Evaluation — on-demand and continuous agent quality scoring.

Lazy imports to avoid pulling in ``bedrock_agentcore_starter_toolkit``
at module load time.
"""

from __future__ import annotations


def __getattr__(name: str):  # noqa: N807
    """Lazy import to defer SDK import until first attribute access."""
    if name == "EvaluationClient":
        from agent_core.evaluation.client import EvaluationClient

        return EvaluationClient

    if name in ("EvaluationResult", "EvaluationScore"):
        from agent_core.evaluation import results as _results

        return getattr(_results, name)

    if name in ("BUILTIN_EVALUATORS", "EvaluatorInfo", "resolve_evaluator_ids"):
        from agent_core.evaluation import evaluators as _evaluators

        return getattr(_evaluators, name)

    if name in ("EvaluationError", "EvaluationConfigError", "EvaluatorNotFoundError"):
        from agent_core.evaluation import client as _client

        return getattr(_client, name)

    raise AttributeError(f"module 'agent_core.evaluation' has no attribute {name!r}")


__all__ = [
    "BUILTIN_EVALUATORS",
    "EvaluationClient",
    "EvaluationConfigError",
    "EvaluationError",
    "EvaluationResult",
    "EvaluationScore",
    "EvaluatorInfo",
    "EvaluatorNotFoundError",
    "resolve_evaluator_ids",
]
