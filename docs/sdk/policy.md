---
title: Policy
nav_order: 8
parent: SDK Reference
---

# Policy

The Policy subsystem enforces access control for agent tool invocations using [Cedar](https://www.cedarpolicy.com/), an open-source policy language developed by AWS. The platform uses the AgentCore Policy Engine for policy storage and evaluation. The default model is **default-DENY**: every tool call is denied unless an explicit `permit` policy allows it.

> **Architecture guide:** [Identity, Policy & IAM](../policy.md)

## Key Classes and Functions

| Class / Function | Module | Purpose |
|-----------------|--------|---------|
| `PolicyClient` | `agent_core.policy.client` | Creates policy engines, manages Cedar policies, attaches to Gateway, generates via NL2Cedar |
| `CedarPolicyBuilder` | `agent_core.policy.cedar_policies` | Builds `CedarPolicy` dataclass instances and serializes them to Cedar syntax |
| `translate_rule()` | `agent_core.policy.translator` | Converts a single `PolicyRuleConfig` to Cedar syntax |
| `translate_rules()` | `agent_core.policy.translator` | Converts a list of `PolicyRuleConfig` objects to Cedar syntax |

## Cedar Runtime Entity Namespaces

The platform uses specific Cedar entity namespaces at runtime. **These differ from generic Cedar tutorials:**

| Entity | Namespace |
|--------|-----------|
| Action | `AgentCore::Action::"<target>___<tool>"` |
| Resource | `AgentCore::Gateway::"<gateway_arn>"` |
| Principal | `AgentCore::Agent::"<agent_id>"` or `AgentCore::AgentGroup::"<group>"` |

The three controlled actions are `invoke_tool`, `read_memory`, and `write_memory`.

## `PolicyClient`

```python
class PolicyClient:
    def __init__(self, region: str | None = None) -> None: ...

    def create_engine(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new policy engine. Returns {"policyEngineId": ..., "policyEngineArn": ...}"""
        ...

    def get_engine(self, engine_id: str) -> dict[str, Any]: ...
    def delete_engine(self, engine_id: str) -> None: ...

    def create_policy(
        self,
        engine_id: str,
        name: str,
        cedar_statement: str,
    ) -> dict[str, Any]:
        """Create a Cedar policy. Uses validationMode=IGNORE_ALL_FINDINGS."""
        ...

    def list_policies(self, engine_id: str) -> list[dict[str, Any]]: ...
    def delete_policy(self, engine_id: str, policy_id: str) -> None: ...

    def attach_to_gateway(
        self,
        gateway_identifier: str,
        policy_engine_arn: str,
        mode: PolicyMode,       # PolicyMode.ENFORCE | PolicyMode.LOG_ONLY
    ) -> None: ...

    def detach_from_gateway(self, gateway_identifier: str) -> None: ...

    def generate_policy(
        self,
        engine_id: str,
        name: str,
        gateway_arn: str,
        natural_language: str,
    ) -> dict[str, Any]:
        """NL2Cedar — converts natural language to Cedar. Review output before deploying."""
        ...
```

## Enforcement Modes

| `PolicyMode` | Behavior |
|-------------|----------|
| `ENFORCE` | Unauthorized tool calls are blocked; agent receives an authorization error |
| `LOG_ONLY` | All calls proceed; unauthorized decisions are logged only (audit mode) |

## `CedarPolicyBuilder`

`CedarPolicyBuilder` collects `CedarPolicy` dataclass instances and serializes them to Cedar format. It does **not** expose a fluent chain API — policies are constructed as `CedarPolicy` dataclass instances and added via `add_policy`:

```python
from agent_core.policy.cedar_policies import (
    CedarPolicyBuilder,
    CedarPolicy,
    PolicyEffect,
    PolicyAction,
)

builder = CedarPolicyBuilder()

# permit — any principal can invoke search_records (with condition)
builder.add_policy(CedarPolicy(
    policy_id="allow-search",
    effect=PolicyEffect.PERMIT,
    description="Any caller can search with limit <= 100",
    principal='principal',
    action=PolicyAction.INVOKE_TOOL,
    resource='Tool::"DataTarget___search_records"',
    conditions=["context.input.limit <= 100"],  # list of Cedar expressions, AND-ed together
))

# forbid — no condition, blocks everyone from delete_record
builder.add_policy(CedarPolicy(
    policy_id="deny-delete",
    effect=PolicyEffect.FORBID,
    description="Forbid delete_record for all principals",
    principal='principal',
    action=PolicyAction.INVOKE_TOOL,
    resource='Tool::"DataTarget___delete_record"',
    conditions=[],  # no conditions = unconditional forbid
))

# Serialize all policies to Cedar syntax
cedar_text = builder.build()

# Write to a .cedar file
builder.write_to_file("/tmp/policies.cedar")

# Load policies from a YAML file (list of policy dicts under "policies" key)
builder.load_policies_from_file("/tmp/rules.yaml")
```

`PolicyEffect` enum: `PERMIT`, `FORBID`. `PolicyAction` enum: `INVOKE_TOOL`, `READ_MEMORY`, `WRITE_MEMORY`.

## `translate_rule()` / `translate_rules()`

Convert blueprint YAML `PolicyRuleConfig` objects to Cedar syntax. Used internally by `PolicyWiring` during blueprint loading. Each rule sets exactly one of `allow` (generates `permit`) or `deny` (generates `forbid`):

```python
from agent_core.policy.translator import translate_rule, translate_rules
from agent_core.schemas.policy_config import PolicyRuleConfig

# allow generates a Cedar permit statement
rule = PolicyRuleConfig(
    name="limit-search",
    allow="search_records",
    when="context.input.limit <= 100",
)

cedar = translate_rule(
    rule=rule,
    gateway_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/gw-abc",
    target_prefix="DataTarget",
    # → permit(principal,
    #     action == AgentCore::Action::"DataTarget___search_records",
    #     resource == AgentCore::Gateway::"arn:...")
    #   when { context.input.limit <= 100 };
)

# deny generates a Cedar forbid statement
deny_rule = PolicyRuleConfig(
    name="admins-only-delete",
    deny="delete_record",
    unless='principal.scope.contains("group:Admins")',
)

# Translate a list of rules in one call
full_cedar = translate_rules(
    [rule, deny_rule],
    gateway_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/gw-abc",
    target_prefix="DataTarget",
)
```

## `PolicyWiring`

`PolicyWiring` is the high-level orchestrator called by `BlueprintLoader`. It creates a per-agent policy engine, translates blueprint rules to Cedar, deploys each as a named policy, attaches the engine to the Gateway with the configured mode, and optionally persists a versioned DynamoDB snapshot.

`PolicyWiring.__init__` does all the work — pass `config`, `agent_id`, `gateway_identifier`, and optionally `versions_table_name`:

```python
from agent_core.policy.wiring import PolicyWiring
from agent_core.schemas.policy_config import PolicyConfig, PolicyRuleConfig

config = PolicyConfig(
    engine="MyAgentPolicies",
    mode="ENFORCE",
    target_prefix="DataTarget",
    rules=[
        PolicyRuleConfig(name="allow-search", allow="search_records"),
        PolicyRuleConfig(
            name="limit-results",
            allow="search_records",
            when="context.input.limit <= 100",
        ),
        PolicyRuleConfig(
            name="admins-only-delete",
            deny="delete_record",
            unless='principal.scope.contains("group:Admins")',
        ),
    ],
)

wiring = PolicyWiring(
    config=config,
    agent_id="my-agent",
    gateway_identifier="arn:aws:bedrock-agentcore:us-west-2:123456789012:gateway/gw-abc",
    region="us-west-2",
    versions_table_name="my-policy-versions-table",  # optional; enables versioning
)

# Inspect what was deployed
print(wiring.engine_id)           # AgentCore policy engine ID
print(wiring.engine_arn)          # ARN of the policy engine
print(wiring.deployed_policy_ids) # list of deployed policy IDs

# List stored versions (requires versions_table_name)
versions = wiring.list_versions()  # → [{version, timestamp_ms, rules_hash, mode, ...}, ...]

# Roll back to version 2 (redeploys Cedar from stored snapshot)
wiring.rollback(version=2)

# Tear down — detach from Gateway and delete the engine
wiring.cleanup()
```

## Blueprint Configuration

`PolicyConfig` schema — all valid fields:

```yaml
policy:
  engine: MyAgentPolicies          # policy engine name (required)
  mode: ENFORCE                    # ENFORCE | LOG_ONLY (required)
  target_prefix: DataTarget        # prepended to all action names as TargetName___tool (optional)
  rules:
    # allow → generates Cedar permit()
    - name: allow-search
      allow: search_records

    # allow with condition
    - name: limit-search-results
      allow: search_records
      when: "context.input.limit <= 100"

    # deny → generates Cedar forbid()
    - name: admins-only-delete
      deny: delete_record
      unless: "principal.scope.contains('group:Admins')"

    # per-rule target override (overrides target_prefix for this rule)
    - name: analytics-export
      allow: bulk_export
      target: AnalyticsTarget

    # restrict to a specific principal
    - name: service-account-only
      allow: internal_api
      principal: "AgentCore::Principal::\"service-account\""

  versioning:
    enabled: true
    table_env: POLICY_VERSIONS_TABLE   # env var holding DynamoDB table name
    max_versions: 10
```

`PolicyRuleConfig` field reference:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Rule identifier |
| `allow` | `str \| None` | Conditional | Tool name to permit — exactly one of `allow`/`deny` |
| `deny` | `str \| None` | Conditional | Tool name to forbid — exactly one of `allow`/`deny` |
| `when` | `str \| None` | No | Cedar `when` condition expression (passed verbatim) |
| `unless` | `str \| None` | No | Cedar `unless` condition expression (passed verbatim) |
| `target` | `str \| None` | No | Per-rule target override (overrides `target_prefix`) |
| `principal` | `str \| None` | No | Cedar principal — defaults to any principal when `None` |

## See Also

- [Identity, Policy & IAM guide](../policy.md) — Cedar default-DENY model, enforcement modes, NL2Cedar
- [Identity SDK reference](identity.md) — Inbound and outbound authentication
