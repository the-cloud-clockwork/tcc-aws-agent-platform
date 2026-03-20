"""Tests for StrategyEvaluator."""

from __future__ import annotations

import pytest

from agent_core.blueprints.strategy import Condition, ConditionGroup, StrategyBlueprint
from agent_core.blueprints.strategy_evaluator import (
    StrategyEvaluator,
)


def _make_blueprint(
    strategy_id: str = "test_strategy",
    entry_conditions: ConditionGroup | None = None,
    exit_conditions: ConditionGroup | None = None,
) -> StrategyBlueprint:
    return StrategyBlueprint(
        id=strategy_id,
        version="1.0.0",
        name="Test Strategy",
        description="A test strategy",
        asset_types=["default"],
        scopes=["us_equity"],
        required_signals=["gap_pct"],
        entry_conditions=entry_conditions or ConditionGroup(logic="AND", conditions=[]),
        exit_conditions=exit_conditions or ConditionGroup(logic="AND", conditions=[]),
        required_agents=["detector"],
        required_mcps=["data-mcp"],
    )


class TestEvaluateCondition:
    def setup_method(self):
        self.evaluator = StrategyEvaluator()

    def test_eq_operator_passes(self):
        cond = Condition(field="status", op="eq", value="bullish")
        result = self.evaluator.evaluate_condition(cond, {"status": "bullish"})
        assert result.passed is True
        assert result.actual == "bullish"

    def test_eq_operator_fails(self):
        cond = Condition(field="status", op="eq", value="bullish")
        result = self.evaluator.evaluate_condition(cond, {"status": "bearish"})
        assert result.passed is False

    def test_gt_operator(self):
        cond = Condition(field="gap_pct", op="gt", value=2.0)
        result = self.evaluator.evaluate_condition(cond, {"gap_pct": 3.5})
        assert result.passed is True

    def test_lt_operator(self):
        cond = Condition(field="gap_pct", op="lt", value=2.0)
        result = self.evaluator.evaluate_condition(cond, {"gap_pct": 3.5})
        assert result.passed is False

    def test_gte_operator(self):
        cond = Condition(field="score", op="gte", value=0.7)
        result = self.evaluator.evaluate_condition(cond, {"score": 0.7})
        assert result.passed is True

    def test_lte_operator(self):
        cond = Condition(field="score", op="lte", value=0.7)
        result = self.evaluator.evaluate_condition(cond, {"score": 0.5})
        assert result.passed is True

    def test_in_operator(self):
        cond = Condition(field="sector", op="in", value=["tech", "finance"])
        result = self.evaluator.evaluate_condition(cond, {"sector": "tech"})
        assert result.passed is True

    def test_not_in_operator(self):
        cond = Condition(field="sector", op="not_in", value=["tech", "finance"])
        result = self.evaluator.evaluate_condition(cond, {"sector": "energy"})
        assert result.passed is True

    def test_missing_field_fails(self):
        cond = Condition(field="missing_field", op="gt", value=1.0)
        result = self.evaluator.evaluate_condition(cond, {"other": 5.0})
        assert result.passed is False
        assert result.actual is None

    def test_unknown_operator_raises(self):
        cond = Condition(field="x", op="regex", value=".*")
        with pytest.raises(ValueError, match="Unknown operator"):
            self.evaluator.evaluate_condition(cond, {"x": "test"})

    def test_type_condition_present(self):
        cond = Condition(type="trailing_stop")
        result = self.evaluator.evaluate_condition(cond, {"trailing_stop": True})
        assert result.passed is True
        assert result.op == "type_check"

    def test_type_condition_absent(self):
        cond = Condition(type="trailing_stop")
        result = self.evaluator.evaluate_condition(cond, {"gap_pct": 2.0})
        assert result.passed is False

    def test_neq_operator(self):
        cond = Condition(field="status", op="neq", value="closed")
        result = self.evaluator.evaluate_condition(cond, {"status": "open"})
        assert result.passed is True


class TestEvaluateGroup:
    def setup_method(self):
        self.evaluator = StrategyEvaluator()

    def test_and_all_pass(self):
        group = ConditionGroup(
            logic="AND",
            conditions=[
                Condition(field="gap_pct", op="gt", value=2.0),
                Condition(field="volume", op="gt", value=1000),
            ],
        )
        result = self.evaluator.evaluate_group(group, {"gap_pct": 3.0, "volume": 2000})
        assert result.matched is True
        assert result.score == 1.0

    def test_and_one_fails(self):
        group = ConditionGroup(
            logic="AND",
            conditions=[
                Condition(field="gap_pct", op="gt", value=2.0),
                Condition(field="volume", op="gt", value=1000),
            ],
        )
        result = self.evaluator.evaluate_group(group, {"gap_pct": 3.0, "volume": 500})
        assert result.matched is False
        assert result.score == 0.5

    def test_or_one_passes(self):
        group = ConditionGroup(
            logic="OR",
            conditions=[
                Condition(field="gap_pct", op="gt", value=5.0),
                Condition(field="volume", op="gt", value=1000),
            ],
        )
        result = self.evaluator.evaluate_group(group, {"gap_pct": 1.0, "volume": 2000})
        assert result.matched is True
        assert result.score == 0.5

    def test_empty_group(self):
        group = ConditionGroup(logic="AND", conditions=[])
        result = self.evaluator.evaluate_group(group, {})
        assert result.matched is True  # vacuous truth
        assert result.score == 0.0


class TestEvaluate:
    def setup_method(self):
        self.evaluator = StrategyEvaluator()

    def test_full_strategy_match(self):
        bp = _make_blueprint(
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[Condition(field="gap_pct", op="gt", value=2.0)],
            ),
            exit_conditions=ConditionGroup(
                logic="AND",
                conditions=[Condition(field="gap_pct", op="lt", value=0.5)],
            ),
        )
        result = self.evaluator.evaluate(bp, {"gap_pct": 3.0})
        assert result.entry_matched is True
        assert result.exit_matched is False
        assert result.strategy_id == "test_strategy"

    def test_evaluate_all_sorted_by_score(self):
        bp1 = _make_blueprint(
            strategy_id="low_score",
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[Condition(field="x", op="gt", value=100)],
            ),
            exit_conditions=ConditionGroup(logic="AND", conditions=[]),
        )
        bp2 = _make_blueprint(
            strategy_id="high_score",
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[Condition(field="x", op="gt", value=1)],
            ),
            exit_conditions=ConditionGroup(logic="AND", conditions=[]),
        )
        results = self.evaluator.evaluate_all([bp1, bp2], {"x": 50})
        assert results[0].strategy_id == "high_score"
        assert results[1].strategy_id == "low_score"
