"""Pydantic models for the ``policy:`` block in agent blueprints.

Defines the simplified YAML format that the platform translates into
Cedar policies and attaches to the AgentCore Gateway policy engine.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyRuleConfig(BaseModel):
    """A single access-control rule in simplified YAML format.

    Exactly one of ``allow`` or ``deny`` must be set. The value is the
    tool name (or action) the rule applies to. ``when`` and ``unless``
    are optional Cedar condition expressions passed through verbatim.

    Example YAML::

        - name: refund_limit
          allow: process_refund
          when: "context.input.amount <= 500"

        - name: managers_only_approve
          deny: approve_claim
          unless: "principal.scope.contains('group:Managers')"
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Rule identifier (e.g. 'refund_limit').")
    allow: str | None = Field(
        default=None,
        description="Tool name to permit (generates Cedar 'permit').",
    )
    deny: str | None = Field(
        default=None,
        description="Tool name to forbid (generates Cedar 'forbid').",
    )
    when: str | None = Field(
        default=None,
        description="Cedar 'when' condition expression (raw Cedar syntax).",
    )
    unless: str | None = Field(
        default=None,
        description="Cedar 'unless' condition expression (raw Cedar syntax).",
    )
    principal: str | None = Field(
        default=None,
        description=(
            "Specific Cedar principal (e.g. 'AgentCore::Principal::\"admin\"'). "
            "Defaults to any principal when None."
        ),
    )

    @model_validator(mode="after")
    def _validate_allow_deny(self) -> PolicyRuleConfig:
        if self.allow and self.deny:
            msg = f"Rule '{self.name}': set exactly one of 'allow' or 'deny', not both."
            raise ValueError(msg)
        if not self.allow and not self.deny:
            msg = f"Rule '{self.name}': one of 'allow' or 'deny' is required."
            raise ValueError(msg)
        return self


class PolicyVersioningConfig(BaseModel):
    """DynamoDB versioning for deployed policy sets."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=True,
        description="Enable DynamoDB versioning for policy deployments.",
    )
    table_env: str = Field(
        ...,
        description="Environment variable holding the DynamoDB table name.",
    )
    max_versions: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of versions to retain per agent.",
    )


class PolicyConfig(BaseModel):
    """Top-level ``policy:`` block in an agent blueprint.

    Controls Cedar access-control policies attached to the AgentCore
    Gateway. When present, the platform creates a policy engine, translates
    the simplified rules into Cedar, and attaches the engine to the Gateway.

    Example YAML::

        policy:
          engine: DataServicePolicies
          mode: ENFORCE
          target_prefix: DataServiceTarget
          rules:
            - name: allow_query
              allow: query_data
            - name: limit_updates
              allow: update_record
              when: "context.input.record_count <= 100"
    """

    model_config = ConfigDict(frozen=True)

    engine: str = Field(
        ...,
        description="Policy engine name (e.g. 'DataServicePolicies').",
    )
    mode: str = Field(
        ...,
        pattern=r"^(ENFORCE|LOG_ONLY)$",
        description="Enforcement mode: ENFORCE or LOG_ONLY.",
    )
    rules: list[PolicyRuleConfig] = Field(
        default_factory=list,
        description="Simplified Cedar rules to translate and deploy.",
    )
    target_prefix: str | None = Field(
        default=None,
        description=(
            "Gateway target prefix for action names. When set, actions "
            "become '{prefix}___{tool_name}' (e.g. 'OrderTarget___process_refund')."
        ),
    )
    versioning: PolicyVersioningConfig | None = Field(
        default=None,
        description="DynamoDB versioning for policy deployments. None disables versioning.",
    )
