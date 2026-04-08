# BLOCKS.md — Active Work Blocks

> **Purpose:** Major work blocks for the project. Always kept current.
> **Rule:** Update this file every session. Blocks move through: `design` → `ready` → `in-progress` → `done`
> **Definition of Done:** `terraform plan` + `terraform apply` in `tccw-qitp` (domain consumer) with zero errors. No exceptions.

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
**DoD:** ✅ `terraform apply` in `tccw-qitp`: Apply complete! 0 added, 36 changed, 0 destroyed. Zero errors.

---

## Block 3: Runtime & Observability ▸ `done`

**Goal:** Add middleware, evaluation, and policy enforcement to agent runtimes.

- [x] ENH-003: Middleware chain — `CorrelationIdMiddleware` + `StructuredErrorMiddleware` as default middleware on `AgentCoreApp`. Correlation ID wired into StructuredLogger and LangfuseHook.
- [x] ENH-002: Online evaluation — evaluation DynamoDB table added to data module, `EVALUATION_TABLE` env var injected, IAM scoped to table + indexes.
- [x] ENH-001: Cedar policies — SDK runtime path confirmed complete (`PolicyWiring`). Documented as KI-002 (SDK-managed, not IaC).
- [x] ENH-007: Bedrock Guardrails — `GuardrailHook` for I/O content filtering, `aws_bedrock_guardrail` Terraform resource (gated by `guardrail_enabled`), env var threading through platform → agents.
- [x] KI-001: Workaround active. No changes needed.

**Completed:** 2026-04-08
**DoD:** ✅ `terraform apply` in `tccw-qitp`: 3 added, 45 changed, 0 destroyed. Zero errors.

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
**DoD:** ✅ `terraform apply` in `tccw-qitp`: 0 added, 36 changed, 0 destroyed. Zero errors.

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
