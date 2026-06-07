---
title: graph
nav_order: 3
parent: CLI Reference
---

# agentcli graph

Generate ASCII topology diagrams from multi-agent graph blueprints. Useful for visualizing agent pipelines, understanding routing logic, and documenting multi-agent architectures.

## Synopsis

```
agentcli graph <subcommand> [OPTIONS] YAML_PATH
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `render` | Generate an ASCII diagram and markdown report from a multi-agent graph blueprint |

## agentcli graph render

Reads the `multi_agent` section of an agent blueprint and produces a markdown document containing:

- ASCII box diagram with topologically sorted nodes and directed edges
- Node table (id, agent ref, type)
- Edge table (from, to, condition, label)
- Circuit breaker section (if any `gate` nodes are defined)

If an output file is specified, the markdown is written to disk. Otherwise it prints to the terminal.

```
agentcli graph render YAML_PATH [--output OUTPUT_FILE]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `YAML_PATH` | Path to agent blueprint YAML containing a `multi_agent` section with `pattern: graph` |

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output file path for the markdown report (default: print to terminal) |

## Requirements

The blueprint must contain a `multi_agent` block with `pattern: graph`. The `nodes` and `edges` fields define the graph topology:

```yaml
multi_agent:
  pattern: graph
  nodes:
    - id: intake
      agent_ref: intake-agent
      type: agent
    - id: quality-gate
      type: gate
      trip_condition: "confidence < 0.7"
      fallback: human-review
    - id: processor
      agent_ref: processor-agent
      type: agent
  edges:
    - from: intake
      to: quality-gate
      label: always
    - from: quality-gate
      to: processor
      condition: "confidence >= 0.7"
      label: pass
```

## Example: Render to Terminal

```bash
agentcli graph render agents/document-pipeline.yaml
```

Output panel:

```
# Agent Graph: document-pipeline

**Pattern:** graph
**Nodes:** 3 | **Edges:** 2

## Topology

+----------------------------+
|  intake                    |
|  (intake-agent)            |
+----------------------------+
    | --> quality-gate
    v
+----------------------------+
|  quality-gate              |
|  [GATE]                    |
+----------------------------+
    | --[pass]--> processor
    v
+----------------------------+
|  processor                 |
|  (processor-agent)         |
+----------------------------+

## Nodes

| ID            | Agent Ref        | Type  |
|---------------|------------------|-------|
| intake        | intake-agent     | agent |
| quality-gate  | —                | gate  |
| processor     | processor-agent  | agent |

## Edges

| From          | To            | Condition           | Label  |
|---------------|---------------|---------------------|--------|
| intake        | quality-gate  | —                   | always |
| quality-gate  | processor     | confidence >= 0.7   | pass   |

## Circuit Breakers

- **quality-gate**: trip=`confidence < 0.7`, fallback=`human-review`
```

## Example: Write to File

```bash
agentcli graph render agents/my-pipeline.yaml \
  --output diagrams/my-pipeline-graph.md
# Written graph diagram to diagrams/my-pipeline-graph.md
```

## Graph Summary

After rendering, a summary table is always printed to the terminal:

```
      Graph Summary
+--------------+-------+
| Metric       | Value |
+--------------+-------+
| Pattern      | graph |
| Nodes        | 3     |
| Edges        | 2     |
| Gate nodes   | 1     |
+--------------+-------+
```

## Node Types

| Type | Description |
|------|-------------|
| `agent` | An agent node — runs an `agent_ref` blueprint |
| `gate` | A circuit breaker node — evaluates a `trip_condition` and routes to `fallback` on failure |

## See Also

- [Agent Blueprint](../blueprints/agent-blueprint) — `multi_agent` block reference
- [A2A Protocol](../runtime/a2a) — architectural reasoning behind multi-agent communication
