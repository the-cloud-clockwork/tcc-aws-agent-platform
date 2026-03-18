"""Tests for CostTracker."""
from __future__ import annotations

from agent_core.observability.cost_tracker import CostTracker, TokenCost


class TestCostTracker:
    def test_known_model_pricing(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            input_tokens=1000,
            output_tokens=500,
        )
        assert isinstance(cost, TokenCost)
        assert cost.input_tokens == 1000
        assert cost.output_tokens == 500
        # $0.003/1K input + $0.015/1K output
        assert abs(cost.input_cost_usd - 0.003) < 1e-8
        assert abs(cost.output_cost_usd - 0.0075) < 1e-8
        assert abs(cost.total_usd - 0.0105) < 1e-8

    def test_opus_pricing(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            model_id="eu.anthropic.claude-opus-4-6-v1",
            input_tokens=2000,
            output_tokens=1000,
        )
        # $0.015/1K input + $0.075/1K output
        assert abs(cost.input_cost_usd - 0.030) < 1e-8
        assert abs(cost.output_cost_usd - 0.075) < 1e-8
        assert abs(cost.total_usd - 0.105) < 1e-8

    def test_unknown_model_uses_default(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            model_id="some-future-model-v99",
            input_tokens=1000,
            output_tokens=1000,
        )
        # Default: $0.003/1K input + $0.015/1K output
        assert abs(cost.input_cost_usd - 0.003) < 1e-8
        assert abs(cost.output_cost_usd - 0.015) < 1e-8

    def test_custom_pricing(self) -> None:
        tracker = CostTracker(
            custom_pricing={"my-model": (0.001, 0.002)}
        )
        cost = tracker.compute_cost("my-model", 5000, 2000)
        assert abs(cost.input_cost_usd - 0.005) < 1e-8
        assert abs(cost.output_cost_usd - 0.004) < 1e-8
        assert abs(cost.total_usd - 0.009) < 1e-8

    def test_zero_tokens(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost("us.anthropic.claude-sonnet-4-20250514-v1:0", 0, 0)
        assert cost.total_usd == 0.0

    def test_to_dict(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost("us.anthropic.claude-sonnet-4-20250514-v1:0", 1000, 500)
        d = cost.to_dict()
        assert d["model_id"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"
        assert d["input_tokens"] == 1000
        assert d["output_tokens"] == 500
        assert isinstance(d["total_usd"], float)

    def test_known_models_list(self) -> None:
        tracker = CostTracker()
        models = tracker.known_models
        assert len(models) > 5
        assert "us.anthropic.claude-sonnet-4-20250514-v1:0" in models

    def test_get_pricing(self) -> None:
        tracker = CostTracker()
        inp, out = tracker.get_pricing("amazon.nova-micro-v1:0")
        assert inp == 0.000035
        assert out == 0.00014

    def test_haiku_pricing(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            "anthropic.claude-3-5-haiku-20241022-v1:0",
            10000,
            5000,
        )
        # $0.0008/1K input + $0.004/1K output
        assert abs(cost.input_cost_usd - 0.008) < 1e-8
        assert abs(cost.output_cost_usd - 0.020) < 1e-8
