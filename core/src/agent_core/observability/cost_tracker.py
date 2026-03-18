"""Token cost computation per model using Bedrock pricing.

Maintains a lookup table of per-token costs for Bedrock models and
computes the cost of a single model invocation given input/output token counts.

Usage::

    tracker = CostTracker()
    cost = tracker.compute_cost(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        input_tokens=1500,
        output_tokens=800,
    )
    # cost.total_usd == 0.0069  (example)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenCost:
    """Result of a cost computation."""

    model_id: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_cost_usd": round(self.input_cost_usd, 8),
            "output_cost_usd": round(self.output_cost_usd, 8),
            "total_usd": round(self.total_usd, 8),
        }


# Pricing per 1K tokens in USD (as of 2025-05)
# Source: https://aws.amazon.com/bedrock/pricing/
_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1k, output_per_1k)
    # Claude 4 Sonnet
    "us.anthropic.claude-sonnet-4-20250514-v1:0": (0.003, 0.015),
    "eu.anthropic.claude-sonnet-4-6": (0.003, 0.015),
    "anthropic.claude-sonnet-4-20250514-v1:0": (0.003, 0.015),
    # Claude 4 Opus
    "eu.anthropic.claude-opus-4-6-v1": (0.015, 0.075),
    "us.anthropic.claude-opus-4-20250514-v1:0": (0.015, 0.075),
    "anthropic.claude-opus-4-20250514-v1:0": (0.015, 0.075),
    # Claude 3.5 Sonnet (v2)
    "anthropic.claude-3-5-sonnet-20241022-v2:0": (0.003, 0.015),
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": (0.003, 0.015),
    # Claude 3.5 Haiku
    "anthropic.claude-3-5-haiku-20241022-v1:0": (0.0008, 0.004),
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": (0.0008, 0.004),
    # Nova Micro
    "amazon.nova-micro-v1:0": (0.000035, 0.00014),
    # Nova Lite
    "amazon.nova-lite-v1:0": (0.00006, 0.00024),
    # Nova Pro
    "amazon.nova-pro-v1:0": (0.0008, 0.0032),
}

# Fallback for unknown models
_DEFAULT_PRICING: tuple[float, float] = (0.003, 0.015)


class CostTracker:
    """Computes token costs for Bedrock model invocations.

    Parameters
    ----------
    custom_pricing:
        Optional dict to override or extend the built-in pricing table.
        Keys are model IDs, values are ``(input_per_1k, output_per_1k)`` tuples.
    """

    def __init__(self, custom_pricing: dict[str, tuple[float, float]] | None = None) -> None:
        self._pricing = dict(_PRICING)
        if custom_pricing:
            self._pricing.update(custom_pricing)

    def get_pricing(self, model_id: str) -> tuple[float, float]:
        """Return ``(input_per_1k, output_per_1k)`` for a model ID.

        Falls back to default pricing if the model is unknown.
        """
        return self._pricing.get(model_id, _DEFAULT_PRICING)

    def compute_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> TokenCost:
        """Compute the USD cost of a single model invocation.

        Parameters
        ----------
        model_id:
            Bedrock model identifier.
        input_tokens:
            Number of input tokens.
        output_tokens:
            Number of output tokens.

        Returns
        -------
        TokenCost:
            Breakdown of costs.
        """
        input_per_1k, output_per_1k = self.get_pricing(model_id)
        input_cost = (input_tokens / 1000.0) * input_per_1k
        output_cost = (output_tokens / 1000.0) * output_per_1k

        return TokenCost(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_usd=input_cost + output_cost,
        )

    @property
    def known_models(self) -> list[str]:
        """Return list of all model IDs with known pricing."""
        return sorted(self._pricing.keys())
