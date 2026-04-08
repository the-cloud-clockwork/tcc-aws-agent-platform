# tccw-aws-agent-platform — Project State Assessment

> **Last assessed:** 2026-04-08 (evening)
> **Assessor:** AI-assisted (validated by operator)
> **Overall Score:** 8.5 / 10

---

## Dimensional Ratings

| Dimension | Score | Notes |
|-----------|-------|-------|
| Architecture | 9/10 | Provider-agnostic inference (Stage 1). 4 Python modules + 7 TF modules. Blueprint-driven, configuration-first. |
| Infrastructure | 8.5/10 | SFN agent integration fixed (IAM wildcard, ResultSelector). Pipeline E2E validated 16/16 states. |
| Code Quality | 8.5/10 | `extra="forbid"` on schemas. Middleware chain. PII filter. 10 ruff errors fixed (0 remaining). Provider dispatch tests added. |
| Documentation | 9/10 | CLAUDE.md updated with inference providers + pipeline architecture. Skills hardened. inference-migration.md created. |
| Testing | 6.5/10 | 5 provider dispatch tests added. Schema hardening tests. CI-only. Runtime/Memory/Gateway coverage still low. |
| Security | 8/10 | Gateway IAM scoped. KMS fallback eliminated. PII filter active. JWT precondition. 13 domain IAM items remain. |
| Production Readiness | 7.5/10 | Full pipeline validated E2E. Provider-agnostic ready. Guardrail disabled. KI-001 workaround active. |

---

## Strengths

- **Provider-agnostic inference** — Stage 1 complete: bedrock/anthropic/litellm/vertex via match/case dispatch
- **Full E2E pipeline validated** — 16/16 states green, 6 agents + 3 Lambdas + 4 choice gates in 39s
- **SFN agent integration hardened** — IAM wildcard for sub-resources, ResultSelector parses agent JSON responses
- **Zero ruff errors** — 10 pre-existing lint issues fixed (was blocking CI)
- **Zero domain contamination** — all platform changes are generic
- **Skills hardened** — 5 tccw-qitp skills corrected with real AWS CLI gotchas

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
| 2026-04-08 (eve) | 8.5/10 | Stage 1 inference decoupling. Pipeline E2E validated. 10 ruff errors fixed. SFN agent integration hardened. Skills updated. |
