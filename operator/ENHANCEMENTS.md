# ENHANCEMENTS.md — Feature Requests & Improvements

> **Purpose:** Track desired enhancements, feature ideas, and improvement proposals. Unlike BLOCKS.md (active work) or BUGS.md (defects), these are forward-looking ideas that may or may not be scheduled.
> **Priority:** `must-have` | `nice-to-have` | `someday`
> **Source:** Extracted from operator/references/PLATFORM-REFERENCE.md (9-agent deep analysis, 2026-03-30)

---

## ENH-001: AgentCore Policy GA — Cedar on Gateway ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Policy / Gateway / Infrastructure
**Description:** Replace code-level tool access checks with Cedar policies enforced at the Gateway layer. Infrastructure-level guarantees: only execution-agent calls ibkr-mcp, only live mode allows orders, risk engine PASS required. Leverage parameter-level Cedar rules (e.g., `permit when position_size <= max`).
**Motivation:** Compliance-critical. Moves access control from application logic to infrastructure. Auditable, declarative, and impossible to bypass from agent code.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §Top 10 Opportunities #1, §Amazon Samples — Cedar per-tool policies

---

## ENH-002: Online Evaluation (Continuous Monitoring) ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Evaluation / Observability
**Description:** Enable 5% production sampling with ToolSelectionAccuracy + Correctness evaluators. Configure quality alerts on metric degradation. Use the 13 built-in evaluators (currently UNUSED).
**Motivation:** Catch agent regressions before they affect operations. Currently only execution-agent has custom evaluators; 8 agents have zero evaluation coverage.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Capability Matrix (Evaluation: UNUSED), §Top 10 #2

---

## ENH-003: Middleware Chain (Correlation IDs + Structured Errors) ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Runtime
**Description:** Add ObservabilityMiddleware (correlation IDs, timing) + ErrorHandlingMiddleware (structured errors) to all agent runtimes. Starlette middlewares on `BedrockAgentCoreApp`. Zero business logic changes required.
**Motivation:** Zero-code observability improvement. Currently no correlation IDs or request timing middleware. Amazon samples demonstrate the pattern.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Amazon Samples — Middleware Chain, §Capability Matrix (Middleware: UNUSED)

---

## ENH-004: Memory Strategy Expansion (EPISODIC + USER_PREFERENCE) ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Memory
**Description:** Add EPISODIC strategy for pattern tracking over time. Expand USER_PREFERENCE usage for per-user configuration (risk tolerance, preferred sectors, position sizing). Note: EPISODIC requires `customMemoryStrategy` with `episodicOverride` — not a simple type string.
**Motivation:** Currently only portfolio-recommender and watchlist-screener use USER_PREFERENCE. No agents use EPISODIC. Both are high-value for personalization and temporal pattern recognition.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Memory System, §Top 10 #4

---

## ENH-005: Server-Side Tool Execution (Bedrock Responses API) ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Runtime / Gateway
**Description:** Bedrock Responses API + Gateway eliminates client-side tool orchestration for simple agents. Analysis agents become simpler — Bedrock handles tool discovery/selection/execution via Gateway.
**Motivation:** Reduces agent complexity for simple tool-calling patterns. Available since February 2026.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §AWS Feature Releases, §Top 10 #5

---

## ENH-006: AG-UI Protocol for Dashboard Streaming ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Runtime / Dashboard
**Description:** Standardized streaming of agent reasoning + tool results to the Next.js dashboard via SSE. Replaces custom polling. Real-time thinking display.
**Motivation:** New March 2026 AWS feature. Provides standardized protocol for frontend streaming instead of custom implementations.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §AWS Feature Releases, §Top 10 #6

---

## ENH-007: Bedrock Guardrails for Agent I/O ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Runtime / Policy
**Description:** Content filtering + PII detection on agent inputs/outputs. Automated Reasoning check validates recommendations against logical rules. Currently only execution-agent declares Data Protection (PARTIAL).
**Motivation:** Compliance-critical content filtering. Amazon samples demonstrate the pattern for finance use cases.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §Capability Matrix (Data Protection: PARTIAL), §Amazon Samples — Bedrock Guardrails

---

## ENH-008: PII Filter on Langfuse Traces ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Observability
**Description:** Pass `pii_filter` callback to LangfuseHook to sanitize account numbers, personal details, API keys before sending to external Langfuse service. Currently UNUSED.
**Motivation:** Secrets and PII currently flow to external Langfuse unfiltered. Low effort, high security value.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Capability Matrix (PII filter: UNUSED), §Top 10 #8

---

## ENH-009: A2A Protocol (Cross-Runtime Invocation) ▸ `someday` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** A2A / Runtime
**Description:** Enable direct cross-runtime invocation via A2A protocol. Currently A2AClient is UNUSED, A2AServerWrapper is PARTIAL (execution-agent has port 9000 but no A2A config). Adopt the A2A coordinator pattern from Amazon samples.
**Motivation:** Lower latency for sub-workflows. Currently all coordination goes through Step Functions.
**Effort estimate:** High
**Related:** operator/references/PLATFORM-REFERENCE.md §Capability Matrix (A2A: UNUSED/PARTIAL), §Top 10 #9

---

## ENH-010: Memory Streaming to Kinesis ▸ `someday` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Memory / Events
**Description:** Event-driven reactions to agent memory updates via Kinesis streaming. New March 2026 feature. Trigger downstream actions (rebalancing, dashboard refresh) when agent memory changes.
**Motivation:** Enables reactive architectures. Currently memory updates are fire-and-forget.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §AWS Feature Releases, §Capability Matrix (Memory streaming: UNUSED)

---

## ENH-011: Platform Terraform Module — `modules/lambda` ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Infrastructure / Terraform
**Description:** Reusable Lambda module that generates: archive_file, lambda_function, iam_role, 2× policy_attachment, iam_role_policy (optional), log_group. Accepts `vpc_enabled` bool to auto-select IAM policy variant. Eliminates ~56 lines of boilerplate per Lambda (~306 lines total across 6 domain Lambdas).
**Motivation:** Domain repos currently copy-paste identical IAM boilerplate 7 times (500+ lines). Highest savings; grows with every new Lambda.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §Missing Platform Abstractions — modules/lambda

---

## ENH-012: Platform Terraform Module — `modules/lambda_alarms` ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Infrastructure / Terraform
**Description:** Alarm factory: accepts Lambda map → generates Error + Duration (p99 at 75% timeout) alarms. Auto-derives duration threshold from timeout. Eliminates ~154 lines of identical alarm patterns.
**Motivation:** Pure repetition elimination. Auto-derived threshold prevents misconfiguration bugs.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Missing Platform Abstractions — modules/lambda_alarms

---

## ENH-013: Platform Terraform Module — `modules/scheduled_lambda` ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Infrastructure / Terraform
**Description:** Encapsulates the EventBridge rule + target + permission triad. Appears 7 times in domain infra. Eliminates ~112 lines.
**Motivation:** Most error-prone pattern to wire manually (3 resources in lockstep).
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Missing Platform Abstractions — modules/scheduled_lambda

---

## ENH-014: Platform Terraform Module — `modules/s3_encrypted_bucket` ▸ `someday` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Infrastructure / Terraform
**Description:** Generates versioning, KMS encryption config, public access block, SSM parameter for each bucket. ~47 lines per bucket, multiplicative savings.
**Motivation:** Ensures consistent encryption and access controls across all future S3 buckets.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Missing Platform Abstractions — modules/s3_encrypted_bucket

---

## ENH-015: Blueprint Schema Hardening (`extra="forbid"`) ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Schemas / Blueprints
**Description:** Add `extra="forbid"` to critical Pydantic models (AgentBlueprint, ToolDeclaration, GraphNodeConfig, CredentialConfig, StrategyEvaluationConfig). Currently all models use default `extra="ignore"` — unknown fields are silently dropped. 12+ fields across 9 blueprints are silently lost.
**Motivation:** 3 blueprints currently fail to load silently. 12+ YAML fields are silently dropped. Silent failures mask configuration bugs that surface only at runtime.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §Schema Mismatch Audit, §Blueprint Schema Fixes Needed

---

## ENH-016: Schema Fixes — A2A, Gate Nodes, Credentials ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Schemas
**Description:** Six schema fixes needed: (1) Add `A2aToolConfig` to `ToolDeclaration` union, (2) Make `GraphNodeConfig.agent_ref` optional for gate nodes, (3) Add `secret_arn` to `CredentialConfig`, (4) Add `persistence` to `StrategyEvaluationConfig`, (5) Add gate fields (`type`, `trip_condition`, `fallback`) to `GraphNodeConfig`, (6) Add `specialists` to `MultiAgentConfig`.
**Motivation:** 3 blueprints raise ValidationError at load time (execution-agent, portfolio-recommender, strategy-evaluator). Currently masked by GenericHandler fallback.
**Effort estimate:** Medium
**Related:** operator/references/PLATFORM-REFERENCE.md §Schema Mismatch Audit — Complete Findings

---

## ENH-017: Expose `secrets_kms_key_arn` from Platform Outputs ▸ `nice-to-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Infrastructure / Security
**Description:** Platform doesn't expose `secrets_kms_key_arn` output. Domain manually creates Secrets Manager resources without platform's KMS key.
**Motivation:** Enables domain repos to use consistent envelope encryption for secrets.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Infrastructure Improvement Roadmap P0

---

## ENH-018: Add Descriptions to 30+ Platform Outputs ▸ `someday` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Infrastructure / Terraform
**Description:** `modules/platform/outputs.tf:110-254` has 30+ outputs without description fields. Domain consumers can't understand the API surface.
**Motivation:** Self-documenting infrastructure. Terraform docs and IDE autocomplete rely on descriptions.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Terraform Coherence Analysis — Critical Issue #4

---

## ENH-019: Production IAM Tightening (17 Permissive Items) ▸ `must-have` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Security / IAM
**Description:** 17 permissive IAM items documented for dev phase. Top priorities: (1) Scope `bedrock:*` on `*` to `bedrock:InvokeModel` on specific model ARNs, (2) Move M2M client secret and Langfuse key from env vars to runtime SSM fetch, (3) Add `aws:SourceAccount` condition to EventBridge trust, (4) Enable WAF on artifacts API + dashboard ALB.
**Motivation:** Items 13+14 (secrets as env vars in 17 Runtimes) expose credentials via Runtime metadata API. Highest priority before production.
**Effort estimate:** Large
**Related:** operator/references/PLATFORM-REFERENCE.md §IAM & Security Posture, INFRA.md Block 2

---

## ENH-020: `build_entrypoint()` Zero-Boilerplate App ▸ `someday` ▸ `proposed`

**Proposed:** 2026-03-30
**Component:** Blueprints / Runtime
**Description:** `build_entrypoint()` is available in the SDK but UNUSED. Domain uses manual `app.py` wiring. Adopting it would reduce per-agent boilerplate to a single function call.
**Motivation:** Consistency and reduced boilerplate across all agent runtimes.
**Effort estimate:** Low
**Related:** operator/references/PLATFORM-REFERENCE.md §Capability Matrix (build_entrypoint: UNUSED)
