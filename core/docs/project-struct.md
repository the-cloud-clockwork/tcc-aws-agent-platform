# tccw-agent-core — Project Structure

## Root

| File | Purpose |
|---|---|
| `pyproject.toml` | Package `agent-core` v0.2.0. Core deps: `pydantic`, `pyyaml`, `httpx`, `strands-agents`. Optional extras for observability (`langfuse`, `xray`, `boto3`) and dev tooling |
| `CLAUDE.md` | Agent instructions — no hardcoded prompts, EXECUTION_MODE env var, idempotent side-effects, no domain-specific code |
| `README.md` | Installation from CodeArtifact, env var reference, execution modes |
| `dist/` | Published wheel for CodeArtifact |

## CI/CD (`.github/workflows/`)

| File | Purpose |
|---|---|
| `ci.yml` | Lint (ruff), type check (mypy strict), test (pytest) on every push/PR |
| `publish.yml` | Build wheel → publish to CodeArtifact on changes to `src/` or `pyproject.toml` |
| `sonar-scan.yml` | Coverage + static analysis → SonarQube |

---

## `src/agent_core/`

### `__init__.py`

Single import point for the entire library. Re-exports 17 symbols so consumers write `from agent_core import AgentBlueprint, StructuredLogger` without knowing the internal package layout.

---

### `blueprints/` — YAML-to-Pydantic blueprint engine

**`agent.py`** — Defines `AgentBlueprint`, the Pydantic model that every agent YAML validates against. Covers model config, prompt registry reference, tool whitelist, execution mode gates, runtime limits, multi-agent settings (`MultiAgentConfig` for Swarm/Graph patterns), and hooks. All models are frozen (immutable).

**`loader.py`** — The `BlueprintLoader` reads YAML files from a directory tree, validates them into typed blueprints, and can build a fully wired `strands.Agent` instance. Its `build_strands_agent()` method is the key integration point: it loads the blueprint, checks execution mode permissions, resolves the prompt from the registry, filters MCP tools to only those declared in the blueprint, and returns a ready-to-run agent.

**`strategy.py`** — Defines `StrategyBlueprint` with entry/exit condition trees (`ConditionGroup` of `Condition` objects supporting AND/OR logic), asset scopes, allocation limits, and required agents/MCPs.

**`workflow.py`** — Defines `WorkflowBlueprint` mapping 1:1 to Step Functions ASL. Contains `WorkflowState` (task/choice/parallel/wait/succeed/fail), `ChoiceRule` for branching, and `TriggerConfig` for EventBridge schedule/event triggers.

---

### `execution/` — Mode system

**`mode.py`** — The `ExecutionMode` enum (SIMULATION/STAGING/PRODUCTION), `get_execution_mode()` which reads the `EXECUTION_MODE` env var with graceful fallback to simulation, and `validate_agent_mode()` which gates whether an agent is allowed to run in the current mode. This is the central enforcement point for the "same code, different mode" design.

---

### `schemas/` — Shared Pydantic building blocks

**`execution_modes.py`** — `ExecutionModes` flags (simulation/staging/production). Defaults to simulation-only — agents must explicitly opt into staging and production.

**`model_config.py`** — `ModelConfig` for LLM settings: provider (bedrock/anthropic/litellm), model_id, temperature, max_tokens, caching hints.

**`runtime_config.py`** — `RuntimeConfig` for agent runtime: type (agentcore/lambda/ecs), max iterations, max execution time.

**`tool_config.py`** — `ToolConfig` declares which tools from which MCP server an agent is allowed to use. The loader filters to only these.

**`outputs.py`** — Intentionally empty. Domain-specific output schemas belong in consuming repos, not here.

---

### `prompt/` — Prompt Registry client

**`client.py`** — `PromptRegistryClient` resolves prompt text via a two-tier strategy: try the remote Prompt Registry API first, fall back to local `.txt` files for offline dev. Supports both pinned versions (`gap_detector_v1.2`) and latest-stable references (`gap_detector`).

---

### `hooks/` — Strands SDK callbacks

**`observability.py`** — `ObservabilityHook`, a lightweight hook that emits structured JSON logs on agent start, tool calls, and agent end. Tracks tool call counts and elapsed time.

**`constraints.py`** — `ConstraintHook`, a post-processing guardrail that trims agent output (e.g., capping recommendation lists) to enforce allocation limits.

**`observability_hooks.py`** — `CompositeObservabilityHook` composes Langfuse tracing, audit logging, and structured logging into a single callback. Covers the full agent lifecycle. Audit failures are non-fatal. `create_observability_hooks()` is the factory agents use to get the full stack in one call.

---

### `observability/` — Telemetry stack

**`structured_logger.py`** — `StructuredLogger` wraps Python logging to emit JSON with mandatory fields (`agent_id`, `execution_mode`, `trace_id`, `execution_id`). `LogSchema` defines the record shape. Every log line is valid JSON for CloudWatch Logs Insights.

**`langfuse_hook.py`** — `LangfuseHook` tracks prompt versions, token usage, latency, and cost per agent run in Langfuse. Composes `CostTracker` internally. Gracefully degrades when the Langfuse SDK is not installed.

**`cost_tracker.py`** — `CostTracker` computes token costs against a built-in pricing table (13 Claude and Nova model variants). Extensible via `custom_pricing`. `TokenCost` is the output dataclass.

**`xray_tracing.py`** — `XRayTracer` provides context manager (`subsegment`) and decorator (`capture`) APIs for X-Ray tracing. Falls back to `_NoOpSubsegment` when the SDK is disabled — code that adds annotations works safely in any environment.

**`audit_log.py`** — `AuditLogWriter` writes decision events to DynamoDB with 5-year TTL (MiFID II). Uses conditional writes for idempotency — duplicate events from agent retries are silently ignored. Supports GSI queries by execution_id and event_type.

**`alerts.py`** — `AlertPublisher` sends structured alerts to SNS (→ Telegram). Convenience methods for circuit breaker events and pipeline status. Never crashes on failure — returns None instead.

---

### `memory/` — Session and long-term memory

**`manager.py`** — `MemoryManager` provides three-tier memory (short_term, long_term, episodic). Tries to use the AgentCore Memory SDK, falls back to `_InMemoryFallback` (dict-based) for dev/test. All operations are failure-safe (return None/empty on error).

**`session_bridge.py`** — Maps between Step Functions execution ARNs and AgentCore session IDs. `sfn_execution_id_to_session_id()` extracts the execution name from an ARN; `extract_session_metadata()` pulls session context from the SFN Context Object. Ensures the same session_id convention works in both Lambda and AgentCore Runtime.

---

### `identity/` — Credential management

**`providers.py`** — `IdentityProvider` is an abstract base for credential resolution (env vars in Phase 1, AgentCore Identity OAuth/OIDC in Phase 2). `Credential` is the output dataclass. `ProviderRegistry` is a registry pattern so domain repos can register their own providers (e.g., third-party OAuth).

---

### `gateway/` — AgentCore Gateway client (Phase 2)

**`client.py`** — `GatewayClient` talks to the AgentCore Gateway single-URL endpoint. Invokes tools, lists tools (with TTL cache), and performs semantic search across all registered MCP targets. Handles Cedar policy denials (403 → `GatewayPolicyDeniedError`) and retries on transient failures.

**`target_registry.py`** — `TargetRegistry` registers MCP servers, OpenAPI specs, and REST APIs with the Gateway. `GatewayTarget` defines a target's endpoint, auth type, and metadata. `synchronize_all()` batch-registers targets after MCP redeploy.

**`tool_discovery.py`** — `ToolDiscovery` wraps `GatewayClient` for semantic tool search with relevance filtering. `DiscoveredTool` carries the fully qualified name (`data-mcp::get_data`), schema, and relevance score.

---

### `policy/` — Cedar authorization (Phase 2)

**`cedar_policies.py`** — `CedarPolicy` represents a single permit/forbid rule. `CedarPolicyBuilder` assembles policies from code or YAML and serializes to Cedar format. `CEDAR_SCHEMA` defines entity types (Agent, AgentGroup, Tool, ToolGroup) and actions (invoke_tool, read_memory, write_memory). `generate_cedar_files()` produces deployment artifacts for CDK.

---

### `agentcore/` — Advanced AgentCore features (Phase 2)

**`memory_branching.py`** — `MemoryBranchManager` enables the Strategy Evaluation agent to explore multiple approaches in parallel. Branches are created from a base state, updated with metrics, compared to find the best, and merged or discarded. In-memory for POC.

**`multi_tenant.py`** — `TenantContext` holds tenant metadata and tier-based resource limits. `TenantScopedKey` generates tenant-prefixed keys for DynamoDB, S3, and sessions. `TenantResourceGuard` enforces per-tenant limits. Every data path includes tenant_id even in single-tenant mode.

**`streaming.py`** — `StreamBuffer` is an async pub/sub buffer for real-time UI streaming. Agents push `StreamEvent` objects; subscribers consume them via AsyncIterator (SSE) or polling. `format_sse()` serializes events for Server-Sent Events transport.

---

## `tests/` — ~132 tests across 20 files

| File | Coverage |
|---|---|
| `conftest.py` | Shared fixtures: temp blueprint directories with sample YAML, parsed dicts, temp prompt files |
| `test_agent_blueprint.py` | 9 tests — all AgentBlueprint fields, model config, tools, modes, multi-agent, hooks, minimal required fields |
| `test_strategy_blueprint.py` | 6 tests — entry/exit condition trees, required agents/MCPs, asset scopes, allocation limits |
| `test_loader.py` | 6 tests — load by ID, load from path, not-found error, workflow state parsing |
| `test_execution_mode.py` | 6 tests — default simulation, all modes, invalid fallback, mode validation |
| `test_hooks.py` | 7 tests — ObservabilityHook lifecycle, ConstraintHook trimming and edge cases |
| `test_prompt_client.py` | 7 tests — remote resolution, local fallback, version pinning, error cases |
| `test_langfuse_hook.py` | 6 tests — lifecycle without SDK, tags, cost accumulation, mock trace calls |
| `test_cost_tracker.py` | 9 tests — known/unknown model pricing, custom overrides, zero tokens, serialization |
| `test_structured_logger.py` | 9 tests — all log levels, JSON structure, env var defaults, auto-generated IDs |
| `test_alerts.py` | 8 tests — publish success/failure, circuit breaker events, pipeline events, SNS attributes |
| `test_audit_log.py` | 10 tests — write/read, TTL, idempotency, duplicate handling, GSI queries, env var config |
| `test_xray_tracing.py` | 7 tests — NoOp fallback, context manager, decorator, annotations, exception recording |
| `test_gateway_client.py` | 6 tests — defaults, invoke/list/search tools, policy denial (403) |
| `test_target_registry.py` | 4 tests — target types, register, synchronize batch |
| `test_tool_discovery.py` | 3 tests — relevance filtering, agent_id parameter, access control placeholder |
| `test_memory_manager.py` | 6 tests — in-memory fallback CRUD, episodic store/search, manager roundtrip |
| `test_session_bridge.py` | 5 tests — ARN parsing, passthrough, reconstruction, SFN context extraction |
| `test_cedar_policies.py` | 10 tests — policy serialization, builder, validation, schema structure |
| `test_identity_providers.py` | 5 tests — credential resolution, registry pattern, unknown provider error |
| `test_observability_hooks.py` | 5 tests — composite lifecycle, error tracking, audit failure isolation, factory |
| `test_agentcore_advanced.py` | 17 tests — memory branching (6), streaming (3), multi-tenant (8) |
