"""Evaluation result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationScore:
    """A single evaluator score from an evaluation run."""

    evaluator_name: str
    label: str
    value: float
    explanation: str
    token_usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregated result of an evaluation run across multiple evaluators."""

    agent_id: str
    session_id: str
    scores: list[EvaluationScore] = field(default_factory=list)
