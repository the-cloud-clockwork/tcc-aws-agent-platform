# tccw-aws-agent-platform — Project State Assessment

> **Last assessed:** 2026-04-08
> **Assessor:** AI-assisted (validated by operator)
> **Overall Score:** 8 / 10

---

## Dimensional Ratings

| Dimension | Score | Notes |
|-----------|-------|-------|
| Architecture | 9/10 | Clean separation: 4 Python modules + 6 TF sub-modules + 4 utility modules. Blueprint-driven, configuration-first. |
| Infrastructure | 8/10 | Platform module wiring complete. 4 reusable modules created. Guardrail + evaluation table provisioned. 13 ENH-019 domain items remain. |
| Code Quality | 8/10 | `extra="forbid"` on all critical schemas. Middleware chain. PII filter wired. 9 pre-existing ruff errors in untouched code. |
| Documentation | 9/10 | All 48 platform outputs described. CLAUDE.md, operator docs, KNOWN-ISSUES all current. |
| Testing | 6/10 | `test_schema_hardening.py` added. Runtime 0%, Memory 0%, Gateway 5% coverage unchanged. CI-only — no local validation. |
| Security | 8/10 | Gateway IAM scoped to 16 actions. KMS fallback eliminated. PII filter active. JWT precondition. 13 domain IAM items remain. |
| Production Readiness | 7/10 | Guardrail created but disabled in dev. Online eval tables ready but not configured. KI-001 workaround active. Domain IAM not hardened. |

---

## Strengths

- **All 4 execution blocks completed in one session** — 26 items across schema, security, runtime, and infrastructure
- **DoD validated end-to-end** — every block passed `terraform apply` in the domain consumer
- **Zero domain contamination** — all changes are platform-generic
- **Configuration-driven guardrails** — gated by variables, not hardcoded
- **Reusable modules ready** — `modules/lambda`, `lambda_alarms`, `scheduled_lambda`, `s3_encrypted_bucket` available for domain adoption

---

## Weaknesses

- **Test coverage gaps** — Runtime, Memory, Gateway subsystems have near-zero test coverage
- **13 domain IAM items unaddressed** — `bedrock:*` on agent runtimes, secrets in env vars, EventBridge trust conditions
- **KI-001 workaround** — `GATEWAY_DIRECT_MCP=true` bypasses Gateway for MCP calls. Depends on AWS fixing Issue #809
- **KI-002 policy drift** — Cedar policies are SDK-managed, not IaC. No Terraform drift detection
- **Guardrail disabled** — `guardrail_enabled = false` in all envs. Needs operator decision to activate
- **Online evaluation not configured** — `evaluation.online: null` in all 9 blueprints. Table is ready but no sampling configured

---

## Assessment History

| Date | Score | Key Changes |
|------|-------|-------------|
| 2026-03-31 | — | Initial assessment (template) |
| 2026-04-08 | 8/10 | All 4 blocks complete: schema hardening, security, runtime/observability, infra modules. 14/20 enhancements done. |
