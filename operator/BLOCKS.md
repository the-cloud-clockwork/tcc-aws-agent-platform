# BLOCKS.md — Active Work Blocks

> **Purpose:** Major work blocks for the project. Always kept current.
> **Rule:** Update this file every session. Blocks move through: `design` → `ready` → `in-progress` → `done`

---

## Block 1: Schema & Blueprint Hardening ▸ `ready`

**Goal:** Fix silent schema failures so all 9 blueprints load correctly with strict validation.

- [ ] ENH-015: Add `extra="forbid"` to critical Pydantic models (AgentBlueprint, ToolDeclaration, GraphNodeConfig, CredentialConfig, StrategyEvaluationConfig) — Medium
- [ ] ENH-016: Six schema fixes — A2aToolConfig union, optional agent_ref for gate nodes, secret_arn on CredentialConfig, persistence on StrategyEvaluationConfig, gate fields on GraphNodeConfig, specialists on MultiAgentConfig — Medium

**Why first:** 3 blueprints currently fail silently. 12+ YAML fields are dropped. Everything downstream (runtime, evaluation, policy) depends on correct schema loading.

---

## Block 2: Security & Production Hardening ▸ `ready`

**Goal:** Close all security gaps before production. IAM tightening, secrets hygiene, PII filtering.

- [ ] ENH-019: Production IAM tightening — scope `bedrock:*`, move secrets from env vars to SSM fetch, `aws:SourceAccount` conditions, WAF on artifacts API + dashboard ALB (17 items) — Large
- [ ] ENH-008: PII filter callback on Langfuse traces — Low
- [ ] ENH-017: Expose `secrets_kms_key_arn` from platform outputs — Low
- [ ] SWEEP: Fix throttle burst/rate inversion in staging+prod tfvars
- [ ] SWEEP: Add JWT cross-variable validation
- [ ] SWEEP: Move KMS ARNs from SSM String to SecureString
- [ ] SWEEP: Address `mcp_m2m_client_id` sensitivity (mark sensitive in Terraform)

**Why second:** Items 13+14 from ENH-019 expose credentials via Runtime metadata API. PII flows unfiltered to external Langfuse. Must close before any production traffic.

---

## Block 3: Runtime & Observability ▸ `ready`

**Goal:** Add middleware, evaluation, and policy enforcement to agent runtimes.

- [ ] ENH-003: Middleware chain — ObservabilityMiddleware (correlation IDs, timing) + ErrorHandlingMiddleware (structured errors) on all runtimes — Low
- [ ] ENH-002: Online evaluation — 5% sampling with ToolSelectionAccuracy + Correctness evaluators, quality alerts — Low
- [ ] ENH-001: Cedar policies on Gateway — replace code-level tool access checks with infrastructure-level Cedar enforcement — Medium
- [ ] ENH-007: Bedrock Guardrails — content filtering + PII detection on agent I/O — Medium
- [ ] KI-001: Monitor AWS Gateway Issue #809 — workaround deployed (`GATEWAY_DIRECT_MCP=true`), remove when AWS fixes

**Why third:** These are operational maturity features. Schema must be correct first (Block 1), and secrets must be secured (Block 2) before adding runtime instrumentation.

---

## Block 4: Infrastructure Modules & Cleanup ▸ `ready`

**Goal:** Reusable Terraform modules to eliminate domain repo boilerplate. Cleanup remaining sweep items.

- [ ] ENH-011: `modules/lambda` — reusable Lambda module (archive, function, IAM, logs, VPC toggle). Saves ~56 lines per Lambda — Medium
- [ ] ENH-012: `modules/lambda_alarms` — alarm factory from Lambda map. Auto-derives duration threshold — Low
- [ ] ENH-013: `modules/scheduled_lambda` — EventBridge rule + target + permission triad — Low
- [ ] ENH-014: `modules/s3_encrypted_bucket` — versioning, KMS, public access block, SSM param — Low
- [ ] ENH-018: Add descriptions to 30+ platform outputs — Low
- [ ] SWEEP: Fix hardcoded `enable_artifacts_gateway_target`
- [ ] SWEEP: Add CloudFront output guards
- [ ] SWEEP: Add missing `sns_alert_email` in staging/prod tfvars

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
