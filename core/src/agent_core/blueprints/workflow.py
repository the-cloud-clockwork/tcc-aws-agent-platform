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
    type: Literal[
        "task", "choice", "parallel", "wait", "wait_for_token", "succeed", "fail"
    ] = "task"
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

    # Agent task fields — used by Terraform state_machines.tf for invokeAgentRuntime
    agent_ref: str | None = Field(
        default=None,
        description="Agent blueprint ID to invoke via AgentCore Runtime.",
    )
    prompt: str | None = Field(
        default=None,
        description="JSONPath to the prompt field in execution input, e.g. '$.prompt'.",
    )
    input_mapping: dict[str, str] | None = Field(
        default=None,
        description="Map of state input keys to agent payload keys.",
    )

    # Fail state fields
    error: str | None = Field(
        default=None,
        description="Error code for fail states.",
    )
    cause: str | None = Field(
        default=None,
        description="Error description for fail states.",
    )

    # Wait / callback fields
    heartbeat_seconds: int | None = Field(
        default=None,
        gt=0,
        description="Heartbeat interval in seconds for callback-pattern wait states.",
    )

    # Retry shorthand
    retry_max: int | None = Field(
        default=None,
        ge=1,
        description="Maximum retry attempts for this state.",
    )


class MemoryBranchConfig(BaseModel):
    """Workflow-level memory branching for multi-agent pipelines."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=False, description="Enable per-state memory branches."
    )
    merge_strategy: Literal["union", "latest", "coordinator_wins", "none"] = Field(
        default="union",
        description="How to merge branch memories after parallel execution.",
    )
    branch_namespace: str = Field(
        default="{sessionId}/branches/{stateId}",
        description="Namespace template for branch isolation. Supports {sessionId}, {stateId}.",
    )


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
    memory_branching: MemoryBranchConfig | None = Field(
        default=None,
        description="Memory branching config for multi-agent pipelines.",
    )
