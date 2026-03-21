"""AgentCore Policy — Cedar access control for Gateway tool invocations.

Lazy imports to avoid pulling in ``bedrock_agentcore_starter_toolkit``
at module load time.
"""

from __future__ import annotations


def __getattr__(name: str):  # noqa: N807
    """Lazy import to defer SDK import until first attribute access."""
    if name == "PolicyClient":
        from agent_core.policy.client import PolicyClient

        return PolicyClient

    if name in (
        "PolicyError",
        "PolicyConfigError",
        "PolicyEngineNotFoundError",
        "PolicyMode",
        "PolicyWiring",
    ):
        from agent_core.policy import client as _client

        return getattr(_client, name)

    if name in (
        "CedarPolicy",
        "CedarPolicyBuilder",
        "PolicyEffect",
        "PolicyAction",
        "CEDAR_SCHEMA",
        "validate_policy_set",
        "generate_cedar_files",
    ):
        from agent_core.policy import cedar_policies as _cedar

        return getattr(_cedar, name)

    if name in (
        "translate_rule",
        "translate_rules",
        "CedarTranslationError",
        "validate_cedar_expression",
    ):
        from agent_core.policy import translator as _translator

        return getattr(_translator, name)

    if name == "PolicyWiring":
        from agent_core.policy.wiring import PolicyWiring

        return PolicyWiring

    if name in ("NL2CedarResult", "generate_from_natural_language"):
        from agent_core.policy import nl2cedar as _nl2cedar

        return getattr(_nl2cedar, name)

    raise AttributeError(f"module 'agent_core.policy' has no attribute {name!r}")


__all__ = [
    "CEDAR_SCHEMA",
    "CedarPolicy",
    "CedarPolicyBuilder",
    "CedarTranslationError",
    "NL2CedarResult",
    "PolicyAction",
    "PolicyClient",
    "PolicyConfigError",
    "PolicyEffect",
    "PolicyEngineNotFoundError",
    "PolicyError",
    "PolicyMode",
    "PolicyWiring",
    "generate_cedar_files",
    "generate_from_natural_language",
    "translate_rule",
    "translate_rules",
    "validate_cedar_expression",
    "validate_policy_set",
]
