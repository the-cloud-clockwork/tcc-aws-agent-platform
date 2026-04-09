"""Token cost computation per model — provider-agnostic.

Pricing is loaded from environment variables — no hardcoded model IDs or
prices.  Set ``MODEL_PRICING`` to a JSON object mapping model IDs
to ``[input_per_1k, output_per_1k]`` tuples.  Set ``MODEL_DEFAULT_PRICING``
to a JSON array ``[input_per_1k, output_per_1k]`` for unknown models.

The legacy ``BEDROCK_MODEL_PRICING`` / ``BEDROCK_DEFAULT_PRICING`` env vars
are still accepted as deprecated aliases for backward compatibility with
Bedrock-only deployments — a warning is logged when they are used.

Usage::

    tracker = CostTracker()
    cost = tracker.compute_cost(
        model_id="claude-sonnet-4-6",
        input_tokens=1500,
        output_tokens=800,
    )
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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


# Sensible defaults so token→USD works out of the box for the models
# currently in use on the LiteLLM proxy. Pricing is USD per 1k tokens
# and reflects the Anthropic public list price for claude-sonnet-4 /
# claude-haiku-4 as of 2026-Q1. Override with MODEL_PRICING env var
# if your proxy negotiates different rates.
_DEFAULT_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-6": (0.00025, 0.00125),
    "openai/claude-sonnet-4-6": (0.003, 0.015),
    "openai/claude-haiku-4-6": (0.00025, 0.00125),
}


def _load_pricing_from_env() -> dict[str, tuple[float, float]]:
    """Load model pricing from ``MODEL_PRICING`` env var.

    Expected format: JSON object ``{"model_id": [input_per_1k, output_per_1k], ...}``
    Falls back to the deprecated ``BEDROCK_MODEL_PRICING`` alias when
    ``MODEL_PRICING`` is absent. Built-in defaults are merged underneath
    so known LiteLLM model IDs always resolve.
    """
    pricing: dict[str, tuple[float, float]] = dict(_DEFAULT_MODEL_PRICING)
    raw = os.environ.get("MODEL_PRICING", "")
    if not raw:
        raw = os.environ.get("BEDROCK_MODEL_PRICING", "")
        if raw:
            logger.warning(
                "BEDROCK_MODEL_PRICING is deprecated, use MODEL_PRICING instead."
            )
    if not raw:
        return pricing
    try:
        data = json.loads(raw)
        pricing.update({k: (v[0], v[1]) for k, v in data.items()})
    except (json.JSONDecodeError, IndexError, TypeError):
        logger.warning("Invalid MODEL_PRICING format, ignoring override")
    return pricing


def _load_default_pricing_from_env() -> tuple[float, float] | None:
    """Load fallback pricing from ``MODEL_DEFAULT_PRICING`` env var.

    Expected format: JSON array ``[input_per_1k, output_per_1k]``
    Falls back to the deprecated ``BEDROCK_DEFAULT_PRICING`` alias when
    ``MODEL_DEFAULT_PRICING`` is absent.
    """
    raw = os.environ.get("MODEL_DEFAULT_PRICING", "")
    if not raw:
        raw = os.environ.get("BEDROCK_DEFAULT_PRICING", "")
        if raw:
            logger.warning(
                "BEDROCK_DEFAULT_PRICING is deprecated, use MODEL_DEFAULT_PRICING instead."
            )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return (data[0], data[1])
    except (json.JSONDecodeError, IndexError, TypeError):
        logger.warning("Invalid MODEL_DEFAULT_PRICING format, ignoring")
        return None


class CostTracker:
    """Computes token costs for model invocations — provider-agnostic.

    Pricing is resolved from (in order):
    1. ``custom_pricing`` constructor param
    2. ``MODEL_PRICING`` env var (falls back to ``BEDROCK_MODEL_PRICING``)
    3. Built-in defaults for known LiteLLM model IDs
    4. ``default_pricing`` constructor param
    5. ``MODEL_DEFAULT_PRICING`` env var (falls back to ``BEDROCK_DEFAULT_PRICING``)
    6. Logs a warning and returns zero pricing for unknown models

    Parameters
    ----------
    custom_pricing:
        Optional dict to override or extend env-based pricing.
        Keys are model IDs, values are ``(input_per_1k, output_per_1k)`` tuples.
    default_pricing:
        Optional fallback for unknown models.
    """

    def __init__(
        self,
        custom_pricing: dict[str, tuple[float, float]] | None = None,
        default_pricing: tuple[float, float] | None = None,
    ) -> None:
        self._pricing: dict[str, tuple[float, float]] = _load_pricing_from_env()
        if custom_pricing:
            self._pricing.update(custom_pricing)

        self._default_pricing = default_pricing or _load_default_pricing_from_env()

    def get_pricing(self, model_id: str) -> tuple[float, float]:
        """Return ``(input_per_1k, output_per_1k)`` for a model ID.

        Raises ``ValueError`` if the model is unknown and no default pricing
        is configured.
        """
        pricing = self._pricing.get(model_id)
        if pricing is not None:
            return pricing
        if self._default_pricing is not None:
            return self._default_pricing
        # Return zero pricing instead of crashing — cost tracking is
        # observability, not critical path. Log a warning once.
        logger.warning(
            "No pricing configured for model '%s' — cost tracking disabled. "
            "Set MODEL_PRICING or MODEL_DEFAULT_PRICING env var.",
            model_id,
        )
        return (0.0, 0.0)

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
