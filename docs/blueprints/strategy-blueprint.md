---
title: Strategy Blueprint
nav_order: 2
parent: Blueprints
---

# Strategy Blueprint

A strategy blueprint declares a domain-agnostic evaluation strategy as a YAML file. It defines parameterized configuration, condition-based entry and exit rules, evaluation criteria, and risk control thresholds. Strategy blueprints are consumed by domain-specific modules that build on the platform SDK.

Strategy blueprints are validated at load time by the `StrategyBlueprint` Pydantic schema in `agent_core.blueprints.strategy`. Invalid blueprints fail loudly -- there are no silent defaults.

---

## Top-Level Identity Fields

All three top-level fields are **required**.

```yaml
id: confidence-threshold           # Unique strategy identifier. Required.
name: Confidence Threshold         # Human-readable display name. Required.
version: "1.0.0"                   # Semantic version string. Required.
description: |                     # Optional description.
  Activates when the primary confidence signal crosses above threshold
  and data quality conditions are confirmed.
```

---

## `required_agents:`, `required_mcps:`, `required_signals:`

Declares dependencies. All three are lists of strings and are optional (default to empty lists).

```yaml
required_agents:                   # Agent IDs that must produce input signals
  - data-collector
  - analyzer

required_mcps:                     # MCP server names needed by this strategy
  - scoring-mcp

required_signals:                  # Named signals expected from required agents
  - confidence_score
  - data_quality_score
  - accuracy_metric
```

---

## `parameters:` Block

Declares named strategy parameters with type constraints. Each parameter has a `name` and `type` (required), plus optional `default`, `description`, `min_value`, and `max_value`.

Supported types: `int`, `float`, `str`, `bool`, `list`. Common aliases are accepted: `string` maps to `str`, `integer` to `int`, `number` to `float`, `boolean` to `bool`, `array` to `list`.

```yaml
parameters:
  - name: threshold
    type: float
    default: 0.7
    description: Minimum confidence score to activate
    min_value: 0.0
    max_value: 1.0

  - name: lookback_window
    type: int
    default: 20
    description: Number of periods to consider
    min_value: 5
    max_value: 500

  - name: mode
    type: str
    default: "standard"
    description: Operating mode

  - name: enabled
    type: bool
    default: true

  - name: target_metrics
    type: list
    default: ["accuracy", "precision"]
```

---

## `entry_conditions:` Block

Declares conditions that must be met to activate the strategy. Uses a `ConditionGroupConfig` with a `logic` operator (`and` or `or`) and a list of `conditions`. At least one condition is required.

Each condition has `field`, `operator`, and `value`. Supported operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `between`.

A condition may alternatively use `type` for structured domain-specific conditions (e.g., `type: threshold_breach`) instead of the `field`/`operator`/`value` pattern.

```yaml
entry_conditions:
  logic: and                       # and | or (default: and, accepts AND/OR)
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

Declares conditions that trigger strategy deactivation. Same structure as `entry_conditions`.

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

Configures how this strategy is evaluated. The `primary_metric` field is **required**. All other fields are optional.

```yaml
evaluation:
  primary_metric: accuracy         # Required. Primary performance metric for ranking.
  metrics:                         # All metrics to compute (list of strings)
    - accuracy
    - precision
    - recall
    - f1_score
    - latency_p95
  benchmark: baseline-strategy     # Benchmark strategy ID for comparison
  lookback_window: 100             # Lookback window in periods (must be > 0)
  min_activations_threshold: 10    # Minimum activations for statistical significance (must be > 0)
```

---

## `risk_controls:` Block

Hard limits enforced independently of evaluation logic. These are non-negotiable guardrails.

All fields are optional. Rate values must be between 0.0 and 1.0.

```yaml
risk_controls:
  max_daily_error_rate: 0.03       # Halt if daily error rate exceeds 3%
  max_degradation_halt: 0.10       # Halt if quality degradation from baseline exceeds 10%
  circuit_breaker:                 # Arbitrary dict for domain-specific circuit breaker config
    consecutive_failures: 5
    pause_periods: 10
```

---

## `execution_modes:` Block

Controls in which execution environments the strategy is active. Aligns with the platform's `simulation -> staging -> production` promotion model.

```yaml
execution_modes:
  simulation: true                 # Active in simulation/testing environment
  staging: true                    # Active in staging environment
  production: false                # Disabled in production until promoted
```

---

## `tags:` Block

Arbitrary key-value metadata tags. Optional.

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
  Activates when confidence score crosses above threshold
  with data quality confirmation. Exits on error threshold or signal reversal.

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
    description: Minimum confidence score to activate
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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Unique strategy identifier |
| `name` | `str` | Yes | Human-readable name |
| `version` | `str` | Yes | Semantic version string |
| `description` | `str` | No | Strategy description |
| `required_agents` | `list[str]` | No | Agent IDs that produce input signals |
| `required_mcps` | `list[str]` | No | MCP server names needed |
| `required_signals` | `list[str]` | No | Named signals expected from agents |
| `parameters` | `list[ParameterConfig]` | No | Parameterized configuration |
| `entry_conditions` | `ConditionGroupConfig` | No | Activation conditions |
| `exit_conditions` | `ConditionGroupConfig` | No | Deactivation conditions |
| `evaluation` | `StrategyEvaluationConfig` | No | Evaluation configuration |
| `risk_controls` | `RiskControlConfig` | No | Risk control thresholds |
| `execution_modes` | `ExecutionModes` | No | Environment gates |
| `tags` | `dict[str, str]` | No | Arbitrary metadata tags |
