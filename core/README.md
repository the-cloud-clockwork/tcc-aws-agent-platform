# tccw-agent-core

> Generic, domain-agnostic platform SDK for building AI agents with the Strands Agents SDK — Blueprint Engine, Execution Modes, Hooks, Observability, Gateway, Memory, Identity, and Policy.

[![CI](https://github.com/The-Cloud-Clock-Work/tccw-agent-core/actions/workflows/ci.yml/badge.svg)](https://github.com/The-Cloud-Clock-Work/tccw-agent-core/actions/workflows/ci.yml)
[![SonarQube](https://sonar.homeofanton.com/api/project_badges/measure?project=tccw-agent-core&metric=alert_status)](https://sonar.homeofanton.com/dashboard?id=tccw-agent-core)

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
pip install agent-core \
  --index-url https://tccw-835618032093.d.codeartifact.eu-west-1.amazonaws.com/pypi/tccw-python/simple/

# Development (editable install)
git clone git@github.com:The-Cloud-Clock-Work/tccw-agent-core.git
cd tccw-agent-core
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

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
```

---

*Part of [The Cloud Clock Work](https://github.com/The-Cloud-Clock-Work) platform*
