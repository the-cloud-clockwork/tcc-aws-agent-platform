# TODO.md — Minor Items & Pending Decisions

> **Purpose:** Small items, notes, and things to not forget. Not major blocks — those go in BLOCKS.md.

---

## Completed Execution (2026-04-08)

All 4 blocks executed and validated via `terraform apply` in `tccw-qitp`:

| Block | Theme | Items | Status |
|-------|-------|-------|--------|
| 1 | Schema & Blueprint Hardening | 6 | ✅ Done |
| 2 | Security & Production Hardening | 8 | ✅ Done |
| 3 | Runtime & Observability | 5 | ✅ Done |
| 4 | Infrastructure Modules & Cleanup | 7 | ✅ Done |

**Total completed:** 26 items (14 enhancements + 8 sweep items + 4 extras)

---

## Remaining Work (not blocked, not urgent)

### Domain Repo IAM Hardening (out of scope for platform)

ENH-019 items #1, #2, #5-14, #15-17 live in `modules/agents/` or `tccw-qitp` domain infra:
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
- [ ] Adopt `modules/lambda` in `tccw-qitp` to replace manual Lambda boilerplate (~639 lines)
- [ ] Adopt `modules/lambda_alarms` in `tccw-qitp` to replace manual alarm definitions (~130 lines)
- [ ] Adopt `modules/scheduled_lambda` in `tccw-qitp` to replace 7 event triads (~105 lines)
- [ ] Enable `guardrail_enabled = true` in staging/production when ready
- [ ] Configure online evaluation (`evaluation.online`) in domain blueprints when ready
- [ ] Check AWS Issue #809 status — remove `GATEWAY_DIRECT_MCP` workaround when fixed

---

## Notes

- 2026-03-31: Project initialized with operator pattern
- 2026-04-08: Organized 20 enhancements + 8 sweep remainders into 4 blocks
- 2026-04-08: All 4 blocks executed and validated. 14/20 enhancements done, 6 deferred to backlog.
