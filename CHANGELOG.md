# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Apache-2.0 license** — `LICENSE` and `NOTICE` files added; the project is
  now published as open source under the Apache License 2.0.
- **GitHub Pages documentation site** — reorganized into topic sections
  (concepts, blueprints, inference, observability, runtime, infrastructure,
  CLI, SDK, tools, policy) with pretty permalinks.
- **Provider-agnostic inference** — `_build_model_config()` in `loader.py`
  dispatches on `ModelConfig.provider` via `match/case`. Supported providers:
  `bedrock` (default), `anthropic`, `litellm`, `vertex` (all Strands SDK
  providers). `base_url`, `api_key_env`, and `extra_headers_env` (generic
  header-to-env map) are configurable per blueprint.
- **LiteLLM `openai/` prefix auto-injection** — when `base_url` is set,
  the loader auto-prefixes the model ID with `openai/` to prevent
  LiteLLM's provider auto-detection from bypassing the proxy.
- **`extra_headers_env` support** — generic header→env map on `ModelConfig`
  enabling per-request headers (e.g. Cloudflare Access service tokens) for
  any OpenAI-compatible backend.
- **Presidio PII guardrail** — `PresidioGuardrailHook` provides local,
  MIT-licensed PII redaction via Microsoft Presidio. Configurable via
  `observability.data_protection.provider: presidio`, `presidio_entities`,
  and `presidio_language` blueprint keys. Works with any inference provider.
- **Langfuse evaluation client** — `LangfuseEvaluationClient` as an
  alternative to the AgentCore evaluator. Activated by
  `evaluation.provider: langfuse` in the blueprint. Requires `LANGFUSE_HOST`,
  `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.
- **`observability.enabled` master toggle** — when `false`, no Langfuse,
  audit log, structured logger, or cost tracker hooks register.
- **`CostTracker` built-in pricing defaults** — covers `claude-sonnet-4-6`
  and `claude-haiku-4-5` so cost tracking works on LiteLLM with zero
  configuration. `MODEL_PRICING` and `MODEL_DEFAULT_PRICING` env vars
  override. Deprecated `BEDROCK_MODEL_PRICING` / `BEDROCK_DEFAULT_PRICING`
  aliases still accepted.
- **`default_input` for scheduled triggers** — blueprints can declare a
  static default payload for EventBridge-scheduled invocations.
- **`event_mode` override** — Lambda handler and Step Functions payload
  accept an `event_mode` key to override the blueprint execution mode at
  runtime.
- **Gate node support in graph builder** — gate/decision nodes are filtered
  from `GraphBuilder` edges; `agent_ref` is `None` for gate nodes and
  handled without crashing.
- **`extra_s3_read_bucket_arns` Terraform variable** — grants domain agents
  read access to additional S3 buckets beyond the platform artifact bucket.
- **Lambda wrapper for agent invocation** — routes all agent task states
  through a Lambda wrapper, bypassing the 60-second Step Functions SDK
  timeout for long-running agents.
- **`timeout_seconds` and `heartbeat_seconds` on SFN agent task states** —
  configurable per agent in the Step Functions workflow module.
- **OTel metrics and logs exporters** — `enable_otel_metrics` and
  `enable_otel_logs` blueprint flags; stdlib `logging` bridge into the OTel
  logs pipeline.
- **EventBridge audit logging** — optional audit event emission on each
  agent invocation.
- **POST /api/artifacts endpoint** — REST API gateway route for direct
  artifact registration.
- **Artifacts table name and ARN outputs** — platform Terraform module
  exposes DynamoDB artifact table name and ARN as outputs for downstream
  consumers.
- **MCP Runtime authorizer safeguards** — input validation and auth checks
  in the MCP Runtime invocation path.
- **`agent_core.mcp` subpackage** — shared MCP server infrastructure
  (`BaseMCPServer`) used by the artifacts MCP server and domain MCP servers.
- **SonarQube CI integration** — `sonar-project.properties` configured for
  multi-module paths; all ratings at A, ≥ 80 % coverage baseline.
- **Self-hosted CI runners** — all GitHub Actions workflows (`ci-core`,
  `ci-prompts`, `ci-artifacts`, CI pages deploy) migrated to self-hosted
  runners.
- **Hermetic Lambda layer build** — `platform-deps` layer is built entirely
  within Terraform using the Python `zipfile` module; no dependency on the
  host `zip` binary.

### Changed

- **Structured output enforcement** — `StructuredOutputEnforcer` fallback
  removed from `loader.py`; Strands native structured output is used for all
  providers (resolves Bug B).
- **Graph coordinator synthesis** — coordinator now performs a synthesis turn
  after all graph nodes complete (resolves Bug F + Bug A).
- **Langfuse trace input/output** — agent reasoning is now captured in the
  Langfuse trace `input` and `output` fields (resolves Bug H).
- **OTel flush at invocation end** — logs and metrics are force-flushed at
  the end of each Lambda invocation (resolves Bug G).
- **`model_id` env template expansion** — template variables (including
  `${VAR:-default}` syntax) are expanded before the model ID is passed to
  the enforcer or model factory.
- **LiteLLM version pin** — `litellm>=1.83.0,<2` (versions 1.82.7–1.82.8
  were the CVE-2026-33634 supply-chain attack).
- **CI build/test/publish** — pipelines now run from `dev` branch, not
  `main`.
- **Org and repo rename** — `the-cloud-clock-work` → `The-Cloud-Clockwork`;
  module prefix aligned to match the updated org slug across all modules and configurations.
- **`LOG_ONLY` policy mode** — policy engine creation is skipped entirely
  when mode is `LOG_ONLY` (no Cedar policy compile).
- **`AGENT_INVOKE_TIMEOUT`** — bumped from 600 s to 840 s for long-running
  graph agents.
- **`DirectMCPClient` session ID** — padded to meet the AgentCore minimum
  length requirement.
- **Parallel SFN branches** — always routed through the Lambda wrapper;
  `jsondecode(jsonencode())` applied to erase Terraform type mismatches in
  parallel branch parameters.
- **`INVOKE_REGION` env var** — replaces the reserved `AWS_DEFAULT_REGION`
  in agent task definitions.

### Fixed

- **LLM failure classification reads the whole `__cause__` chain.**
  `GenericHandler` classified only the outermost exception, so a retriable
  litellm error wrapped by Strands in an `EventLoopException` was reported as
  `error_class: agent_error` / `retriable: false` and callers did not retry a
  transient upstream outage. `_cause_chain()` and `_classify_llm_failure()` are
  now module-level and unit-tested; `http_status` and `provider` are read from
  the matched node rather than the wrapper.
- Marshal walker tightened to skip `toolUse` blocks not matching the schema
  artifact name, preventing false-positive artifact extraction.
- `create_artifact` tool name matched with MCP namespace prefix.
- Conversation history last message scanned for post-hook `toolUse` blocks.
- `StructuredOutputEnforcer` mode order corrected to `TOOLS` first with
  `JSON` fallback.
- Artifacts handler updated to support the API Gateway Lambda proxy event
  format alongside direct invocation.
- Artifacts handler supports both sync and async MCP tool functions.
- ECR image digest used in `container_uri` to force re-pull on rollout.
- Python 3.11-safe f-strings in CLI module; unused imports removed (ruff).
- `ruff` configuration consolidated to repo root; all lint errors resolved
  across all modules.
- Dead `generate_otel_env()` function removed from `config_gen`.

### Security

- **CVE-2026-33634** — LiteLLM versions 1.82.7 and 1.82.8 were a supply-chain
  attack; minimum version pinned to 1.83.0 in `core/pyproject.toml`.

---

[Unreleased]: https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform/compare/HEAD...HEAD
