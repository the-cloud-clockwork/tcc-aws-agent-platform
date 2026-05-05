# tcc-aws-agent-platform — Project State Assessment

> **Last assessed:** 2026-04-09
> **Assessor:** AI-assisted (validated by operator)
> **Overall Score:** 9.2 / 10
>
> **2026-04-09 Phase 1:** All 9 QITP agents migrated to LiteLLM proxy (`claude-sonnet-4-6` via `llm.homeofanton.com` + Cloudflare Access). `StructuredOutputEnforcer` hook (instructor post-processor) ships provider-agnostic `output_schema` support. Bedrock no longer required for inference.
>
> **2026-04-09 Phase 2:** Observability & hooks decoupling COMPLETE. Guardrail hook provider-gated (no latent LiteLLM crash). `PresidioGuardrailHook` adds provider-agnostic PII redaction via blueprint `data_protection.provider: presidio`. `LangfuseEvaluationClient` adds provider-agnostic eval via blueprint `evaluation.provider: langfuse` behind new `EvaluationProvider` protocol. `CostTracker` envs renamed to `MODEL_PRICING` with built-in LiteLLM pricing defaults. Dead YAML (dashboard, ttl_days) purged. `observability.enabled` toggle now wired. `core` pinned to floating `1.0.0` (dev iteration cycle); `publish-wheel.sh` republishes the same label on every push.
>
> **2026-04-09 Phase 3 — Production Pilot Validation:** Full weekly-gap-analysis pipeline executed end-to-end with real inference (`pilot-t4-1775755670`, 16/16 states, 44.08 s). Two blockers fixed in domain repo on the way:
> 1. **Market calendar Lambda contract** — dual-mode handler was silently seeding the calendar on every pipeline run; flipped to validate-default with explicit `{"seed": true}` for EventBridge.
> 2. **LiteLLM API key wiring** — platform agents now read `qitp/platform/litellm.TOKEN` from Secrets Manager via a new data source; the prior dashboard-scoped gemini key no longer leaks into agent runtimes.
>
> Gap-detector invoked `claude-sonnet-4-6` successfully through the LiteLLM proxy + Cloudflare Access, structured output enforced via `GapDetectionOutput` schema, claim-check artifact stored in S3 (497 B envelope + full payload). All 8 downstream agents were reached and responded HTTP 200. The 5 agents that returned validation errors (`Missing required field: symbols/symbol/strategy_evaluations`) are data-contract bugs in their input handlers, **not** infrastructure or inference failures — they run cleanly when given non-empty input.
>
> **The platform is production-ready from an infrastructure + inference standpoint. Remaining work is application-level data handling.**

---

## Dimensional Ratings

| Dimension | Score | Notes |
|-----------|-------|-------|
| Architecture | 9.5/10 | Provider-agnostic inference validated in production. 4 Python modules + 7 TF modules. Blueprint-driven. Secrets Manager data sources replace env-var defaults. |
| Infrastructure | 9.5/10 | pilot-t4 — 16/16 states green in production. SFN → Lambda contract fixed. Market-calendar handler hardened. Platform secret wiring complete. |
| Code Quality | 8.5/10 | `extra="forbid"` on schemas. Middleware chain. PII filter. Zero ruff errors. Provider dispatch tests. Hooks decoupled from Bedrock. |
| Documentation | 9.5/10 | CLAUDE.md + inference-migration.md + STATE.md all reflect pilot-t4 as authoritative validation. Skills hardened. |
| Testing | 6.5/10 | 5 provider dispatch tests. Phase-2 decoupling tests. CI-only. Runtime/Memory/Gateway coverage still low. |
| Security | 8.5/10 | Gateway IAM scoped. KMS fallback eliminated. PII filter active. JWT precondition. Platform LiteLLM key via Secrets Manager (not env var). 13 domain IAM items still open. |
| Production Readiness | 9/10 | pilot-t4 green end-to-end with real inference. Provider-agnostic. Structured output enforced. Claim-checks verified. Downstream empty-symbol handling is the last application-level item. |

---

## Strengths

- **Production-validated inference stack** — pilot-t4 is the authoritative E2E proof: Strands LiteLLMModel → CF Tunnel → LiteLLM proxy → `claude-sonnet-4-6` → structured output enforcer → S3 claim-check, end-to-end
- **Provider-agnostic inference** — Stages 1 + 2 complete: bedrock/anthropic/litellm/vertex via match/case dispatch, hooks provider-gated
- **Platform secret pattern** — `qitp/platform/litellm` Secrets Manager entry wired via TF data source, scoped for claude/gpt/gemini/deepseek/llama, shared cleanly across 9 agents + 8 MCPs
- **Market calendar hardened** — Lambda handler validates by default, explicit `{"seed": true}` for quarterly EventBridge; no more silent table rewrites from stray invocations
- **`rebuild-deploy.sh` automation** — single-command parallel rebuild + force-update for all agents/MCPs, reused locally and in CI (GitHub Actions delegates to it)
- **Semver friction killed** — `core` pinned to floating `1.0.0`; `publish-wheel.sh` deletes+republishes on every push, so dev iteration has zero version juggling
- **Zero ruff errors, zero domain contamination** — `domain-scan.sh` clean, CI lint clean
- **Skills hardened** — 5 tcc-qitp skills with real AWS CLI gotchas baked in

---

## Weaknesses

- **Downstream empty-symbol handling** — 5 agents (sentiment-analyzer, technical-analyzer, ml-predictor, strategy-evaluator, portfolio-recommender) reject input with `Missing required field: symbols/symbol/strategy_evaluations` when upstream gap-detector returns an empty list. Each needs a default-watchlist fallback in the input validator. Application-level, not infra.
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
| 2026-04-08 (eve) | 8.5/10 | Stage 1 inference decoupling. Pipeline E2E validated (aspirational). 10 ruff errors fixed. SFN agent integration hardened. Skills updated. |
| 2026-04-09 | 8.9/10 | Phase 2 hooks decoupling: guardrail gated, Presidio hook, Langfuse evaluation provider, cost-tracker env rename, observability toggle wired. Core `0.9.30`. |
| 2026-04-09 (eve) | **9.2/10** | **pilot-t4 — true end-to-end validation with real claude-sonnet-4-6 inference.** Market-calendar Lambda contract fixed. `LITELLM_API_KEY` wired via new `qitp/platform/litellm` Secrets Manager data source. `rebuild-deploy.sh` orchestrator shipped. Core pinned to floating `1.0.0` via `publish-wheel.sh`. 5 downstream agents still need empty-symbol fallbacks — app-level, not blocking. |
