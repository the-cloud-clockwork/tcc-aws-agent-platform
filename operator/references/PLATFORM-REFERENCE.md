# PLATFORM.md — AgentCore Platform Reference

> **Last updated:** 2026-03-30 | **Source:** 9-agent deep analysis (5 Opus + 4 Sonnet sweeps) of platform SDK, Amazon samples, Terraform modules, YAML configs, security posture, and web research
> **Platform repo:** `~/dev/tccw-aws-agent-platform` | **Samples repo:** `~/dev/amazon-bedrock-agentcore-samples`

---

## TLDR — What We Have and How It Connects

### The Stack (Working End-to-End)

```
Dashboard (Next.js 15)  ─── reads ──→  DynamoDB + S3 artifacts
       ↑                                      ↑
       │                                      │ creates
       │                              ┌───────┴───────┐
       │                              │  9 Agents     │
       │                              │  (microVMs)   │
       │                              └───────┬───────┘
       │                                      │ calls tools via
       │                              ┌───────┴───────┐
       │                              │   Gateway     │──→ 8 MCP Servers (microVMs)
       │                              │   (OAuth2)    │──→ 2 Lambda targets
       │                              │               │──→ 1 artifacts Lambda
       │                              └───────────────┘
       │
  Cognito (Google OAuth) ──→ User auth
```

### What Connects to What

| From | To | How | Status |
|---|---|---|---|
| Agent → Gateway | All tool access | SigV4 auth, single MCP URL | WORKING |
| Agent → MCP Server | Direct bypass | DirectMCPClient + Cognito JWT (Issue #809) | WORKING |
| Agent → Bedrock | Model invocation | Strands SDK, Claude Sonnet | WORKING |
| Agent → Artifacts | Create/read outputs | artifacts-mcp Lambda via Gateway | WORKING |
| Agent → Memory | Session + semantic | AgentCore Memory service | WORKING |
| Agent → Langfuse | Observability | LangfuseHook (trace per invocation) | WORKING |
| MCP → Polygon.io | Live market data | resolve_provider (staging mode) | WORKING |
| Step Functions → Agents | Workflow orchestration | invoke_agent_runtime | WORKING |
| Dashboard → DynamoDB | Read data | AWS SDK (task role IAM) | WORKING |
| Dashboard → S3 | Read artifacts | Signed URLs via artifacts API | WORKING |
| Dashboard → Cognito | User auth | Google OAuth + session cookies | WORKING |
| Terraform → Everything | Infrastructure | Platform + domain modules | WORKING |
| CodeBuild → ECR | Image builds | terraform_data parallel builds | WORKING |

### Platform SDK Module Map (One Line Each)

| Module | What It Does |
|---|---|
| `blueprints/` | YAML → Pydantic → Strands Agent builder (full lifecycle wiring) |
| `runtime/` | AgentCoreApp + GenericHandler + idempotency + session + marshalling |
| `gateway/` | GatewayClient (SigV4/JWT), DirectMCPClient bypass, tool discovery |
| `memory/` | MemoryManager + hooks + branching + tool provider (recall/record) |
| `observability/` | Langfuse + AuditLog + StructuredLogger + CostTracker + X-Ray + OTEL |
| `hooks/` | CompositeObservabilityHook factory (composes all observability) |
| `tools/` | Code Interpreter + Browser builtins via Gateway |
| `identity/` | Cognito/Entra/Okta providers + API key creds + @requires decorators |
| `evaluation/` | 13 built-in evaluators + custom LLM-as-judge + online monitoring |
| `policy/` | Cedar policies + NL2Cedar + versioning + Gateway enforcement |
| `a2a/` | Agent-to-Agent protocol (client + server + @tool wrappers) |
| `mcp/` | BaseMCPServer + cache + resolve_provider + VersionedS3Store |
| `schemas/` | Pydantic models for all config (memory, eval, policy, identity, etc.) |
| `prompt/` | PromptRegistryClient (Lambda + HTTP + local fallback) |
| `api/` | Artifacts REST API + MCP handler |
| `execution/` | ExecutionMode enum + validation |

---

## Capability Matrix — What We Use vs What's Available

### Legend: USED / PARTIAL / UNUSED

| Capability | Status | Notes |
|---|---|---|
| **Blueprints** | | |
| Agent blueprints (YAML → Pydantic) | USED | All 9 agents |
| Strategy blueprints | USED | 5 strategies |
| Workflow blueprints | USED | 2 workflows (weekly_analysis, watchlist-screening) |
| `build_entrypoint()` (zero-boilerplate app) | UNUSED | QITP uses manual app.py wiring |
| Thinking config (extended reasoning) | PARTIAL | Only portfolio-recommender |
| **Runtime** | | |
| AgentCoreApp + @entrypoint | USED | All agents |
| GenericHandler (validation, idempotency, marshalling) | USED | Core dispatch |
| AgentConfig + Registry | USED | All 8 agents registered |
| Output marshalling + claim-check | USED | S3 artifacts, SFN claim-check |
| Middleware support | UNUSED | No correlation IDs, no request timing |
| **Gateway** | | |
| GatewayClient (SigV4 auth) | USED | All agents |
| DirectMCPClient (bypass) | USED | Issue #809 workaround |
| Tool discovery | UNUSED | Implicit via Gateway |
| JWT auth mode | UNUSED | All agents use AWS_IAM |
| **Memory** | | |
| MemoryManager + hooks | USED | All 9 agents |
| Semantic memory | USED | All agents with retrieval configs |
| Memory tool provider (recall/record) | USED | `enable_tool_provider: true` everywhere |
| Memory branching | USED | weekly_analysis workflow |
| EPISODIC strategy | UNUSED | Ideal for trading pattern tracking |
| USER_PREFERENCE strategy | UNUSED | Ideal for per-portfolio config |
| Memory streaming to Kinesis | UNUSED | New March 2026 feature |
| **Observability** | | |
| Langfuse traces | USED | All 17 runtimes |
| AuditLog (DynamoDB) | USED | All agents |
| StructuredLogger | USED | Auto-wired |
| CostTracker | USED | Token pricing |
| X-Ray tracing | UNUSED | |
| GenAI Metrics Publisher | PARTIAL | Declared in blueprints, not publishing |
| Dashboard auto-deployment | UNUSED | deploy_dashboard() available but not called |
| PII filter on Langfuse | UNUSED | Available via pii_filter callback |
| Data Protection (Bedrock Guardrails) | PARTIAL | execution-agent declares it |
| **Tools** | | |
| MCP tools via Gateway | USED | All agents, 55 tools total |
| Code Interpreter (builtin) | PARTIAL | Only portfolio-recommender |
| Browser (builtin) | UNUSED | Available for web scraping |
| **Identity** | | |
| Inbound auth (aws_iam) | USED | All agents |
| Outbound credentials (api_key) | PARTIAL | Only execution-agent (IBKR) |
| OAuth2 credential providers | UNUSED | Only api_key type used |
| @requires_api_key decorators | UNUSED | |
| **Evaluation** | | |
| Custom evaluators (LLM-as-judge) | PARTIAL | Only execution-agent |
| 13 built-in evaluators | UNUSED | Correctness, Faithfulness, ToolSelectionAccuracy, etc. |
| Online evaluation (continuous) | UNUSED | Production sampling not configured |
| Evaluation persistence | PARTIAL | 8 of 9 agents |
| **Policy** | | |
| Cedar policy rules (allow/deny) | USED | 8 of 9 agents |
| Policy versioning | UNUSED | DynamoDB audit trail |
| NL2Cedar (natural language → Cedar) | UNUSED | CLI-only |
| Conditional rules (when/unless) | UNUSED | Only simple allow/deny used |
| **A2A** | | |
| A2AClient (cross-runtime) | UNUSED | No remote agent invocations |
| A2AServerWrapper | PARTIAL | execution-agent has port 9000 but no A2A config |
| remote_agent_tool wrappers | UNUSED | |
| Multi-agent Graph pattern | PARTIAL | strategy-evaluator coordinates, but simple |
| **MCP Infrastructure** | | |
| BaseMCPServer | USED | All 8 MCPs |
| cache_get/cache_set | USED | All MCPs |
| resolve_provider (mode routing) | USED | 7 of 8 MCPs |
| VersionedS3Store | USED | ml-predict for model artifacts |

---

## Amazon Samples — Features We're Not Using

Source: `~/dev/amazon-bedrock-agentcore-samples` (59 tutorials, 20+ use cases, 10+ integrations)

### High Value Gaps

| Feature | Sample Location | QITP Value |
|---|---|---|
| **Middleware chain** (correlation IDs, timing, error handling) | `01-tutorials/01-AgentCore-runtime/03-advanced-concepts/06-middleware-support/` | Immediate — zero-code observability improvement |
| **Bedrock Guardrails** for financial agents | `02-use-cases/finance-personal-assistant/utils/guardrail.py` | High — compliance-critical content filtering |
| **Memory hooks** (auto-inject preferences, save insights) | `02-use-cases/slide-deck-generator-memory/memory_hooks/slide_hooks.py` | High — agents remember user risk tolerance |
| **A2A coordinator pattern** with discovery | `02-use-cases/A2A-multi-agent-incident-response/` | Medium — portfolio-recommender delegates to specialists via A2A |
| **Gateway tool discovery** at startup | `02-use-cases/A2A-multi-agent-incident-response/monitoring_strands_agent/agent.py` | Medium — dynamic tool registration instead of hardcoded |
| **Langfuse experiment runner** (CI/CD eval) | `03-integrations/AgentOps-Langfuse/utils/langfuse.py` | Medium — regression testing for agent behavior |
| **Cedar parameter-level policies** | `01-tutorials/08-AgentCore-policy/03-Fine-Grained-Access/` | High — `permit order when position_size <= max` |
| **Terraform aws_bedrockagentcore_* resources** | `04-infrastructure-as-code/terraform/end-to-end-weather-agent/main.tf` | Strategic — native TF resources for runtime, memory, tools |
| **SQL injection prevention** via interceptors | `01-tutorials/02-AgentCore-gateway/15-prevent-sql-injection/` | Low — DynamoDB not SQL, but pattern is relevant |
| **Sensitive data masking** in transit | `01-tutorials/02-AgentCore-gateway/10-sensitive-data-masking/` | Medium — mask account numbers in traces |
| **AG-UI Protocol** for dashboard streaming | New March 2026 — not yet in samples | High — real-time agent reasoning in dashboard |

### Key Patterns Worth Adopting

**1. Middleware Chain** — Starlette middlewares on `BedrockAgentCoreApp` for cross-cutting concerns. ObservabilityMiddleware attaches timing + correlation to OTEL baggage. ErrorHandlingMiddleware returns structured errors. QITP has no middleware layer.

**2. Memory Hooks** — `SlideMemoryHooks(HookProvider)` registers on `MessageAddedEvent` (inject preferences before processing) and `AfterInvocationEvent` (save to long-term memory). Clean separation of memory concerns from agent logic.

**3. A2A Server on FastAPI** — `A2AServer(agent=agent, http_url=runtime_url)` mounted on FastAPI. Each QITP agent could expose an A2A endpoint for direct cross-runtime invocation.

**4. Cedar for Trading** — `permit(principal, action == "execute_trade", resource) when { context.input.position_size <= 10000 && context.input.leverage <= 5 }` — declarative, auditable, infrastructure-level constraints.

---

## AWS Feature Releases (Q1 2026) — What's New

| Feature | Date | Relevance |
|---|---|---|
| **AgentCore Policy GA** | March 2026 | Cedar policies on Gateway — enforce tool access at infrastructure level |
| **AG-UI Protocol** | March 2026 | Streaming agent reasoning/tool results to frontends via SSE |
| **Memory Streaming to Kinesis** | March 2026 | Event-driven reactions to agent memory updates |
| **Stateful MCP Features** | March 2026 | Elicitation, sampling, progress notifications for MCP servers |
| **WebRTC Support** | March 2026 | Real-time voice agents (not needed for QITP) |
| **Shell Command Execution** | March 2026 | Remote shell into running Runtimes (debugging) |
| **Managed Session Storage** | March 2026 | Persist agent filesystem across stop/resume |
| **Server-Side Tool Execution** | February 2026 | Bedrock Responses API + Gateway = no client-side tool loops |
| **Evaluations Preview** | March 2026 | 13 built-in evaluators + online monitoring + quality alerts |
| **Strands 1.0** | March 2026 | Production-ready: Handoffs, Graph, Swarm, Session Manager |

### Most Impactful for QITP

1. **AgentCore Policy GA** — Replace code-level checks with Cedar on Gateway. Only execution-agent calls ibkr-mcp. Only live mode allows orders. Risk Engine PASS at infrastructure level.
2. **Server-Side Tool Execution** — Eliminate client-side orchestration for simple agents. Bedrock handles tool discovery/selection/execution via Gateway.
3. **Evaluations** — Online mode continuously monitors agent quality. 13 built-in evaluators catch regressions. Quality alerts fire when metrics degrade.
4. **AG-UI Protocol** — Standardized streaming for the dashboard chat. Agent reasoning steps and tool results stream in real-time.
5. **Memory Streaming** — Kinesis notifications when agent memory updates. Trigger portfolio rebalancing or dashboard refresh.

---

## Terraform Coherence Analysis

### Module Architecture

```
platform/ (root composition)
  ├── modules/network/     VPC, subnets, NAT, security groups
  ├── modules/security/    5 KMS keys, Secrets Manager, WAF, VPC endpoints
  ├── modules/data/        5 DynamoDB tables, 4 S3 buckets, SQS, CloudFront
  ├── modules/agentcore/   Gateway, Memory, OAuth2, Cognito, builtins
  ├── modules/observability/ CloudWatch, SNS, X-Ray, dashboard
  ├── modules/api/         REST API Gateway, Lambda (artifacts)
  └── modules/prompt_registry/ Lambda + Function URL

agents/ (reused for both agents + MCPs)
  ├── Blueprint YAML parsing (locals.tf)
  ├── Per-agent IAM (iam.tf)
  ├── ECR repos (ecr.tf)
  ├── CodeBuild CI/CD (codebuild.tf)
  ├── AgentCore Runtimes (runtime.tf)
  ├── Gateway targets (gateway_targets.tf)
  ├── Memory strategies (memory_strategies.tf)
  ├── Identity providers (identity_providers.tf)
  └── Docker builds (build.tf)

workflows/ (Step Functions from YAML)
  ├── YAML parsing + ref extraction (locals.tf)
  ├── SFN + EventBridge IAM (iam.tf)
  ├── ASL generation (state_machines.tf)
  └── Schedule + event triggers (triggers.tf)
```

### Coherence Scores

| Dimension | Score | Issue |
|---|---|---|
| Module boundaries | 9/10 | Clean separation. Domain never reaches into platform internals. |
| Naming conventions | 8/10 | Consistent `{prefix}-{env}-{resource}`. Minor: memory uses underscores. |
| Resource tagging | 9/10 | Module, Component, Role, AgentId tags throughout. |
| Multi-environment | 8/10 | Clean tfvars separation (dev/staging/prod). VPC CIDRs differ per env. |
| Provider constraints | 8/10 | Terraform >= 1.10, AWS >= 6.21 pinned. Cross-region Bedrock aliased. |
| Documentation | 8/10 | Header comments on every file. Blueprints self-documenting. |
| Variable/output consistency | 7/10 | 30+ platform outputs lack descriptions. Submodule vars excellent. |
| Security patterns | 7/10 | 5 KMS keys with rotation, VPC endpoints. BUT: `bedrock:*` on `*` in agent IAM. |
| State management | 6/10 | S3 backend with file locking but no DynamoDB lock table. Hardcoded bucket. |
| Scaling | 5/10 | No autoscaling anywhere. PAY_PER_REQUEST DynamoDB. No Lambda reserved concurrency. |

### Critical Issues

| # | Issue | Location | Impact |
|---|---|---|---|
| 1 | Agent IAM grants `bedrock:*` and `bedrock-agentcore:*` on `*` | `modules/agents/iam.tf:63-79` | Any agent can invoke any model, modify any AgentCore resource |
| 2 | `DEPLOY_TIMESTAMP = timestamp()` forces redeployment on every apply | `modules/agents/runtime.tf:29` | Unnecessary downtime and apply noise |
| 3 | Gateway targets YAML contains hardcoded account ID and region | `infra/.generated/gateway-targets.yaml` | Breaks in staging/production |
| 4 | 30+ platform outputs lack description fields | `modules/platform/outputs.tf:110-254` | Domain consumers can't understand the API surface |
| 5 | Cognito disabled in staging but MCP OAuth2 depends on it | `infra/envs/staging.tfvars` | MCP targets fail at runtime |
| 6 | Domain creates duplicate SNS alerts topic | `infra/domain_alerts.tf:3` | Confusion about which topic alarms point to |
| 7 | Backend state bucket hardcoded, no env prefix in key | `infra/backend.tf:3` | All environments share one state key |

### Missing Platform Abstractions

Things the domain wires manually that the platform should provide:

1. **Domain Lambda module** — 15+ Lambdas with identical IAM boilerplate (500+ lines). Platform should provide `modules/domain_lambda`.
2. **CloudWatch alarms factory** — 30+ alarms following same Lambda error/duration pattern. Platform should accept function list → generate alarms.
3. **EventBridge schedule factory** — 6+ three-resource patterns (rule + target + permission). Platform should accept schedule + Lambda → generate all three.
4. **Secrets Manager helper** — Domain manually creates secrets. Platform doesn't expose `secrets_kms_key_arn` output.
5. **Log retention override** — Domain creates duplicate log groups for MiFID II 5-year retention. Should be passable per-agent.
6. **DynamoDB table factory** — Domain creates 11 tables manually. Platform has clean map-based pattern that should be reusable.

---

## Blueprint & Configuration Analysis

### Schema Issues Found

| # | Issue | Severity | Location |
|---|---|---|---|
| 1 | `a2a:` tool declaration not in ToolDeclaration schema | CRITICAL | portfolio_recommender.yaml:27 — Pydantic rejects it |
| 2 | Execution mode `backtest/paper/live` silently ignored (schema expects `simulation/staging/production`) | CRITICAL | All 9 blueprints — no alias registered |
| 3 | Strategy `evaluation.persistence` not in StrategyEvaluationConfig | HIGH | All 5 strategy blueprints |
| 4 | Graph "gate" node type (`trip_condition`, `fallback`) not in GraphNodeConfig | HIGH | strategy_evaluator.yaml:172 |
| 5 | `multi_agent.specialists` not in MultiAgentConfig | MEDIUM | portfolio_recommender.yaml:158-161 |
| 6 | watchlist-screener missing policy block entirely | MEDIUM | Only agent without Cedar rules |
| 7 | gap-detector missing evaluation block entirely | LOW | Only agent without eval persistence |
| 8 | tax-reporter has `a2a_port: 0` (all others: 9000) | LOW | Correct but undocumented |

### Blueprint Consistency Matrix

| Feature | Used By | Not Used By |
|---|---|---|
| Thinking (extended reasoning) | portfolio-recommender | 8 others |
| Code Interpreter | portfolio-recommender | 8 others |
| Custom hooks | portfolio-recommender | 8 others |
| IBKR credentials | execution-agent | 8 others |
| Multi-agent graph | strategy-evaluator, sentiment-analyzer, technical-analyzer | 6 others |
| USER_PREFERENCE memory | portfolio-recommender, watchlist-screener | 7 others |
| SUMMARIZATION memory | 8 agents | watchlist-screener |
| Policy LOG_ONLY mode | gap-detector | 7 others (ENFORCE) |
| Policy block | 8 agents | watchlist-screener |
| Evaluation custom evaluators | 5 agents | gap-detector, ml-predictor, technical-analyzer, watchlist-screener |

### Unused Blueprint Fields (Platform Supports, QITP Doesn't Use)

| Field | What It Does | Value for QITP |
|---|---|---|
| `gateway` (GatewayConfig) | Custom gateway URL, auth_type, JWT env | Low — env var fallback works |
| `model.cache_prompt` / `cache_tools` | Prompt/tool caching config | Medium — reduce Bedrock costs |
| `evaluation.online` | Production sampling + continuous eval | High — catch regressions |
| `policy.versioning` | DynamoDB-backed policy version history | High — audit trail for compliance |
| `policy.rules[].when` / `unless` | Cedar conditional expressions | High — `permit when position_size <= max` |
| `multi_agent.max_node_executions` | Limit executions per graph node | Low — prevent infinite loops |

### Prompt Analysis

All 9 prompts follow a consistent 4-section structure: Role → Capabilities → Workflow → Output.

**Strengths:**
- Tool references match blueprint declarations
- Output schemas described clearly
- execution-agent has thorough partial fill + rejection recovery

**Missing from all prompts:**
- Error handling instructions (only execution-agent has them)
- Execution mode awareness (agents don't know if they're in backtest/paper/live)
- Memory instructions (all agents have memory but prompts don't mention recall/record)
- Artifact schema references (prompts say "Return a JSON" but don't reference Pydantic model names)
- strategy-evaluator prompt has 5 stages but graph has 4 nodes (naming mismatch: signal_gate vs composite_gate)

---

## Top 10 Opportunities (Prioritized)

### Tier 1 — High Impact, Proven Patterns

| # | Opportunity | What | Effort |
|---|---|---|---|
| 1 | **AgentCore Policy GA** | Replace code-level tool access checks with Cedar on Gateway. Enforce: only execution-agent calls ibkr-mcp, only live mode allows orders, risk engine pass required. Infrastructure-level guarantees. | Medium |
| 2 | **Online Evaluation** | Enable 5% production sampling with ToolSelectionAccuracy + Correctness evaluators. Catch regressions before they affect trading. Quality alerts on metric degradation. | Low |
| 3 | **Middleware Chain** | Add ObservabilityMiddleware (correlation IDs, timing) + ErrorHandlingMiddleware (structured errors) to all agent runtimes. Zero business logic changes. | Low |
| 4 | **Memory Strategy Expansion** | Add EPISODIC for trading pattern tracking over time. Add USER_PREFERENCE for per-user risk tolerance, preferred sectors, position sizing rules. | Low |

### Tier 2 — Medium Effort, Strategic Value

| # | Opportunity | What | Effort |
|---|---|---|---|
| 5 | **Server-Side Tool Execution** | Bedrock Responses API + Gateway eliminates client-side tool orchestration for simple agents. Analysis agents become simpler. | Medium |
| 6 | **AG-UI Protocol for Dashboard Chat** | Standardized streaming of agent reasoning + tool results to the Next.js dashboard. Replaces custom polling. Real-time thinking display. | Medium |
| 7 | **Bedrock Guardrails** | Content filtering + PII detection on agent inputs/outputs. Automated Reasoning check validates trading recommendations against logical rules. | Medium |
| 8 | **PII Filter on Langfuse** | Pass `pii_filter` callback to LangfuseHook to sanitize account numbers, personal details, API keys before sending to external Langfuse service. | Low |

### Tier 3 — Strategic, Higher Effort

| # | Opportunity | What | Effort |
|---|---|---|---|
| 9 | **A2A Protocol** | portfolio-recommender invokes sentiment-analyzer, technical-analyzer directly via A2A instead of Sequential SFN states. Lower latency for sub-workflows. | High |
| 10 | **Bedrock Knowledge Bases + MCP** | MCP server for Knowledge Bases → agents query regulatory docs (MiFID II, CNMV, IRPF) without custom RAG. | High |

---

## Blueprint Schema Fixes Needed (Platform Changes)

These are gaps in the platform SDK that QITP's blueprints have outgrown:

1. **Add `A2aToolConfig` to ToolDeclaration union** — `a2a: strategy-evaluator` needs schema support
2. **Register execution mode aliases** — `backtest→simulation`, `paper→staging`, `live→production`
3. **Add `persistence` to StrategyEvaluationConfig** — 5 strategies declare it, schema doesn't have it
4. **Add gate node fields to GraphNodeConfig** — `type`, `trip_condition`, `fallback`
5. **Add `specialists` to MultiAgentConfig** — Or document proper A2A references
6. **Add `extra="forbid"` to critical Pydantic models** — Catch field mismatches at load time

---

## Infrastructure Improvement Roadmap

### P0 — Security
- Tighten agent IAM: scope `bedrock:InvokeModel` to foundation-model ARN
- Expose `secrets_kms_key_arn` from platform outputs

### P1 — Correctness
- Fix gateway-targets.yaml to use Terraform interpolation (no hardcoded account/region)
- Fix Cognito consistency across environments (staging breaks MCP OAuth2)
- Add environment prefix to backend state key

### P2 — Reusability (New Platform Modules)
- `modules/domain_lambda` — IAM + Lambda + logs from simple inputs
- `modules/alarm_set` — Standard error/duration alarms from Lambda list
- `modules/schedule` — EventBridge rule + target + permission from schedule + Lambda

### P3 — Quality
- Add descriptions to 30+ platform outputs
- Remove `DEPLOY_TIMESTAMP` (use proper image tagging)
- Deduplicate SNS alerts topic (domain vs platform)

---

## Quick Reference — File Locations

### Platform SDK (`~/dev/tccw-aws-agent-platform/core/src/agent_core/`)

| Path | Key Classes |
|---|---|
| `blueprints/agent.py` | AgentBlueprint, MultiAgentConfig, GraphNodeConfig |
| `blueprints/loader.py` | BlueprintLoader, build_agent_session(), build_entrypoint() |
| `runtime/entrypoint.py` | AgentCoreApp, @entrypoint |
| `runtime/handler.py` | GenericHandler |
| `gateway/client.py` | GatewayClient, as_tool_provider() |
| `gateway/direct_mcp_client.py` | DirectMCPClient (Issue #809 bypass) |
| `memory/manager.py` | MemoryManager |
| `memory/hook_provider.py` | MemoryHookProvider |
| `observability/langfuse_hook.py` | LangfuseHook (pii_filter support) |
| `observability/dashboard.py` | deploy_dashboard() |
| `evaluation/evaluators.py` | 13 BuiltinEvaluator types |
| `policy/cedar_policies.py` | CedarPolicy, CedarPolicyBuilder |
| `a2a/client.py` | A2AClient |
| `mcp/base_server.py` | BaseMCPServer |
| `schemas/evaluation_config.py` | OnlineEvaluationConfig |
| `schemas/policy_config.py` | PolicyVersioningConfig |
| `schemas/memory_config.py` | MemoryStrategyType (4 types) |

### Platform Terraform (`~/dev/tccw-aws-agent-platform/modules/`)

| Path | What |
|---|---|
| `platform/modules/network/` | VPC, subnets, NAT, security groups |
| `platform/modules/security/` | 5 KMS keys, Secrets Manager, VPC endpoints |
| `platform/modules/data/` | 5 DynamoDB tables, 4 S3 buckets |
| `platform/modules/agentcore/` | Gateway, Memory, OAuth2, Cognito |
| `platform/modules/observability/` | CloudWatch, SNS, X-Ray |
| `platform/modules/api/` | REST API Gateway, artifacts Lambda |
| `platform/modules/prompt_registry/` | Prompt lifecycle Lambda |
| `agents/` | Runtime deployment (agents + MCPs) |
| `workflows/` | Step Functions from YAML |

### Amazon Samples (`~/dev/amazon-bedrock-agentcore-samples/`)

| Path | Key Pattern |
|---|---|
| `01-tutorials/01-AgentCore-runtime/03-advanced-concepts/06-middleware-support/` | Middleware chain |
| `01-tutorials/02-AgentCore-gateway/09-fine-grained-access-control/` | Cedar per-tool policies |
| `01-tutorials/04-AgentCore-memory/02-long-term-memory/` | Semantic + preference memory |
| `01-tutorials/07-AgentCore-evaluations/02-running-evaluations/` | Online + on-demand eval |
| `02-use-cases/A2A-multi-agent-incident-response/` | A2A coordinator pattern |
| `02-use-cases/finance-personal-assistant/` | Guardrails for finance |
| `03-integrations/AgentOps-Langfuse/` | CI/CD eval pipeline |
| `04-infrastructure-as-code/terraform/` | Native TF resources |

---

## Sources

### AWS Announcements (2026)
- [AgentCore Quality Evaluations & Policy Controls](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/)
- [AG-UI Protocol Support](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-agentcore-runtime-ag-ui-protocol/)
- [Memory Streaming to Kinesis](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-memory-streaming-ltm/)
- [Stateful MCP Features](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-agentcore-runtime-stateful-mcp/)
- [Server-Side Tool Execution](https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-bedrock-server-side-tool-execution-agentcore-gateway/)
- [Policy GA](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/)
- [Strands 1.0](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/)

### Documentation
- [AgentCore Policy with Cedar](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
- [AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html)
- [Memory Streaming](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-record-streaming.html)
- [A2A Protocol Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a-protocol-contract.html)
- [Strands Multi-Agent Patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [MCP 2026 Roadmap](http://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
- [MCP Spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)

---

# Deep Sweep Findings (4-Agent Sonnet Sweep)

---

## Memory System — Known Issues and API Reality

### SDK Schema vs AWS API

| Strategy Type | SDK Enum | Terraform `strategy_type_map` | AWS API Key | Status |
|---|---|---|---|---|
| `SEMANTIC` | Defined | Maps to `"SEMANTIC"` | `semanticMemoryStrategy` | SUPPORTED |
| `SUMMARY` / `SUMMARIZATION` | Defined (SUMMARY) | Both map to `"SUMMARIZATION"` | `summaryMemoryStrategy` | SUPPORTED |
| `USER_PREFERENCE` | Defined | Maps to `"USER_PREFERENCE"` | `userPreferenceMemoryStrategy` | SUPPORTED |
| `EPISODIC` | Defined in SDK enum | **MISSING from TF map** | `episodicMemoryStrategy` (different API shape) | **NOT SUPPORTED as simple type string** |
| `CUSTOM` | Not in SDK | Not in TF map | `customMemoryStrategy` | Not supported via current TF resource |

**Root cause:** The Terraform file `memory_strategies.tf` explicitly documents at line 9-10:
```
# NOTE: EPISODIC is documented but not yet supported by the AWS API
# NOTE: CUSTOM is documented but not yet supported by the AWS API
```

EPISODIC in the real API is NOT a `type` string but a compound `episodicMemoryStrategy` dict with nested `reflectionConfiguration`. The `aws_bedrockagentcore_memory_strategy` TF resource's `type` field only accepts `SEMANTIC`, `SUMMARIZATION`, and `USER_PREFERENCE`. If any blueprint declared `type: EPISODIC`, Terraform would pass it through and the AWS API would reject it at apply time.

### Current QITP Memory Configuration

| Agent | Strategies Declared | Issue |
|---|---|---|
| gap-detector | SEMANTIC + SUMMARIZATION | Clean |
| sentiment-analyzer | SEMANTIC + SUMMARIZATION | Clean |
| strategy-evaluator | SEMANTIC + SEMANTIC + SUMMARIZATION | **Two SEMANTIC entries** — TF deduplicates, second namespace silently dropped |
| portfolio-recommender | SEMANTIC + USER_PREFERENCE + SUMMARIZATION | Clean — all 3 supported types |
| ml-predictor | SEMANTIC + SUMMARIZATION | Clean |
| technical-analyzer | SEMANTIC + SUMMARIZATION | Clean |
| tax-reporter | SEMANTIC + SUMMARIZATION | Clean |
| watchlist-screener | SEMANTIC + USER_PREFERENCE | Clean (no SUMMARIZATION) |
| execution-agent | SEMANTIC + SUMMARIZATION | Clean |

**No QITP blueprint uses EPISODIC.** The problem exists in the SDK schema but is NOT triggered by current configs.

### Memory Issues Found

**Issue 1 — `strategy-evaluator` dual SEMANTIC namespace drop (silent data loss)**
The blueprint declares two `SEMANTIC` strategies with different namespaces (`/knowledge` and `/events`). TF's `_strategies_by_type` groups by API type, deduplicates, keeps only the first namespace. The `market_events` namespace is never created. The agent can only retrieve from `/knowledge`. Silent failure — no error, no warning.

**Issue 2 — `MemoryManager.create_memory_resource()` has wrong API payload**
At `memory/manager.py:65-72`, it builds `{"strategyType": s["type"]}` but `MemoryClient.create_memory()` expects `{"semanticMemoryStrategy": {...}}`. This is **dead code** — never called by the wiring path. If invoked directly, it would fail.

**Issue 3 — EPISODIC in SDK schema but unusable**
`MemoryStrategyType.EPISODIC = "EPISODIC"` is defined in `memory_config.py`. If a blueprint author declares `type: EPISODIC`, TF passes `type = "EPISODIC"` to the AWS API, which rejects it. No validation error in the SDK — fails at Terraform apply time. The samples implement episodic via `customMemoryStrategy` with `episodicOverride` (LangGraph nutrition assistant pattern).

**Issue 4 — SUMMARIZATION namespace in retrieval configs**
`hook_provider.py` calls `retrieve_memories()` (semantic vector search) for every namespace in `retrieval:`. Agents that list `{actorId}/{sessionId}/summary` in their retrieval config are calling vector search against a summary namespace. This may work but is conceptually mismatched — summaries are session-scoped and vector searching them has low utility.

### Memory Wiring Flow

```
Blueprint YAML (memory.strategies[])
  → BlueprintLoader._wire_memory() [loader.py:517]
      → MemoryWiring(config, memory_id)
          → MemoryManager (wraps bedrock_agentcore.MemoryClient)
          → MemoryHookProvider → registered into Strands hooks
          → MemoryBranchManager → for multi-agent branching

At agent init (AgentInitializedEvent):
  → get_last_k_turns() → MemoryClient.get_events()
  → retrieve_memories() → MemoryClient.retrieve_memories()

At each message (MessageAddedEvent):
  → create_event() → MemoryClient.create_event()

Memory resource creation (strategies) → Terraform ONLY
  → modules/agents/memory_strategies.tf
  → aws_bedrockagentcore_memory_strategy per deduplicated type
```

### Memory Recommendations

| Priority | Fix |
|---|---|
| HIGH | Fix `strategy-evaluator` dual SEMANTIC — change second to SUMMARIZATION or remove |
| MEDIUM | Remove `EPISODIC` from `MemoryStrategyType` enum to prevent misuse |
| MEDIUM | Delete or fix `create_memory_resource()` dead code (wrong API format) |
| LOW | Review whether SUMMARIZATION namespaces belong in `retrieval:` configs |

---

## Schema Mismatch Audit — Complete Findings

### Pydantic Extra-Field Behavior

**Every Pydantic model** uses `ConfigDict(frozen=True)` with **no `extra=` setting**. In Pydantic v2, when `extra` is absent, the default is `"ignore"` — unknown fields are **silently dropped without any warning or error**. None of the models use `extra="forbid"`.

The `BlueprintLoader` performs **zero pre-processing**: it calls `AgentBlueprint(**data)` directly on `yaml.safe_load()`. No renames, no transformations, no key stripping.

### Complete Mismatch Table

| Blueprint | YAML Field Path | Schema Expected | Actual Value | Issue Type | Impact |
|---|---|---|---|---|---|
| ALL 9 agents | `execution_modes.backtest` | Not in `ExecutionModes` (has: simulation, staging, production) | `bool` | SILENT_DROP (unless `register_qitp_aliases()` called) | Execution mode gates silently disabled — agent runs in all modes |
| ALL 9 agents | `execution_modes.paper` | Same | `bool` | SILENT_DROP | Same |
| ALL 9 agents | `execution_modes.live` | Same | `bool` | SILENT_DROP | Same |
| `execution_agent` | `identity.credentials[0].secret_arn` | Not in `CredentialConfig` | `str` (ARN) | SILENT_DROP | IBKR secret ARN ignored |
| `execution_agent` | `identity.credentials[0].provider` | **REQUIRED** field | **MISSING** | ValidationError | Blueprint **fails to load** |
| `portfolio_recommender` | `tools[3].a2a` | `Union[McpToolConfig, BuiltinToolConfig]` — no A2aToolConfig | `{a2a: ...}` | ValidationError | Blueprint **fails to load** |
| `portfolio_recommender` | `multi_agent.specialists` | Not in `MultiAgentConfig` | `list[dict]` | SILENT_DROP | A2A relationship lost |
| `strategy_evaluator` | `multi_agent.nodes[3].agent_ref` | **REQUIRED** field | **MISSING** (gate node) | ValidationError | Blueprint **fails to load** |
| `strategy_evaluator` | `multi_agent.nodes[3].type` | Not in `GraphNodeConfig` | `"gate"` | SILENT_DROP | Gate concept not recognized |
| `strategy_evaluator` | `multi_agent.nodes[3].trip_condition` | Not in `GraphNodeConfig` | `"composite_score < 0.65"` | SILENT_DROP | Trigger condition lost |
| `strategy_evaluator` | `multi_agent.nodes[3].fallback` | Not in `GraphNodeConfig` | `"low_conviction_exit"` | SILENT_DROP | Exit path lost |
| ALL 5 strategies | `evaluation.persistence` | Not in `StrategyEvaluationConfig` | `{enabled, table_env, retention_days}` | SILENT_DROP | Strategy eval results **never persisted** |
| `weekly_analysis` | `states[*].comment` | Not in `WorkflowState` | `str` | SILENT_DROP | Cosmetic — no functional impact |

### 3 Blueprints That Fail to Load

These blueprints raise `ValidationError` when `BlueprintLoader.load_agent()` is called:

1. **`execution-agent`** — `identity.credentials[0].provider` is required but absent. The YAML has `secret_arn` instead (not in schema).
2. **`portfolio-recommender`** — `tools[3]` has `a2a` key which matches neither `McpToolConfig` nor `BuiltinToolConfig`.
3. **`strategy-evaluator`** — `multi_agent.nodes[3]` (composite_gate) has no `agent_ref` (required by `GraphNodeConfig`).

**Why these agents work in production:** The `GenericHandler` catches these errors and falls back to a simplified agent construction path that skips the broken fields. The multi-agent graph, A2A tools, and IBKR credentials are declared in YAML but never actually wired into the Strands agent at runtime. They are aspirational configuration.

### Execution Modes — Conditional Correctness

`execution_modes.backtest/paper/live` resolve correctly **only if** `register_qitp_aliases()` is invoked before `load_agent()`. This happens in `qitp_agents/app.py` at module import time. Any code path that constructs a `BlueprintLoader` without importing `qitp_agents.app` first will silently drop all mode flags, defaulting to `simulation=True, staging=False, production=False`.

### Fields That Look Wrong But Are Fine

| YAML Field | Why It Works |
|---|---|
| `memory.strategies[*].type: SUMMARIZATION` | Field validator normalizes `SUMMARIZATION` → `SUMMARY` |
| `identity.authorizer.type: aws_iam` | Exact match: `AuthorizerType.AWS_IAM = "aws_iam"` |
| `tools[*] builtin: code_interpreter` | Exact match: `BuiltinToolType.CODE_INTERPRETER` |
| Strategy `parameters[*].type: string` | Field validator normalizes `string` → `str` |
| Strategy `entry_conditions.logic: AND` | Field validator normalizes uppercase |
| Strategy `execution_modes.simulation/staging/production` | Correct canonical names |

### Schema Fixes Needed (Platform)

| Priority | Fix |
|---|---|
| CRITICAL | Add `A2aToolConfig` to `ToolDeclaration` union — `{a2a: str, description: str}` |
| CRITICAL | Make `GraphNodeConfig.agent_ref` optional (gate nodes don't have agents) |
| CRITICAL | Add `secret_arn` to `CredentialConfig` or make `provider` optional |
| HIGH | Add `persistence` to `StrategyEvaluationConfig` |
| HIGH | Add `type`, `trip_condition`, `fallback` to `GraphNodeConfig` |
| HIGH | Add `specialists` to `MultiAgentConfig` |
| MEDIUM | Add `extra="forbid"` to critical models to catch future mismatches at load time |
| LOW | Export JSON Schema from Pydantic models for CI/IDE validation |

---

## Missing Platform Abstractions — Concrete Module Proposals

**Total domain infra:** 2,907 lines across 11 files. Extractable boilerplate: ~651 lines (~22%).

### modules/lambda

**Pattern:** Every domain Lambda requires 5-6 identical resources: `data.archive_file`, `aws_lambda_function`, `aws_iam_role` (identical trust policy copy-pasted 7 times), two `aws_iam_role_policy_attachment` (basic + X-Ray), and `aws_cloudwatch_log_group`.

**Boilerplate:** ~56 fixed lines per Lambda × 6 individual Lambdas = **~336 lines**

```hcl
module "risk_engine" {
  source = "...//modules/lambda"

  name        = "risk-engine"
  source_dir  = "${path.module}/../risk"
  handler     = "qitp_risk_engine.platform_handler.platform_handler"
  memory_size = 512
  timeout     = 60
  vpc_enabled = true   # auto-selects VPCAccessExecutionRole vs BasicExecutionRole

  environment_variables = { /* domain-specific env vars */ }
  extra_policy_statements = [ /* DDB + KMS statements */ ]

  name_prefix             = local.name_prefix
  tags                    = local.tags
  log_retention_days      = 1827  # MiFID II 5yr default
  kms_key_arn             = module.platform.data_kms_key_arn
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
}
```

**Resources generated:** archive_file, lambda_function, iam_role, 2× policy_attachment, iam_role_policy (optional), log_group
**Lines saved:** ~306

### modules/scheduled_lambda

**Pattern:** Every EventBridge trigger = 3 resources in lockstep: event_rule + event_target + lambda_permission. This triad appears 7 times.

**Boilerplate:** 7 × 21 lines = **147 lines**

```hcl
module "schedule_cnmv_sync" {
  source = "...//modules/scheduled_lambda"

  name                 = "${local.name_prefix}-cnmv-sync"
  description          = "Daily CNMV short-sell ban list sync"
  schedule_expression  = "cron(0 5 ? * MON-FRI *)"
  lambda_arn           = aws_lambda_function.compliance["cnmv-sync"].arn
  lambda_function_name = aws_lambda_function.compliance["cnmv-sync"].function_name
  tags                 = local.tags
}
```

**Resources generated:** event_rule, event_target, lambda_permission
**Lines saved:** ~112

### modules/lambda_alarms

**Pattern:** Every Lambda gets 2 alarms (Errors + Duration p99 at 75% of timeout). 10 alarms with identical structure, only `function_name` and `threshold` vary.

**Boilerplate:** 199 lines for 10 alarms

```hcl
module "lambda_alarms" {
  source = "...//modules/lambda_alarms"

  alarms = {
    "risk-engine"      = { function_name = "...", timeout_seconds = 60 }
    "composite-signal" = { function_name = "...", timeout_seconds = 30 }
    "trailing-stop"    = { function_name = "...", timeout_seconds = 60 }
  }
  compliance_alarms = { for k, v in aws_lambda_function.compliance : k => {
    function_name = v.function_name, timeout_seconds = 120
  }}

  sns_topic_arn = aws_sns_topic.alerts.arn
  name_prefix   = local.name_prefix
  tags          = local.tags
}
```

**Duration threshold auto-derived:** `timeout_seconds * 1000 * 0.75`
**Lines saved:** ~154

### modules/s3_encrypted_bucket

**Pattern:** Every KMS-encrypted S3 bucket needs 4 companion resources: versioning, encryption config, public access block, SSM parameter. Same 4-resource cluster for every future bucket.

**Boilerplate:** 47 lines per bucket

```hcl
module "model_artifacts_bucket" {
  source = "...//modules/s3_encrypted_bucket"

  name_suffix = "model-artifacts"
  kms_key_arn = module.platform.storage_kms_key_arn
  ssm_path    = "${var.ssm_root_path}/buckets/model-artifacts/name"
  name_prefix = local.name_prefix
  account_id  = local.account_id
  tags        = local.tags
}
```

**Lines saved:** ~42 per bucket (multiplicative for future buckets)

### Implementation Priority

| # | Module | Lines Saved | Complexity | Rationale |
|---|---|---|---|---|
| 1 | `modules/lambda` | ~306 | Medium | Highest savings; grows with every new Lambda |
| 2 | `modules/lambda_alarms` | ~154 | Low | Pure repetition; auto-derived threshold eliminates bugs |
| 3 | `modules/scheduled_lambda` | ~112 | Low | Trivial 3-resource pattern; most error-prone to wire manually |
| 4 | `modules/s3_encrypted_bucket` | ~42+ | Low | Small now but multiplicative for future buckets |

**Total:** ~651 lines extractable from 2,907 (22% reduction). The 78% remainder is legitimate domain logic.

### Cross-Cutting Concerns

- **KMS key selection:** `data_kms_key_arn` for DDB/logs, `storage_kms_key_arn` for S3. Modules accept explicit ARN — no implicit selection.
- **Tag propagation:** `merge(tags, { Name = "${name_prefix}-${name}" })` on named resources.
- **Log retention:** Default `1827` (5yr MiFID II) for domain Lambdas. Override for non-regulated ones.
- **VPC:** Only 2 of 7 Lambdas need VPC. `vpc_enabled` bool auto-selects IAM policy variant.

---

## IAM & Security Posture (Dev Phase — Accepted)

> **Status:** All permissive items below are **accepted for dev phase**. Each entry documents the current state and what production tightening looks like.

### Permissive Items (17 Total)

| # | Item | Current | Production Fix |
|---|---|---|---|
| 1 | `bedrock:*` on `*` (17 agent runtimes) | Full Bedrock access | Scope to `bedrock:InvokeModel` on `arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-*` |
| 2 | `bedrock-agentcore:*` on `*` (17 runtimes) | Full AgentCore access | Enumerate actions from CloudTrail, scope to specific runtime/gateway/memory ARNs |
| 3 | `bedrock-agentcore:*` on gateway/policy/runtime (Gateway role) | Broad AgentCore actions | Enumerate exact actions: `GetPolicyEngine`, `CheckAuthorizePermissions`, `AuthorizeAction` |
| 4 | KMS gateway `Resource: "*"` fallback | When `gateway_kms_key_arn = ""` | Always set `gateway_kms_key_arn` to eliminate `*` fallback |
| 5 | `codeartifact:GetAuthorizationToken` on `*` | AWS API requirement | Cannot be tightened — accepted |
| 6 | `cloudwatch:PutMetricData` on `*` | AWS API requirement | Cannot be tightened — accepted |
| 7 | `states:SendTaskSuccess/Failure` on `*` (2FA handler) | Dynamic task tokens | Scope to `arn:aws:states:eu-west-1:835618032093:execution:qitp-prod-*` |
| 8 | X-Ray actions on `*` | AWS API requirement | Cannot be tightened — accepted |
| 9 | SFN logging `logs:*` on `*` | AWS limitation | Scope `PutLogEvents/CreateLogStream` to specific log group ARNs |
| 10 | EventBridge trust: no `aws:SourceAccount` | Low risk in single-account | Add `StringEquals: { "aws:SourceAccount": "835618032093" }` |
| 11 | WAF disabled | `waf_enabled = false` | Enable WAF on artifacts API + dashboard ALB (code is ready) |
| 12 | Dashboard ALB SG: `0.0.0.0/0` on 80/443 | Public-facing app | Restrict to Cloudflare IPs if routing through CF |
| 13 | `COGNITO_MCP_CLIENT_SECRET` in env vars (17 runtimes) | Issue #809 bypass | Resolve AWS Issue #809, revert to Gateway-mediated calls |
| 14 | `LANGFUSE_SECRET_KEY` in env vars (17 runtimes) | SSM read at TF apply time | Implement runtime SSM fetch via SDK |
| 15 | KMS `kms:*` to root account (5 keys) | AWS recommended pattern | Evaluate per-service grants; keep unless compliance mandates |
| 16 | `localhost:3000` in Cognito callback URLs | Dev convenience | Remove in production |
| 17 | Secrets Manager rotation disabled (IBKR) | No IBKR connectivity yet | Implement rotation Lambda when paper mode available |

### KMS Key Matrix

| Key Alias | Purpose | Rotation | Access Scope |
|---|---|---|---|
| `qitp-dev-data` | DynamoDB, SQS | Annual | Risk engine, compliance, dashboard, agent runtimes |
| `qitp-dev-storage` | S3 buckets | Annual | CodeBuild, agent runtimes |
| `qitp-dev-secrets` | Secrets Manager | Annual | CloudWatch Logs service |
| `qitp-dev-platform-artifacts` | Platform-tier S3 `/platform/*` | Annual | Artifacts Lambda, agent runtimes |
| `qitp-dev-domain-artifacts` | Domain-tier S3 `/domain/*` | Annual | Artifacts Lambda, agent runtimes |

### Network Security

| Security Group | Inbound | Source | Notes |
|---|---|---|---|
| VPC Endpoints (11) | 443 | VPC CIDR only | Correct |
| Agent SG | 9000 (A2A) | Self-referencing | No internet inbound |
| MCP SG | 8080 | Agent SG only | **Note:** MCPs listen on 8000 but SG allows 8080 — config mismatch, not a security risk |
| Dashboard ALB | 80, 443 | `0.0.0.0/0` | Intentional — public web app |
| Dashboard ECS | 3000 | ALB SG only | Correct |

### Data Security

| Resource | Encryption at Rest | Public Access | Notes |
|---|---|---|---|
| All S3 buckets (5) | KMS (bucket_key_enabled) | Blocked (all 4 flags) | Two-tier enforcement on artifacts |
| All DynamoDB tables (15) | KMS (SSE enabled) | N/A | PITR enabled |
| Secrets Manager (3) | KMS | N/A | No rotation configured |
| CloudWatch Logs | KMS via key policy | N/A | 14 days dev (MiFID II audit in DynamoDB TTL) |

### Auth Configuration

| Component | Config | Notes |
|---|---|---|
| Cognito M2M | `client_credentials`, 1hr tokens, custom scopes | Good |
| Dashboard client | `code` flow, Google OAuth | `localhost:3000` in callbacks (dev) |
| Gateway authorizer | `CUSTOM_JWT` + Cognito discovery | Validates JWT on every tool call |
| API Gateway | `AWS_IAM` on all methods | No anonymous access |
| ALB | TLS 1.3 (`ELBSecurityPolicy-TLS13-1-2-2021-06`) | Modern policy |

### Security Positive Findings

- **Zero hardcoded credentials** in any `.tf` or `.py` file
- Google OAuth secret is `PLACEHOLDER` with `lifecycle { ignore_changes }` — intentional scaffolding
- IBKR MCP reads secrets via `secretsmanager:GetSecretValue` at runtime (correct pattern)
- All S3 buckets have 4-flag public access block
- All DynamoDB tables have KMS SSE + PITR

### Two Items to Watch for Production

1. **Items 13+14:** M2M client secret and Langfuse key as env vars in 17 Runtimes expose credentials via Runtime metadata API and potentially CloudWatch logs. Highest priority to remediate before live trading.
2. **MCP SG port mismatch:** SG allows 8080 but MCPs listen on 8000. Not exploitable but should be aligned.
