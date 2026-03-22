---
title: Evaluation
nav_order: 7
---

# Evaluation

The Evaluation subsystem measures agent output quality. It ships 13 built-in evaluators covering correctness, safety, and groundedness, and supports custom LLM-as-judge evaluators. Evaluation can run on-demand (for testing) or online (sampling live traffic in production).

## Key Classes

| Class | Purpose |
|-------|---------|
| `EvaluationClient` | Runs evaluators against agent outputs, aggregates scores |
| `BuiltinEvaluators` | Factory for the 13 built-in evaluator instances |

## Built-in Evaluators

| Evaluator | What It Measures |
|-----------|-----------------|
| `Faithfulness` | Whether the response is grounded in the provided context (no hallucinations) |
| `AnswerRelevance` | Whether the response directly addresses the user's question |
| `ContextRecall` | Whether the retrieved context contained the information needed |
| `ContextPrecision` | Whether the retrieved context was free of irrelevant material |
| `Toxicity` | Presence of harmful, abusive, or inappropriate content |
| `Bias` | Presence of demographic or ideological bias in the response |
| `PromptInjection` | Whether the user input attempts to override system instructions |
| `SemanticSimilarity` | Cosine similarity between response and a reference answer |
| `ExactMatch` | Exact string match against a reference answer |
| `RougeScore` | ROUGE-L overlap between response and reference |
| `Coherence` | Logical consistency and fluency of the response |
| `Completeness` | Whether the response addresses all parts of the question |
| `Conciseness` | Whether the response is appropriately brief without losing information |

## On-Demand Evaluation

Run evaluators explicitly against a single input/output pair:

```python
from agent_core.evaluation import EvaluationClient, BuiltinEvaluators

client = EvaluationClient.from_blueprint("agent.yaml")
evaluators = BuiltinEvaluators.from_blueprint("agent.yaml")

result = await client.evaluate(
    input="What is the capital of France?",
    output="The capital of France is Paris.",
    context=["France is a country in Western Europe. Its capital city is Paris."],
    evaluators=[
        evaluators.faithfulness(),
        evaluators.answer_relevance(),
        evaluators.context_recall(),
    ],
)

for score in result.scores:
    print(f"{score.evaluator}: {score.value:.3f}  ({score.reason})")
```

## Online Evaluation (Sampling)

Enable online evaluation to automatically evaluate a percentage of live production traffic:

```python
from agent_core.evaluation import EvaluationClient

client = EvaluationClient.from_blueprint("agent.yaml")

# Register the hook with the agent
agent = Agent(
    model=model,
    tools=tools,
    hooks=[client.as_hook()],  # Samples according to blueprint sampling_rate
)
```

Evaluation results are written to CloudWatch and, if Langfuse is enabled, attached to the corresponding Langfuse trace.

## Sampling Rates

Configure sampling in the blueprint. A rate of `0.1` means 10% of production invocations are evaluated:

```yaml
evaluation:
  enabled: true
  sampling_rate: 0.1
  evaluators:
    - faithfulness
    - answer_relevance
    - toxicity
    - prompt_injection
```

Set `sampling_rate: 1.0` for staging environments where you want full coverage.

## Custom LLM-as-Judge

Define a custom evaluator using an LLM prompt. The judge model receives the input, output, and context, and returns a score between 0.0 and 1.0:

```python
from agent_core.evaluation import EvaluationClient

client = EvaluationClient.from_blueprint("agent.yaml")

custom_evaluator = client.create_llm_judge(
    name="domain_accuracy",
    prompt="""
You are evaluating whether an agent's response is accurate for {domain_context}.

Input: {input}
Response: {output}

Score from 0.0 (completely wrong) to 1.0 (fully accurate).
Respond with JSON: {"score": <float>, "reason": "<string>"}
""",
    model="anthropic.claude-3-haiku-20240307-v1:0",
)

result = await client.evaluate(
    input=user_question,
    output=agent_response,
    evaluators=[custom_evaluator],
)
```

The model ID for LLM-as-judge evaluators must always come from the blueprint or explicit parameter — never hardcoded.

## Aggregating Results

`EvaluationClient` can aggregate scores across many samples to produce a dashboard-ready summary:

```python
summary = client.aggregate(results)
print(summary.mean_scores)       # {"faithfulness": 0.87, "answer_relevance": 0.91, ...}
print(summary.pass_rate)         # Fraction of samples above threshold
print(summary.failed_samples)    # List of samples that failed any evaluator
```

## Blueprint Configuration

```yaml
evaluation:
  enabled: true
  sampling_rate: 0.1
  judge_model: anthropic.claude-3-haiku-20240307-v1:0
  evaluators:
    - faithfulness
    - answer_relevance
    - context_recall
    - toxicity
    - prompt_injection
  thresholds:
    faithfulness: 0.8
    toxicity: 0.05      # Fail if toxicity score exceeds this
```

Evaluation scores are published to CloudWatch under the `/Agents/{agent_name}/Evaluation` namespace.
