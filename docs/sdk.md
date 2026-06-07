---
title: SDK Reference
nav_order: 11
has_children: true
---

# SDK Reference

`agent-core` is the foundational Python library for the AWS Agent Platform. It provides a configuration-driven, domain-agnostic runtime that lets you declare AI agents in YAML and run them on Amazon Bedrock AgentCore.

`agent-core` is built as an abstraction layer over the [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and Amazon Bedrock AgentCore. Both are **hard dependencies** — the package fails loudly if either is missing.

> **Guides vs. Reference** — This section is the terse API reference (classes, signatures, parameters). For the architectural "why" and configuration patterns, see the topic guide sections: [Inference Providers](inference.md), [Observability & Evaluation](observability.md), [Identity, Policy & IAM](policy.md), [Tools, MCP & Gateway](tools.md), and [Runtime & Memory](runtime.md).

## Installation

```bash
pip install agent-core
```

For development (editable install with all extras):

```bash
pip install -e "core/[dev]"
```

## Subsystem Index

| Subsystem | Key Classes / Functions | Guide |
|-----------|------------------------|-------|
| [Runtime](sdk/runtime.md) | `AgentCoreApp`, `GenericHandler`, `@app.entrypoint` | [Runtime & Memory](runtime.md) |
| [Gateway](sdk/gateway.md) | `GatewayClient`, `TargetRegistry` | [Tools, MCP & Gateway](tools.md) |
| [Identity](sdk/identity.md) | `IdentityWiring`, `CredentialCache`, `requires_access_token`, `requires_api_key` | [Identity, Policy & IAM](policy.md) |
| [Memory](sdk/memory.md) | `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager`, `MemoryToolProvider` | [Runtime & Memory](runtime.md) |
| [Built-in Tools](sdk/tools.md) | `CodeInterpreterProvider`, `BrowserProvider`, `BuiltinToolWiring` | [Tools, MCP & Gateway](tools.md) |
| [Observability](sdk/observability.md) | `LangfuseHook`, `AuditLogWriter`, `CostTracker`, `CompositeObservabilityHook`, `create_observability_hooks()` | [Observability & Evaluation](observability.md) |
| [Evaluation](sdk/evaluation.md) | `EvaluationClient`, `LangfuseEvaluationClient`, `BUILTIN_EVALUATORS` | [Observability & Evaluation](observability.md) |
| [Policy](sdk/policy.md) | `PolicyClient`, `CedarPolicyBuilder`, `translate_rule()`, `translate_rules()` | [Identity, Policy & IAM](policy.md) |
| [A2A](sdk/a2a.md) | `A2AServerWrapper`, `A2AClient`, `A2AWiring` | [Runtime & Memory](runtime.md) |
| [MCP Base Classes](sdk/mcp.md) | `BaseMCPServer`, `cache_get()`, `cache_set()`, `resolve_provider()` | [Tools, MCP & Gateway](tools.md) |
| [Prompt Registry](sdk/prompts.md) | `PromptRegistryClient` | [Runtime & Memory](runtime.md) |
| [Artifacts](sdk/artifacts.md) | `create_artifact`, `get_artifact`, `list_artifacts`, `poll_artifact` | [Tools, MCP & Gateway](tools.md) |

## Standard Wiring Pattern

Every production agent follows this five-line pattern. `BlueprintLoader.build_entrypoint()` reads the blueprint, wires all subsystems (memory, observability, gateway, policy, identity), and returns an `AgentCoreApp` ready to serve `/invocations` and `/ping`:

```python
from agent_core.blueprints import BlueprintLoader

loader = BlueprintLoader("blueprints/")
app = loader.build_entrypoint("my-agent")

if __name__ == "__main__":
    app.run()
```

Alternatively, `AgentCoreApp.from_blueprint(loader, agent_id)` is a thin alias for the same operation:

```python
from agent_core.blueprints import BlueprintLoader
from agent_core.runtime import AgentCoreApp

loader = BlueprintLoader("blueprints/")
app = AgentCoreApp.from_blueprint(loader, "my-agent")

if __name__ == "__main__":
    app.run()
```

Blueprint YAML drives all resource names, model IDs, feature flags, and provider choices. Nothing is hardcoded in the SDK. See the [Blueprints reference](blueprints/) for the full schema.
