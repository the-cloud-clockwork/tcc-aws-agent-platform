# agent-core

> Generic, domain-agnostic platform SDK for building AI agents with the Strands Agents SDK — Blueprint Engine, Execution Modes, Hooks, Observability, Gateway, Memory, Identity, and Policy.

`agent-core` is a generic Python library for defining, loading, and running AI agents using YAML blueprints with the Strands Agents SDK. It contains no domain-specific knowledge — all domain-specific logic lives in the repos that consume this package.

## Features

- **Blueprint Engine** — load and validate agent, strategy, and workflow YAML blueprints with Pydantic; build fully-configured Strands `Agent` instances in one call
- **Execution Mode system** — `EXECUTION_MODE=simulation|staging|production` drives every routing decision; zero code changes between modes
- **Prompt Registry client** — resolves versioned prompts from the registry API with local-file fallback
- **Structured observability** — `ObservabilityHook`, `LangfuseHook`, `XRayTracer`, `StructuredLogger`, `CostTracker`, and `AlertPublisher` form a complete observability stack
- **Audit log** — `AuditLogWriter` writes events to DynamoDB with configurable TTL and idempotency, queryable by execution ID or event type
- **AgentCore Gateway client** — routes tool calls to MCP targets via the AgentCore Gateway; supports semantic tool search and Cedar-enforced policy denial
- **AgentCore Memory manager** — three-tier memory (short-term, long-term, episodic) with semantic search; in-memory fallback for local development
- **Identity providers** — abstract `IdentityProvider` base class with `ProviderRegistry` for registering credential providers
- **Cedar policy builder** — generates `.cedar` policy files and schema from Python dataclasses; load policies from YAML files
- **Real-time streaming** — `StreamBuffer` with SSE formatter for streaming agent progress to UI clients
- **Multi-tenant support** — `agentcore/` module provides multi-tenant isolation and memory-branching patterns

## Installation

```bash
# From AWS CodeArtifact (production)
pip install agent-core

# Development (editable install)
pip install -e ".[dev]"
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `EXECUTION_MODE` | Yes | `simulation` | `simulation` \| `staging` \| `production` |
| `AWS_DEFAULT_REGION` | Yes | `eu-west-1` | AWS region for DynamoDB, SNS |
| `AUDIT_TABLE` | No | `audit_log` | DynamoDB audit log table name |
| `ALERT_TOPIC_ARN` | No | — | SNS topic ARN for alerts |
| `PLATFORM_NAME` | No | `AGENT` | Platform name used in alert subjects |
| `PLATFORM_PREFIX` | No | `agent` | Prefix for memory namespaces |

## Execution Modes

| Mode | Description |
|---|---|
| `simulation` | Uses historical/test data, no external side effects |
| `staging` | Uses external data feeds, sandbox accounts |
| `production` | Full production mode with real external systems |

## Direct Agent Invocation

Agents run as Bedrock AgentCore Runtimes behind `aws bedrock-agentcore invoke-agent-runtime`. The handler reads a specific payload shape — **agent-specific inputs go inside `parameters`**, not at the top level. Flat payloads like `{"prompt":"test","date":"2026-04-10"}` return HTTP 400 with no diagnostic.

### Payload contract

`GenericHandler.handle()` in `core/src/agent_core/runtime/handler.py` calls `normalize_payload()` (`core/src/agent_core/runtime/adapter.py`), which reads:

| Key | Type | Required | Notes |
|---|---|---|---|
| `agent_id` | string | no | Falls back to `AGENT_ID` env var |
| `session_id` | string | no | Auto-UUID if missing |
| `execution_mode` | string | no | Defaults to `simulation` |
| `parameters` (or `params`) | object | no | **All agent-specific inputs** |
| `memory_context` | object | no | Pre-loaded memory passthrough |
| `metadata` | object | no | Arbitrary metadata |

Top-level keys outside this table are ignored by the handler.

### Minimal example (direct invoke)

```json
{
  "parameters": {
    "date": "2026-04-10",
    "watchlist_id": "default",
    "threshold_pct": 2.0
  }
}
```

```bash
PAYLOAD=$(echo -n '{"parameters":{"date":"2026-04-10","watchlist_id":"default","threshold_pct":2.0}}' | base64 -w0)
SID=$(uuidgen | tr -d '-')$(uuidgen | tr -d '-' | head -c 8)
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "arn:aws:bedrock-agentcore:eu-west-1:ACCT:runtime/AGENT-SUFFIX" \
  --runtime-session-id "$SID" \
  --payload "$PAYLOAD" /tmp/out.json
cat /tmp/out.json | python3 -m json.tool
```

### Lambda-wrapper convention (Step Functions path)

The Step Functions `invoke_agent_lambda` wrapper (`modules/workflows/lambda/invoke_agent.py`) uses a **different** shape when `MemoryBranch` is set — it JSON-encodes the entire prompt dict into a `"prompt"` string key and adds `memory_branch` + `memory_merge_strategy` top-level keys:

```json
{
  "prompt": "{\"execution_mode\": \"backtest\", \"date\": \"2026-04-10\"}",
  "memory_branch": "{sessionId}/weekly-pipeline/FetchWatchlistGaps",
  "memory_merge_strategy": "coordinator_wins"
}
```

These top-level memory keys are consumed by the AgentCore SDK memory layer upstream of `GenericHandler`; they do NOT populate `parameters`. Use the direct `parameters` shape for tests and tool-level invocations — use the Lambda wrapper only when you need memory branching in a workflow.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
```
