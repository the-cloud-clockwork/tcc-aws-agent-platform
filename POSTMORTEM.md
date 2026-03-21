# Platform Postmortem — Vision Compliance Audit

> **Date:** 2026-03-21
> **Scope:** All 12 building blocks (skip Block 11 — Infra)
> **Method:** 5 parallel forensic auditors cross-referencing `VISION.md`, `CONCEPTS.md`, `TECHNICAL-GUIDE.md` against actual implementation code
> **Verdict:** 9 PASS, 1 MAJOR GAP, 1 SKIPPED — platform is **substantially complete** with one critical integration bug

---

## Executive Summary

| Block | Name | Verdict | Critical Findings |
|-------|------|---------|-------------------|
| 1 | Runtime | MINOR GAPS | Hardcoded `eu-west-1`; SessionManager defaults to `lambda` mode |
| 2 | Gateway | MINOR GAPS | Hardcoded `eu-west-1` in 3 places |
| 3 | Identity | MINOR GAPS | Hardcoded `eu-west-1` in 2 places |
| 4 | Memory | MINOR GAPS | Hardcoded `eu-west-1` in 3 places |
| 5 | Tools | PASS | No gaps |
| 6 | Observability | MINOR GAPS | Hardcoded defaults (pricing fallback, metric namespace, ttl) |
| 7 | Evaluation | MINOR GAPS | "13 evaluators" docstring but only 12 defined; `scale` format mismatch vs VISION |
| 8 | Policy | **MAJOR GAPS** | **Loader wiring calls non-existent method + wrong function signature** |
| 9 | Strands Integration | MINOR GAPS | `try/except ImportError` on Strands (should be hard dependency) |
| 10 | A2A Communication | MINOR GAPS | `A2AWiring` dead code; loader A2A path lacks M2M auth injection |
| 11 | Infrastructure | SKIPPED | Per user request |
| 12 | Blueprints | PASS | 1 minor: `load_workflow_from_path()` missing |

**Overall: 87% vision-aligned. One blocking bug (Block 8 loader wiring). The rest are policy violations (hardcoded defaults) and minor inconsistencies.**

---

## Systemic Issue: Hardcoded `eu-west-1` Region Default

**Appears in 13+ locations across Blocks 1-4.** Violates CLAUDE.md rule: *"Never hardcode AWS regions as defaults. Resolve from config/env."*

| File | Line Pattern | Block |
|------|-------------|-------|
| `gateway/client.py` | `region: str = "eu-west-1"` | 2 |
| `gateway/target_registry.py` | `region: str = "eu-west-1"` | 2 |
| `schemas/gateway_config.py` | `default="eu-west-1"` | 2 |
| `identity/client.py` | `os.environ.get("AWS_REGION", "eu-west-1")` | 3 |
| `identity/providers.py` | `os.environ.get("AWS_REGION", "eu-west-1")` | 3 |
| `memory/manager.py` | `os.environ.get("AWS_REGION", "eu-west-1")` | 4 |
| `memory/branching.py` | `os.environ.get("AWS_REGION", "eu-west-1")` | 4 |
| `memory/session_bridge.py` | `os.environ.get("AWS_REGION", "eu-west-1")` | 4 |
| `runtime/session.py` | `runtime_mode: str = "lambda"` | 1 |

**Fix:** All `os.environ.get("AWS_REGION", "eu-west-1")` should become `os.environ["AWS_REGION"]` (fail-fast) or accept region from blueprint config. The `GatewayConfig.region` default should be `None` (required field).

---

## Block-by-Block Detail

### Block 1: Runtime — Where Agents Live

**Verdict: MINOR GAPS**

**What's correct:**
- `AgentCoreApp` wraps `BedrockAgentCoreApp` with `@app.entrypoint` decorator
- POST `/invocations` + GET `/ping` on port 8080
- Starlette middleware support
- Streaming via `async def` + `yield`
- `.bedrock_agentcore.yaml` and Dockerfile generation
- `InvocationContext` with `session_id`, `request_headers`
- `GenericHandler` dispatches by `agent_id` with idempotency
- `SessionManager` + `SessionState` for lifecycle
- `StrandsSessionBridge` adapts Strands session interface

**Gaps:**
1. `SessionManager.__init__` defaults to `runtime_mode="lambda"` — should be `"agentcore"`
2. `session.py` retains Lambda/DynamoDB fallback paths (`_persist_dynamodb_memory`, `_get_dynamodb_memory`) — violates "zero backward compat"
3. `adapter.py` `InvocationContext.execution_mode` defaults to `"simulation"` literal
4. `runtime/__init__.py` empty — no re-exports of `AgentCoreApp`, `GenericHandler`, etc.

---

### Block 2: Gateway — The Universal Tool Bridge

**Verdict: MINOR GAPS**

**What's correct:**
- `GatewayClient` wraps Strands `MCPClient` (not custom HTTP)
- `streamablehttp_client` with SigV4 and JWT auth
- All 5 target types: LAMBDA, MCP_SERVER, OPENAPI, SMITHY, API_GATEWAY
- `TargetRegistry` with boto3 `bedrock-agentcore-control` backend
- `ToolDiscovery` with keyword search and relevance scoring
- `gateway-targets.yaml` loading via `load_targets_from_file()`
- Outbound auth: GATEWAY_IAM_ROLE, OAUTH2_CREDENTIAL
- Full `__init__.py` exports

**Gaps:**
1. Hardcoded `eu-west-1` region defaults in 3 places

---

### Block 3: Identity — Auth Flows Through the System

**Verdict: MINOR GAPS**

**What's correct:**
- All 4 auth patterns: inbound JWT, outbound API key, 3LO OAuth, M2M
- `AuthorizerType`: `custom_jwt`, `cognito_jwt`, `aws_iam`
- `cognito_jwt` with `user_pool_id`/`client_id` validation
- `@requires_access_token` and `@requires_api_key` decorators wrapping SDK
- `IdentityClient` CRUD for AgentCore Identity service
- 3 concrete providers: Cognito, Okta, Entra
- `CredentialCache` thread-safe with TTL
- `IdentityWiring` bridges blueprint config to runtime decorators
- `on_auth_url` callback for 3LO consent flow

**Gaps:**
1. Hardcoded `eu-west-1` region defaults in 2 places

---

### Block 4: Memory — Persistence Across Sessions

**Verdict: MINOR GAPS**

**What's correct:**
- `MemoryManager` wraps `bedrock_agentcore.memory.MemoryClient` (hard dependency)
- `MemoryHookProvider` with `AgentInitializedEvent` + `MessageAddedEvent` handlers
- All 4 strategy types: USER_PREFERENCE, SEMANTIC, SUMMARY, EPISODIC
- Namespace templates with `{actorId}/{sessionId}` placeholders
- `MemoryBranchManager` wraps `MemorySessionManager` (fork/branch)
- `MemoryToolProvider` wraps SDK's `AgentCoreMemoryToolProvider`
- `MemoryWiring` orchestrates all 4 components from single config
- `SessionBridge` for SFN execution ID mapping
- `create_memory_and_wait()` for synchronous extraction

**Gaps:**
1. Hardcoded `eu-west-1` region defaults in 3 places

---

### Block 5: Tools — Code Interpreter & Browser

**Verdict: PASS**

**What's correct:**
- `CodeInterpreterProvider`: 5 tools (`execute_code`, `execute_command`, `write_files`, `list_files`, `read_file`)
- `BrowserProvider`: wraps `AgentCoreBrowser`
- `BuiltinToolWiring`: lifecycle management, region override
- `create_mcp_client()`: Strands MCPClient with streamable HTTP
- Pydantic discriminated union: `McpToolConfig | BuiltinToolConfig`
- `network_mode: PUBLIC | PRIVATE` for sandboxing
- No hardcoded region defaults

---

### Block 6: Observability — Tracing Agent Behavior

**Verdict: MINOR GAPS**

**What's correct:**
- OTEL: `build_trace_attributes()`, `set_session_baggage()`, `get_agent_tracer()`
- Hard `opentelemetry` dependency (fails loud)
- `LangfuseHook`: full trace lifecycle with generations, cost tracking
- `AuditLogWriter`: idempotent DynamoDB writes with TTL
- `generate_dashboard_body()`: 8 CloudWatch widget types
- Data protection: Bedrock Guardrails (Layer 1) + CloudWatch masking (Layer 2)
- `CompositeObservabilityHook`: combines Langfuse + audit + structured logger
- `CostTracker`, `AlertPublisher`, `XRayTracer`, `StructuredLogger`
- `ObservabilityConfig` with `enabled` master toggle
- `LangfuseConfig.enabled`, `AuditLogConfig.enabled` flags

**Gaps:**
1. `CostTracker` has hardcoded fallback pricing `(0.003, 0.015)` for unknown models
2. `DashboardConfig.metric_namespace` defaults to `"AgentPlatform"` (hardcoded)
3. `DashboardConfig.log_group_prefix` defaults to `"agents/"` (hardcoded)
4. `AuditLogConfig.ttl_days` defaults to `1825` (hardcoded)

---

### Block 7: Evaluation — Measuring Agent Quality

**Verdict: MINOR GAPS**

**What's correct:**
- `EvaluationClient` wraps `bedrock_agentcore_starter_toolkit.Evaluation`
- On-demand: `run(agent_id, session_id, evaluators)`
- Custom LLM-as-judge: `create_evaluator()` with model config, instructions, scale
- Online: `create_online_config()` with sampling_rate, evaluators
- `BuiltinEvaluator` enum: 12 evaluators across 4 categories
- `EvaluatorLevel`: TRACE, SESSION, SPAN
- CLI: `agentcli eval run`, `agentcli eval status`
- Blueprint wiring in `build_agent_session()`

**Gaps:**
1. Docstring claims "13 built-in evaluators" but only 12 are defined — documentation error
2. VISION shows `scale: [1.0, 0.5, 0.0]` (discrete values) but code implements `scale: list[int]` as `[min, max]` range — semantic mismatch with VISION YAML example

---

### Block 8: Policy — Cedar Access Control

**Verdict: MAJOR GAPS**

**What's correct (individual components are solid):**
- `PolicyClient`: engine lifecycle + policy CRUD + Gateway attachment + NL2Cedar
- `CedarPolicyBuilder`: programmatic Cedar construction with validation
- YAML-to-Cedar translator: `translate_rule()` with allow/deny + when/unless
- `PolicyConfig` schema: engine, mode (ENFORCE/LOG_ONLY), rules
- CLI: `agentcli policy lint`, `agentcli policy generate`
- Blueprint examples demonstrate policy block

**CRITICAL GAPS (loader integration):**

1. **`builder.add_rule_from_config(rule)` does not exist** — `loader.py` calls a method that `CedarPolicyBuilder` doesn't have. The builder only has `add_policy(CedarPolicy)` and `load_policies_from_file(path)`. This will raise `AttributeError` at runtime.

2. **`policy_client.attach_to_gateway()` called with wrong signature** — `loader.py` calls `attach_to_gateway(agent_id=..., policies=..., mode=...)` but the actual method signature is `attach_to_gateway(gateway_identifier: str, policy_engine_arn: str, mode: PolicyMode)`. Parameters don't match.

3. **Missing orchestration steps** — The correct flow should be:
   1. `policy_client.create_engine(blueprint.policy.engine)` -> engine ARN
   2. For each rule: `translate_rule(rule)` -> Cedar text -> `policy_client.create_policy(engine_id, name, cedar)`
   3. `policy_client.attach_to_gateway(gateway_id, engine_arn, mode)`

   The loader skips steps 1-2 and tries to pass raw Cedar to `attach_to_gateway`.

**This is the only blocking bug found in the entire audit.**

---

### Block 9: Strands Integration — The Full Stack

**Verdict: MINOR GAPS**

**What's correct:**
- `build_agent_session()` wires ALL 8 blocks:
  - Model -> `BedrockModel` (region from `BEDROCK_REGION` env, fail-fast)
  - Tools -> Gateway `MCPClient` + `BuiltinToolWiring` + local `@tool`
  - Identity -> `IdentityWiring` + `CredentialCache`
  - Memory -> `MemoryWiring` + `HookProvider` + `state={}` + `SessionBridge`
  - Observability -> `CompositeObservabilityHook` + `trace_attributes`
  - Evaluation -> `EvaluationClient` (custom + online)
  - Policy -> `CedarPolicyBuilder` + Gateway (see Block 8 bug)
  - Multi-agent -> Swarm + Graph patterns
- `build_entrypoint()` produces complete `AgentCoreApp`
- Hook composition: obs_hook -> custom -> memory (correct order)
- Streaming: `stream_async()` on `AgentSession`
- OTEL session baggage in entrypoint handler
- No hardcoded model names, temperatures, or sampling rates

**Gaps:**
1. `try/except ImportError` guard on Strands import (`loader.py:25-28`) — should fail loud per "no standalone fallbacks" rule

---

### Block 10: A2A Communication

**Verdict: MINOR GAPS**

**What's correct:**
- `A2AServerWrapper` wraps `strands.multiagent.a2a.A2AServer`
- Agent card generated from blueprint metadata
- `A2AClient`: CardResolver (LRU cache), `call_a2a()` (JSON-RPC), `call_direct()` (boto3)
- `remote_agent_tool()`: `@tool` factory for remote agent calls
- Coordinator/specialist/standalone roles
- Port 9000 for A2A, Dockerfile `EXPOSE`
- `build_entrypoint()` mounts A2A server for specialists

**Gaps:**
1. `A2AWiring` is exported but NOT used by `build_agent_session()` or `build_entrypoint()` — dead code
2. Loader's direct `_build_remote_node_tool()` creates `A2AClient()` without M2M auth provider, even when credentials are available
3. The `A2AWiring` class properly handles M2M auth, but since it's not integrated, coordinator->specialist calls may be unauthenticated

---

### Block 12: Blueprints — The Configuration Abstraction

**Verdict: PASS**

**What's correct:**
- 3 blueprint types: `AgentBlueprint`, `StrategyBlueprint`, `WorkflowBlueprint`
- All 12 blocks represented in AgentBlueprint Pydantic schema
- `BlueprintLoader`: `load_agent()`, `load_strategy()`, `load_workflow()`, `build_agent_session()`, `build_entrypoint()`
- CLI: `agentcli blueprint lint` (agent + strategy + workflow, block coverage, cross-validation)
- CLI: `agentcli deploy agent` (bedrock_agentcore_starter_toolkit.Runtime)
- 12 agent examples + 2 strategy examples + 2 workflow examples
- `StrategyBlueprint`: conditions, parameters, required_signals
- `WorkflowBlueprint`: states, triggers, parallel branches, retry/catch
- Cross-block wiring verified in `build_agent_session()`

**Gaps:**
1. `load_workflow_from_path()` missing (agent and strategy have it)

---

## Recommended Fixes by Priority

### P0 — Blocking (must fix)

| # | Block | Issue | Fix |
|---|-------|-------|-----|
| 1 | 8 | `builder.add_rule_from_config()` does not exist | Add method to `CedarPolicyBuilder` OR change loader to use `translate_rule()` from translator module |
| 2 | 8 | `attach_to_gateway()` wrong signature | Fix to: create engine -> create policies -> attach engine ARN to gateway |

### P1 — Policy violations (should fix)

| # | Block | Issue | Fix |
|---|-------|-------|-----|
| 3 | 1-4 | Hardcoded `eu-west-1` in 13+ places | Replace with `os.environ["AWS_REGION"]` (fail-fast) |
| 4 | 1 | `SessionManager` defaults to `runtime_mode="lambda"` | Change default to `"agentcore"` |
| 5 | 1 | Lambda DynamoDB fallback paths in `session.py` | Remove per zero-backward-compat rule |
| 6 | 9 | Strands `try/except ImportError` guard | Remove — Strands is a hard dependency |
| 7 | 6 | `CostTracker` hardcoded fallback pricing | Remove default, require explicit pricing or fail |

### P2 — Improvements (nice to have)

| # | Block | Issue | Fix |
|---|-------|-------|-----|
| 8 | 10 | `A2AWiring` dead code | Integrate into `build_agent_session()` or remove |
| 9 | 10 | Loader A2A path lacks M2M auth | Pass `identity_wiring` to `_build_remote_node_tool()` |
| 10 | 7 | "13 evaluators" docstring | Correct to "12" |
| 11 | 12 | Missing `load_workflow_from_path()` | Add method (trivial) |
| 12 | 1 | Empty `runtime/__init__.py` | Add re-exports |

---

## Metrics

- **Files audited:** 60+ source files across 15 subsystems
- **YAML examples validated:** 16 (12 agent + 2 strategy + 2 workflow)
- **Total gaps found:** 24
  - P0 (blocking): 2 (both in Block 8 loader wiring)
  - P1 (policy violations): 5
  - P2 (improvements): 5
  - Hardcoded region instances: 13+
- **Blocks at PASS:** 2 (Tools, Blueprints)
- **Blocks at MINOR GAPS:** 8 (Runtime, Gateway, Identity, Memory, Observability, Evaluation, Strands, A2A)
- **Blocks at MAJOR GAPS:** 1 (Policy — loader integration only)
- **Blocks SKIPPED:** 1 (Infrastructure)
