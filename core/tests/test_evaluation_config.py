"""Tests for evaluation config schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.schemas.evaluation_config import (
    BuiltinEvaluator,
    CustomEvaluatorConfig,
    EvaluationConfig,
    EvaluatorLevel,
    OnlineEvaluationConfig,
)


class TestBuiltinEvaluator:
    def test_all_13_evaluators_defined(self) -> None:
        assert (
            len(BuiltinEvaluator) == 12
        )  # 12 enum members (Harmlessness != Harmfulness)

    def test_response_quality_evaluators(self) -> None:
        assert BuiltinEvaluator.CORRECTNESS.value == "Builtin.Correctness"
        assert BuiltinEvaluator.COMPLETENESS.value == "Builtin.Completeness"
        assert BuiltinEvaluator.FAITHFULNESS.value == "Builtin.Faithfulness"
        assert BuiltinEvaluator.HELPFULNESS.value == "Builtin.Helpfulness"
        assert BuiltinEvaluator.HARMLESSNESS.value == "Builtin.Harmlessness"
        assert BuiltinEvaluator.COHERENCE.value == "Builtin.Coherence"
        assert BuiltinEvaluator.RELEVANCE.value == "Builtin.Relevance"

    def test_task_completion_evaluators(self) -> None:
        assert BuiltinEvaluator.GOAL_SUCCESS_RATE.value == "Builtin.GoalSuccessRate"

    def test_tool_usage_evaluators(self) -> None:
        assert (
            BuiltinEvaluator.TOOL_SELECTION_ACCURACY.value
            == "Builtin.ToolSelectionAccuracy"
        )
        assert (
            BuiltinEvaluator.TOOL_PARAMETER_ACCURACY.value
            == "Builtin.ToolParameterAccuracy"
        )

    def test_safety_evaluators(self) -> None:
        assert BuiltinEvaluator.HARMFULNESS.value == "Builtin.Harmfulness"
        assert BuiltinEvaluator.STEREOTYPING.value == "Builtin.Stereotyping"


class TestEvaluatorLevel:
    def test_all_levels(self) -> None:
        assert EvaluatorLevel.TRACE.value == "TRACE"
        assert EvaluatorLevel.SESSION.value == "SESSION"
        assert EvaluatorLevel.SPAN.value == "SPAN"



class TestCustomEvaluatorConfig:
    def _make_config(self, **overrides) -> CustomEvaluatorConfig:
        defaults = {
            "name": "test_eval",
            "level": EvaluatorLevel.TRACE,
            "model_id": "some-model-id",
            "max_tokens": 500,
            "temperature": 1.0,
            "instructions": "Evaluate {context} and {assistant_turn}",
            "scale": [1, 5],
        }
        defaults.update(overrides)
        return CustomEvaluatorConfig(**defaults)

    def test_all_fields_required(self) -> None:
        with pytest.raises(ValidationError):
            CustomEvaluatorConfig(name="test")  # type: ignore[call-arg]

    def test_valid_config(self) -> None:
        cfg = self._make_config()
        assert cfg.name == "test_eval"
        assert cfg.model_id == "some-model-id"
        assert cfg.max_tokens == 500
        assert cfg.temperature == 1.0
        assert cfg.scale == [1, 5]

    def test_temperature_bounds(self) -> None:
        with pytest.raises(ValidationError):
            self._make_config(temperature=3.0)
        with pytest.raises(ValidationError):
            self._make_config(temperature=-0.1)

    def test_max_tokens_positive(self) -> None:
        with pytest.raises(ValidationError):
            self._make_config(max_tokens=0)

    def test_scale_minimum_entries(self) -> None:
        with pytest.raises(ValidationError):
            self._make_config(scale=[1])


class TestOnlineEvaluationConfig:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            OnlineEvaluationConfig()  # type: ignore[call-arg]

    def test_valid_config(self) -> None:
        cfg = OnlineEvaluationConfig(
            sampling_rate=50,
            evaluators=["Builtin.Correctness", "Builtin.GoalSuccessRate"],
        )
        assert cfg.sampling_rate == 50
        assert len(cfg.evaluators) == 2
        assert cfg.auto_create_execution_role is True

    def test_sampling_rate_bounds(self) -> None:
        with pytest.raises(ValidationError):
            OnlineEvaluationConfig(sampling_rate=0, evaluators=["Builtin.Correctness"])
        with pytest.raises(ValidationError):
            OnlineEvaluationConfig(
                sampling_rate=101, evaluators=["Builtin.Correctness"]
            )

    def test_evaluators_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            OnlineEvaluationConfig(sampling_rate=50, evaluators=[])


class TestEvaluationConfig:
    def test_defaults(self) -> None:
        cfg = EvaluationConfig()
        assert cfg.online is None
        assert cfg.custom_evaluators == []

    def test_with_online(self) -> None:
        cfg = EvaluationConfig(
            online=OnlineEvaluationConfig(
                sampling_rate=100,
                evaluators=["Builtin.GoalSuccessRate"],
            ),
        )
        assert cfg.online is not None
        assert cfg.online.sampling_rate == 100

    def test_with_custom_evaluators(self) -> None:
        cfg = EvaluationConfig(
            custom_evaluators=[
                CustomEvaluatorConfig(
                    name="quality",
                    level=EvaluatorLevel.TRACE,
                    model_id="test-model",
                    max_tokens=300,
                    temperature=0.5,
                    instructions="Rate {context} {assistant_turn}",
                    scale=[1, 5],
                )
            ]
        )
        assert len(cfg.custom_evaluators) == 1
        assert cfg.custom_evaluators[0].name == "quality"

    def test_frozen(self) -> None:
        cfg = EvaluationConfig()
        with pytest.raises(ValidationError):
            cfg.online = OnlineEvaluationConfig(  # type: ignore[misc]
                sampling_rate=50,
                evaluators=["Builtin.Correctness"],
            )
