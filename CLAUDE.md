# AWS Agent Platform — Project Instructions

> **Configuration-driven, provider-agnostic runtime for AI agents on AWS — Strands SDK + Bedrock AgentCore.**
>
> Phase 1 (provider-agnostic inference) and Phase 2 (observability decoupling) are complete and production-validated. Stage 3 (Infrastructure Optionality — standalone runtime / ECS Fargate) is **POSTPONED** (operator decision, 2026-04-09). The decoupling goal is achieved — inference and observability are no longer tied to Bedrock.

## Boot Sequence
1. `operator/VISION.md` — Intent, philosophy (operator-owned, never edit)
2. `operator/SPECS.md` — Technical contract, schemas
3. `operator/BLOCKS.md` — Work blocks and status

## Operator Documents
`operator/` contains: VISION.md, SPECS.md, BLOCKS.md, TODO.md, STATE.md, BUGS.md, KNOWN-ISSUES.md (KI-001 Gateway, KI-002 Cedar), ENHANCEMENTS.md, MVP.md, inference-migration.md

> **Note:** `operator/` is local/internal only and is NOT tracked in the public repo.

## What This Repo Is
Monorepo: 4 Python modules + 7 Terraform modules (3 core + 4 utility).

| Module | Purpose |
|--------|---------|
| `core/` | Blueprint engine, runtime, hooks, schemas, observability, gateway, memory, identity, policy, evaluation, A2A |
| `prompts/` | Versioned prompt management — S3 + DynamoDB |
| `artifacts/` | MCP artifact store — S3 + signed URLs + claim-check |
| `cli/` | CLI for blueprint validation, prompt management |
| `modules/platform` | 6 sub-modules: security, data, observability, api, agentcore, prompt_registry. VPC/subnets are external inputs — no network sub-module. |
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
cd <your-domain-consumer-repo>/infra
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
gh run list --repo The-Cloud-Clockwork/tcc-aws-agent-platform --limit 5
gh run view <run-id> --log-failed   # read failures
gh workflow run sonar-scan.yml      # manual SonarQube scan (only this repo)
```
**A domain consumer repo may have no workflow_dispatch** — push a change to trigger CI.

### After changes: infra clean + CI clean = done.

## Inference Providers (Stage 1 — Provider-Agnostic) ✅ Complete 2026-04-09
`_build_model_config()` in `loader.py` dispatches on `ModelConfig.provider` via match/case.
Supported: `bedrock` (default), `anthropic`, `litellm`, `vertex`. All Strands SDK providers.

| Provider | Required config | Notes |
|----------|----------------|-------|
| `bedrock` | `BEDROCK_REGION` env var | Default. Raises `BlueprintLoadError` if region is absent. |
| `anthropic` | `api_key_env` in blueprint | `temperature` is accepted in blueprint schema but NOT forwarded to `AnthropicModel` — only `model_id` and `max_tokens` are passed. |
| `litellm` | `base_url` + `api_key_env` + optional `extra_headers_env` | When `base_url` is set, loader sets `custom_llm_provider="openai"` in `client_args` so the litellm library routes through `api_base` instead of auto-detecting from the model name. `model_id` is passed unchanged. `extra_headers_env` is a `{header: env_var}` map. |
| `vertex` | Google ADC (`GOOGLE_APPLICATION_CREDENTIALS` etc.) | Only `model_id` is forwarded to `GeminiModel`. `api_key_env`, `base_url`, `temperature`, `max_tokens` are ignored. |

**Structured output**: blueprints with `output_schema` use Strands native `structured_output_model` for all providers. The `StructuredOutputEnforcer` instructor-based workaround was removed in commit `8c784df` — upstream Strands bugs #743, #1005, #891 are resolved in strands-agents ≥ 1.41.0. (`StructuredOutputEnforcer` class still exists in `hooks/` as dead code; it is no longer wired by the loader.)

**LiteLLM safety pin**: `litellm>=1.83.0,<2` — versions 1.82.7–1.82.8 were a supply chain attack (CVE-2026-33634).

**model_id env-template expansion**: `${VAR}` and `${VAR:-default}` patterns are expanded at load time for `bedrock`, `anthropic`, and `litellm`. `vertex` uses `os.path.expandvars` instead.

## Observability & Hooks Decoupling (Stage 2) ✅ Complete 2026-04-09
All agent-level observability hooks are provider-agnostic. Key blueprint knobs:

- **`observability.enabled: true|false`** — master toggle. When false, no Langfuse / audit log / structured logger / cost tracker hooks register.
- **`observability.data_protection.provider: bedrock|presidio|none`**
  - `bedrock` — AWS Bedrock Guardrails. Requires model provider also `bedrock` AND `BEDROCK_GUARDRAIL_ID` env. No-ops silently on any other combination.
  - `presidio` — Microsoft Presidio, MIT-licensed, local redaction via `PresidioGuardrailHook`. Works with any inference provider. Requires `pip install 'agent-core[presidio]'`. Configure entities with `presidio_entities: [EMAIL_ADDRESS, PHONE_NUMBER, ...]` and language with `presidio_language: en`.
  - `none` — no in-process PII filter. CloudWatch data protection (storage-layer masking) still applies when `cloudwatch_masking_identifiers` is set.
- **`evaluation.provider: agentcore|langfuse`**
  - `agentcore` (default) — `bedrock_agentcore_starter_toolkit.Evaluation`. Judge model must be a Bedrock ARN.
  - `langfuse` — `LangfuseEvaluationClient`. Provider-agnostic. Requires `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. Online eval is dashboard-driven, not env-driven (the `create_online_config` method is a no-op stub).
- **`CostTracker` env vars**: `MODEL_PRICING` (JSON map, model_id → [input_per_1k, output_per_1k]) and `MODEL_DEFAULT_PRICING` (JSON array). `BEDROCK_MODEL_PRICING` / `BEDROCK_DEFAULT_PRICING` accepted as deprecated aliases. Built-in defaults cover `claude-sonnet-4-6` and `claude-haiku-4-5` (and their `openai/`-prefixed variants), so cost tracking works on LiteLLM with zero config for those models.
- **Langfuse is double-traced by design**: LiteLLM proxy writes per-generation spans via `success_callback: langfuse`; agent-level `LangfuseHook` writes session-level traces including aggregated token totals, tool calls, and full conversation JSON. Different granularities — duplication is intentional.
- **Built-in evaluators**: exactly **12** (7 response quality + 1 task completion + 2 tool usage + 2 safety). The `BuiltinEvaluator` enum docstring incorrectly states "13 total" — the enum has 12 members and `BUILTIN_EVALUATORS` dict has 12 entries.

## Pipeline Validation (E2E — Production) ✅ PRODUCTION-VALIDATED 2026-04-09
Phase 1 + Phase 2 were validated via a 16-state Step Functions execution (all states SUCCEEDED): single-agent path with real `claude-sonnet-4-6` via LiteLLM, structured output enforced, claim-check artifact persisted to S3 (`s3://<domain-artifacts-bucket>/domain/<date>/<uuid>/artifact.json`). A subsequent parallel fan-out run (empty-gaps path, ml-predictor structured output via fallback) also succeeded end-to-end.

**Known data-contract issue (not infra):** downstream agents reject input with `Missing required field` when upstream agent returns empty results. Fix is per-agent input-validator fallbacks to the default watchlist.

## Domain Dependencies — Secrets Manager / API Key Wiring
The platform reads its LiteLLM API key from AWS Secrets Manager at Terraform apply time; `LITELLM_API_KEY` is then injected as a plaintext env var into every AgentCore Runtime via `modules/agents/runtime.tf`. The value is present in Terraform state. Rotate out-of-band via litellm_tools MCP; TF only reads, never writes.

SSM SecureString parameters back credential providers for identity (API key and OAuth2 outbound auth). Operators must run `aws ssm put-parameter` before `terraform apply` or the plan will fail — see `modules/agents/identity_providers.tf` comments.

## Roadmap Pivot (Apr 2026)
Phase 1 + Phase 2 are done. Stage 3 is postponed. The current focus is:

1. **Scheduled pipeline runs** — EventBridge cadence (hourly / 6h / nightly) for automated analysis runs, accumulating decision traces.
2. **Multi-model validation** — run the same pipeline across multiple inference providers (Gemini / GPT / DeepSeek via LiteLLM) and compare quality + cost + latency.
3. **Agent / schema / blueprint hardening** — candidates: stricter Pydantic output schemas, SFN step-boundary validation, blueprint linter, schema versioning.
4. **Decision-level observability** — Langfuse trace wiring exists. Gap is surfacing decisions as a morning digest (generator, dashboard panel, summary endpoint).

## Known Platform Debt (tracked, not blocking roadmap)
- `evaluation.provider: agentcore` fails on some agents with `create_evaluator` errors. Workaround: use `evaluation.provider: langfuse` or disable evaluation on affected blueprints.
- `bedrock_agentcore_starter_toolkit.operations.gateway.client.update_gateway` crashes on gateway refresh for some agent types.
- `AgentBlueprint` Pydantic `ValidationError` on blueprint load for agents with schema drift.
- `rebuild-deploy.sh force_update_runtime` drops env vars on live update (replace-not-merge). Workaround: follow up with `terraform apply -target=module.agents` to restore env.

## Quick Test Lambda — `test-litellm-proxy`
Disposable Lambda for testing connectivity, headers, and API calls from inside AWS networking.

```bash
# Update code
cd /tmp && zip test.zip test.py
aws lambda update-function-code --function-name test-litellm-proxy --zip-file fileb:///tmp/test.zip

# Invoke
aws lambda invoke --function-name test-litellm-proxy \
  --payload '{"key":"val"}' /tmp/result.json \
  && cat /tmp/result.json | python3 -m json.tool
```

Runtime: python3.12, 30 s timeout. Role has VPC + secrets access.

## AWS Configuration
| Setting | Value |
|---------|-------|
| Account | `123456789012` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` |
| CodeArtifact | `platform` / `platform-python` |

## Key Rules

### Universal
1. **Zero domain contamination** — `domain-scan.sh` must return zero
2. **No hardcoded defaults** — Everything from blueprints/env/config
3. **No backward compatibility** — Build for the vision
4. **Hard dependencies** — `bedrock_agentcore` (runtime) and `strands-agents` (SDK) required. Inference provider is configurable.
5. **Configuration-driven** — All resource names from config
6. **Claim-check pattern** — Large outputs in S3, keys through Step Functions
7. **IaC: Terraform only** — `modules/` is the sole infrastructure source
8. **Never run tests locally** — CI only. Push and `gh run` to monitor.
9. **Commit directly to main** — No branches, no PRs

### Infrastructure-Specific (Terraform)
10. **Networking is external** — Consume VPC/subnets via input variables; no network sub-module
11. **Envelope encryption** — 5 KMS keys (data, storage, secrets, platform_artifacts, domain_artifacts), never AES256
12. **Conditional resources** — WAF, CloudFront, Cognito, guardrails gated by variables
13. **Sub-module interfaces are locked** — Update all consumers on changes
14. **Provider schema verification** — `aws_bedrockagentcore_*` resources require AWS provider ≥ 6.21
15. **Blueprint-driven scaling** — `for_each` over YAML blueprints
16. **Least privilege IAM** — Scope to specific ARNs (note: `bedrock:*` + `bedrock-agentcore:*` wildcard grants in `modules/agents/iam.tf` are intentional dev-phase grants, annotated for tightening)
17. **Three tfvars** — `dev`, `staging`, `production`. Add new variables in all three.
18. **Definition of Done** — `terraform apply` in domain consumer with zero errors + CI pipelines green after push
