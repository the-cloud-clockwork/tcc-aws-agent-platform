# AWS Agent Platform — Project Instructions

> **Configuration-driven, provider-agnostic runtime for AI agents on AWS — Strands SDK + Bedrock AgentCore.**
> **Status: 78/100 production readiness.** Stage 1 inference decoupling done. Pipeline validated E2E (16/16 states). 7 Next Moves remain.

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
- **All 9 QITP agents run on LiteLLM in dev** (`claude-sonnet-4-6` via `your-litellm-proxy.example.com` + Cloudflare Access service tokens). Bedrock path retained but unused for QITP inference.
- LiteLLM: set `base_url` + `api_key_env` + optional `extra_headers_env` in blueprint YAML. `extra_headers_env` is a generic header→env map (used for CF Access tokens).
- Anthropic: set `api_key_env` in blueprint. Direct Anthropic API.
- Bedrock: requires `BEDROCK_REGION`. Default path for future agents.
- **Structured output on non-Bedrock providers**: blueprints with `output_schema` auto-register `StructuredOutputEnforcer` (instructor-based post-processor) — bypasses Strands' broken forced-tool path for OpenAI-compatible endpoints.
- **LiteLLM safety pin**: `litellm>=1.83.0,<2` (versions 1.82.7–1.82.8 were CVE-2026-33634 supply chain attack).
- **LiteLLM model_id rule**: when `base_url` is set, loader auto-prefixes `openai/` to prevent LiteLLM's provider auto-detection from bypassing the proxy.
- Migration strategy: `operator/inference-migration.md` (Stage 2: hooks decoupling; Stage 3: infra optionality — both still pending).

## Pipeline Validation (E2E — tccw-qitp)
Full pipeline validated 2026-04-08 (16/16 states, 39s):
```
ValidateMarketCalendar → CheckTradingDay → gap-detector → CheckGapCount
→ PARALLEL(sentiment-analyzer, technical-analyzer, ml-predictor)
→ ResolveClaimChecks → CompositeSignal → EvaluateStrategies
→ SynthesizeRecommendations → CheckBacktestPass → RouteByMode
→ StoreResults → PipelineComplete
```
Skills in `tccw-qitp/.claude/skills/`: invoke-agent, check-agent, check-deploy, check-artifacts, run-pipeline.

## Next Moves (Hardening Only — Independent, No Dependencies)
7 items in `operator/ENHANCEMENTS.md` (NM-001 to NM-008, NM-007 blocked on AWS).
To 85/100: NM-001 (tests), NM-002 (domain IAM), NM-003 (enable guardrails).
To 95/100: NM-004 (secrets rotation), NM-005 (online eval), NM-006 (adopt modules).
**Next:** LiteLLM test — add `litellm` to one agent image, set API key, invoke with `provider: litellm`.

## Quick Test Lambda — `test-litellm-proxy`
Disposable Lambda for testing connectivity, headers, and API calls from inside AWS networking.
Update code: `cd /tmp && zip test.zip test.py && aws lambda update-function-code --function-name test-litellm-proxy --zip-file fileb:///tmp/test.zip`
Invoke: `aws lambda invoke --function-name test-litellm-proxy --payload '{"key":"val"}' /tmp/result.json && cat /tmp/result.json | python3 -m json.tool`
Role: `qitp-dev-risk-engine-role` (has VPC + secrets access). Runtime: python3.12, 30s timeout.

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
