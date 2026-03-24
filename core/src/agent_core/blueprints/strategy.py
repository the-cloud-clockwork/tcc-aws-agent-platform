"""Pydantic model for strategy blueprints.

A ``StrategyBlueprint`` declares domain-agnostic evaluation logic:
required signals, parameterized configuration, and condition-based
entry/exit rules.  Domain repos fill in the specifics; the platform
validates structure and loads strategies into the evaluation engine.

Example YAML::

    id: my-strategy
    name: My Strategy
    version: "1.0.0"
    required_agents: [data-collector, analyzer]
    required_signals: [score, confidence]
    parameters:
      - name: threshold
        type: float
        default: 0.7
        min_value: 0.0
        max_value: 1.0
    entry_conditions:
      logic: and
      conditions:
        - field: score
          operator: gte
          value: 0.8
    exit_conditions:
      logic: or
      conditions:
        - field: confidence
          operator: lt
          value: 0.3
    evaluation:
      primary_metric: accuracy
      metrics: [accuracy, precision, recall]
      benchmark: baseline
    risk_controls:
      max_daily_error_rate: 0.03
      max_degradation_halt: 0.10
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_core.schemas.execution_modes import ExecutionModes

_PARAM_TYPE_ALIASES: dict[str, str] = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
}


class ConditionConfig(BaseModel):
    """A single field comparison condition.

    For structured exit conditions (e.g. trailing stops), use ``type``
    instead of ``field``/``operator``/``value``.  The platform stores
    the raw dict for the domain evaluation engine.
    """

    model_config = ConfigDict(frozen=True)

    field: str | None = Field(
        default=None, description="Signal or parameter name to compare."
    )
    operator: (
        Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "between"] | None
    ) = Field(default=None, description="Comparison operator.")
    value: Any = Field(default=None, description="Threshold or target value.")
    type: str | None = Field(
        default=None,
        description="Structured condition type (e.g. 'threshold_breach') for domain evaluation.",
    )


class ConditionGroupConfig(BaseModel):
    """Logical group of conditions combined with AND/OR."""

    model_config = ConfigDict(frozen=True)

    logic: Literal["and", "or"] = Field(
        default="and", description="Logical operator combining all conditions."
    )
    conditions: list[ConditionConfig] = Field(
        ..., min_length=1, description="Condition list (at least one required)."
    )

    @field_validator("logic", mode="before")
    @classmethod
    def normalize_logic(cls, v: str) -> str:
        """Accept uppercase AND/OR."""
        if isinstance(v, str):
            return v.lower()
        return v


class ParameterConfig(BaseModel):
    """A named strategy parameter with type and optional constraints."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Parameter name (unique within strategy).")
    type: Literal["int", "float", "str", "bool", "list"] = Field(
        ..., description="Parameter data type."
    )
    default: Any = Field(default=None, description="Default value if not overridden.")
    description: str = Field(default="", description="Human-readable description.")
    min_value: float | None = Field(
        default=None, description="Minimum numeric value (int/float types only)."
    )
    max_value: float | None = Field(
        default=None, description="Maximum numeric value (int/float types only)."
    )

    @field_validator("type", mode="before")
    @classmethod
    def normalize_param_type(cls, v: str) -> str:
        """Accept common aliases (string -> str, integer -> int, etc.)."""
        if isinstance(v, str):
            return _PARAM_TYPE_ALIASES.get(v.lower(), v)
        return v


class StrategyEvaluationConfig(BaseModel):
    """Strategy backtesting and evaluation configuration."""

    model_config = ConfigDict(frozen=True)

    primary_metric: str = Field(
        ..., description="Primary performance metric for ranking."
    )
    metrics: list[str] = Field(
        default_factory=list, description="All metrics to compute."
    )
    benchmark: str | None = Field(
        default=None, description="Benchmark strategy for comparison."
    )
    lookback_window: int | None = Field(
        default=None, gt=0, description="Lookback window in periods."
    )
    min_activations_threshold: int | None = Field(
        default=None,
        gt=0,
        description="Minimum activations for statistical significance.",
    )


class RiskControlConfig(BaseModel):
    """Strategy-level risk control thresholds."""

    model_config = ConfigDict(frozen=True)

    max_daily_error_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Max daily error rate before circuit break.",
    )
    max_degradation_halt: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Max performance degradation before halt.",
    )
    circuit_breaker: dict[str, Any] | None = Field(
        default=None,
        description="Circuit breaker config (consecutive_failures, pause_periods).",
    )


class StrategyBlueprint(BaseModel):
    """Domain-agnostic strategy declaration.

    Strategies describe *what* to evaluate and *when* to act, using
    generic field comparisons.  Domain repos provide the actual signal
    values; the platform evaluates conditions and routes results.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique strategy identifier.")
    name: str = Field(..., description="Human-readable strategy name.")
    version: str = Field(..., description="Semantic version string.")
    description: str = Field(default="", description="Strategy description.")

    required_agents: list[str] = Field(
        default_factory=list,
        description="Agent IDs that must produce input signals for this strategy.",
    )
    required_mcps: list[str] = Field(
        default_factory=list,
        description="MCP server names needed by this strategy.",
    )
    required_signals: list[str] = Field(
        default_factory=list,
        description="Named signals expected from required agents.",
    )

    parameters: list[ParameterConfig] = Field(
        default_factory=list,
        description="Parameterized configuration that domain repos define.",
    )

    entry_conditions: ConditionGroupConfig | None = Field(
        default=None,
        description="Conditions that must be met to activate the strategy.",
    )
    exit_conditions: ConditionGroupConfig | None = Field(
        default=None,
        description="Conditions that trigger strategy deactivation.",
    )

    evaluation: StrategyEvaluationConfig | None = Field(
        default=None,
        description="Backtesting and evaluation configuration.",
    )
    risk_controls: RiskControlConfig | None = Field(
        default=None,
        description="Risk control thresholds and circuit breakers.",
    )

    execution_modes: ExecutionModes | None = Field(
        default=None,
        description="Execution mode gates (which modes this strategy runs in).",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata tags.",
    )
