# Postmortem — Platform Audit Findings

> Each block below is a self-contained work unit. Assign one block per agent session to avoid context rot.
> Check off items as they are fixed. Run `./scripts/domain-scan.sh` after every block.

---

## Block 1: Runtime — Critical Bugs + Vision Alignment

**Files:** `core/src/agent_core/runtime/adapter.py`, `handler.py`, `entrypoint.py`

- [x] Fix `AgentResult` dataclass — add missing fields: `claim_check`, `artifact_id`, `s3_key`, `tier`, `error` (`adapter.py:44-51`)
- [x] Add `to_lambda_response()` method to `AgentResult` — `handler.py:145` calls it but only `to_response()` exists
- [x] Reconcile `handler.py` Lambda pattern — `handle(self, event, context)` is Lambda-shaped; either remove or align with `@app.entrypoint`
- [x] Implement `.bedrock_agentcore.yaml` generation from blueprint config (marked done in old PROGRESS.md but no code exists)
- [x] Implement Dockerfile template generation from blueprint config (marked done but not implemented)

---

## Block 2: Gateway — Hardcoded Defaults

**Files:** `core/src/agent_core/gateway/client.py`, `target_registry.py`, `tool_discovery.py`

- [x] Remove hardcoded `"eu-west-1"` default from `client.py:83` — require explicit region or fail
- [x] Remove hardcoded `"eu-west-1"` default from `target_registry.py:79` — require explicit region or fail
- [x] Improve `ToolDiscovery.find_tools_for_task()` — currently keyword matching only, consider semantic matching

---

## Block 3: Identity — Export Gap + Hardcoded Defaults

**Files:** `core/src/agent_core/identity/__init__.py`, `client.py`, `providers.py`

- [x] Export `IdentityClient` from `identity/__init__.py` — class exists but is not in public API
- [x] Remove hardcoded `"eu-west-1"` default from `identity/client.py:23`
- [x] Remove hardcoded `"eu-west-1"` default from `identity/providers.py:105`

---

## Block 4: Memory — Critical Bug + Hardcoded Defaults

**Files:** `core/src/agent_core/memory/__init__.py`, `manager.py`, `session_bridge.py`, `branching.py`

- [x] Implement `get_memory_manager()` factory function — `runtime/session.py:181` calls it but it doesn't exist anywhere
- [x] Remove hardcoded `"eu-west-1"` default from `memory/manager.py:31`
- [x] Remove hardcoded `"eu-west-1"` default from `memory/session_bridge.py:73`
- [x] Remove hardcoded `"eu-west-1"` default from `memory/branching.py:30`

---

## Block 5: Tools — Vision Alignment

**Files:** `core/src/agent_core/tools/code_interpreter.py`, `browser.py`, `wiring.py`

- [x] Route builtin tools (CodeInterpreter, Browser) through Gateway as targets instead of direct Strands instantiation — current code creates local providers, vision says they should be Gateway-mediated like all other tools

---

## Block 6: Observability — Hardcoded Pricing + Missing Features

**Files:** `core/src/agent_core/observability/cost_tracker.py`, `otel.py`, `data_protection.py`

- [x] Externalize model pricing from `cost_tracker.py:40-67` — 13 hardcoded model IDs + prices. Load from config/env var instead
- [x] Remove hardcoded fallback pricing `(0.003, 0.015)` — make configurable
- [x] Add OTEL auto-instrumentation wrapper pattern (Dockerfile CMD with `opentelemetry-instrument`)
- [x] Apply PII anonymization to Langfuse traces, not just CloudWatch logs
- [x] Implement CloudWatch GenAI-specific metrics (model inference time, token counts per model)

---

## Block 7: Evaluation — Missing Wiring

**Files:** `core/src/agent_core/evaluation/client.py`, `evaluators.py`

- [x] Create `evaluation/wiring.py` — bridge blueprint `EvaluationConfig` to `EvaluationClient` (auto-create custom evaluators, enable online evaluation from YAML)
- [x] Wire `evaluation/wiring.py` into `BlueprintLoader.build_agent_session()`
- [x] Add evaluation result persistence (store scores to DynamoDB or similar)

---

## Block 8: Policy — Missing Wiring

**Files:** `core/src/agent_core/policy/client.py`, `cedar_policies.py`, `translator.py`

- [x] Create `policy/wiring.py` — bridge blueprint `PolicyConfig` to `PolicyClient` (auto-create engine, deploy Cedar policies, attach to Gateway)
- [x] Wire `policy/wiring.py` into `BlueprintLoader.build_agent_session()`
- [x] Add policy versioning (track deployed policy versions, support rollback)

---

## Block 9: Strands Integration — Minor Gaps

**Files:** `core/src/agent_core/blueprints/loader.py`

- [ ] Verify `build_agent_session()` calls `evaluation/wiring.py` after Block 7 creates it
- [ ] Verify `build_agent_session()` calls `policy/wiring.py` after Block 8 creates it

---

## Block 10: A2A — Broken Exports + Streaming

**Files:** `core/src/agent_core/__init__.py`, `a2a/client.py`

- [ ] Add missing imports for `A2AClient`, `A2AServerWrapper`, `A2AWiring`, `remote_agent_tool` to `core/__init__.py` — declared in `__all__` but never imported
- [ ] Add streaming support to `A2AClient.call_a2a()` — currently returns final text only

---

## Block 11: Terraform — Complete

No remaining issues.

---

## Block 12: Schemas + CLI — Hardcoded Defaults + Missing Lint

**Files:** `core/src/agent_core/schemas/model_config.py`, `gateway_config.py`; `cli/src/agent_cli/`

- [ ] Remove hardcoded `temperature=0.2` default from `schemas/model_config.py:19` — make required or None
- [ ] Remove hardcoded `max_tokens=4096` default from `schemas/model_config.py:20` — make required or None
- [ ] Remove hardcoded `"eu-west-1"` default from `schemas/gateway_config.py:42`
- [ ] Implement `agentcli blueprint lint` CLI command — validates agent/strategy/workflow YAML against Pydantic schemas

---

## Block 13: Code Quality — Error Handling

**Files:** `core/src/agent_core/api/artifacts_api.py`

- [ ] Fix silent error swallowing at `artifacts_api.py:128-130` — `except Exception: pass` on S3 get_object
- [ ] Fix overly broad exception at `artifacts_api.py:46-49` — catch specific exceptions, not `Exception`

---

## Block 14: Test Coverage — Critical Gaps

- [ ] Runtime module tests (`core/tests/test_runtime_*.py`) — currently 0% coverage
- [ ] Memory module tests (`core/tests/test_memory_*.py`) — currently 0% coverage
- [ ] Gateway module tests (`core/tests/test_gateway_*.py`) — currently ~5% coverage
