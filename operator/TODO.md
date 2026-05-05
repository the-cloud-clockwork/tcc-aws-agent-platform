# TODO.md — Minor Items & Pending Decisions

> **Purpose:** Small items, notes, and things to not forget. Not major blocks — those go in BLOCKS.md.

---

## Completed Execution (2026-04-08 and 2026-04-09)

All 5 blocks executed and validated:

| Block | Theme | Items | Status | DoD evidence |
|-------|-------|-------|--------|--------------|
| 1 | Schema & Blueprint Hardening | 6 | ✅ Done | Validated via Block 2 apply (2026-04-08) |
| 2 | Security & Production Hardening | 8 | ✅ Done | `terraform apply` in tcc-qitp: 0/36/0 (2026-04-08) |
| 3 | Runtime & Observability | 5 | ✅ Done | `terraform apply` in tcc-qitp: 3/45/0 (2026-04-08) |
| 4 | Infrastructure Modules & Cleanup | 7 | ✅ Done | `terraform apply` in tcc-qitp: 0/36/0 (2026-04-08) |
| **5** | **Inference Migration + Production Pilot** | **20** | ✅ **Done** | **`pilot-t4-1775755670` — 16/16 states, 44.08 s with real claude-sonnet-4-6 inference (2026-04-09)** |

**Total completed:** 46 items (14 enhancements + 8 sweep + 4 extras + 20 inference/pilot)

**Block 5 highlights:**
- Provider-agnostic inference validated in production (bedrock/anthropic/litellm/vertex dispatch)
- Observability hooks decoupled from Bedrock (guardrail gated, Presidio, Langfuse eval)
- Market-calendar Lambda dual-mode ambiguity fixed (validate-default)
- Platform LiteLLM key via Secrets Manager data source (not env var)
- `rebuild-deploy.sh` parallel orchestrator + semver kill via `publish-wheel.sh`
- `core` pinned to floating `1.0.0`, republished on every push

---

## Remaining Work (not blocked, not urgent)

### Domain Repo IAM Hardening (out of scope for platform)

ENH-019 items #1, #2, #5-14, #15-17 live in `modules/agents/` or `tcc-qitp` domain infra:
- [ ] Scope `bedrock:*` on agent runtimes to `bedrock:InvokeModel` on specific model ARNs
- [ ] Scope `bedrock-agentcore:*` on agent runtimes to enumerated actions
- [ ] Move `COGNITO_MCP_CLIENT_SECRET` + `LANGFUSE_SECRET_KEY` from env vars to runtime SSM fetch
- [ ] Add `aws:SourceAccount` condition to EventBridge trust
- [ ] Scope SFN `logs:*` to specific log group ARNs
- [ ] Remove `localhost:3000` from Cognito callback URLs in production
- [ ] Implement Secrets Manager rotation for observability API key

### Backlog Enhancements (6 items)

| ID | Enhancement | Priority | Effort |
|----|-------------|----------|--------|
| ENH-004 | Memory strategy expansion (EPISODIC + USER_PREFERENCE) | nice-to-have | Low |
| ENH-005 | Server-side tool execution (Bedrock Responses API) | nice-to-have | Medium |
| ENH-006 | AG-UI protocol for dashboard streaming | nice-to-have | Medium |
| ENH-009 | A2A protocol (cross-runtime invocation) | someday | High |
| ENH-010 | Memory streaming to Kinesis | someday | Medium |
| ENH-020 | `build_entrypoint()` zero-boilerplate app | someday | Low |

### Platform Hardening Follow-ups

- [ ] Add `extra="forbid"` to remaining sub-models: `ArtifactConfig`, `ThinkingConfig`, `ModelConfig`, `RuntimeConfig`, `GatewayConfig`, `MemoryConfig`, `ObservabilityConfig`
- [ ] Adopt `modules/lambda` in `tcc-qitp` to replace manual Lambda boilerplate (~639 lines)
- [ ] Adopt `modules/lambda_alarms` in `tcc-qitp` to replace manual alarm definitions (~130 lines)
- [ ] Adopt `modules/scheduled_lambda` in `tcc-qitp` to replace 7 event triads (~105 lines)
- [ ] Enable `guardrail_enabled = true` in staging/production when ready
- [ ] Configure online evaluation (`evaluation.online`) in domain blueprints when ready
- [ ] Check AWS Issue #809 status — remove `GATEWAY_DIRECT_MCP` workaround when fixed

---

## Application-level Follow-ups (Block 6 candidate)

Downstream agents need empty-input fallbacks. When gap-detector returns zero gaps on a quiet market day, the following five agents fail their own input validation:

| Agent | Error | Fix location |
|---|---|---|
| sentiment-analyzer | `Missing required field: symbols` | input validator — fall back to `watchlist_id=default` |
| technical-analyzer | `Missing required field: symbols` | same |
| ml-predictor | `Missing required field: symbols` | same |
| strategy-evaluator | `Missing required field: symbol` | skip scoring when empty |
| portfolio-recommender | `Missing required field: strategy_evaluations` | emit empty recommendations payload |

These are NOT infra or inference bugs — the agents never reach the LLM. Each fix is a per-agent handler change in `tcc-qitp/agents/src/qitp_agents/<agent>/handler.py`. Ship via `rebuild-deploy.sh --agents <name>`.

## Notes

- 2026-03-31: Project initialized with operator pattern
- 2026-04-08: Organized 20 enhancements + 8 sweep remainders into 4 blocks
- 2026-04-08: All 4 blocks executed and validated. 14/20 enhancements done, 6 deferred to backlog.
- 2026-04-09: **Block 5 — Production Pilot Validation.** True E2E with real claude-sonnet-4-6 inference. pilot-t4-1775755670. Platform is production-ready from an infrastructure standpoint. Merging `phase-2-hooks-decoupling` → `main` in both repos.
