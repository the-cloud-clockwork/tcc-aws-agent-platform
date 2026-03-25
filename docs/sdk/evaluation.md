---
title: Evaluation
nav_order: 7
parent: SDK Reference
---

# Evaluation

The Evaluation subsystem measures agent output quality. It ships 12 built-in evaluators covering correctness, safety, tool usage, and task completion, and supports custom LLM-as-judge evaluators. Evaluation can run on-demand (for testing) or online (sampling live traffic in production).

## Key Classes

| Class | Purpose |
|-------|---------|
| `EvaluationClient` | Wraps `bedrock_agentcore_starter_toolkit.Evaluation` — runs evaluators, manages online configs |
| `BUILTIN_EVALUATORS` | Dict of 12 built-in evaluator metadata (name, category, level) |

The upstream `Evaluation` class from `bedrock_agentcore_starter_toolkit` handles the actual API calls. `EvaluationClient` adds error handling, logging, and evaluator ID resolution.

## Built-in Evaluators

12 built-in evaluators across four categories:

**Response Quality (TRACE level):**

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.Correctness` | Factual accuracy of agent responses |
| `Builtin.Completeness` | Whether the response fully addresses the request |
| `Builtin.Faithfulness` | Whether the response is grounded in retrieved context |
| `Builtin.Helpfulness` | How useful the response is to the user |
| `Builtin.Harmlessness` | Whether the response avoids harmful content |
| `Builtin.Coherence` | Logical consistency and flow of the response |
| `Builtin.Relevance` | How relevant the response is to the query |

**Task Completion (SESSION level):**

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.GoalSuccessRate` | Whether the agent achieved the stated goal |

**Tool Usage (SPAN level):**

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.ToolSelectionAccuracy` | Whether the agent chose the right tools |
| `Builtin.ToolParameterAccuracy` | Whether the agent passed correct parameters to tools |

**Safety (TRACE level):**

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.Harmfulness` | Detection of harmful or dangerous content |
| `Builtin.Stereotyping` | Detection of stereotyping or biased content |

## On-Demand Evaluation

Run evaluators against a specific agent session's OTEL traces:

```python
from agent_core.evaluation.client import EvaluationClient

client = EvaluationClient(region="us-west-2")

result = client.run(
    agent_id="my-agent",
    session_id="sess-001",
    evaluators=[
        "Builtin.Faithfulness",
        "Builtin.Correctness",
        "Builtin.ToolSelectionAccuracy",
    ],
)

for score in result.scores:
    print(f"{score.evaluator_name}: {score.label} = {score.value}  ({score.explanation})")
```

## Online Evaluation (Continuous Monitoring)

Enable online evaluation to automatically sample and evaluate a percentage of live production sessions. Use `create_online_config()` on `EvaluationClient`:

```python
from agent_core.evaluation.client import EvaluationClient
from agent_core.schemas.evaluation_config import OnlineEvaluationConfig

client = EvaluationClient(region="us-west-2")

config = OnlineEvaluationConfig(
    sampling_rate=10,  # 10% of sessions
    evaluators=["Builtin.Faithfulness", "Builtin.Harmfulness"],
)

config_id = client.create_online_config(
    agent_id="my-agent",
    config_name="production-monitoring",
    config=config,
)

# Later, retrieve results
results = client.get_online_results(
    agent_id="my-agent",
    config_name="production-monitoring",
)
```

Evaluation results are written to CloudWatch and, if Langfuse is enabled, attached to the corresponding Langfuse trace.

## Custom LLM-as-Judge

Define a custom evaluator using the `CustomEvaluatorConfig` schema. The judge model receives the agent trace and scores it according to your instructions:

```python
from agent_core.evaluation.client import EvaluationClient
from agent_core.schemas.evaluation_config import CustomEvaluatorConfig, EvaluatorLevel

client = EvaluationClient(region="us-west-2")

config = CustomEvaluatorConfig(
    name="domain_accuracy",
    level=EvaluatorLevel.TRACE,
    model_id="anthropic.claude-3-haiku-20240307-v1:0",
    max_tokens=1024,
    temperature=0.0,
    instructions="Evaluate whether the agent's response is factually accurate for the given context. {context} {assistant_turn}",
    scale=[1, 5],
)

evaluator_id = client.create_evaluator(config)

# Use the custom evaluator in on-demand or online evaluation
result = client.run(
    agent_id="my-agent",
    session_id="sess-001",
    evaluators=[evaluator_id, "Builtin.Faithfulness"],
)
```

The model ID for LLM-as-judge evaluators must always come from the blueprint or explicit parameter — never hardcoded.

## Blueprint Configuration

```yaml
evaluation:
  online:
    sampling_rate: 10              # Percentage of sessions to evaluate (1-100)
    evaluators:
      - Builtin.Faithfulness
      - Builtin.Correctness
      - Builtin.Harmfulness
  custom_evaluators:
    - name: domain_accuracy
      level: TRACE
      model_id: anthropic.claude-3-haiku-20240307-v1:0
      max_tokens: 1024
      temperature: 0.0
      instructions: "Evaluate domain accuracy. {context} {assistant_turn}"
      scale: [1, 5]
  persistence:
    enabled: true
    table_env: EVAL_TABLE_NAME
    retention_days: 90
```

Evaluation scores are published to CloudWatch under the `/Agents/{agent_name}/Evaluation` namespace.
