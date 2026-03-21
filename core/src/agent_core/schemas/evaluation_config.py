"""Pydantic schemas for the ``evaluation:`` blueprint block."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BuiltinEvaluator(str, Enum):
    """AgentCore built-in evaluators (13 total).

    Response Quality (TRACE level):
    """

    CORRECTNESS = "Builtin.Correctness"
    COMPLETENESS = "Builtin.Completeness"
    FAITHFULNESS = "Builtin.Faithfulness"
    HELPFULNESS = "Builtin.Helpfulness"
    HARMLESSNESS = "Builtin.Harmlessness"
    COHERENCE = "Builtin.Coherence"
    RELEVANCE = "Builtin.Relevance"

    # Task Completion (SESSION level)
    GOAL_SUCCESS_RATE = "Builtin.GoalSuccessRate"

    # Tool Usage (SPAN level)
    TOOL_SELECTION_ACCURACY = "Builtin.ToolSelectionAccuracy"
    TOOL_PARAMETER_ACCURACY = "Builtin.ToolParameterAccuracy"

    # Safety (TRACE level)
    HARMFULNESS = "Builtin.Harmfulness"
    STEREOTYPING = "Builtin.Stereotyping"


class EvaluatorLevel(str, Enum):
    """Granularity at which an evaluator operates."""

    TRACE = "TRACE"
    SESSION = "SESSION"
    SPAN = "SPAN"


class CustomEvaluatorConfig(BaseModel):
    """Configuration for a custom LLM-as-judge evaluator.

    All fields are required — the platform does not assume any default
    model, temperature, or token budget. The consumer blueprint specifies
    everything.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Unique evaluator name.")
    level: EvaluatorLevel = Field(
        ..., description="Granularity: TRACE, SESSION, or SPAN."
    )
    model_id: str = Field(
        ..., description="Bedrock model ID for the judge (e.g. from blueprint)."
    )
    max_tokens: int = Field(..., ge=1, description="Max tokens for judge inference.")
    temperature: float = Field(
        ..., ge=0.0, le=2.0, description="Judge model temperature."
    )
    instructions: str = Field(
        ...,
        description="Evaluation prompt template. Must contain {context} and {assistant_turn} placeholders.",
    )
    scale: list[int] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Rating scale range as [min, max] (e.g. [1, 5]).",
    )


class OnlineEvaluationConfig(BaseModel):
    """Continuous production monitoring configuration.

    Sampling rate and evaluator list are required — no defaults.
    """

    model_config = ConfigDict(frozen=True)

    sampling_rate: int = Field(
        ...,
        ge=1,
        le=100,
        description="Percentage of sessions to evaluate (1-100).",
    )
    evaluators: list[str] = Field(
        ...,
        min_length=1,
        description="Evaluator identifiers — mix of Builtin.* names and custom evaluator IDs.",
    )
    auto_create_execution_role: bool = Field(
        default=True,
        description="Let AgentCore create the IAM execution role for evaluation.",
    )


class EvaluationPersistenceConfig(BaseModel):
    """DynamoDB persistence for evaluation results."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=True,
        description="Enable DynamoDB persistence for evaluation scores.",
    )
    table_env: str = Field(
        ...,
        description="Environment variable holding the DynamoDB table name.",
    )
    retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Retention period for evaluation results in days.",
    )


class EvaluationConfig(BaseModel):
    """Top-level ``evaluation:`` block in an agent blueprint.

    Controls on-demand and online (continuous) evaluation pipelines.
    When ``online`` is set, the loader configures continuous monitoring.
    Custom evaluators are created before being referenced in online config.
    """

    model_config = ConfigDict(frozen=True)

    online: OnlineEvaluationConfig | None = Field(
        default=None,
        description="Continuous evaluation config. None means no online monitoring.",
    )
    custom_evaluators: list[CustomEvaluatorConfig] = Field(
        default_factory=list,
        description="Custom LLM-as-judge evaluators to create.",
    )
    persistence: EvaluationPersistenceConfig | None = Field(
        default=None,
        description="DynamoDB persistence for evaluation results. None disables persistence.",
    )
