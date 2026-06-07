# tcc-aws-agent-platform — Project State Assessment

> **Last assessed:** 2026-06-07 (updated to reflect post-Block-5 bug fix commits)
> **Assessor:** AI-assisted (validated by operator)
> **Overall Score:** 9.2 / 10
>
> **Phase 1 (inference decoupling):** Provider-agnostic model factory ships. Providers: bedrock (default), anthropic, litellm, vertex — dispatched by `_build_model_config()` match/case. Bedrock no longer required for inference.
>
> **Phase 2 (observability decoupling):** COMPLETE. Guardrail hook provider-gated (no latent non-Bedrock crash). `PresidioGuardrailHook` adds provider-agnostic PII redaction via blueprint `data_protection.provider: presidio`. `LangfuseEvaluationClient` adds provider-agnostic eval via blueprint `evaluation.provider: langfuse`. `CostTracker` envs renamed to `MODEL_PRICING` with built-in pricing defaults. `observability.enabled` toggle wired. Dead YAML purged.
>
> **Phase 3 — Production Pilot Validation:** Full pipeline executed end-to-end with real inference (16/16 states, 44.08 s). Real `claude-sonnet-4-6` invoked via LiteLLM proxy, structured output enforced, claim-check artifact persisted to S3. All downstream agents reachable. Five agents returned input-validation errors on empty symbols — data-contract bugs in their handlers, not platform failures.
>
> **Post-Phase-3 bug fixes (commits on `dev`):**
> - `8c784df` — `StructuredOutputEnforcer` (instructor-based fallback) deleted from the loader wiring path. Strands native `structured_output_model` used for all providers; upstream Strands bugs #743/#1005/#891 resolved in strands-agents 1.41.0.
> - `4c57d6c` — Graph coordinator synthesis turn now fires correctly after graph nodes complete (Bug F + Bug A).
> - `8f8b367` — Agent reasoning (full conversation JSON) captured in Langfuse trace input/output (Bug H). Before this fix, trace input/output were null.
> - `319ba11` — platform-deps Lambda layer built hermetically in Terraform; CI no longer runs local pip install.
>
> **The platform is production-ready from an infrastructure + inference standpoint. Remaining work is application-level data handling and test coverage.**

---

## Dimensional Ratings

| Dimension | Score | Notes |
|-----------|-------|-------|
| Architecture | 9.5/10 | Provider-agnostic inference validated in production. 4 Python modules + 7 TF modules. Blueprint-driven. Secrets Manager data sources replace env-var defaults. |
| Infrastructure | 9.5/10 | pilot-t4 — 16/16 states green in production. SFN → Lambda contract fixed. Market-calendar handler hardened. Platform secret wiring complete. |
| Code Quality | 8.5/10 | `extra="forbid"` on schemas. Middleware chain. PII filter. Zero ruff errors. Provider dispatch tests. Hooks decoupled from Bedrock. StructuredOutputEnforcer removed — Strands native structured output for all providers. |
| Documentation | 9.0/10 | CLAUDE.md + inference-migration.md + STATE.md updated to reflect post-Block-5 bug fixes. Public docs audit underway. |
| Testing | 6.5/10 | 5 provider dispatch tests. Phase-2 decoupling tests. CI-only. Runtime/Memory/Gateway coverage still low. |
| Security | 8.5/10 | Gateway IAM scoped. KMS fallback eliminated. PII filter active. JWT precondition. Platform LiteLLM key via Secrets Manager (not env var). 13 domain IAM items still open. |
| Production Readiness | 9/10 | pilot-t4 green end-to-end with real inference. Provider-agnostic. Structured output enforced. Claim-checks verified. Downstream empty-symbol handling is the last application-level item. |

---

## Strengths

- **Production-validated inference stack** — Strands LiteLLMModel → CF Tunnel → LiteLLM proxy → `claude-sonnet-4-6` → Strands native structured output → S3 claim-check, end-to-end. StructuredOutputEnforcer (instructor-based workaround) removed as of `8c784df`; Strands native forced-tool used for all providers.
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
| 2026-04-09 (eve) | **9.2/10** | **Pilot — true end-to-end validation with real claude-sonnet-4-6 inference.** Market-calendar Lambda contract fixed. `LITELLM_API_KEY` wired via Secrets Manager data source. `rebuild-deploy.sh` orchestrator shipped. Core pinned to floating `1.0.0` via `publish-wheel.sh`. 5 downstream agents still need empty-symbol fallbacks — app-level, not blocking. |
| 2026-06-07 | **9.2/10** | Bug fixes: `8c784df` StructuredOutputEnforcer removed (Strands native for all providers); `4c57d6c` graph coordinator synthesis turn fix; `8f8b367` Langfuse reasoning capture; `319ba11` hermetic Lambda layer. Score unchanged — fixes close known gaps, no new regressions. |
