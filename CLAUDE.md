# AWS Agent Platform — Project Instructions

> **Configuration-driven, provider-agnostic runtime for AI agents on AWS — Strands SDK + Bedrock AgentCore.**
> **Status: 92/100 production readiness.** Phase 1 (provider-agnostic inference) + Phase 2 (observability decoupling) complete and **validated in production** twice:
> - `pilot-t4-1775755670` — gap-detector single-agent path, real claude-sonnet-4-6 via LiteLLM, claim-check artifact in S3.
> - `pilot-t6-1775766858` — 16/16 Step Functions states SUCCEEDED in 61s, empty-gaps parallel fan-out, ml-predictor produced structured output via the Block 6 empty-symbols fallback.
>
> **Stage 3 (Infrastructure Optionality) is POSTPONED** (operator decision, 2026-04-09). The decoupling goal is achieved — inference and observability are no longer tied to Bedrock. Current focus has pivoted to: scheduled pipeline runs + multi-model validation (Gemini/GPT/DeepSeek via LiteLLM) + decision-level observability. See `operator/inference-migration.md` for the full Phase 1/2 story and the postponed Stage 3.

## Boot Sequence
1. `operator/VISION.md` — Intent, philosophy (operator-owned, never edit)
2. `operator/SPECS.md` — Technical contract, schemas
3. `operator/BLOCKS.md` — Work blocks and status

## Operator Documents
`operator/` contains: VISION.md, SPECS.md, BLOCKS.md, TODO.md, STATE.md, BUGS.md, KNOWN-ISSUES.md (KI-001 Gateway, KI-002 Cedar), ENHANCEMENTS.md (14 done + 8 Next Moves NM-001–NM-008), MVP.md

## What This Repo Is
Monorepo: 4 Python modules + 7 Terraform modules (3 core + 4 utility).

| Module | Purpose |
|--------|---------|
| `core/` | Blueprint engine, runtime, hooks, schemas, observability, gateway, memory, identity, policy, evaluation, A2A |
| `prompts/` | Versioned prompt management — S3 + DynamoDB |
| `artifacts/` | MCP artifact store — S3 + signed URLs + claim-check |
| `cli/` | CLI for blueprint validation, prompt management |
| `modules/platform` | 6 sub-modules: security, data, observability, api, agentcore, prompt_registry |
| `modules/agents` | Blueprint-driven for_each — runtimes, IAM, ECR, gateway targets |
| `modules/workflows` | Step Functions for_each |
| `modules/lambda` | Reusable Lambda (archive + function + IAM + VPC + logs) |
| `modules/lambda_alarms` | Alarm factory — Error + Duration per Lambda |
| `modules/scheduled_lambda` | EventBridge rule + target + permission triad |
| `modules/s3_encrypted_bucket` | Bucket + versioning + KMS SSE + public access block |

## The #1 Rule: ZERO Domain Contamination
`scripts/domain-scan.sh` must return ZERO hits.

## Validation — Two Levels

### Level 1: Infrastructure — terraform plan/apply in domain consumer
```bash
cd /home/iamroot/dev/tccw-ecosystem/tccw-qitp/infra
bash scripts/generate-gateway-targets.sh envs/dev.tfvars
terraform init -upgrade && terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars -auto-approve
```
Clean apply = infra is not broken. Bugs in individual services are separate concerns.

### Level 2: Code — CI pipelines (push triggers, monitor with gh)
**Never run tests locally — CI only.** Push to main triggers GitHub Actions.

**This repo:** `ci-core.yml` (core/cli), `ci-prompts.yml`, `ci-artifacts.yml` → ruff + mypy + pytest.
**Domain repo:** `ci-agents.yml`, `ci-mcps.yml` (matrix), `ci-risk.yml`, `ci-infra.yml` (plan+apply), `build-deploy.yml` (ECR+CodeBuild).

```bash
gh run list --repo The-Cloud-Clock-Work/tccw-aws-agent-platform --limit 5
gh run view <run-id> --log-failed   # read failures
gh workflow run sonar-scan.yml      # manual SonarQube scan (only this repo)
```
**tccw-qitp has no workflow_dispatch** — push a change to trigger CI.

### After changes: infra clean + CI clean = done.

## Inference Providers (Stage 1 — Provider-Agnostic) ✅ Complete 2026-04-09
`_build_model_config()` in `loader.py` dispatches on `ModelConfig.provider` via match/case.
Supported: `bedrock` (default), `anthropic`, `litellm`, `vertex`. All Strands SDK providers.
- **All 9 QITP agents run on LiteLLM in dev** (`claude-sonnet-4-6` via `llm.homeofanton.com` + Cloudflare Access service tokens). Bedrock path retained but unused for QITP inference.
- LiteLLM: set `base_url` + `api_key_env` + optional `extra_headers_env` in blueprint YAML. `extra_headers_env` is a generic header→env map (used for CF Access tokens).
- Anthropic: set `api_key_env` in blueprint. Direct Anthropic API.
- Bedrock: requires `BEDROCK_REGION`. Default path for future agents.
- **Structured output on non-Bedrock providers**: blueprints with `output_schema` auto-register `StructuredOutputEnforcer` (instructor-based post-processor) — bypasses Strands' broken forced-tool path for OpenAI-compatible endpoints.
- **LiteLLM safety pin**: `litellm>=1.83.0,<2` (versions 1.82.7–1.82.8 were CVE-2026-33634 supply chain attack).
- **LiteLLM model_id rule**: when `base_url` is set, loader auto-prefixes `openai/` to prevent LiteLLM's provider auto-detection from bypassing the proxy.
- Migration strategy: `operator/inference-migration.md` (Stage 3: infra optionality still pending).

## Observability & Hooks Decoupling (Stage 2) ✅ Complete 2026-04-09
All agent-level observability hooks are provider-agnostic. Key blueprint knobs:

- **`observability.enabled: true|false`** — master toggle. When false, no Langfuse / audit log / structured logger / cost tracker hooks register.
- **`observability.data_protection.provider: bedrock|presidio|none`**
  - `bedrock` — AWS Bedrock Guardrails. Requires a Bedrock model provider AND `BEDROCK_GUARDRAIL_ID` env. No-ops on any other combination (no crash).
  - `presidio` — Microsoft Presidio, MIT-licensed, local redaction via `PresidioGuardrailHook`. Works with any inference provider. Configure entities with `presidio_entities: [EMAIL_ADDRESS, PHONE_NUMBER, ...]` and language with `presidio_language: en`.
  - `none` — no in-process PII filter. CloudWatch data protection (storage-layer masking) still applies when `cloudwatch_masking_identifiers` is set.
- **`evaluation.provider: agentcore|langfuse`**
  - `agentcore` (default) — `bedrock_agentcore_starter_toolkit.Evaluation`. Judge model must be a Bedrock ARN.
  - `langfuse` — `LangfuseEvaluationClient`. Provider-agnostic, requires `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. Online eval is dashboard-driven, not env-driven.
- **`CostTracker` env vars**: `MODEL_PRICING` (JSON map) and `MODEL_DEFAULT_PRICING` (JSON array). `BEDROCK_MODEL_PRICING` / `BEDROCK_DEFAULT_PRICING` still accepted as deprecated aliases. Built-in defaults cover `claude-sonnet-4-6` / `claude-haiku-4-6` so cost tracking works on LiteLLM with zero config.
- **Langfuse is already double-traced**: LiteLLM proxy writes generations via `success_callback: langfuse`; agent-level `LangfuseHook` writes session/tool spans. Intentional — they capture different granularities.

## Pipeline Validation (E2E — tccw-qitp) ✅ PRODUCTION-VALIDATED 2026-04-09
Authoritative run: **`pilot-t4-1775755670`** — 16/16 states, 44.08 s, gap-detector called real `claude-sonnet-4-6` via LiteLLM, `GapDetectionOutput` structured output enforced, claim-check artifact persisted to `s3://qitp-dev-artifacts-835618032093/domain/2026-04-09/13b6f34b-7306-40fe-b30c-9a2feeb9c63b/gap-detector.json`.
```
ValidateMarketCalendar → CheckTradingDay → gap-detector → CheckGapCount
→ PARALLEL(sentiment-analyzer, technical-analyzer, ml-predictor)
→ ResolveClaimChecks → CompositeSignal → EvaluateStrategies
→ SynthesizeRecommendations → CheckBacktestPass → RouteByMode
→ StoreResults → PipelineComplete
```
Skills in `tccw-qitp/.claude/skills/`: invoke-agent, check-agent, check-deploy, check-artifacts, run-pipeline.

**Known data-contract issue (not infra):** 5 downstream agents (sentiment-analyzer, technical-analyzer, ml-predictor, strategy-evaluator, portfolio-recommender) reject input with `Missing required field: symbols/symbol/strategy_evaluations` when upstream gap-detector returns empty `ranked_gaps`. Fix is per-agent input-validator fallbacks to the default watchlist.

## Domain Dependencies — Secrets Manager wiring
The platform reads its LiteLLM API key from AWS Secrets Manager, never from env vars:
- **Secret:** `qitp/platform/litellm` (JSON field `TOKEN`)
- **Data source:** `tccw-qitp/infra/domain_dashboard.tf:186` — `data "aws_secretsmanager_secret_version" "platform_litellm"`
- **Wiring:** `tccw-qitp/infra/main.tf:52` (agents) + `:122` (mcps) — both pass `jsondecode(...)["TOKEN"]` to `module.agents.litellm_api_key` / `module.mcps.litellm_api_key`
- **Env var injected:** `LITELLM_API_KEY` in every runtime via `modules/agents/runtime.tf:40`
- **Key scope:** claude-sonnet-4-6, claude-max-sonnet, claude-max-opus, gpt-5-codex, gpt-5.4-codex, gemini-3.1-pro, deepseek-r1, claude-max-haiku-worker-001, llama-3.3-70b
- **Rotation:** out-of-band via litellm_tools MCP; TF only reads, never writes.

The older `qitp-dev/dashboard/litellm` secret is still alive and still feeds the dashboard ECS chat agent only (gemini-scoped). Do not reuse it for platform agents.

## Roadmap Pivot (Apr 2026)
Phase 1 + Phase 2 are done. Stage 3 is postponed. The current focus is:

1. **Scheduled pipeline runs** — EventBridge cadence (hourly / 6h / nightly) to fire `weekly-gap-analysis` automatically, keep free-tier LiteLLM data flowing, accumulate decision traces.
2. **Multi-model validation** — the platform LiteLLM key (`qitp/platform/litellm.TOKEN`) is scoped for 9 models (`claude-sonnet-4-6, claude-max-sonnet, claude-max-opus, gpt-5-codex, gpt-5.4-codex, gemini-3.1-pro, deepseek-r1, claude-max-haiku-worker-001, llama-3.3-70b`). Run the same pipeline across Gemini / GPT / DeepSeek and compare quality + cost + latency.
3. **Agent / schema / blueprint hardening** — form still open, waiting for operator direction. Candidates: stricter Pydantic output schemas, SFN step-boundary validation, blueprint linter, schema versioning.
4. **Decision-level observability** — Langfuse trace wiring exists. Gap is surfacing decisions to the operator each morning (digest generator, dashboard panel, summary endpoint).

**Old NM-001..NM-008 hardening list is deprecated** — see `operator/ENHANCEMENTS.md` if you need historical context, but do not treat it as the priority list.

## Known Platform Debt (not blocking the pivot)
These hit pilot-t6 but are tracked separately and are NOT on the roadmap:
- `sentiment-analyzer` + `strategy-evaluator` → `agent_core.evaluation.client.create_evaluator` fails with `evaluation.provider: agentcore`. Workaround: `evaluation.provider: langfuse` or disable evaluation on those blueprints.
- `technical-analyzer` → `bedrock_agentcore_starter_toolkit.operations.gateway.client.update_gateway` crashes on gateway refresh.
- `portfolio-recommender` → `AgentBlueprint` Pydantic `ValidationError` on blueprint load — schema drift.
- `tccw-qitp/scripts/rebuild-deploy.sh force_update_runtime` (line 333) drops env vars because `update-agent-runtime` is replace-not-merge and the call omits `--environment-variables`. Workaround: after a live `rebuild-deploy` run, follow up with `terraform apply -target=module.agents` to restore env.

## Quick Test Lambda — `test-litellm-proxy`
Disposable Lambda for testing connectivity, headers, and API calls from inside AWS networking.
Update code: `cd /tmp && zip test.zip test.py && aws lambda update-function-code --function-name test-litellm-proxy --zip-file fileb:///tmp/test.zip`
Invoke: `aws lambda invoke --function-name test-litellm-proxy --payload '{"key":"val"}' /tmp/result.json && cat /tmp/result.json | python3 -m json.tool`
Role: `qitp-dev-risk-engine-role` (has VPC + secrets access). Runtime: python3.12, 30s timeout.

## AWS Configuration
| Setting | Value |
|---------|-------|
| Account | `835618032093` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact | `platform` / `platform-python` |

## Key Rules
### Universal
1. **Zero domain contamination** — `domain-scan.sh` must return zero
2. **No hardcoded defaults** — Everything from blueprints/env/config
3. **No backward compatibility** — Build for the vision
4. **Hard dependencies** — `bedrock_agentcore` (runtime) and `strands` (SDK) required. Inference provider is configurable.
5. **Configuration-driven** — All resource names from config
6. **Claim-check pattern** — Large outputs in S3, keys through Step Functions
7. **IaC: Terraform only** — `modules/` is the sole infrastructure source
8. **Never run tests locally** — CI only. Push and `gh run` to monitor.
9. **Commit directly to main** — No branches, no PRs

### Infrastructure-Specific (Terraform)
10. **Networking is external** — Consume VPC/subnets via input variables
11. **Envelope encryption** — 5 KMS keys, never AES256
12. **Conditional resources** — WAF, CloudFront, Cognito, guardrails gated by variables
13. **Sub-module interfaces are locked** — Update all consumers on changes
14. **Provider schema verification** — `aws_bedrockagentcore_*` new (provider >= 6.21)
15. **Blueprint-driven scaling** — `for_each` over YAML blueprints
16. **Least privilege IAM** — Scope to specific ARNs
17. **Three tfvars** — `dev`, `staging`, `production`. New variables in all three.
18. **Definition of Done** — `terraform apply` in `tccw-qitp` zero errors + CI pipelines green after push
