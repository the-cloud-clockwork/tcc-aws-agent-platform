"""StrategyBlueprint Pydantic model."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Condition(BaseModel):
    """A single condition in an entry/exit rule."""

    model_config = ConfigDict(frozen=True)

    field: str | None = None
    op: str | None = None
    value: float | str | bool | list[str] | list[float] | None = None
    type: str | None = Field(
        default=None,
        description="Special condition type, e.g. 'threshold_breach'.",
    )


class ConditionGroup(BaseModel):
    """A group of conditions joined by logic."""

    model_config = ConfigDict(frozen=True)

    logic: Literal["AND", "OR"] = "AND"
    conditions: list[Condition] = Field(default_factory=list)


class StrategyBlueprint(BaseModel):
    """Full specification for a strategy, loaded from YAML."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str
    name: str
    description: str = ""
    asset_types: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    required_signals: list[str] = Field(default_factory=list)
    entry_conditions: ConditionGroup = Field(default_factory=ConditionGroup)
    exit_conditions: ConditionGroup = Field(default_factory=ConditionGroup)
    max_concurrent_positions: int = Field(default=3, gt=0)
    required_agents: list[str] = Field(default_factory=list)
    required_mcps: list[str] = Field(default_factory=list)
