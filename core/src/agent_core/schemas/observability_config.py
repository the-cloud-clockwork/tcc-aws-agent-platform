"""Pydantic models for the ``observability:`` block in agent blueprints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LangfuseConfig(BaseModel):
    """Langfuse tracing configuration.

    Env var names point to the actual secrets — never store
    credentials directly in blueprint YAML.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=True,
        description="Enable Langfuse tracing for this agent.",
    )
    public_key_env: str = Field(
        default="LANGFUSE_PUBLIC_KEY",
        description="Environment variable holding the Langfuse public key.",
    )
    secret_key_env: str = Field(
        default="LANGFUSE_SECRET_KEY",
        description="Environment variable holding the Langfuse secret key.",
    )
    host_env: str = Field(
        default="LANGFUSE_HOST",
        description="Environment variable holding the Langfuse host URL.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Static tags attached to every Langfuse trace.",
    )


class AuditLogConfig(BaseModel):
    """DynamoDB audit log configuration."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=True,
        description="Enable DynamoDB audit logging for this agent.",
    )
    ttl_days: int = Field(
        default=1825,
        ge=1,
        le=3650,
        description="Retention period for audit events in days (default ~5 years).",
    )
    table_env: str = Field(
        default="AUDIT_LOG_TABLE",
        description="Environment variable holding the DynamoDB audit table name.",
    )


class DashboardConfig(BaseModel):
    """CloudWatch GenAI Observability dashboard configuration."""

    model_config = ConfigDict(frozen=True)

    metric_namespace: str = Field(
        default="AgentPlatform",
        description="CloudWatch metric namespace for agent metrics.",
    )
    log_group_prefix: str = Field(
        default="agents/",
        description="CloudWatch log group prefix for agent logs.",
    )
    custom_metrics: list[str] = Field(
        default_factory=list,
        description="Additional custom metric names to include in the dashboard.",
    )


class DataProtectionConfig(BaseModel):
    """PII protection — provider-selectable guardrail + CloudWatch log masking.

    Layer 1 (provider=bedrock): Bedrock Guardrails anonymize PII in model responses.
    Layer 1 (provider=presidio): Local Microsoft Presidio redacts PII in-process.
    Layer 1 (provider=none): No in-process PII filtering.
    Layer 2: CloudWatch Data Protection masks PII patterns in log streams (always on).
    """

    model_config = ConfigDict(frozen=True)

    provider: Literal["bedrock", "presidio", "none"] = Field(
        default="bedrock",
        description=(
            "PII guardrail provider. 'bedrock' uses AWS Bedrock Guardrails "
            "(requires a Bedrock model). 'presidio' uses local Microsoft "
            "Presidio (provider-agnostic). 'none' disables in-process PII filtering."
        ),
    )
    guardrail_id_env: str = Field(
        default="BEDROCK_GUARDRAIL_ID",
        description="Environment variable holding the Bedrock Guardrail ID.",
    )
    guardrail_version_env: str = Field(
        default="BEDROCK_GUARDRAIL_VERSION",
        description="Environment variable holding the Guardrail version.",
    )
    presidio_entities: list[str] = Field(
        default_factory=list,
        description=(
            "Presidio entity types to detect, e.g. "
            "['EMAIL_ADDRESS', 'PHONE_NUMBER', 'CREDIT_CARD', 'US_SSN']. "
            "Empty list = detect Presidio's default set."
        ),
    )
    presidio_language: str = Field(
        default="en",
        description="Presidio analyzer language code (e.g. 'en', 'es').",
    )
    cloudwatch_masking_identifiers: list[str] = Field(
        default_factory=list,
        description=(
            "PII types to mask in CloudWatch logs "
            "(e.g. 'EmailAddress', 'CreditCardNumber', 'USPhoneNumber')."
        ),
    )


class ObservabilityConfig(BaseModel):
    """Top-level ``observability:`` block in an agent blueprint.

    Controls OTEL trace attributes, Langfuse tracing, audit logging,
    CloudWatch GenAI dashboards, and data protection.

    The infrastructure-level toggle ``runtime.observability_enabled``
    controls the OTEL auto-instrumentation wrapper in the Dockerfile.
    This config controls application-level observability features
    that run on top of OTEL.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=True,
        description="Master toggle for all observability features on this agent.",
    )
    trace_attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Static key-value pairs attached to every OTEL span via Strands Agent.",
    )
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    audit_log: AuditLogConfig = Field(default_factory=AuditLogConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    data_protection: DataProtectionConfig = Field(default_factory=DataProtectionConfig)
