---
title: Policy
nav_order: 8
parent: SDK Reference
---

# Policy

The Policy subsystem enforces access control for agent tool invocations using [Cedar](https://www.cedarpolicy.com/), an open-source policy language developed by AWS. The platform uses the AgentCore Policy Engine for policy storage and evaluation. The default model is DENY-all: every tool call is denied unless an explicit permit policy allows it.

## Key Classes

| Class | Purpose |
|-------|---------|
| `PolicyClient` | Creates policy engines, manages Cedar policies, attaches to Gateways, generates policies via NL2Cedar |
| `CedarPolicyBuilder` | Fluent Python API for constructing Cedar policies |
| `PolicyTranslator` | Converts platform policy schemas to Cedar syntax |

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

## Policy Engine Lifecycle

`PolicyClient` wraps both the boto3 `bedrock-agentcore-control` client (for engine CRUD) and the `bedrock_agentcore_starter_toolkit` policy SDK (for policy CRUD and NL2Cedar):

```python
from agent_core.policy.client import PolicyClient, PolicyMode

client = PolicyClient(region="us-west-2")

# Create a policy engine
result = client.create_engine(name="my-agent-policies")
engine_id = result["policyEngineId"]

# Create a Cedar policy in the engine
client.create_policy(
    engine_id=engine_id,
    name="allow-search",
    cedar_statement='permit(principal in Role::"analyst", action == Action::"invoke_tool", resource == Tool::"search");',
)

# List policies
policies = client.list_policies(engine_id)
```

## Policy Engine Attachment to Gateway

The policy engine is evaluated before every tool invocation routed through the Gateway. Attach a policy engine to a Gateway with an enforcement mode:

```python
# Attach with enforcement
client.attach_to_gateway(
    gateway_identifier="gw-abc123",
    policy_engine_arn=result["policyEngineArn"],
    mode=PolicyMode.ENFORCE,  # or PolicyMode.LOG_ONLY
)

# Later, detach
client.detach_from_gateway(gateway_identifier="gw-abc123")
```

If a policy decision is DENY, `GatewayClient` raises `PolicyDeniedError` with the matching `forbid` policy attached for logging and audit.

## NL-to-Cedar Generation

`PolicyClient.generate_policy()` uses the AgentCore NL2Cedar API to convert a plain-language policy description into valid Cedar syntax:

```python
result = client.generate_policy(
    engine_id=engine_id,
    name="reviewer-access",
    gateway_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:gateway/gw-abc",
    natural_language="Allow users in the 'reviewer' role to view documents but not edit or delete them.",
)

# result contains {"generatedPolicies": [...]}
for policy in result.get("generatedPolicies", []):
    print(policy)
```

Always review LLM-generated Cedar policies before deploying them. `generate_policy()` is a productivity tool, not a security guarantee.

## Storing and Loading Policies

Policies are stored in the AgentCore Policy Engine. The `PolicyClient` manages the full lifecycle:

```python
client = PolicyClient(region="us-west-2")

# List all policies in an engine
policies = client.list_policies(engine_id)

# Add a new policy (idempotent — uses create_or_get_policy)
client.create_policy(engine_id, name="allow-search", cedar_statement=cedar_text)

# Remove a policy
client.delete_policy(engine_id, policy_id="pol-123")
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
