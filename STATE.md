# Documentation Audit — STATE (Verified)

> **Audit date:** 2026-03-24
> **Phase 1:** 6 Opus sub-agents scanned all 49 docs/ files against source-of-truth documents
> **Phase 2:** 3 Opus verification agents cross-referenced findings against actual platform code (`core/src/agent_core/`) and working domain repo (`tccw-qitp/`)
> **Source of truth:** `resources/CONCEPTS.md`, `resources/VISION.md`, `resources/TECHNICAL-GUIDE.md`
> **Standards:** AI DLC workflow rules (`aidlc-workflows/aidlc-rules/`)

---

## Executive Summary (Post-Verification)

The initial audit flagged 7 CRITICAL and 61 HIGH findings. Verification against actual platform code revealed **20+ false positives** — the platform SDK is far more complete than the upstream TECHNICAL-GUIDE.md suggests. Many "invented" methods actually exist as platform abstractions.

| Severity | Initial | Verified | Description |
|----------|---------|----------|-------------|
| **CRITICAL** | 7 | **2** | Entrypoint signature wrong, strategy blueprint fictional |
| **HIGH** | 61 | **34** | Wrong field names, wrong method names, missing required fields, AI DLC violations |
| **MEDIUM** | 66 | **52** | Incomplete coverage, vision gaps, missing diagrams (14 downgraded to LOW) |
| **LOW** | 35 | **35** | Minor wording, style differences |
| **SCHEMA GAP** | 0 | ~~3~~ **0** | ~~Pydantic models missing fields~~ **FIXED in commit `27fa322`** |
| **FALSE POSITIVE** | 0 | **22** | Platform code supports what docs describe; initial audit was wrong |
| **PASS** | — | — | Zero domain contamination, navigation correct, CLI accurate |

---

## False Positives Removed (22 findings)

These were initially flagged but verification proved the platform code supports them:

| Original ID | Finding | Why It's a False Positive |
|-------------|---------|--------------------------|
| C3 | `from agent_core.*` imports wrong | `AgentCoreApp` is the public export; `BedrockAgentCoreApp` is internal |
| C5 | 3LO nested function pattern missing | Pattern IS documented in `identity/wiring.py` docstring |
| C6 | A2A server pattern wrong | `A2AServerWrapper`, `A2AClient`, `A2AWiring` all exist in platform |
| C7 | Evaluator names wrong | `BuiltinEvaluator` enum has 12 members matching `Builtin.*` naming |
| H30 | Identity decorator imports wrong | `requires_access_token`/`requires_api_key` exist in `agent_core.identity.decorators` |
| H32 | Missing `EPISODIC` strategy type | `EPISODIC` IS in `MemoryStrategyType` enum |
| H33 | Missing `MemoryClient` | `MemoryManager` wraps `MemoryClient`; both exist |
| H34 | Missing HookProvider pattern | `MemoryHookProvider.register_hooks()` with `HookRegistry` exists exactly as expected |
| H36 | Missing OTEL env vars | `config_gen.py` generates all OTEL env vars |
| H37 | Missing `trace_attributes` | `loader.py` builds and passes `trace_attributes` to Strands `Agent()` |
| H38 | Missing evaluator levels | `EvaluatorLevel` enum has `TRACE`, `SESSION`, `SPAN` |
| H40 | Cedar entity types wrong | `CEDAR_SCHEMA` uses `AgentCore` namespace with correct entity types |
| H41 | PolicyClient missing | `PolicyClient` has full lifecycle: `create_engine()`, `attach_to_gateway()`, etc. |
| H42 | Code Interpreter API wrong | `CodeInterpreterProvider` exists as gateway-backed provider |
| H43 | Browser API wrong | `BrowserProvider` exists as gateway-backed provider |
| H1 | `prompt_ref` type | Platform uses `str` — docs and code agree on the data type itself |
| H25 | Three-port convention | Port 8080 (runtime) + optional 9000 (A2A) — 8000 doesn't exist but 2-port is correct |
| H31 | Identity decorator params | All 7 parameters exist with correct names and defaults |
| M5 | Missing `StrategyType` enum | Exists as `MemoryStrategyType` in `schemas/memory_config.py` |
| M6 | Missing HookRegistry pattern | `register_hooks(registry: HookRegistry)` exists in `hook_provider.py` |
| M65 | Import mapping never explained | `agent_core` IS the correct import; no mapping needed |
| M66 | `AgentCoreApp` vs `BedrockAgentCoreApp` | `AgentCoreApp` is the public API; upstream class is wrapped internally |

---

## Block 1 — CRITICAL Findings (2 verified)

### C1. Strategy Blueprint Doc Is Fiction
- **File:** `docs/blueprints/strategy-blueprint.md`
- **Verified:** CONFIRMED + PARTIAL
- **Detail:** The documented YAML structures (`entry_conditions.all[]`, `parameters.sizing`, `required_signals[].source/type`, `risk_controls`, `evaluation.primary_metric`) do NOT exist in the `StrategyBlueprint` Pydantic model. Actual schema uses `ConditionGroupConfig` (with `logic: and/or`, `conditions: [{field, operator, value}]`), `ParameterConfig` (with `name, type, default, min_value, max_value`), and `required_signals: list[str]`.
- **Nuance:** The domain repo `tccw-qitp` YAML also uses `evaluation` and `risk_controls` — but those fields are silently dropped by Pydantic (not `extra="forbid"`). So the docs describe aspirational schema fields that don't actually do anything.
- **Impact:** Complete rewrite required.

### C2. Runtime Entrypoint Signature Is Wrong
- **File:** `docs/sdk/runtime.md`
- **Verified:** CONFIRMED
- **Evidence:** `entrypoint.py` line 73: "The decorated function receives `(payload, context)`". Domain repo `app.py` line 39: `def handler(event: dict, context=None)`. Docs show `async def handle(context)` with single parameter and invented `context.input_text`.
- **Impact:** Copy-pasting the documented handler will fail at runtime.

---

## Block 2 — HIGH Findings (34 verified)

### 2A. Docs Say X, Platform Code Says Y (14 confirmed)

| # | File | Finding | Verified Evidence |
|---|------|---------|-------------------|
| H3 | `blueprints/agent-blueprint.md` | Strategy type `SUMMARIZATION` | ~~Enum has `SUMMARY` only.~~ **Schema now accepts both** (commit `27fa322`). Docs still need to show `SUMMARY` as canonical with `SUMMARIZATION` as alias. |
| H4 | `blueprints/agent-blueprint.md` | Credential types `m2m`/`oauth_3lo` | Enum: `api_key`, `oauth2` only |
| H13 | `getting-started/quickstart.md` | Uses `agent_id:` instead of `id:` | Field is `id` in schema + domain YAML |
| H14 | `getting-started/quickstart.md` | Missing required `prompt_ref`, `name`, `model.temperature`, `model.max_tokens` | All use `Field(...)` — required, no defaults |
| H15 | `getting-started/quickstart.md` | `memory.mode: MANAGED` | No `mode` field in `MemoryConfig` |
| H16 | `getting-started/first-agent.md` | Uses `agent_id:` | Same as H13 |
| H17 | `getting-started/first-agent.md` | Missing required fields | Same as H14 |
| H18 | `getting-started/first-agent.md` | `memory.mode: MANAGED` | Same as H15 |
| H19 | `getting-started/first-agent.md` | `audit_log.ttl_years: 5` | Actual: `ttl_days: int` |
| H20 | `getting-started/first-agent.md` | `agentcli invoke` | No `invoke` subcommand in CLI |
| H21 | `blueprints/agent-blueprint.md` | `multi_agent.type: graph` | Actual field: `pattern` |
| H22 | `sdk/runtime.md` | `context.stream.write()` | Streaming uses `async def` + `yield` |
| H23 | `sdk/runtime.md` | `@app.middleware` decorator | Actual: `AgentCoreApp(middleware=[Middleware(...)])` |
| H24 | `sdk/runtime.md` | Dockerfile `public.ecr.aws/lambda/python:3.12` | Actual: `python:3.12-slim` |

### 2B. Docs Show Method That Doesn't Exist (3 confirmed)

| # | File | Finding | Actual Method |
|---|------|---------|---------------|
| C4 | `sdk/gateway.md` | `client.as_mcp_client()` | `client.as_tool_provider()` |
| H35 | `sdk/observability.md` | `configure_otel()` function | Doesn't exist — OTEL via env vars in `config_gen.py` |
| H39 | `sdk/evaluation.md` | `client.as_hook()` | Doesn't exist — `create_online_config()` is the real method |

### 2C. Partial — Method Names Differ (2)

| # | File | Docs Say | Actual |
|---|------|----------|--------|
| H5.3 | `sdk/memory.md` | `write_event()` / `search()` | `create_event()` / `retrieve_memories()` or `semantic_search()` |
| M29 | `sdk/policy.md` | "Amazon Verified Permissions" | AgentCore Policy Engine (zero AVP references in code) |

### 2D. Strategy Blueprint Schema Errors (6 confirmed)

| # | File | Finding |
|---|------|---------|
| H5 | `blueprints/strategy-blueprint.md` | Operator names: `greater_than` → actual: `gt`, `eq`, `lt`, etc. |
| H6 | `blueprints/strategy-blueprint.md` | `entry_conditions.all[]` → actual: `ConditionGroupConfig` with `logic`/`conditions` |
| H7 | `blueprints/strategy-blueprint.md` | `required_signals` as objects → actual: `list[str]` |
| H8 | `blueprints/strategy-blueprint.md` | `parameters.sizing` → actual: `list[ParameterConfig]` |
| H9 | `blueprints/strategy-blueprint.md` | `evaluation` block fabricated |
| H10 | `blueprints/strategy-blueprint.md` | `risk_controls` block fabricated |

### 2E. Infrastructure (5 confirmed — unchanged from initial audit)

| # | File | Finding |
|---|------|---------|
| H56 | `infrastructure/platform-module.md` | Missing `prompt_registry` sub-module (7 exist, 6 documented) |
| H57 | `infrastructure/platform-module.md` | Missing `prompt_registry_url` output |
| H58 | `infrastructure/agents-module.md` | Missing `prompt_registry_url` variable |
| H59 | `infrastructure/workflows-module.md` | Missing `lambda_arns` variable |
| H60 | `infrastructure/infrastructure.md` | `prompt-registry-module.md` not linked in index |

### 2F. AI DLC Compliance (1 — unchanged)

| # | Scope | Finding |
|---|-------|---------|
| H61 | 10 files | Unicode box-drawing characters violate AI DLC. Files: `concepts/runtime.md`, `concepts/gateway.md`, `concepts/memory.md`, `concepts/observability.md`, `architecture/building-blocks.md`, `architecture/platform-vs-domain.md`, `cli/evaluation.md`, `cli/graph.md`, `cli/prompt.md`, `cli/blueprint.md` |

### 2G. Concepts/Architecture Missing Content (3 confirmed)

| # | File | Finding |
|---|------|---------|
| H52 | `architecture/building-blocks.md` | Strategy Blueprint uses domain language: "entry/exit rules, sizing logic" |
| H53 | `architecture/building-blocks.md` | Execution mode isolation completely missing |
| H54 | `architecture/platform-vs-domain.md` | Missing VISION.md 6-step consumption walkthrough |

---

## Block 3 — Schema Gaps ~~(code bugs, not doc bugs)~~ RESOLVED

> **Fixed in commit `27fa322`** — All 3 schema gaps resolved.

| # | Schema | Fix Applied | Commit |
|---|--------|-------------|--------|
| ~~SG1~~ | `WorkflowState` | Added `agent_ref`, `prompt`, `input_mapping`, `error`, `cause`, `heartbeat_seconds`, `retry_max`. Also added `wait_for_token` to state type Literal. | `27fa322` |
| ~~SG2~~ | `WorkflowBlueprint` | Added `MemoryBranchConfig` class with `enabled`, `merge_strategy` (union/latest/coordinator_wins/none), `branch_namespace`. | `27fa322` |
| ~~SG3~~ | `StrategyBlueprint` | Added `StrategyEvaluationConfig` (primary_metric, metrics, benchmark, lookback_window, min_activations_threshold) and `RiskControlConfig` (max_daily_error_rate, max_degradation_halt, circuit_breaker). Also added type aliases (string->str) and case-insensitive logic (AND->and). | `27fa322` |

**Additionally fixed:** `MemoryStrategyConfig` now accepts `SUMMARIZATION` as alias for `SUMMARY` via `field_validator`.

**Verified:** All 2 platform + 7 domain YAML blueprints pass validation. Zero domain contamination.

---

## Block 4 — MEDIUM Findings (52 verified)

*Kept from initial audit with minor adjustments. Key themes:*

### Vision Misalignment (10)
- M1-M4, M7-M12: Architecture index missing "bundle concept", "zero boilerplate", "execution mode isolation", "Terraform-native consumption" principles. Concepts pages omit raw FastAPI approach, Gateway aggregation, credential setup steps.

### Incomplete Content (18)
- M13-M28 (minus false positives): SDK pages missing `app.run()` calls, Gateway creation APIs, workload identity CRUD, M2M auth flow detail, on-demand evaluation, NL2Cedar `generate_policy()`, OTEL baggage, custom spans, Guardrails.

### Missing Concept Pages (4 concepts)
- M63: `concepts/` has 8 pages but `sdk/` has 12. Missing: **Tools**, **MCP**, **Prompts**, **Artifacts**.

### Blueprints/CLI Gaps (11)
- M50-M60: `multi_agent.nodes` wrong field names, missing `gateway` block docs, trigger type `event` omitted, `model.region` fabricated, CLI command syntax wrong.

### Infrastructure (5)
- M45-M49: Composition diagram missing prompt_registry, missing CodeArtifact variables, network mode `PRIVATE` vs `VPC`, unverified VPC endpoint.

### AI DLC (2)
- M61: 15 Mermaid diagrams lack text fallbacks
- M62: Index page doesn't mention Prompt Registry or MCP Artifacts

---

## Block 5 — Systemic Issues (Post-Verification)

### S1. Platform Wrapper Layer (DOWNGRADED from initial)
Initial audit claimed platform wrappers "hide" upstream patterns. Verification shows the platform IS the correct abstraction — `agent_core` imports are right, classes exist, methods work. The issue is narrower: **a few specific method names are wrong** (C4: `as_mcp_client` → `as_tool_provider`, H35: `configure_otel` doesn't exist, H39: `as_hook` doesn't exist) and **some SDK pages should note the upstream equivalent for advanced users**.

### S2. Getting-Started Examples Fail Validation (CONFIRMED)
Every getting-started blueprint uses wrong field names (`agent_id` → `id`), missing required fields (`prompt_ref`, `name`, `model.temperature`, `model.max_tokens`), and fabricated fields (`memory.mode`). Domain repo `tccw-qitp` uses correct field names — these docs diverge from working code.

### S3. Strategy Blueprint Is Fictional (CONFIRMED)
Schema in docs has zero overlap with actual `StrategyBlueprint` Pydantic model. Domain repo uses some fields (`evaluation`, `risk_controls`) that don't exist in the model either — they're silently dropped.

### S4. Domain Language in Strategy (CONFIRMED)
"Entry/exit rules", "sizing logic", "required signals" come from trading/investment context. Not in `domain-scan.sh` hard terms but violate the spirit.

### S5. AI DLC Unicode Violation (CONFIRMED)
10 files use forbidden Unicode box-drawing characters.

---

## Passes (Unchanged)

| Category | Result |
|----------|--------|
| Domain contamination (hard terms) | **ZERO** across all 49 files |
| Navigation hierarchy | **PASS** — all index pages link correctly |
| Section depth levels | **PASS** — appropriate for each audience |
| Cross-section consistency | **PASS** — no contradictions between sections |
| Infrastructure variables | **28/28** platform, **5/5** agent outputs, **3/3** workflow outputs match |
| CLI commands | **PASS** — 7 command groups match Typer implementation |
| Outdated patterns | **ZERO** CDK references, **ZERO** Lambda-as-agent-host |
| Platform SDK completeness | **PASS** — `agent_core` exports, wrappers, hooks, providers all verified working |

---

## Recommended Fix Priority (Revised)

### Phase 1 — Critical (blocks new users)
1. Fix runtime entrypoint signature: `def handler(payload, context)` with two args
2. Rewrite `strategy-blueprint.md` from actual `StrategyBlueprint` schema
3. Fix all getting-started examples: `id` not `agent_id`, add required fields, remove `memory.mode`
4. Fix 3 wrong method names: `as_tool_provider()`, remove `configure_otel()`, `create_online_config()`

### Phase 2 — High (misleading content)
5. Fix agent-blueprint.md: `SUMMARY` not `SUMMARIZATION`, `oauth2` not `oauth_3lo`, `pattern` not `type`
6. Fix runtime.md: streaming via `yield`, middleware via constructor, correct Dockerfile base image
7. Fix memory method names: `create_event()` not `write_event()`, `retrieve_memories()` not `search()`
8. Fix policy.md: AgentCore Policy Engine, not Amazon Verified Permissions
9. Add missing infra variables/outputs (prompt_registry, lambda_arns)
10. Convert 10 files from Unicode to ASCII box characters (AI DLC)

### ~~Phase 3 — Schema Gaps~~ DONE (commit `27fa322`)
~~11. Add `agent_ref`, `prompt`, `input_mapping` etc. to `WorkflowState` Pydantic model~~
~~12. Add `memory_branching` to `WorkflowBlueprint`~~
~~13. Add `evaluation`, `risk_controls` to `StrategyBlueprint`~~

### Phase 4 — Completeness
14. Add 4 missing concept pages: Tools, MCP, Prompts, Artifacts
15. Add vision principles to architecture index (bundle, zero boilerplate, execution modes)
16. Add 6-step consumption walkthrough to platform-vs-domain.md
17. Sanitize strategy domain language
18. Add Mermaid text fallbacks (AI DLC)

### Phase 5 — Polish
19. Terminology consistency ("building block" vs "subsystem")
20. Prompt Registry / Artifacts visibility in index
21. Minor detail additions from source-of-truth
