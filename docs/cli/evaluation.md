---
title: evaluation
nav_order: 6
parent: CLI Reference
---

# agentcli eval

Run on-demand evaluation against a specific agent session, or check the status of continuous online evaluation. Communicates with AgentCore Evaluation via the `agent-core` SDK.

## Synopsis

```
agentcli eval <subcommand> [OPTIONS]
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_REGION` | AWS region for the evaluation client |

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `run` | Run on-demand evaluation for a specific agent and session |
| `status` | Check online evaluation status and fetch recent results |

## agentcli eval run

Score a completed agent session using one or more evaluators. Evaluation reads the OTEL traces captured during the session — no need to re-run the agent.

```
agentcli eval run --agent-id AGENT_ID --session-id SESSION_ID --evaluators EVALUATORS
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--agent-id` | Yes | AgentCore Runtime agent ID |
| `--session-id` | Yes | Session ID to evaluate |
| `--evaluators` | Yes | Comma-separated evaluator IDs |

### Built-in Evaluator IDs

| Category | Evaluator ID | What It Measures |
|----------|-------------|-----------------|
| Response Quality | `Builtin.Correctness` | Factual accuracy of the response |
| Response Quality | `Builtin.Completeness` | Whether the response addresses all aspects of the question |
| Response Quality | `Builtin.Faithfulness` | Whether claims are grounded in retrieved context |
| Response Quality | `Builtin.Helpfulness` | Practical usefulness to the user |
| Response Quality | `Builtin.Harmlessness` | Absence of harmful content |
| Response Quality | `Builtin.Coherence` | Logical consistency and clarity |
| Response Quality | `Builtin.Relevance` | Relevance to the user's question |
| Task Completion | `Builtin.GoalSuccessRate` | Whether the agent achieved the user's stated goal |
| Tool Usage | `Builtin.ToolSelectionAccuracy` | Whether the agent selected appropriate tools |
| Tool Usage | `Builtin.ToolParameterAccuracy` | Whether tool inputs were correctly specified |
| Safety | `Builtin.Harmfulness` | Detection of dangerous or harmful content |
| Safety | `Builtin.Stereotyping` | Detection of biased or stereotyped outputs |

### Examples

```bash
# Evaluate with correctness and goal success
agentcli eval run \
  --agent-id my-agent \
  --session-id sess-a1b2c3 \
  --evaluators Builtin.Correctness,Builtin.GoalSuccessRate
```

Output:

```
Running evaluation: agent=my-agent session=sess-a1b2c3 evaluators=2

      Evaluation Results
+-------------------------+-----------+-------+------------------------------------------+
| Evaluator               | Label     | Score | Explanation                              |
+-------------------------+-----------+-------+------------------------------------------+
| Builtin.Correctness     | Correct   |  1.00 | The response accurately reflects the ... |
| Builtin.GoalSuccessRate | Achieved  |  1.00 | The agent successfully completed the ...  |
+-------------------------+-----------+-------+------------------------------------------+
```

```bash
# Evaluate tool usage accuracy
agentcli eval run \
  --agent-id my-agent \
  --session-id sess-a1b2c3 \
  --evaluators Builtin.ToolSelectionAccuracy,Builtin.ToolParameterAccuracy
```

```bash
# Full quality evaluation
agentcli eval run \
  --agent-id my-agent \
  --session-id sess-a1b2c3 \
  --evaluators Builtin.Correctness,Builtin.Completeness,Builtin.Helpfulness,Builtin.GoalSuccessRate,Builtin.ToolSelectionAccuracy
```

## agentcli eval status

Check the status of a continuous online evaluation configuration and retrieve recent aggregate results.

```
agentcli eval status --agent-id AGENT_ID [--config-name CONFIG_NAME]
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--agent-id` | Yes | AgentCore Runtime agent ID |
| `--config-name` | No | Online eval config name (default: `{agent_id}_online_eval`) |

### Example

```bash
agentcli eval status --agent-id my-agent
# Fetching online eval status: agent=my-agent config=my-agent_online_eval

agentcli eval status \
  --agent-id my-agent \
  --config-name my-agent_prod_monitoring
```

## Score Interpretation

Evaluators return a numeric score and a label:

| Score | Typical Label | Meaning |
|-------|--------------|---------|
| `1.0` | Achieved / Correct / Accurate | Full success |
| `0.5` | Partial | Partial success |
| `0.0` | Failed / Incorrect / Inaccurate | Failure |

Scores are on a 0–1 scale. Labels vary by evaluator but follow the same pattern.

## See Also

- [Evaluation Concepts](../concepts/evaluation) — how evaluation works, 13 built-in evaluators, LLM-as-judge
- [Observability Concepts](../concepts/observability) — OTEL traces that evaluation reads
- [Evaluation SDK Reference](../sdk/) — programmatic evaluation API
