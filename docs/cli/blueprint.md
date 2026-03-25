---
title: blueprint
nav_order: 1
parent: CLI Reference
---

# agentcli blueprint

Lint and validate blueprint YAML files against the platform's Pydantic schemas. Auto-detects whether the file is an agent, strategy, or workflow blueprint and runs the appropriate validation.

## Synopsis

```
agentcli blueprint <subcommand> [OPTIONS] YAML_PATH
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `lint` | Validate a blueprint YAML file and display a coverage report |
| `validate` | Alias for `lint` |

## agentcli blueprint lint

```
agentcli blueprint lint YAML_PATH
```

Validates the file against the appropriate Pydantic model (`AgentBlueprint`, `StrategyBlueprint`, or `WorkflowBlueprint`), then runs cross-block validation to catch configuration inconsistencies. Exits with code `1` on failure, `0` on success.

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to the blueprint YAML file to validate |

### Output

For agent blueprints, `lint` prints a block coverage tree showing which subsystems are configured:

```
my-agent.yaml (agent blueprint)
+-- Name: my-agent
+-- Version: 1.0.0
+-- Model
|   +-- provider: bedrock
|   +-- model_id: eu.anthropic.claude-sonnet-4-6
+-- Block Coverage
    +-- runtime
    +-- gateway
    +-- identity  —
    +-- memory
    +-- tools  —
    +-- observability
    +-- evaluation  —
    +-- policy  —
    +-- multi_agent  —

PASS — Blueprint is valid.
```

A check mark indicates the block is configured; a dash indicates it is absent (not an error).

### Cross-Block Warnings

After schema validation, `lint` checks for configuration inconsistencies:

| Warning | Cause |
|---------|-------|
| `Policy rules declared but no gateway configured` | `policy.rules` defined but no `gateway` block |
| `Memory strategies require runtime.type: agentcore` | Memory strategies set but runtime type is not `agentcore` |
| `Coordinator role declared but no multi_agent.nodes defined` | Coordinator pattern declared without nodes |
| `Online evaluation configured but no observability block` | `evaluation.online` enabled without observability (evaluation reads OTEL traces) |

## Examples

### Validate an agent blueprint

```bash
agentcli blueprint lint agents/my-agent.yaml
```

### Validate a strategy blueprint

```bash
agentcli blueprint lint strategies/extraction-strategy.yaml
```

Strategy blueprints are auto-detected by the presence of `required_signals`, `entry_conditions`, or `exit_conditions` fields.

### Validate a workflow blueprint

```bash
agentcli blueprint lint workflows/document-pipeline.yaml
```

Workflow blueprints are auto-detected by the presence of a `states` field.

### Use in CI

```bash
agentcli blueprint lint agents/my-agent.yaml && echo "Blueprint OK"
# Exit code 1 on validation failure — safe to use in CI pipelines
```

### Validate all blueprints in a directory

```bash
for f in agents/*.yaml; do agentcli blueprint lint "$f"; done
```

## Blueprint Types and Required Fields

### Agent Blueprint

Required fields: `id`, `name`, `version`, `model`.

```yaml
id: my-agent
name: My Agent
version: 1.0.0
model:
  provider: bedrock
  model_id: ${MODEL_ID}
runtime:
  type: agentcore
```

### Strategy Blueprint

Required fields: `id`, `name`, `version`. Detected by `required_signals`, `entry_conditions`, or `exit_conditions`.

### Workflow Blueprint

Required fields: `id`, `version`, `states`. Detected by the `states` field.

## See Also

- [Agent Blueprint Spec](../blueprints/agent-blueprint) — full YAML schema reference
- [agentcli deploy](deploy) — deploy a validated blueprint to AgentCore Runtime
