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
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_core.schemas.execution_modes import ExecutionModes


class ConditionConfig(BaseModel):
    """A single field comparison condition."""

    model_config = ConfigDict(frozen=True)

    field: str = Field(..., description="Signal or parameter name to compare.")
    operator: Literal[
        "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "between"
    ] = Field(..., description="Comparison operator.")
    value: Any = Field(..., description="Threshold or target value.")


class ConditionGroupConfig(BaseModel):
    """Logical group of conditions combined with AND/OR."""

    model_config = ConfigDict(frozen=True)

    logic: Literal["and", "or"] = Field(
        default="and", description="Logical operator combining all conditions."
    )
    conditions: list[ConditionConfig] = Field(
        ..., min_length=1, description="Condition list (at least one required)."
    )


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

    execution_modes: ExecutionModes | None = Field(
        default=None,
        description="Execution mode gates (which modes this strategy runs in).",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata tags.",
    )
