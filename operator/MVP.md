# tccw-aws-agent-platform — MVP Status & Backlog

> **Last updated:** 2026-04-08
> **Owner:** Nestor Colt
> **Phase:** Enhancement blocks complete. Production hardening in progress.

---

## What's Running

| Component | Count/Status | Notes |
|-----------|-------------|-------|
| SDK subsystems | 11 complete | runtime, gateway, identity, memory, tools, observability, evaluation, policy, blueprints, a2a, schemas |
| TF platform sub-modules | 6 | security, data, observability, api, agentcore, prompt_registry |
| TF utility modules | 4 (new) | lambda, lambda_alarms, scheduled_lambda, s3_encrypted_bucket |
| TF agents module | 1 | Blueprint-driven for_each over YAML |
| TF workflows module | 1 | SFN integration |
| Domain agents (tccw-qitp) | 9 runtimes | All deployed to AgentCore |
| Domain MCPs (tccw-qitp) | 8 runtimes | All deployed to AgentCore |
| Known issues | 2 open | KI-001 (Gateway #809), KI-002 (Cedar SDK-managed) |

---

## Completed Blocks

| Block | What | When |
|-------|------|------|
| Network removal | Externalized VPC/subnets to input variables | 2026-04-02 |
| Block 1 | Schema & Blueprint Hardening (ENH-015, 016) | 2026-04-08 |
| Block 2 | Security & Production Hardening (ENH-008, 017, 019 partial) | 2026-04-08 |
| Block 3 | Runtime & Observability (ENH-001, 002, 003, 007) | 2026-04-08 |
| Block 4 | Infrastructure Modules & Cleanup (ENH-011-014, 018) | 2026-04-08 |

---

## Backlog

| Priority | Item | Depends On | Effort |
|----------|------|-----------|--------|
| P1 | Domain IAM hardening (13 ENH-019 items) | Domain repo work | L |
| P1 | Enable guardrail in staging/prod | Operator decision | S |
| P1 | Configure online evaluation sampling | Domain blueprint updates | S |
| P2 | Adopt `modules/lambda` in tccw-qitp | None | M |
| P2 | Adopt `modules/lambda_alarms` in tccw-qitp | None | S |
| P2 | Adopt `modules/scheduled_lambda` in tccw-qitp | None | S |
| P2 | Add `extra="forbid"` to remaining sub-models | None | S |
| P2 | ENH-004: Memory strategy expansion | None | S |
| P2 | ENH-020: `build_entrypoint()` adoption | None | S |
| P3 | ENH-005: Server-side tool execution | Bedrock Responses API GA | M |
| P3 | ENH-006: AG-UI dashboard streaming | Dashboard work | M |
| P3 | ENH-009: A2A cross-runtime invocation | AWS A2A GA | H |
| P3 | ENH-010: Memory streaming to Kinesis | AWS feature | M |

---

## Release Criteria

- [x] SDK: All 11 subsystems complete (POSTMORTEM.md verified)
- [x] Schemas: `extra="forbid"` on critical models, 6 schema fixes
- [x] Security: Gateway IAM scoped, KMS fallback removed, PII filter wired
- [x] Middleware: Correlation IDs + structured errors on all runtimes
- [x] Evaluation: DynamoDB table + env var + IAM ready
- [x] Guardrails: Terraform resource created (gated), SDK hook wired
- [x] Policies: SDK runtime path complete, Gateway IAM authorized
- [x] Infrastructure: 4 reusable modules, all outputs described, sweep items fixed
- [x] DoD: `terraform apply` passes in domain consumer with zero errors
- [ ] Domain IAM: 13 permissive items hardened (P1 — domain repo)
- [ ] Guardrail enabled in production (P1 — operator decision)
- [ ] Online evaluation configured (P1 — domain blueprint update)
- [ ] Test coverage: Runtime, Memory, Gateway above 50% (P2)

---

## Audit Findings

| ID | Finding | Status |
|----|---------|--------|
| F1 | 12+ YAML fields silently dropped (extra="ignore") | ✅ CLOSED — extra="forbid" on 9 models |
| F2 | `bedrock-agentcore:*` wildcard on gateway IAM | ✅ CLOSED — 16 enumerated actions |
| F3 | KMS Resource:"*" fallback in gateway policy | ✅ CLOSED — validation requires ARN |
| F4 | PII flows unfiltered to Langfuse | ✅ CLOSED — pii_filter wired |
| F5 | No correlation IDs in HTTP pipeline | ✅ CLOSED — CorrelationIdMiddleware |
| F6 | No structured error responses | ✅ CLOSED — StructuredErrorMiddleware |
| F7 | 32 platform outputs without descriptions | ✅ CLOSED — all 48 described |
| F8 | Throttle burst = rate in staging/prod | ✅ CLOSED — burst 1000 > rate 500 |
| F9 | JWT validation was non-fatal warning | ✅ CLOSED — precondition on gateway |
| F10 | 13 domain IAM permissive items | OPEN — domain repo scope |
| F11 | KI-001 Gateway MCP workaround active | OPEN — AWS dependency |
| F12 | Cedar policies SDK-managed (no IaC drift detection) | ACCEPTED — KI-002 |
