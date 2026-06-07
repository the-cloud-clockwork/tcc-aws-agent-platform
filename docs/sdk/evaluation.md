---
title: Evaluation
nav_order: 7
parent: SDK Reference
---

# Evaluation

The Evaluation subsystem measures agent output quality. It ships 12 built-in evaluators covering correctness, safety, tool usage, and task completion, and supports custom LLM-as-judge evaluators. Two evaluation backends are supported: AWS Bedrock AgentCore (`agentcore`) and Langfuse (`langfuse`).

> **Architecture guide:** [Observability & Evaluation](../observability.md)

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `EvaluationClient` | `agent_core.evaluation.client` | AgentCore backend — wraps `bedrock_agentcore_starter_toolkit.Evaluation` |
| `LangfuseEvaluationClient` | `agent_core.evaluation.langfuse_client` | Langfuse backend — LLM-as-judge via Langfuse API |
| `BUILTIN_EVALUATORS` | `agent_core.evaluation.evaluators` | Dict of 12 built-in evaluator metadata |
| `EvaluationWiring` | `agent_core.evaluation.wiring` | Instantiates the correct backend from blueprint config |

The backend is selected by `evaluation.provider` in the blueprint (`agentcore` is the default). `EvaluationWiring` is called automatically by `BlueprintLoader`; you rarely need to instantiate it directly.

## 12 Built-in Evaluators

**Response Quality (TRACE level):**

| `BuiltinEvaluator` | What It Measures |
|-------------------|-----------------|
| `Correctness` | Factual accuracy of agent responses |
| `Completeness` | Whether the response fully addresses the request |
| `Faithfulness` | Whether the response is grounded in retrieved context |
| `Helpfulness` | How useful the response is to the user |
| `Harmlessness` | Whether the response avoids harmful content |
| `Coherence` | Logical consistency and flow |
| `Relevance` | How relevant the response is to the query |

**Task Completion (SESSION level):**

| `BuiltinEvaluator` | What It Measures |
|-------------------|-----------------|
| `GoalSuccessRate` | Whether the agent achieved the stated goal |

**Tool Usage (SPAN level):**

| `BuiltinEvaluator` | What It Measures |
|-------------------|-----------------|
| `ToolSelectionAccuracy` | Whether the agent chose the right tools |
| `ToolParameterAccuracy` | Whether the agent passed correct parameters |

**Safety (TRACE level):**

| `BuiltinEvaluator` | What It Measures |
|-------------------|-----------------|
| `Harmfulness` | Detection of harmful or dangerous content |
| `Stereotyping` | Detection of stereotyping or biased content |

## `EvaluationClient` (AgentCore Backend)

Requires `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` for score export, and `AWS_REGION` for the AgentCore Evaluation API.

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

### Online Evaluation

```python
from agent_core.evaluation.client import EvaluationClient
from agent_core.schemas.evaluation_config import OnlineEvaluationConfig

client = EvaluationClient(region="us-west-2")

config_id = client.create_online_config(
    agent_id="my-agent",
    config_name="production-monitoring",
    config=OnlineEvaluationConfig(
        sampling_rate=10,   # 10% of sessions
        evaluators=["Builtin.Faithfulness", "Builtin.Harmfulness"],
    ),
)

results = client.get_online_results(
    agent_id="my-agent",
    config_name="production-monitoring",
)
```

## `LangfuseEvaluationClient` (Langfuse Backend)

Use when `evaluation.provider: langfuse` is set. Requires `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

```python
from agent_core.evaluation.langfuse_client import LangfuseEvaluationClient
from agent_core.schemas.evaluation_config import CustomEvaluatorConfig, EvaluatorLevel

client = LangfuseEvaluationClient(
    agent_id="my-agent",
    host=os.environ["LANGFUSE_HOST"],
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
)

# Run evaluators against a trace
result = client.run(
    agent_id="my-agent",
    session_id="sess-001",
    evaluators=["Builtin.Faithfulness"],
)
```

> **Online config:** `LangfuseEvaluationClient.create_online_config()` is a no-op stub that logs a reminder. Online evaluation for the Langfuse backend is configured in the Langfuse dashboard, not via the SDK.

## Custom LLM-as-Judge

Use `CustomEvaluatorConfig` for both backends:

```python
from agent_core.schemas.evaluation_config import CustomEvaluatorConfig, EvaluatorLevel

config = CustomEvaluatorConfig(
    name="domain_accuracy",
    level=EvaluatorLevel.TRACE,
    model_id="anthropic.claude-3-haiku-20240307-v1:0",
    max_tokens=1024,
    temperature=0.0,
    instructions="Evaluate factual accuracy for the given context. {context} {assistant_turn}",
    scale=[1, 5],
)

evaluator_id = client.create_evaluator(config)

result = client.run(
    agent_id="my-agent",
    session_id="sess-001",
    evaluators=[evaluator_id, "Builtin.Faithfulness"],
)
```

The `model_id` must come from the blueprint or an explicit parameter — never hardcoded.

## Blueprint Configuration

```yaml
evaluation:
  provider: agentcore      # agentcore | langfuse

  online:
    sampling_rate: 10      # Percentage of sessions to evaluate (1–100)
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
    table_env: EVAL_TABLE_NAME   # Env var name for the DynamoDB table
    retention_days: 90
```

Evaluation scores are published to CloudWatch under the `/Agents/{agent_name}/Evaluation` namespace and, when Langfuse is enabled, attached to the corresponding Langfuse trace.

## See Also

- [Observability & Evaluation guide](../observability.md) — Evaluation provider comparison, online evaluation setup
- [Observability SDK reference](observability.md) — Hook wiring, LangfuseHook
