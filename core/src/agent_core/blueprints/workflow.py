"""WorkflowBlueprint Pydantic model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TriggerConfig(BaseModel):
    """Trigger configuration for a workflow."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schedule", "event", "manual"] = "schedule"
    schedule: str | None = Field(
        default=None,
        description="Cron expression, e.g. 'cron(30 8 ? * MON *)'.",
    )
    timezone: str | None = Field(default=None, description="IANA timezone.")
    event_pattern: dict[str, Any] | None = None


class ChoiceRule(BaseModel):
    """A single choice rule inside a Choice state."""

    model_config = ConfigDict(frozen=True)

    condition: dict[str, Any] = Field(
        ...,
        description="Condition dict with path, op, value.",
    )
    next: str = Field(..., description="State to transition to if condition is met.")


class WorkflowState(BaseModel):
    """A single state in the workflow state machine."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: Literal["task", "choice", "parallel", "wait", "succeed", "fail"] = "task"
    lambda_ref: str | None = None
    result_path: str | None = None
    next: str | None = None
    choices: list[ChoiceRule] | None = None
    default: str | None = Field(
        default=None,
        description="Default next state for choice type.",
    )
    branches: list[dict[str, Any]] | None = None
    retry: list[dict[str, Any]] | None = None
    catch: list[dict[str, Any]] | None = None


class WorkflowBlueprint(BaseModel):
    """Full specification for an orchestration workflow, loaded from YAML."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str
    name: str
    description: str = ""
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    timeout_minutes: int = Field(default=60, gt=0)
    states: list[WorkflowState] = Field(default_factory=list)
