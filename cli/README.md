# tccw-agent-cli

> Agent CLI tool for prompt management, strategy validation, and graph rendering

[![CI](https://github.com/The-Cloud-Clock-Work/tccw-agent-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/The-Cloud-Clock-Work/tccw-agent-cli/actions/workflows/ci.yml)
[![SonarQube](https://sonar.homeofanton.com/api/project_badges/measure?project=tccw-agent-cli&metric=alert_status)](https://sonar.homeofanton.com/dashboard?id=tccw-agent-cli)

`agentcli` is the developer CLI for the tccw agent platform. It provides commands to push and manage prompt templates in the Prompt Registry, validate agent and strategy blueprints against Pydantic schemas, list and promote strategies, and render ASCII topology diagrams from multi-agent graph blueprints. It is used locally by developers and in CI/CD pipelines to enforce schema correctness before any blueprint reaches a deployed agent.

## Installation

```bash
# From AWS CodeArtifact (pip)
pip install agent-cli --index-url https://tccw-123456789012.d.codeartifact.eu-west-1.amazonaws.com/pypi/tccw-python/simple/

# From source
git clone git@github.com:The-Cloud-Clock-Work/tccw-agent-cli.git
cd tccw-agent-cli
pip install -e ".[dev]"
```

## Commands

```bash
agentcli --help
```

All subcommands print `--help` for full option details.

---

### blueprint

Validate agent and strategy blueprint YAML files against `agent-core` Pydantic schemas. The command auto-detects whether the file is an agent blueprint or a strategy blueprint based on its top-level keys.

```bash
# Lint a single blueprint (agent or strategy — auto-detected)
agentcli blueprint lint blueprints/agents/gap_detection.yaml

# validate is an alias for lint
agentcli blueprint validate blueprints/strategies/gap_momentum.yaml
```

**What it checks:**

- For agent blueprints (`agent_id`, `model`, or `multi_agent` present): validates against `AgentBlueprint` — requires `id`, `name`, `version`, `model`.
- For strategy blueprints (`entry_conditions`, `exit_conditions`, or `strategy_id` present): validates against `StrategyBlueprint` — requires `id`, `name`, `version`, `entry_conditions`, `exit_conditions`.
- Prints a Rich tree showing name, version, model info, multi-agent node/edge counts, and tool count.
- Exits with code `1` on any validation error.

---

### prompt

Manage prompt templates in the Prompt Registry (tccw-prompt-registry). All commands communicate with the registry API over HTTP.

```bash
# Upload a prompt template
agentcli prompt push prompts/gap_detection_system.txt --id gap_detection_system --version 1.0.0

# Fetch and display a prompt (latest stable version)
agentcli prompt get gap_detection_system

# Fetch a specific version
agentcli prompt get gap_detection_system --version 1.0.0

# List all versions of a prompt with status and content hash
agentcli prompt list gap_detection_system

# Show unified diff between two versions
agentcli prompt diff gap_detection_system 1.0.0 2.0.0

# Promote a version to stable status
agentcli prompt promote gap_detection_system 1.0.0

# Rollback to a previous version (marks it stable, demotes current)
agentcli prompt rollback gap_detection_system 0.9.0
```

The registry URL defaults to `http://localhost:8000` and is overridden by the `AGENT_REGISTRY_URL` environment variable.

---

### strategy

Validate strategy YAML files and manage their lifecycle. Strategy blueprints define entry/exit conditions, scope targeting, and stop conditions.

```bash
# Validate a strategy YAML against StrategyBlueprint schema
agentcli strategy validate blueprints/strategies/gap_momentum_up.yaml

# List all strategies in the default directory (blueprints/strategies/)
agentcli strategy list

# List strategies from a custom directory
agentcli strategy list --dir /path/to/strategies/

# Promote a strategy to stable (writes status: stable into the YAML file)
agentcli strategy promote blueprints/strategies/gap_momentum_up.yaml
```

The default strategies directory is `blueprints/strategies/` and is overridden by the `AGENT_STRATEGIES_DIR` environment variable. `strategy list` shows a table with file name, strategy name, version, validation status, and description for every `.yaml`/`.yml` file found.

---

### graph

Generate ASCII topology diagrams from multi-agent graph blueprints. Reads the `multi_agent` section of an agent blueprint YAML and produces a markdown document with a box-and-arrow diagram, node table, edge table, and a circuit breaker summary when gate nodes are present.

```bash
# Render graph to terminal
agentcli graph render blueprints/agents/strategy_evaluator.yaml

# Write graph diagram to a markdown file
agentcli graph render blueprints/agents/strategy_evaluator.yaml --output docs/strategy_evaluator_graph.md
agentcli graph render blueprints/agents/strategy_evaluator.yaml -o docs/strategy_evaluator_graph.md
```

**Output includes:**

- ASCII box diagram with nodes rendered as boxes and directed arrows between them, ordered by topological sort (BFS from root nodes).
- Node table: ID, agent_ref, type.
- Edge table: from, to, condition, label.
- Circuit breaker section listing all `gate` nodes with their `trip_condition` and `fallback` values.
- Rich terminal summary table showing pattern, node count, edge count, and gate node count.

The command requires `multi_agent.pattern: graph` in the blueprint but will render other patterns with a warning.

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_REGISTRY_URL` | No | `http://localhost:8000` | Prompt Registry API base URL |
| `AGENT_STRATEGIES_DIR` | No | `blueprints/strategies` | Default directory for `strategy list` |
| `AWS_DEFAULT_REGION` | No | `eu-west-1` | AWS region for CodeArtifact auth |

---

## Architecture Role

The CLI is developer tooling — used locally and in CI/CD pipelines to enforce correctness before any blueprint reaches a deployed agent.

```
Developer / CI Pipeline
        |
        v
  agentcli (this repo)
  ├── blueprint lint/validate  →  agent_core.blueprints.{agent,strategy}.{AgentBlueprint,StrategyBlueprint}
  ├── prompt push/get/list/    →  tccw-prompt-registry API (HTTP)
  │        diff/promote/rollback
  ├── strategy validate/list/  →  agent_core.blueprints.strategy.StrategyBlueprint
  │        promote
  └── graph render             →  ASCII diagram from multi_agent YAML section
```

The blueprint commands delegate schema validation to `agent-core` (`AgentBlueprint`, `StrategyBlueprint` Pydantic models). If `agent-core` is not installed, a lightweight fallback checks required field presence. This means the CLI can also be used in CI environments where only the CLI package is installed, with `agent-core` as an optional enhancement.

---

## Blueprint YAML Schemas

### Agent Blueprint (minimum required fields)

```yaml
id: gap-detection-agent
name: Gap Detection Agent
version: "1.0.0"
prompt_ref: gap_detection_system_v1
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
tools:
  - mcp: data-mcp
    tools:
      - get_data
      - get_gap_candidates
```

### Strategy Blueprint (minimum required fields)

```yaml
id: gap-momentum-up
name: Gap Momentum Up
version: "1.0.0"
description: Long gap-up momentum strategy
entry_conditions:
  logic: AND
  conditions:
    - type: gap_up
      field: gap_pct
      op: ">="
      value: 2.0
exit_conditions:
  logic: AND
  conditions:
    - type: stop_loss
      field: loss_pct
      op: "<="
      value: -1.5
target_sizing:
  method: risk_pct
  value: 0.02
```

### Multi-Agent Graph Blueprint (for `graph render`)

```yaml
agent_id: strategy-evaluator
name: Strategy Evaluator
version: "1.0.0"
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
multi_agent:
  pattern: graph
  nodes:
    - id: gap_analysis
      agent_ref: gap-detector
      type: agent
    - id: quality_gate
      type: gate
      trip_condition: "confidence < 0.5"
      fallback: abort
    - id: strategy_eval
      agent_ref: strategy-evaluator
      type: agent
  edges:
    - from: gap_analysis
      to: quality_gate
      condition: "signals_ready"
    - from: quality_gate
      to: strategy_eval
      label: gate_passed
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `typer>=0.12.0` | CLI framework — argument parsing, subcommand registration |
| `rich>=13.7.0` | Terminal formatting — tables, panels, syntax highlighting, trees |
| `httpx>=0.27.0` | HTTP client for Prompt Registry API communication |
| `pyyaml>=6.0.1` | Blueprint and strategy YAML parsing |
| `agent-core>=0.1.0` | Blueprint engine — `AgentBlueprint` and `StrategyBlueprint` Pydantic models |

---

## Development

```bash
cd ~/dev/tccw-agent-cli

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=src/agent_cli --cov-report=xml

# Lint
ruff check src/

# Type check
mypy src/
```

### Test Coverage

Tests use `typer.testing.CliRunner` for CLI integration tests and `unittest.mock.patch` to mock HTTP calls. Each subcommand group has a dedicated test module:

| Test module | Covers |
|---|---|
| `tests/test_blueprint.py` | `blueprint lint`, `blueprint validate` — valid agent/strategy YAMLs, file-not-found, empty YAML |
| `tests/test_prompt.py` | `prompt push/get/list/diff/promote/rollback` — success paths, 404, error responses |
| `tests/test_strategy.py` | `strategy validate/list/promote` — valid/invalid YAML, empty directory, file promotion |
| `tests/test_graph.py` | `graph render` — terminal and file output, ASCII diagram helpers, circuit breaker section |

---

## Phase

Phase 1 (P07) — Developer tooling for blueprint validation, prompt lifecycle management, strategy operations, and multi-agent graph visualization.

---

*Part of the [The Cloud Clock Work platform](https://github.com/The-Cloud-Clock-Work) | The Cloud Clock Work*
