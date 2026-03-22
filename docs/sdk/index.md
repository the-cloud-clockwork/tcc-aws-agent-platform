---
title: SDK Reference
nav_order: 4
has_children: true
---

# SDK Reference

The `agent-core` package is the foundational Python SDK for the AWS Agent Platform. It provides a configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and deploy them on Amazon Bedrock AgentCore.

`agent-core` is built as an abstraction layer over [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and Amazon Bedrock AgentCore. Both are **hard dependencies** — the package will fail loudly if either is missing.

## Installation

```bash
pip install agent-core
```

For development:

```bash
pip install -e "core/[dev]"
```

## Subsystems

| Subsystem | Key Classes | Description |
|-----------|-------------|-------------|
| [Runtime](runtime.md) | `AgentCoreApp`, `GenericHandler`, `SessionManager` | AgentCore container runtime — `@app.entrypoint` pattern, `/invocations` + `/ping` contract, streaming, middleware |
| [Gateway](gateway.md) | `GatewayClient`, `TargetRegistry`, `ToolDiscovery` | Unified gateway client — Lambda, MCP, REST, and OpenAPI targets with dual auth |
| [Identity](identity.md) | `IdentityProvider`, `IdentityClient`, `CredentialCache` | Auth flows — inbound JWT, outbound API key, 3-legged OAuth, M2M with credential caching |
| [Memory](memory.md) | `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager` | Two-tier memory — short-term events with TTL, long-term pgvector semantic retrieval, branching for multi-agent |
| [Tools](tools.md) | `CodeInterpreterProvider`, `BrowserProvider`, `BuiltinToolWiring` | Built-in tool providers — Code Interpreter sessions, browser CDP / Nova Act, Gateway registration |
| [Observability](observability.md) | `LangfuseHook`, `AuditLogWriter`, `XRayTracer`, `CostTracker` | Full-stack observability — OTEL, X-Ray, CloudWatch GenAI metrics, Langfuse, audit logs, PII masking |
| [Evaluation](evaluation.md) | `EvaluationClient`, `BuiltinEvaluators` | 13 built-in evaluators, custom LLM-as-judge, on-demand and online sampling |
| [Policy](policy.md) | `PolicyClient`, `CedarPolicyBuilder`, `PolicyTranslator` | Cedar-based policy engine — default DENY, rate limits, role guards, NL-to-Cedar translation |
| [A2A](a2a.md) | `A2AServerWrapper`, `A2AClient`, `A2AWiring` | Agent-to-Agent protocol — agent cards, coordinator/specialist pattern, M2M auth, remote agents as tools |
| [MCP Base Classes](mcp.md) | `BaseMCPServer`, cache, provider routing | Base classes for building domain MCP servers — cache, routing, versioned store |
| [Prompt Registry](prompts.md) | `PromptRegistryClient` | Versioned prompt management — draft → active → archived lifecycle, mode-gated resolution |
| [Artifacts Server](artifacts.md) | `create_artifact`, `get_artifact` | Artifact MCP server — claim-check pattern, 6 artifact types, pre-signed URLs, idempotency |

## Architecture Overview

All subsystems follow a consistent wiring pattern. Each subsystem exposes a `wiring.py` module that accepts blueprint configuration and returns a configured instance:

```python
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp.from_blueprint("agent.yaml")
```

Blueprint YAML drives all resource names, model IDs, feature flags, and configuration. Nothing is hardcoded in the SDK.

## Blueprint-Driven Configuration

All SDK classes accept blueprint configuration rather than hardcoded defaults:

```yaml
# agent.yaml
name: my-agent
version: "1.0"
model: anthropic.claude-3-5-sonnet-20241022-v2:0

memory:
  enabled: true
  strategy: SEMANTIC

observability:
  langfuse: true
  xray: true

policy:
  enabled: true
```

See the [Blueprints reference](../blueprints/) for the full schema.
