# ENHANCEMENTS.md — Feature Requests & Improvements

> **Purpose:** Track desired enhancements, feature ideas, and improvement proposals. Unlike BLOCKS.md (active work) or BUGS.md (defects), these are forward-looking ideas that may or may not be scheduled.
> **Priority:** `must-have` | `nice-to-have` | `someday`
> **Source:** Extracted from operator/references/PLATFORM-REFERENCE.md (9-agent deep analysis, 2026-03-30)

---

## Done (14 enhancements completed 2026-04-08)

| ID | Enhancement | Block |
|----|-------------|-------|
| ENH-001 | Cedar policies on Gateway (SDK runtime path) | Block 3 |
| ENH-002 | Online evaluation (DynamoDB table + env var + IAM) | Block 3 |
| ENH-003 | Middleware chain (correlation IDs + structured errors) | Block 3 |
| ENH-007 | Bedrock Guardrails (GuardrailHook + TF resource) | Block 3 |
| ENH-008 | PII filter on Langfuse traces | Block 2 |
| ENH-011 | `modules/lambda` reusable module | Block 4 |
| ENH-012 | `modules/lambda_alarms` alarm factory | Block 4 |
| ENH-013 | `modules/scheduled_lambda` EventBridge triad | Block 4 |
| ENH-014 | `modules/s3_encrypted_bucket` | Block 4 |
| ENH-015 | Blueprint schema hardening (`extra="forbid"`) | Block 1 |
| ENH-016 | Schema fixes (A2A, gate nodes, credentials, etc.) | Block 1 |
| ENH-017 | Expose `secrets_kms_key_arn` from platform outputs | Block 2 |
| ENH-018 | Add descriptions to all 48 platform outputs | Block 4 |
| ENH-019 | Production IAM tightening (platform scope: #3, #4) | Block 2 |

---

## Next Moves — Platform-Agnostic Readiness Items

> These are domain-agnostic improvements that any consuming project benefits from.
> Each is self-contained and can be kicked off independently by any agent.
> Ordered by impact on production readiness score (currently 73/100).

---

### NM-001: Test Coverage — Runtime, Memory, Gateway ▸ `must-have` ▸ Target: 85/100

**Current state:** Runtime 0%, Memory 0%, Gateway 5%. A regression in any subsystem hits production undetected.

**What to do:**
1. Add unit tests for `AgentCoreApp` entrypoint: middleware registration, `from_blueprint()`, `invoke()` happy path + error path
2. Add unit tests for `CorrelationIdMiddleware` and `StructuredErrorMiddleware` (mock ASGI app)
3. Add unit tests for `MemoryConfig` resolution, `MemoryStrategyConfig` validation, `MemoryWiring` lifecycle
4. Add integration tests for `GatewayClient`: tool discovery, tool call routing, direct MCP fallback path
5. Add tests for `EvaluationWiring`: custom evaluator creation, online config registration, result persistence

**Target:** Runtime ≥ 50%, Memory ≥ 50%, Gateway ≥ 30%. All via pytest, CI-only.

**Files:** `core/tests/test_runtime_*.py`, `core/tests/test_memory_*.py`, `core/tests/test_gateway_*.py` (new)

**Effort:** Large (3-5 sessions)

---

### NM-002: Domain IAM Hardening (13 items) ▸ `must-have` ▸ Target: 85/100

**Current state:** `bedrock:*` on `*` across 17 agent runtimes. One compromised runtime has full Bedrock access.

**What to do (in `modules/agents/iam.tf` — platform repo, consumed by all domains):**
1. Replace `bedrock:*` with `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` scoped to specific foundation-model ARN patterns
2. Replace `bedrock-agentcore:*` on agent runtimes with enumerated actions (same approach as Block 2 gateway fix)
3. Add `aws:SourceAccount` condition to EventBridge trust policies
4. Scope SFN `logs:*` to specific log group ARN patterns
5. Move `COGNITO_MCP_CLIENT_SECRET` and `LANGFUSE_SECRET_KEY` from env vars to runtime SSM Parameter Store fetch (requires SDK change in `LangfuseHook` and `DirectMCPClient`)

**Reference:** `operator/references/PLATFORM-REFERENCE.md` §IAM & Security Posture, items #1, #2, #5-10, #13-14

**Effort:** Large (2-3 sessions). Items #13-14 (secrets from env vars to SSM) require coordinated SDK + TF changes.

---

### NM-003: Enable Guardrails in Staging/Production ▸ `must-have` ▸ Target: 85/100

**Current state:** `guardrail_enabled = false` in all 3 tfvars. The `aws_bedrock_guardrail` resource and `GuardrailHook` are fully wired but dormant.

**What to do:**
1. Set `guardrail_enabled = true` in `modules/platform/envs/staging.tfvars`
2. Set `guardrail_enabled = true` in `modules/platform/envs/production.tfvars`
3. Review `guardrail_pii_entities` defaults (EMAIL, PHONE, NAME → ANONYMIZE; SSN, CC → BLOCK) — customize per domain if needed
4. In domain repo: `terraform apply` to create the guardrail
5. Verify agent runtimes receive `BEDROCK_GUARDRAIL_ID` and `BEDROCK_GUARDRAIL_VERSION` env vars
6. Test: confirm `GuardrailHook` logs sanitization actions in CloudWatch

**Effort:** Small (1 session). Operator decision required on PII entity list.

---

### NM-004: Secrets Rotation ▸ `nice-to-have` ▸ Target: 95/100

**Current state:** `aws_secretsmanager_secret.observability_api_key` in the security module has no rotation configured. The Langfuse API key and Cognito M2M client secret are static.

**What to do:**
1. Create a rotation Lambda for the observability API key (calls Langfuse API to regenerate key)
2. Configure `aws_secretsmanager_secret_rotation` with a 90-day schedule
3. Evaluate whether Cognito M2M client secret needs rotation (typically managed by Cognito itself)

**Effort:** Medium (1-2 sessions)

---

### NM-005: Configure Online Evaluation Sampling ▸ `nice-to-have` ▸ Target: 95/100

**Current state:** All 9 domain blueprints have `evaluation.online: null`. The DynamoDB table, env var, and IAM are ready. Custom evaluators are defined but online sampling is not active.

**What to do:**
1. In each domain blueprint YAML, set `evaluation.online.sampling_rate: 5` and `evaluation.online.evaluators: ["Builtin.Correctness", "Builtin.ToolSelectionAccuracy"]`
2. Set `evaluation.online.auto_create_execution_role: true` (the IAM pre-auth is already in `modules/agents/iam.tf`)
3. Deploy agents — `EvaluationWiring` will call `create_online_config()` at startup
4. Monitor evaluation results in DynamoDB and via `get_online_results()`

**Effort:** Small (1 session). Domain blueprint changes only.

---

### NM-006: Adopt Utility Modules in Domain Repo ▸ `nice-to-have` ▸ Target: 95/100

**Current state:** `tcc-qitp` has ~870 lines of manual Lambda/alarm/schedule boilerplate that the 4 new utility modules can replace.

**What to do:**
1. Replace 7 manual Lambda definitions in `domain_lambdas.tf` with `module "lambda"` calls (~639 lines → ~70 lines)
2. Replace 22 alarm definitions in `domain_alerts.tf` with `module "lambda_alarms"` (~130 lines → ~15 lines)
3. Replace 7 EventBridge triads in `domain_events.tf` + `domain_compliance.tf` with `module "scheduled_lambda"` (~105 lines → ~35 lines)
4. Replace 1 S3 bucket definition in `domain_data.tf` with `module "s3_encrypted_bucket"` (~35 lines → ~8 lines)
5. Run `terraform plan` to verify identical resources, then `terraform apply`

**Effort:** Medium (1-2 sessions). Requires careful state migration (`terraform state mv`) for existing resources.

---

### NM-007: KI-001 Resolution (AWS Dependency) ▸ `blocked` ▸ Target: 95/100

**Current state:** `GATEWAY_DIRECT_MCP=true` bypasses Gateway for MCP tool calls. Cedar policies don't protect MCP invocations. Depends on AWS fixing Issue #809.

**What to do when AWS fixes #809:**
1. Set `gateway_direct_mcp = false` in domain tfvars
2. `terraform apply`
3. Verify `tools/call` works through Gateway for all MCP targets
4. Remove `agent_core.gateway.direct_mcp_client` module
5. Remove `GATEWAY_DIRECT_MCP` feature flag and related env vars from `modules/agents/runtime.tf`
6. Remove Cognito M2M client wiring (no longer needed when Gateway handles OAuth2)

**Effort:** Medium (1 session once AWS fixes the issue)

---

### NM-008: Extra Forbid on Remaining Sub-Models ▸ `nice-to-have`

**Current state:** `extra="forbid"` applied to 9 critical models. `ArtifactConfig`, `ThinkingConfig`, `ModelConfig`, `RuntimeConfig`, `GatewayConfig`, `MemoryConfig`, `ObservabilityConfig`, `PolicyConfig` still use default `extra="ignore"`.

**What to do:**
1. Add `extra="forbid"` to each remaining model's `ConfigDict`
2. Audit all blueprint YAMLs for unknown fields in those sub-blocks
3. Fix any YAML that has extra fields
4. Add tests in `test_schema_hardening.py`

**Effort:** Small (1 session)

---

## Backlog (unchanged)

| ID | Enhancement | Priority | Effort |
|----|-------------|----------|--------|
| ENH-004 | Memory strategy expansion (EPISODIC + USER_PREFERENCE) | nice-to-have | Low |
| ENH-005 | Server-side tool execution (Bedrock Responses API) | nice-to-have | Medium |
| ENH-006 | AG-UI protocol for dashboard streaming | nice-to-have | Medium |
| ENH-009 | A2A protocol (cross-runtime invocation) | someday | High |
| ENH-010 | Memory streaming to Kinesis | someday | Medium |
| ENH-020 | `build_entrypoint()` zero-boilerplate app | someday | Low |
