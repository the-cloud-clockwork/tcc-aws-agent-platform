---
title: Strategy Blueprint
nav_order: 2
---

# Strategy Blueprint

A strategy blueprint declares a decision strategy as a YAML file. It defines when a strategy should be active (entry conditions), when it should exit, how parameters should be sized, what signals it requires, and how it is evaluated. Strategy blueprints are consumed by domain-specific modules that build on the platform SDK.

Strategy blueprints are validated at load time by the `StrategyBlueprint` Pydantic schema. Invalid blueprints fail loudly — there are no silent defaults.

---

## Top-Level Identity Fields

```yaml
id: high-confidence-route          # Unique strategy identifier (snake_case)
name: High Confidence Routing      # Human-readable display name
version: 2.0.0                     # Semantic version
description: |
  Activates when the primary confidence signal crosses above threshold
  and quality conditions are confirmed.
```

---

## `entry_conditions:` Block

Declares the conditions that must be met before the strategy activates. All conditions in the `all:` list must be true simultaneously. Conditions in `any:` require at least one match.

```yaml
entry_conditions:
  all:
    - signal: confidence_score
      operator: greater_than
      value: 0.7
      lookback_periods: 5

    - signal: quality_gate
      operator: equals
      value: "passed"

  any:
    - signal: volume_signal
      operator: greater_than
      value: 1.5
    - signal: load_regime
      operator: equals
      value: "normal"

  cooldown_periods: 3              # Minimum periods between activations
  require_all_signals: false       # If true, all required_signals must be present
```

---

## `exit_conditions:` Block

Declares the conditions that trigger strategy exit. Exit conditions are evaluated independently after entry.

```yaml
exit_conditions:
  error_threshold:
    type: percentage               # percentage | absolute | rate_multiple
    value: 2.0                     # Exit if error rate exceeds 2%

  success_target:
    type: percentage
    value: 6.0                     # Exit when target success rate of 6% above baseline

  time_limit:
    max_active_periods: 20         # Force exit after 20 periods regardless

  signal_reversal:                 # Exit when entry signal reverses
    signal: confidence_score
    operator: less_than
    value: 0.3
```

---

## `parameters:` Block

Declares sizing rules and parameter limits. The platform enforces these bounds at evaluation time.

```yaml
parameters:
  sizing:
    method: confidence_adjusted    # fixed | percentage | confidence_adjusted | adaptive
    base_size: 0.05                # Base allocation as fraction of capacity
    max_size: 0.15                 # Hard cap regardless of sizing calculation
    min_size: 0.01                 # Minimum meaningful allocation

  limits:
    max_concurrent_activations: 3
    max_total_exposure: 0.40       # Maximum total exposure across all active strategies
    correlation_limit: 0.70        # Skip if correlation with existing activation exceeds threshold

  scaling:
    scale_in_allowed: true         # Allow increasing allocation on reconfirmation
    scale_in_max_additions: 2
    scale_out_allowed: true        # Allow partial deactivation
    scale_out_levels: [0.33, 0.67] # Fraction deactivated at each level
```

---

## `required_signals:` Block

Declares which signals this strategy depends on. The platform validates signal availability before activation.

```yaml
required_signals:
  - id: confidence_score
    source: scoring-agent          # Agent ID that produces this signal
    type: continuous               # continuous | discrete | boolean
    min_history_periods: 20        # Minimum signal history required

  - id: quality_gate
    source: quality-agent
    type: discrete
    allowed_values:
      - passed
      - pending
      - failed

  - id: volume_signal
    source: volume-agent
    type: continuous
    min_history_periods: 5
    optional: true                 # Strategy can activate even if this signal is absent
```

---

## `evaluation:` Block

Configures how this strategy is evaluated. Metrics are calculated by the platform evaluation subsystem and persisted to DynamoDB.

```yaml
evaluation:
  primary_metric: success_rate     # Optimisation objective
  metrics:
    - success_rate
    - activation_rate
    - error_rate
    - coverage_ratio
    - latency_p95

  benchmark: baseline_strategy     # ID of the benchmark strategy to compare against

  lookback_window: 252             # Periods of history used for metric calculation

  min_activations_threshold: 10    # Minimum activation count before evaluation is meaningful

  persistence:
    enabled: true
    table_env: STRATEGY_EVAL_TABLE
    retention_days: 365
```

---

## `execution_modes:` Block

Controls in which execution environments the strategy is active. Aligns with the platform's `simulation → staging → production` promotion model.

```yaml
execution_modes:
  simulation: true                 # Active in simulation/testing environment
  staging: true                    # Active in staging environment with non-production data
  production: false                # Disabled in production until promoted
```

---

## `risk_controls:` Block

Hard limits enforced independently of sizing logic. These are non-negotiable guardrails.

```yaml
risk_controls:
  max_daily_error_rate: 0.03       # Halt strategy if daily error rate exceeds 3%
  max_degradation_halt: 0.10       # Halt strategy if quality degradation from baseline exceeds 10%
  circuit_breaker:
    consecutive_failures: 5        # Pause strategy after 5 consecutive failures
    pause_periods: 10              # Number of periods to wait before resuming
```

---

## Complete Example

```yaml
id: high-confidence-route
name: High Confidence Routing Strategy
version: 2.0.0
description: |
  Activates when confidence score crosses above threshold
  with quality gate confirmation. Exits on error threshold or signal reversal.

entry_conditions:
  all:
    - signal: confidence_score
      operator: greater_than
      value: 0.65
      lookback_periods: 10
    - signal: quality_gate
      operator: equals
      value: "passed"
  cooldown_periods: 5
  require_all_signals: true

exit_conditions:
  error_threshold:
    type: percentage
    value: 2.0
  success_target:
    type: percentage
    value: 8.0
  signal_reversal:
    signal: confidence_score
    operator: less_than
    value: 0.30

parameters:
  sizing:
    method: confidence_adjusted
    base_size: 0.05
    max_size: 0.12
    min_size: 0.01
  limits:
    max_concurrent_activations: 4
    max_total_exposure: 0.35

required_signals:
  - id: confidence_score
    source: scoring-agent
    type: continuous
    min_history_periods: 20
  - id: quality_gate
    source: quality-agent
    type: discrete
    allowed_values: [passed, pending, failed]

evaluation:
  primary_metric: success_rate
  metrics:
    - success_rate
    - activation_rate
    - error_rate
    - latency_p95
  lookback_window: 252
  min_activations_threshold: 15
  persistence:
    enabled: true
    table_env: STRATEGY_EVAL_TABLE
    retention_days: 365

execution_modes:
  simulation: true
  staging: false
  production: false

risk_controls:
  max_daily_error_rate: 0.025
  max_degradation_halt: 0.08
  circuit_breaker:
    consecutive_failures: 4
    pause_periods: 8
```
