"""Strategy condition evaluator.

Evaluates StrategyBlueprint entry/exit conditions against signal data
using safe operator-based comparisons.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any

from agent_core.blueprints.strategy import Condition, ConditionGroup, StrategyBlueprint

OPERATORS: dict[str, Any] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


@dataclass
class ConditionResult:
    field: str | None
    op: str
    expected: Any
    actual: Any
    passed: bool


@dataclass
class EvaluationResult:
    matched: bool
    logic: str
    condition_results: list[ConditionResult] = field(default_factory=list)
    score: float = 0.0


@dataclass
class StrategyMatch:
    strategy_id: str
    entry_matched: bool
    exit_matched: bool
    entry_result: EvaluationResult
    exit_result: EvaluationResult
    score: float = 0.0


class StrategyEvaluator:
    """Evaluates strategy conditions against signal data."""

    def evaluate_condition(self, cond: Condition, signals: dict[str, Any]) -> ConditionResult:
        """Evaluate a single condition against signals."""
        # Special type-based conditions (e.g., threshold_breach)
        if cond.type is not None:
            present = cond.type in signals
            return ConditionResult(
                field=None,
                op="type_check",
                expected=cond.type,
                actual=cond.type if present else None,
                passed=present,
            )

        if cond.field is None:
            return ConditionResult(field=None, op="unknown", expected=None, actual=None, passed=False)

        if cond.op is None:
            return ConditionResult(field=cond.field, op="none", expected=cond.value, actual=None, passed=False)

        if cond.op not in OPERATORS:
            raise ValueError(f"Unknown operator: {cond.op!r}")

        # Missing field → condition fails
        if cond.field not in signals:
            return ConditionResult(
                field=cond.field,
                op=cond.op,
                expected=cond.value,
                actual=None,
                passed=False,
            )

        actual = signals[cond.field]
        try:
            passed = OPERATORS[cond.op](actual, cond.value)
        except (TypeError, ValueError):
            passed = False

        return ConditionResult(
            field=cond.field,
            op=cond.op,
            expected=cond.value,
            actual=actual,
            passed=passed,
        )

    def evaluate_group(self, group: ConditionGroup, signals: dict[str, Any]) -> EvaluationResult:
        """Evaluate a condition group (AND/OR logic) against signals."""
        results = [self.evaluate_condition(c, signals) for c in group.conditions]
        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        score = passed_count / total if total > 0 else 0.0

        if group.logic == "AND":
            matched = all(r.passed for r in results)
        else:  # OR
            matched = any(r.passed for r in results)

        return EvaluationResult(
            matched=matched,
            logic=group.logic,
            condition_results=results,
            score=score,
        )

    def evaluate(self, blueprint: StrategyBlueprint, signals: dict[str, Any]) -> StrategyMatch:
        """Evaluate a strategy blueprint against signals."""
        entry_result = self.evaluate_group(blueprint.entry_conditions, signals)
        exit_result = self.evaluate_group(blueprint.exit_conditions, signals)
        combined_score = (entry_result.score + exit_result.score) / 2.0

        return StrategyMatch(
            strategy_id=blueprint.id,
            entry_matched=entry_result.matched,
            exit_matched=exit_result.matched,
            entry_result=entry_result,
            exit_result=exit_result,
            score=combined_score,
        )

    def evaluate_all(
        self, blueprints: list[StrategyBlueprint], signals: dict[str, Any]
    ) -> list[StrategyMatch]:
        """Evaluate multiple strategies, return sorted by score descending."""
        matches = [self.evaluate(bp, signals) for bp in blueprints]
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches
