# agent-cli

Developer CLI for the agent platform. Three command groups: **blueprint**, **prompt**, and **graph**.

## Install

```bash
pip install agent-cli            # CodeArtifact
pip install -e ".[dev]"          # from source
```

## Commands

### `agentcli blueprint lint <file.yaml>`

Validates an agent blueprint YAML against the `AgentBlueprint` Pydantic schema from `agent-core`. Prints a Rich tree with name, version, model, multi-agent topology, and tool count. Exits `1` on validation errors. `validate` is an alias.

```bash
agentcli blueprint lint blueprints/agents/my_agent.yaml
```

### `agentcli prompt <subcommand>`

CRUD for versioned prompt templates against the Prompt Registry HTTP API.

```bash
agentcli prompt push prompts/system.txt --id my_prompt --version 1.0.0
agentcli prompt get my_prompt
agentcli prompt list my_prompt
agentcli prompt diff my_prompt 1.0.0 2.0.0
agentcli prompt promote my_prompt 1.0.0
agentcli prompt rollback my_prompt 0.9.0
```

Registry URL: `AGENT_REGISTRY_URL` env var (default `http://localhost:8000`).

### `agentcli graph render <file.yaml>`

Renders an ASCII topology diagram from a multi-agent graph blueprint. Produces box-and-arrow diagrams, node/edge tables, and gate summaries.

```bash
agentcli graph render blueprints/agents/pipeline.yaml
agentcli graph render blueprints/agents/pipeline.yaml -o docs/graph.md
```

## Blueprint Examples

### Single Agent

```yaml
id: my-agent
name: My Agent
version: "1.0.0"
prompt_ref: my_prompt_v1
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
tools:
  - mcp: data-mcp
    tools: [get_data, list_sources]
```

### Multi-Agent Graph

```yaml
id: my-pipeline
name: My Pipeline
version: "1.0.0"
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
multi_agent:
  pattern: graph
  nodes:
    - id: collector
      agent_ref: collector-agent
      type: agent
    - id: gate
      type: gate
      trip_condition: "confidence < 0.5"
      fallback: abort
    - id: reporter
      agent_ref: report-agent
      type: agent
  edges:
    - from: collector
      to: gate
      condition: "data_ready"
    - from: gate
      to: reporter
      label: gate_passed
```

## Dependencies

`typer`, `rich`, `httpx`, `pyyaml`, `agent-core` (optional — fallback validation without it).

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
```
