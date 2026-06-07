# BLOCKS.md — Active Work Blocks

> **Purpose:** Major work blocks for the project. Always kept current.
> **Rule:** Update this file every session. Blocks move through: `design` → `ready` → `in-progress` → `done`
> **Definition of Done:** `terraform plan` + `terraform apply` in `tcc-qitp` (domain consumer) with zero errors. No exceptions.

---

## Block 1: Schema & Blueprint Hardening ▸ `done`

**Goal:** Fix silent schema failures so all 9 blueprints load correctly with strict validation.

- [x] ENH-015: `extra="forbid"` on 7 models (AgentBlueprint, GraphNodeConfig, GraphEdgeConfig, MultiAgentConfig, McpToolConfig, BuiltinToolConfig, CredentialConfig, StrategyEvaluationConfig)
- [x] ENH-016: Six schema fixes — A2aToolConfig union, optional agent_ref, secret_arn, persistence, gate fields, specialists
- [x] Pre-existing bug: RuntimeConfig.network_mode `"VPC"` → `"PRIVATE"` (5 blueprints affected)
- [x] Pre-existing bug: policy-agent.yaml missing required `temperature` field
- [x] Test fixes: model dicts in 4 test files missing `temperature`/`max_tokens`
- [x] New test file: `test_schema_hardening.py` — extra-forbid + new field coverage

**Completed:** 2026-04-08
**DoD:** ✅ Block 1 changes are SDK-only (schemas). Validated via Block 2 apply.

---

## Block 2: Security & Production Hardening ▸ `done`

**Goal:** Close all security gaps before production. IAM tightening, secrets hygiene, PII filtering.

- [x] ENH-019 #3: Gateway IAM `bedrock-agentcore:*` → 16 enumerated actions across 3 statements
- [x] ENH-019 #4: KMS `Resource:"*"` fallback removed — validation requires non-empty ARN
- [x] ENH-008: PII filter wired through `CompositeObservabilityHook` → `LangfuseHook` → `build_pii_filter()`
- [x] ENH-017: `secrets_kms_key_arn` exposed from platform outputs
- [x] SWEEP: Throttle burst 500→1000 in staging+prod (burst must exceed rate)
- [x] SWEEP: JWT cross-validation upgraded from `check` (warning) to `precondition` (hard error) on gateway resource
- [x] SWEEP: KMS ARN SSM params → `SecureString` with secrets KMS key encryption
- [x] SWEEP: `mcp_m2m_client_id` marked `sensitive` in platform + agentcore outputs

**Out of scope (domain repo):** ENH-019 items #1, #2, #5-14, #15-17 live in `modules/agents/` or domain infra — tracked separately.

**Completed:** 2026-04-08
**DoD:** ✅ `terraform apply` in `tcc-qitp`: Apply complete! 0 added, 36 changed, 0 destroyed. Zero errors.

---

## Block 3: Runtime & Observability ▸ `done`

**Goal:** Add middleware, evaluation, and policy enforcement to agent runtimes.

- [x] ENH-003: Middleware chain — `CorrelationIdMiddleware` + `StructuredErrorMiddleware` as default middleware on `AgentCoreApp`. Correlation ID wired into StructuredLogger and LangfuseHook.
- [x] ENH-002: Online evaluation — evaluation DynamoDB table added to data module, `EVALUATION_TABLE` env var injected, IAM scoped to table + indexes.
- [x] ENH-001: Cedar policies — SDK runtime path confirmed complete (`PolicyWiring`). Documented as KI-002 (SDK-managed, not IaC).
- [x] ENH-007: Bedrock Guardrails — `GuardrailHook` for I/O content filtering, `aws_bedrock_guardrail` Terraform resource (gated by `guardrail_enabled`), env var threading through platform → agents.
- [x] KI-001: Workaround active. No changes needed.

**Completed:** 2026-04-08
**DoD:** ✅ `terraform apply` in `tcc-qitp`: 3 added, 45 changed, 0 destroyed. Zero errors.

---

## Block 4: Infrastructure Modules & Cleanup ▸ `done`

**Goal:** Reusable Terraform modules to eliminate domain repo boilerplate. Cleanup remaining sweep items.

- [x] ENH-011: `modules/lambda` — archive + function + IAM + VPC toggle + log group. ~70-110 lines per Lambda eliminated.
- [x] ENH-012: `modules/lambda_alarms` — Error + Duration (p99 @ 75% timeout) alarm factory from Lambda map.
- [x] ENH-013: `modules/scheduled_lambda` — EventBridge rule + target + permission triad.
- [x] ENH-014: `modules/s3_encrypted_bucket` — bucket + versioning + KMS SSE + public access block + optional SSM.
- [x] ENH-018: Descriptions added to all 48 platform outputs (was 32 missing).
- [x] SWEEP: `enable_artifacts_gateway_target` + `sns_alert_email` added to staging/prod tfvars.
- [x] SWEEP: CloudFront outputs now have descriptions noting conditional behavior.

**Completed:** 2026-04-08
**DoD:** ✅ `terraform apply` in `tcc-qitp`: 0 added, 36 changed, 0 destroyed. Zero errors.

---

## Block 5: Inference Migration + Production Pilot Validation ▸ `done`

**Goal:** Prove the platform runs a real production pipeline end-to-end on the LiteLLM proxy with `claude-sonnet-4-6`, no Bedrock dependency for inference, and no silent failure modes.

**Phase 1 — Stage 1 Inference Decoupling (2026-04-09 AM)**
- [x] `_build_model_config()` match/case dispatch for bedrock/anthropic/litellm/vertex
- [x] `ModelConfig` + `base_url` / `api_key_env` / `extra_headers_env` optional fields
- [x] `StructuredOutputEnforcer` hook (instructor-based post-processor) for non-Bedrock `output_schema` — **superseded:** enforcer deleted in `8c784df`, Strands native `structured_output_model` used for all providers as of strands-agents 1.41.0
- [x] All 9 QITP agents swapped to `provider: litellm` in blueprints
- [x] `litellm>=1.83.0,<2` safety pin (CVE-2026-33634)
- [x] `custom_llm_provider="openai"` flag in loader (litellm quirk fix — don't let it route claude-* to native Anthropic endpoint)

**Phase 2 — Hooks Decoupling (2026-04-09 afternoon)**
- [x] `GuardrailHook` provider-gated — no-op on non-Bedrock providers
- [x] `PresidioGuardrailHook` — provider-agnostic PII redaction
- [x] `LangfuseEvaluationClient` + `EvaluationProvider` protocol
- [x] `CostTracker` envs renamed `BEDROCK_*` → `MODEL_*`, legacy aliases still honored
- [x] `observability.enabled` toggle wired through `loader.py`
- [x] Dead YAML (`observability.dashboard.*`, `observability.audit_log.ttl_days`) purged from all 9 blueprints
- [x] `TestPhase2Decoupling` tests in `test_block9_strands_integration.py`

**Phase 3 — Production Pilot Validation (2026-04-09 evening)**
- [x] **`rebuild-deploy.sh` orchestrator** in `tcc-qitp/scripts/` — parallel build, parallel poll, parallel force-update for all agents + MCPs; GitHub Actions `build-deploy.yml` delegates to it
- [x] **Semver kill switch** — `core/pyproject.toml` pinned to floating `1.0.0`; `core/scripts/publish-wheel.sh` deletes + republishes to CodeArtifact on every push; `.github/workflows/publish.yml` trigger changed from `tags: ['v*']` to `branches: [main]` with path filter
- [x] **Market-calendar Lambda contract fix** — `tcc-qitp/lambdas/market_calendar/handler.py` flipped from seed-default to validate-default; explicit `{"seed": true}` for EventBridge quarterly refresh; `domain_compliance.tf` EventBridge target updated
- [x] **Platform LiteLLM key wiring** — new Secrets Manager entry `qitp/platform/litellm` (JSON field `TOKEN`), scope covers claude-sonnet-4-6/gpt-5-codex/gemini-3.1-pro/deepseek-r1/llama-3.3-70b; new `data "aws_secretsmanager_secret_version" "platform_litellm"` in `tcc-qitp/infra/domain_dashboard.tf`; `main.tf:52` + `:122` both modules read `["TOKEN"]`
- [x] **True E2E validation** — `pilot-t4-1775755670` 16/16 states in 44.08 s, gap-detector ran on real claude-sonnet-4-6 via LiteLLM, structured-output enforcer produced a valid `GapDetectionOutput` payload, claim-check artifact persisted to S3 (`domain/2026-04-09/13b6f34b-7306-40fe-b30c-9a2feeb9c63b/gap-detector.json`, 497 B envelope + full payload). All 8 downstream agents invoked and returning well-formed HTTP 200.
- [x] **Documentation refresh** — `inference-migration.md`, `STATE.md`, `BLOCKS.md`, `CLAUDE.md`, `TODO.md` all updated to reflect pilot-t4 as the authoritative E2E proof. Earlier aspirational run `exec a2ad23f0-f8fd-4ef2-bbcf-fd2c4f8c1c51` removed from the docs as misleading.

**Not in scope (deferred to Block 6):**
- Downstream agent empty-symbols fallback (5 agents: sentiment-analyzer, technical-analyzer, ml-predictor, strategy-evaluator, portfolio-recommender) — input validators reject empty `symbols` / `symbol` / `strategy_evaluations` fields when upstream gap-detector returns zero gaps. Application-level, not infra.

**Completed:** 2026-04-09
**DoD:** ✅ `terraform apply` in domain consumer — zero errors. Pipeline — 16/16 states, SUCCEEDED in 44.08 s with real inference and claim-check artifact persisted. Two fixes shipped in domain repo, two fixes shipped in platform repo, all E2E validated in a single pipeline run.

---

---

## Post-Block-5 Bug Fixes ▸ `done`

> Targeted fixes landed on `dev` after Block 5 validation. Not a named block — individual commits.

| Commit | Fix | Impact |
|--------|-----|--------|
| `8c784df` | Delete `StructuredOutputEnforcer` from loader wiring — use Strands native `structured_output_model` for all providers | Removes instructor dependency; aligns with strands-agents ≥ 1.41.0 (upstream bugs #743/#1005/#891 resolved) |
| `4c57d6c` | Graph coordinator synthesis turn fires after graph nodes complete (Bug F + Bug A) | Coordinator agents in graph mode now produce a final synthesis response correctly |
| `8f8b367` | Capture agent reasoning in Langfuse trace input/output (Bug H) | Full conversation JSON (prompt, tool calls, results) now in Langfuse traces; was null before |
| `319ba11` | Build platform-deps Lambda layer hermetically in Terraform | CI no longer requires local pip install; layer is reproducible across environments |

---

## Backlog (not scheduled)

| ID | Enhancement | Priority | Effort |
|----|-------------|----------|--------|
| ENH-004 | Memory strategy expansion (EPISODIC + USER_PREFERENCE) | nice-to-have | Low |
| ENH-005 | Server-side tool execution (Bedrock Responses API) | nice-to-have | Medium |
| ENH-006 | AG-UI protocol for dashboard streaming | nice-to-have | Medium |
| ENH-009 | A2A protocol (cross-runtime invocation) | someday | High |
| ENH-010 | Memory streaming to Kinesis | someday | Medium |
| ENH-020 | `build_entrypoint()` zero-boilerplate app | someday | Low |

---

## Completed Blocks

### Remove Network Sub-Module ▸ `done`

Networking is owned by a separate project. This platform module now consumes externally-created VPC resources via input variables + data sources.

- [x] Remove `modules/platform/modules/network/` (VPC, subnets, IGW, NAT, route tables, security groups)
- [x] Replace `vpc_cidr`, `availability_zones`, `nat_gateway_count` with input variables (`vpc_id`, `private_subnet_ids`, etc.)
- [x] Add `data "aws_vpc" "main"` to hydrate VPC ID for `cidr_block` access
- [x] Update security module wiring, outputs, SSM parameters
- [x] Update all 3 tfvars with documented placeholder IDs
- [x] Update CLAUDE.md: add Network Requirements table, add rule #10, trim to <200 lines
- [x] Sweep: removed 3 unused data sources, added `private_subnet_ids` validation

### Sweep Log — 2026-04-02

- **Issues found:** 13 (quality: 13, compliance: 0, integration: 0)
- **Fixed:** 5 (3 unused data sources removed, 1 validation added, 1 doc update)
- **Remaining:** 8 → absorbed into Blocks 2 and 4 above
