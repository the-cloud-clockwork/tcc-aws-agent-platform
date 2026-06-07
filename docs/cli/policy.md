---
title: policy
nav_order: 5
parent: CLI Reference
---

# agentcli policy

Validate policy configuration and generate Cedar policies from blueprint rules. Cedar policies are attached to AgentCore Gateway to enforce fine-grained access control on tool calls.

## Synopsis

```
agentcli policy <subcommand> [OPTIONS] YAML_PATH
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `lint` | Validate the `policy:` block in a blueprint and preview the generated Cedar |
| `generate` | Translate blueprint policy rules to Cedar and output to file or stdout |

## agentcli policy lint

Validates the `policy:` block in a blueprint YAML against the `PolicyConfig` schema. If valid, translates the rules to Cedar and prints a preview. Also validates individual Cedar condition expressions.

```
agentcli policy lint YAML_PATH
```

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to the blueprint YAML file containing a `policy:` block |

### Output

```bash
agentcli policy lint agents/my-agent.yaml
```

```
Policy config valid: engine=cedar, mode=ENFORCE
  Rules: 2

Generated Cedar (preview):
permit(
  principal,
  action == AgentCore::Action::"DataTarget___search_records",
  resource == AgentCore::Gateway::"<GATEWAY_ARN>"
)
when { context.input.limit <= 100 };

forbid(
  principal,
  action == AgentCore::Action::"DataTarget___delete_record",
  resource == AgentCore::Gateway::"<GATEWAY_ARN>"
)
unless { principal has scope && principal.scope.contains("group:Admins") };
```

If a Cedar expression is invalid, lint reports the specific expression and error.

## agentcli policy generate

Translate blueprint policy rules to Cedar and write to a file or print to stdout. Requires the Gateway ARN to construct the resource clause.

```
agentcli policy generate YAML_PATH --gateway-arn GATEWAY_ARN [--output OUTPUT_FILE]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to the blueprint YAML file |

### Options

| Option | Short | Required | Description |
|--------|-------|----------|-------------|
| `--gateway-arn` | | Yes | Gateway ARN for the Cedar resource clause |
| `--output` | `-o` | No | Output file path (default: stdout) |

### Example — print to stdout

```bash
agentcli policy generate agents/my-agent.yaml \
  --gateway-arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${AWS_ACCOUNT_ID}:gateway/my-gateway"
```

### Example — write to file

```bash
agentcli policy generate agents/my-agent.yaml \
  --gateway-arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${AWS_ACCOUNT_ID}:gateway/my-gateway" \
  --output infra/policies/my-agent.cedar
# Cedar written to infra/policies/my-agent.cedar
```

## Blueprint Policy Block

Policies are declared in the `policy:` block of an agent blueprint. The CLI reads this block to generate Cedar.

```yaml
policy:
  engine: DataServicePolicies
  mode: ENFORCE          # ENFORCE blocks unauthorized calls; LOG_ONLY monitors only
  target_prefix: MyTarget
  rules:
    - name: limit-search-results
      when: "context.input.limit <= 100"
      allow: search_records

    - name: admin-only-delete
      unless: "principal has scope && principal.scope.contains(\"group:Admins\")"
      deny: delete_record
```

### Policy Block Fields

| Field | Description |
|-------|-------------|
| `engine` | Policy engine name (e.g. `DataServicePolicies`) |
| `mode` | `ENFORCE` blocks unauthorized calls; `LOG_ONLY` logs without blocking |
| `target_prefix` | Prefix for tool action names in Cedar (matches Gateway target name) |
| `rules[].name` | Human-readable rule name |
| `rules[].when` | Cedar condition that must be true to PERMIT the action |
| `rules[].unless` | Cedar condition that, if false, causes a FORBID |
| `rules[].allow` / `rules[].deny` | Single tool name this rule permits or forbids |

## Common Cedar Patterns

### Parameter guard — limit numeric input

```yaml
rules:
  - name: max-results-100
    when: "context.input.limit <= 100"
    allow: search_records
```

```cedar
permit(principal,
  action == AgentCore::Action::"DataTarget___search_records",
  resource == AgentCore::Gateway::"<gateway_arn>")
when { context.input.limit <= 100 };
```

### Role-based access

```yaml
rules:
  - name: managers-only
    unless: "principal has scope && principal.scope.contains(\"group:Managers\")"
    deny: approve_request
```

### Allow all reads, restrict writes

```yaml
rules:
  - name: read-always
    when: "true"
    allow: get_record
  - name: write-admin-only
    unless: "principal has scope && principal.scope.contains(\"group:Admins\")"
    deny: create_record
  - name: write-admin-only-update
    unless: "principal has scope && principal.scope.contains(\"group:Admins\")"  
    deny: update_record
  - name: write-admin-only-delete
    unless: "principal has scope && principal.scope.contains(\"group:Admins\")"  
    deny: delete_record
```

## See Also

- [Cedar Policy](../policy/cedar-policy) — Cedar model, default-DENY enforcement, ENFORCE vs LOG_ONLY modes, and the policy architecture
- [Identity, Policy & IAM](../policy) — full policy section including identity, Cedar, and IAM
- [Policy SDK Reference](../sdk/policy) — programmatic policy management via `PolicyWiring` and `translate_rules()`
- [agentcli blueprint lint](blueprint) — validate the full blueprint before generating policies
