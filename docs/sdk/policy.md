---
title: Policy
nav_order: 8
---

# Policy

The Policy subsystem enforces access control for agent tool invocations using [Cedar](https://www.cedarpolicy.com/), an open-source policy language developed by AWS. The default model is DENY-all: every tool call is denied unless an explicit permit policy allows it.

## Key Classes

| Class | Purpose |
|-------|---------|
| `PolicyClient` | Evaluates Cedar policies at tool invocation time |
| `CedarPolicyBuilder` | Fluent Python API for constructing Cedar policies |
| `PolicyTranslator` | Converts platform policy schemas to Cedar syntax |
| `NL2Cedar` | Translates natural-language policy descriptions to Cedar using an LLM |

## Cedar Syntax Basics

A Cedar policy has a principal (who), action (what), and resource (which):

```cedar
// Permit users with role "analyst" to call the search_records tool
permit (
  principal in Role::"analyst",
  action == Action::"invoke_tool",
  resource == Tool::"search_records"
);

// Forbid any principal from calling the delete_record tool
forbid (
  principal,
  action == Action::"invoke_tool",
  resource == Tool::"delete_record"
);
```

Cedar evaluates all matching policies. A single `forbid` overrides any number of `permit` policies.

## Default DENY Model

When the policy engine is enabled, all tool invocations are denied by default. You must write explicit `permit` policies for every tool the agent should be able to call. This prevents accidental capability escalation when new tools are registered.

## Policy Patterns

### Role-Based Access

```python
from agent_core.policy import CedarPolicyBuilder

builder = CedarPolicyBuilder()

policy = (
    builder
    .permit()
    .principal_in_role("analyst")
    .action("invoke_tool")
    .resource_in_group("read-only-tools")
    .build()
)
```

### Rate Limit Guard

```python
policy = (
    builder
    .permit()
    .principal_in_role("api-user")
    .action("invoke_tool")
    .resource("expensive-computation-tool")
    .when("context.request_count_today < 100")
    .build()
)
```

### Parameter Guard

```python
# Restrict a tool's allowed parameter values
policy = (
    builder
    .permit()
    .principal_in_role("operator")
    .action("invoke_tool")
    .resource("data-export-tool")
    .when('resource.parameters.format in ["csv", "json"]')
    .build()
)
```

## Policy Engine Attachment to Gateway

The policy engine is evaluated before every tool invocation routed through the Gateway. The `PolicyClient` is attached to the `GatewayClient` at wiring time:

```python
from agent_core.policy import PolicyClient
from agent_core.gateway import GatewayClient

policy = PolicyClient.from_blueprint("agent.yaml")
gateway = GatewayClient.from_blueprint("agent.yaml")

# Policy is checked on every gateway.invoke_tool() call automatically
```

If a policy decision is DENY, `GatewayClient` raises `PolicyDeniedError` with the matching `forbid` policy attached for logging and audit.

## NL-to-Cedar Translation

`NL2Cedar` uses an LLM to translate a plain-language policy description into valid Cedar syntax:

```python
from agent_core.policy import NL2Cedar

nl2cedar = NL2Cedar.from_blueprint("agent.yaml")

cedar_text = await nl2cedar.translate(
    description="Allow users in the 'reviewer' role to view documents but not edit or delete them.",
    available_actions=["view_document", "edit_document", "delete_document"],
    available_roles=["reviewer", "editor", "admin"],
)

print(cedar_text)
# permit (
#   principal in Role::"reviewer",
#   action in [Action::"view_document"],
#   resource
# );
```

Always review LLM-generated Cedar policies before deploying them. `NL2Cedar` is a productivity tool, not a security guarantee.

## Storing and Loading Policies

Policies are stored in Amazon Verified Permissions. The `PolicyClient` loads them at startup and caches them for the policy TTL:

```python
client = PolicyClient.from_blueprint("agent.yaml")

# List all policies in the policy store
policies = await client.list_policies()

# Add a new policy
policy_id = await client.put_policy(cedar_text)

# Remove a policy
await client.delete_policy(policy_id)
```

## Blueprint Configuration

```yaml
policy:
  enabled: true
  policy_store_id: "${POLICY_STORE_ID}"
  cache_ttl_seconds: 60
  default_decision: DENY         # DENY | ALLOW — strongly recommend DENY
  nl2cedar:
    enabled: false               # Enable only in non-production environments
    model: anthropic.claude-3-haiku-20240307-v1:0
```

## PolicyTranslator

`PolicyTranslator` bridges the platform's YAML policy schema with Cedar. It is used internally during blueprint loading and can be called directly for programmatic policy generation:

```python
from agent_core.policy import PolicyTranslator

translator = PolicyTranslator()

# Convert a platform policy dict to Cedar
cedar = translator.to_cedar({
    "effect": "permit",
    "principal": {"role": "analyst"},
    "actions": ["search_records", "get_record"],
    "condition": "context.classification == 'internal'"
})
```
