---
title: Evaluation
nav_order: 6
parent: "Observability & Evaluation"
---

# Measuring Agent Quality

Evaluation answers the question "is my agent good?" — not just "does it run?" It uses an LLM-as-judge to score agent behavior by reading the execution traces captured during real sessions. Evaluation never re-runs the agent — the trace record is sufficient.

The platform supports two evaluation backends: **AgentCore Evaluation** (the default, powered by AWS Bedrock) and **Langfuse** (provider-agnostic, dashboard-driven). Choose the backend with the `evaluation.provider` field in the blueprint.

## How it works

```
Agent runs → OTEL traces captured → Evaluation reads traces → Judge model scores → Results stored
```

Observability must be enabled so traces are captured. Evaluation then reads those traces and runs them through the configured judge model. This decoupling means you can evaluate past sessions, investigate specific failures without recreating them, and run batch evaluations.

## Evaluation providers

### provider: agentcore (default)

Uses AWS Bedrock AgentCore Evaluation. The judge model must be a Bedrock-hosted model. Online config (continuous sampling) is fully functional via the AgentCore API.

**Requirements:** `AWS_REGION` env var; agent IAM role must have Bedrock evaluation permissions.

```yaml
evaluation:
  provider: agentcore
  online:
    sampling_rate: 10
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
```

### provider: langfuse

Uses `LangfuseEvaluationClient` — works with any inference provider. Requires `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY`.

**Key difference:** Langfuse online evaluation is configured in the Langfuse dashboard, not at agent runtime. The `create_online_config()` call logs a reminder and returns a no-op — the loader wiring keeps working, but continuous evaluation runs are triggered from the Langfuse UI or REST API, not from blueprint env vars. On-demand scoring via `EvaluationClient.run()` is fully functional and writes scores to Langfuse traces via `langfuse.score()`.

```yaml
evaluation:
  provider: langfuse
  online:
    sampling_rate: 10     # noted in logs; configure evaluation runs in Langfuse dashboard
    evaluators:
      - Builtin.GoalSuccessRate
```

Install the required extra: `pip install 'agent-core[evaluation_langfuse]'`

## 12 built-in evaluators

### Response quality — TRACE level (7 evaluators)

| Evaluator | What it measures | Typical score labels |
|---|---|---|
| `Builtin.Correctness` | Factual accuracy of the response | Correct / Incorrect |
| `Builtin.Completeness` | Whether all aspects of the question were addressed | Complete / Incomplete |
| `Builtin.Faithfulness` | Whether claims are grounded in retrieved context (no hallucination) | Faithful / Unfaithful |
| `Builtin.Helpfulness` | Practical usefulness to the user | Helpful / Not Helpful |
| `Builtin.Harmlessness` | Absence of harmful, offensive, or dangerous content | Harmless / Harmful |
| `Builtin.Coherence` | Logical consistency and clarity of the response | Coherent / Incoherent |
| `Builtin.Relevance` | Whether the response is on-topic | Relevant / Irrelevant |

### Task completion — SESSION level (1 evaluator)

| Evaluator | What it measures |
|---|---|
| `Builtin.GoalSuccessRate` | Whether the agent achieved the user's stated goal end-to-end |

`GoalSuccessRate` is the most valuable single metric. It evaluates the full conversation holistically, not just the final response.

### Tool usage — SPAN level (2 evaluators)

| Evaluator | What it measures |
|---|---|
| `Builtin.ToolSelectionAccuracy` | Whether the agent selected the right tools for the task |
| `Builtin.ToolParameterAccuracy` | Whether tool inputs were correctly specified |

Low `ToolParameterAccuracy` often reveals prompt engineering issues where the agent misunderstands what a tool expects.

### Safety — TRACE level (2 evaluators)

| Evaluator | What it measures |
|---|---|
| `Builtin.Harmfulness` | Detection of dangerous, illegal, or harmful content |
| `Builtin.Stereotyping` | Detection of biased or stereotyped outputs |

## Scoring scale

All evaluators return a numeric score from 0.0 to 1.0 and a categorical label:

| Score | Typical label | Meaning |
|---|---|---|
| `1.0` | Achieved / Correct / Accurate / Harmless | Full success |
| `0.5` | Partial / Partially Compliant | Partial success |
| `0.0` | Failed / Incorrect / Inaccurate / Harmful | Failure |

The label vocabulary varies by evaluator but follows the same numeric scale. Every score includes an `explanation` field with the judge model's reasoning.

## On-demand evaluation

Score a specific session immediately after it completes:

```python
from agent_core.evaluation.client import EvaluationClient

client = EvaluationClient(region="us-west-2")

result = client.run(
    agent_id="my-agent",
    session_id="sess-a1b2c3",
    evaluators=[
        "Builtin.GoalSuccessRate",
        "Builtin.Correctness",
        "Builtin.ToolSelectionAccuracy",
    ],
)

for score in result.scores:
    print(f"{score.evaluator_name}: {score.label} ({score.value:.2f})")
    print(f"  Explanation: {score.explanation}")
```

Or via CLI:

```bash
agentcli eval run \
  --agent-id my-agent \
  --session-id sess-a1b2c3 \
  --evaluators Builtin.GoalSuccessRate,Builtin.Correctness,Builtin.ToolSelectionAccuracy
```

## Online evaluation (continuous monitoring)

Configure continuous scoring of live sessions in the blueprint:

```yaml
evaluation:
  provider: agentcore
  online:
    sampling_rate: 10      # evaluate 10% of sessions automatically
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
      - Builtin.ToolSelectionAccuracy
```

At 10% sampling you get a representative sample at reasonable cost. At 100% you get complete coverage. Results feed into the CloudWatch GenAI Observability dashboard alongside latency and token metrics.

## Custom LLM-as-judge evaluators

Define domain-specific evaluators when the built-in set is insufficient. The judge model receives the agent trace and scores it according to your instructions:

```python
from agent_core.evaluation.client import EvaluationClient
from agent_core.schemas.evaluation_config import CustomEvaluatorConfig, EvaluatorLevel

client = EvaluationClient(region="us-west-2")

config = CustomEvaluatorConfig(
    name="workflow_compliance",
    level=EvaluatorLevel.TRACE,
    model_id="${EVALUATOR_MODEL_ID}",  # from blueprint or env, never hardcoded
    max_tokens=512,
    temperature=0.0,
    instructions=(
        "Evaluate whether the agent followed the required workflow: "
        "1. Gathered all required information before acting. "
        "2. Confirmed the action with the user. "
        "3. Handled errors gracefully. "
        "Context: {context}  Agent response: {assistant_turn}"
    ),
    scale=[1, 5],
)

evaluator_id = client.create_evaluator(config)

result = client.run(
    agent_id="my-agent",
    session_id="sess-001",
    evaluators=[evaluator_id, "Builtin.Faithfulness"],
)
```

Custom evaluators are declared in the blueprint and used identically to built-in evaluators:

```yaml
evaluation:
  provider: agentcore
  custom_evaluators:
    - name: workflow_compliance
      level: TRACE
      model_id: "${EVALUATOR_MODEL_ID}"
      max_tokens: 512
      temperature: 0.0
      instructions: "... {context} {assistant_turn}"
      scale: [1, 5]
  online:
    sampling_rate: 10
    evaluators:
      - Builtin.GoalSuccessRate
      - workflow_compliance
```

## Score persistence

Evaluation scores can be persisted to DynamoDB independently of the evaluation provider:

```yaml
evaluation:
  persistence:
    enabled: true
    table_env: EVAL_TABLE_NAME   # env var holding the DynamoDB table name
    retention_days: 90
```

Each score is written as a DynamoDB item with a TTL. Query by session via the `session_id-index` GSI on the evaluation table.

## Which evaluators to use

| Scenario | Recommended evaluators |
|---|---|
| General quality baseline | `GoalSuccessRate`, `Correctness`, `Helpfulness` |
| Tool-heavy agents | `ToolSelectionAccuracy`, `ToolParameterAccuracy`, `GoalSuccessRate` |
| RAG / retrieval agents | `Faithfulness`, `Correctness`, `Completeness` |
| Safety-sensitive deployments | `Harmlessness`, `Harmfulness`, `Stereotyping` |
| Production continuous monitoring | `GoalSuccessRate` at 10% sampling |
| Investigating specific failures | Full set on the problem session |

## See also

- [Langfuse](langfuse) — `evaluation.provider: langfuse` attaches scores to Langfuse traces
- [Observability overview](observability) — OTEL traces that evaluation reads
- [SDK Reference: Evaluation](../sdk/evaluation) — `EvaluationClient`, `BUILTIN_EVALUATORS`, `CustomEvaluatorConfig`
