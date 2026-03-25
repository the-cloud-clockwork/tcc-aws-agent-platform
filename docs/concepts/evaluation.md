---
title: Evaluation
nav_order: 6
parent: Concepts
---

# Measuring Agent Quality

AgentCore Evaluation answers the question "is my agent good?" — not just "does it run?" It uses an LLM-as-judge model to score agent behavior by reading the OTEL traces captured during real sessions.

## Why Evaluation Matters

An agent that runs without errors can still give wrong answers, hallucinate tool parameters, ignore the user's actual goal, or produce harmful content. Traditional unit tests cannot catch these because they require evaluating language quality, goal alignment, and reasoning — not just output correctness.

Evaluation solves this by treating a separate LLM as a judge. The judge reads the agent's traces — what was asked, what tools were called, what was returned — and scores the behavior according to defined criteria. You do not re-run the agent. The trace record is sufficient.

## How It Works

```
Agent runs → OTEL traces captured → Evaluation reads traces → Judge model scores → Results
```

Observability must be enabled (traces must be captured). Evaluation then reads those traces and runs them through the judge model. This decoupling means you can evaluate past sessions, evaluate specific problematic sessions without recreating them, and run evaluations in batch.

## 13 Built-in Evaluators

### Response Quality (7 evaluators)

| Evaluator | What It Measures | Typical Score Labels |
|-----------|-----------------|---------------------|
| `Builtin.Correctness` | Factual accuracy of the response | Correct / Incorrect |
| `Builtin.Completeness` | Whether all aspects of the question were addressed | Complete / Incomplete |
| `Builtin.Faithfulness` | Whether claims are grounded in retrieved context (no hallucination) | Faithful / Unfaithful |
| `Builtin.Helpfulness` | Practical usefulness to the user | Helpful / Not Helpful |
| `Builtin.Harmlessness` | Absence of harmful, offensive, or dangerous content | Harmless / Harmful |
| `Builtin.Coherence` | Logical consistency and clarity of the response | Coherent / Incoherent |
| `Builtin.Relevance` | Whether the response is on-topic | Relevant / Irrelevant |

### Task Completion (1 evaluator)

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.GoalSuccessRate` | Whether the agent achieved the user's stated goal end-to-end |

`GoalSuccessRate` is the most valuable single metric. It evaluates the full conversation holistically, not just the final response.

### Tool Usage (2 evaluators)

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.ToolSelectionAccuracy` | Whether the agent selected the right tools for the task |
| `Builtin.ToolParameterAccuracy` | Whether tool inputs were correctly specified (right fields, right types, right values) |

These are critical for tool-heavy agents. A low `ToolParameterAccuracy` score often reveals prompt engineering issues where the agent misunderstands what a tool expects.

### Safety (2 evaluators)

| Evaluator | What It Measures |
|-----------|-----------------|
| `Builtin.Harmfulness` | Detection of dangerous, illegal, or harmful content |
| `Builtin.Stereotyping` | Detection of biased or stereotyped outputs |

## Scoring Scale

All evaluators return a numeric score from 0.0 to 1.0 and a categorical label:

| Score | Typical Label | Meaning |
|-------|--------------|---------|
| `1.0` | Achieved / Correct / Accurate / Harmless | Full success |
| `0.5` | Partial / Partially Compliant | Partial success |
| `0.0` | Failed / Incorrect / Inaccurate / Harmful | Failure |

The label vocabulary varies by evaluator but follows the same numeric scale.

## On-Demand Evaluation

Score a specific session immediately after it completes. Useful for investigating specific failures or testing a new agent version:

```bash
# Via CLI
agentcli eval run \
  --agent-id my-agent \
  --session-id sess-a1b2c3 \
  --evaluators Builtin.GoalSuccessRate,Builtin.Correctness,Builtin.ToolSelectionAccuracy
```

Or via SDK. The platform's `EvaluationClient` wraps the upstream AgentCore Evaluation class, adding blueprint-aware configuration, evaluator resolution, and integration with the platform's observability stack:

```python
from agent_core.evaluation.client import EvaluationClient

client = EvaluationClient(region="${AWS_REGION}")
result = client.run(
    agent_id="my-agent",
    session_id="sess-a1b2c3",
    evaluators=["Builtin.GoalSuccessRate", "Builtin.Correctness"],
)
for score in result.scores:
    print(f"{score.evaluator_name}: {score.label} ({score.value:.2f})")
    print(f"  Explanation: {score.explanation}")
```

Each score includes an `explanation` field with the judge model's reasoning — useful for understanding why a particular score was assigned and for debugging prompt or tool issues.

## Online Evaluation (Continuous Monitoring)

Instead of manually triggering evaluations, configure continuous scoring of live sessions:

```yaml
evaluation:
  online:
    enabled: true
    sampling_rate: 10      # Evaluate 10% of sessions
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.Correctness
      - Builtin.ToolSelectionAccuracy
```

At 100% sampling rate you get complete coverage at higher cost. At 5–10% you get a representative sample for production monitoring. Results feed into the GenAI Observability dashboard alongside latency and token metrics.

## Custom LLM-as-Judge Evaluators

When the built-in evaluators are insufficient — for example, to check compliance with a domain-specific policy or workflow — define a custom evaluator:

```python
custom = client.create_evaluator(
    name="workflow_compliance",
    level="TRACE",
    config={
        "llmAsAJudge": {
            "modelConfig": {
                "bedrockEvaluatorModelConfig": {
                    "modelId": "${EVALUATOR_MODEL_ID}",
                    "inferenceConfig": {"maxTokens": 500, "temperature": 1.0},
                }
            },
            "instructions": """Evaluate whether the agent followed the required workflow:
                1. Did it gather all required information before proceeding?
                2. Did it confirm the action with the user?
                3. Did it handle errors gracefully?
                Context: {context}
                Agent response: {assistant_turn}""",
            "ratingScale": {
                "numerical": [
                    {"value": 1.0, "label": "Fully Compliant"},
                    {"value": 0.5, "label": "Partially Compliant"},
                    {"value": 0.0, "label": "Non-Compliant"},
                ]
            },
        }
    },
)
```

Custom evaluators are referenced in blueprints by ID and used identically to built-in evaluators.

## Which Evaluators to Use

| Scenario | Recommended Evaluators |
|----------|----------------------|
| General quality baseline | `GoalSuccessRate`, `Correctness`, `Helpfulness` |
| Tool-heavy agents | `ToolSelectionAccuracy`, `ToolParameterAccuracy`, `GoalSuccessRate` |
| RAG / retrieval agents | `Faithfulness`, `Correctness`, `Completeness` |
| Safety-sensitive deployments | `Harmlessness`, `Harmfulness`, `Stereotyping` |
| Production continuous monitoring | `GoalSuccessRate` at 10% sampling |
| Investigating specific failures | Full set on the problem session |

## Blueprint Configuration

```yaml
evaluation:
  online:
    enabled: true
    sampling_rate: 10
    evaluators:
      - Builtin.GoalSuccessRate
      - Builtin.ToolSelectionAccuracy
  custom_evaluators:
    - id: ${CUSTOM_EVALUATOR_ID}
      name: workflow_compliance
```

## See Also

- [agentcli eval](../cli/evaluation) — CLI reference for running evaluations
- [Observability Concepts](observability) — OTEL traces that evaluation reads
- [Evaluation SDK Reference](../sdk/) — `EvaluationClient`, `BuiltinEvaluators`
