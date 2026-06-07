---
title: Strategy Blueprint
nav_order: 2
parent: Blueprints
---

# Strategy Blueprint

A strategy blueprint declares a parameterized evaluation strategy as a YAML file. It defines condition-based entry and exit rules, signal dependencies, evaluation criteria, and risk control thresholds. Strategy blueprints are consumed by domain-specific modules that build on the platform SDK.

Blueprints are validated at load time by the `StrategyBlueprint` Pydantic schema in `agent_core.blueprints.strategy`. Invalid blueprints fail loudly — there are no silent defaults for required fields.

Strategy blueprint files live under `blueprints/strategies/*.yaml` in a domain repo.

---

## Top-Level Identity Fields

`id`, `name`, and `version` are **required**. All other top-level fields default to empty or `None`.

```yaml
id: confidence-threshold           # Unique strategy identifier. Kebab-case by convention.
name: Confidence Threshold         # Human-readable display name. Required.
version: "1.0.0"                   # Semantic version string. Required.
description: |                     # Optional description.
  Activates when the primary confidence signal crosses above threshold
  and data quality conditions are confirmed.
```

---

## `required_agents:`, `required_mcps:`, `required_signals:`

Declares dependencies. All three are lists of strings and default to empty lists.

```yaml
required_agents:                   # Agent blueprint IDs that must produce input signals.
  - data-collector
  - analyzer

required_mcps:                     # MCP server names needed by this strategy.
  - scoring-mcp

required_signals:                  # Named signals expected from required agents.
  - confidence_score
  - data_quality_score
  - accuracy_metric
```

---

## `parameters:` Block

Declares named strategy parameters with type constraints. Each parameter requires `name` and `type`. Optional fields: `default`, `description`, `min_value`, `max_value`.

Supported `type` values: `int`, `float`, `str`, `bool`, `list`. Common aliases are accepted: `string` → `str`, `integer` → `int`, `number` → `float`, `boolean` → `bool`, `array` → `list`.

```yaml
parameters:
  - name: threshold
    type: float
    default: 0.7
    description: Minimum confidence score to activate.
    min_value: 0.0
    max_value: 1.0

  - name: lookback_window
    type: int
    default: 20
    description: Number of periods to consider.
    min_value: 5
    max_value: 500

  - name: mode
    type: str
    default: "standard"

  - name: enabled
    type: bool
    default: true

  - name: target_metrics
    type: list
    default: ["accuracy", "precision"]
```

---

## `entry_conditions:` Block

Conditions that must be met to activate the strategy. Uses a `ConditionGroupConfig` with a `logic` operator (`and` or `or`, case-insensitive) and a non-empty `conditions` list.

Each condition uses `field`, `operator`, and `value`. Supported operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `between`. A condition may alternatively use `type` for structured domain-specific conditions (e.g. `type: threshold_breach`) instead of the `field`/`operator`/`value` pattern.

```yaml
entry_conditions:
  logic: and                       # and | or (default: and). Accepts AND/OR.
  conditions:
    - field: confidence_score
      operator: gte
      value: 0.8

    - field: data_quality_score
      operator: gte
      value: 0.7

    - field: status
      operator: in
      value: ["ready", "verified"]
```

---

## `exit_conditions:` Block

Conditions that trigger strategy deactivation. Same structure as `entry_conditions`.

```yaml
exit_conditions:
  logic: or
  conditions:
    - field: confidence_score
      operator: lt
      value: 0.3

    - field: error_rate
      operator: gt
      value: 0.05

    - field: accuracy_metric
      operator: between
      value: [0.0, 0.4]
```

---

## `evaluation:` Block

Configures how this strategy is measured. `primary_metric` is **required** — all other fields are optional.

```yaml
evaluation:
  primary_metric: accuracy         # Required. Primary performance metric for ranking.
  metrics:                         # All metrics to compute.
    - accuracy
    - precision
    - recall
    - f1_score
    - latency_p95
  benchmark: baseline-strategy     # Strategy ID for comparative benchmarking.
  lookback_window: 100             # Periods to include. Must be > 0.
  min_activations_threshold: 10    # Minimum activations for statistical significance. Must be > 0.
  persistence:                     # Optional. Persist evaluation scores to DynamoDB.
    enabled: true
    table_env: EVALUATION_TABLE    # Env var holding the DynamoDB table name.
    retention_days: 90
```

`persistence` stores evaluation scores independently in DynamoDB, regardless of the evaluation provider configured on agent blueprints. It is an `EvaluationPersistenceConfig` and defaults to `None` (disabled).

---

## `risk_controls:` Block

Hard limits enforced independently of evaluation logic. All fields are optional; rate values must be between `0.0` and `1.0`.

```yaml
risk_controls:
  max_daily_error_rate: 0.03       # Halt if daily error rate exceeds 3%.
  max_degradation_halt: 0.10       # Halt if quality degradation from baseline exceeds 10%.
  circuit_breaker:                 # Arbitrary dict for domain-specific circuit-breaker config.
    consecutive_failures: 5
    pause_periods: 10
```

---

## `execution_modes:` Block

Controls in which execution environments this strategy is active.

```yaml
execution_modes:
  simulation: true                 # Active in simulation / testing environment.
  staging: true                    # Active in staging.
  production: false                # Disabled in production until promoted.
```

---

## `tags:` Block

`tags` on `StrategyBlueprint` is a **`dict[str, str]`** — key-value pairs, not a list.

```yaml
tags:
  team: data-science
  category: classification
  priority: high
```

---

## Complete Example

```yaml
id: confidence-threshold
name: Confidence Threshold Strategy
version: "2.0.0"
description: |
  Activates when confidence score crosses above threshold with data quality
  confirmation. Exits on error threshold breach or signal reversal.

required_agents:
  - data-collector
  - analyzer

required_mcps:
  - scoring-mcp

required_signals:
  - confidence_score
  - data_quality_score
  - accuracy_metric

parameters:
  - name: threshold
    type: float
    default: 0.7
    description: Minimum confidence score to activate.
    min_value: 0.0
    max_value: 1.0
  - name: lookback_window
    type: int
    default: 20
    min_value: 5
    max_value: 500

entry_conditions:
  logic: and
  conditions:
    - field: confidence_score
      operator: gte
      value: 0.8
    - field: data_quality_score
      operator: gte
      value: 0.7

exit_conditions:
  logic: or
  conditions:
    - field: confidence_score
      operator: lt
      value: 0.3
    - field: error_rate
      operator: gt
      value: 0.05

evaluation:
  primary_metric: accuracy
  metrics:
    - accuracy
    - precision
    - recall
    - latency_p95
  benchmark: baseline-strategy
  lookback_window: 100
  min_activations_threshold: 15
  persistence:
    enabled: true
    table_env: EVALUATION_TABLE
    retention_days: 90

risk_controls:
  max_daily_error_rate: 0.025
  max_degradation_halt: 0.08
  circuit_breaker:
    consecutive_failures: 4
    pause_periods: 8

execution_modes:
  simulation: true
  staging: false
  production: false

tags:
  team: data-science
  category: classification
```

---

## Schema Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | `str` | **Yes** | — | Unique strategy identifier (kebab-case recommended) |
| `name` | `str` | **Yes** | — | Human-readable display name |
| `version` | `str` | **Yes** | — | Semantic version string |
| `description` | `str` | No | `""` | Strategy description |
| `required_agents` | `list[str]` | No | `[]` | Agent blueprint IDs that must produce input signals |
| `required_mcps` | `list[str]` | No | `[]` | MCP server names needed |
| `required_signals` | `list[str]` | No | `[]` | Named signals expected from agents |
| `parameters` | `list[ParameterConfig]` | No | `[]` | Parameterized configuration with type constraints |
| `entry_conditions` | `ConditionGroupConfig` | No | `null` | Activation conditions |
| `exit_conditions` | `ConditionGroupConfig` | No | `null` | Deactivation conditions |
| `evaluation` | `StrategyEvaluationConfig` | No | `null` | Evaluation config (`primary_metric` required if set) |
| `risk_controls` | `RiskControlConfig` | No | `null` | Hard limit guardrails |
| `execution_modes` | `ExecutionModes` | No | simulation=true | Environment gates |
| `tags` | `dict[str, str]` | No | `{}` | Arbitrary key-value metadata tags |
