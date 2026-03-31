# SPECS.md — Technical Specifications

> **Last updated:** 2026-03-31
> **Status:** Active
> **Sources:** Distilled from `operator/references/CONCEPTS.md`, `operator/references/TECHNICAL-GUIDE.md`, `operator/references/PLATFORM-REFERENCE.md`

---

## 1. Architecture Overview

### System Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Amazon Bedrock AgentCore                            │
│                                                                             │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐   │
│  │   AgentCore Runtime      │◄──►│  AgentCore Gateway                  │   │
│  │  ┌────────────────────┐  │    │  (Lambda → MCP, REST → MCP,         │   │
│  │  │ Strands Agents SDK │  │    │   OpenAPI → MCP, Smithy → MCP)      │   │
│  │  ├────────────────────┤  │    ├──────────────────────────────────────┤   │
│  │  │ Platform SDK       │  │    │  AgentCore Browser (CDP, Nova Act)   │   │
│  │  │ (agent-core)       │  │    ├──────────────────────────────────────┤   │
│  │  └────────────────────┘  │    │  AgentCore Code Interpreter         │   │
│  └─────────┬────────────────┘    └──────────────┬───────────────────────┘   │
│            │                                     │                          │
│  ┌─────────▼────────────────┐    ┌──────────────▼───────────────────┐      │
│  │   AgentCore Memory       │    │     AgentCore Identity           │      │
│  │  (pgvector, TTL,         │    │  (OAuth 2.0, Cognito, Okta,     │      │
│  │   namespaces, strategies)│    │   Entra, 3LO, M2M, API Keys)   │      │
│  └──────────────────────────┘    └──────────────────────────────────┘      │
│  ┌──────────────────────────┐    ┌──────────────────────────────────┐      │
│  │   AgentCore Evaluation   │    │     AgentCore Policy (Cedar)     │      │
│  │  (13 built-in + custom   │    │  (FGAC, NL2Cedar, per-tool      │      │
│  │   LLM-as-judge)          │    │   access control per identity)  │      │
│  └──────────────────────────┘    └──────────────────────────────────┘      │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │   CloudWatch GenAI Observability (OTEL traces, spans, metrics)  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Platform Module Map

| Module | Package | Purpose |
|--------|---------|---------|
| `core/` | `agent-core` (CodeArtifact) | Blueprint engine, runtime, hooks, schemas, observability, gateway, memory, identity, policy, evaluation, A2A, MCP base classes |
| `prompts/` | `prompt-registry` (CodeArtifact) | Versioned prompt management — S3 + DynamoDB + mode-gated resolution |
| `artifacts/` | `mcp-artifacts` (Docker) | Artifact store MCP server — S3 + DynamoDB + signed URLs + claim-check pattern |
| `cli/` | `agent-cli` (pip) | CLI for blueprint validation, prompt management, strategy lifecycle |
| `modules/` | Terraform IaC | 3 Terraform modules (platform, agents, workflows) |

### SDK Subsystem Map

| Subsystem | Key Classes | Purpose |
|-----------|-------------|---------|
| `blueprints/` | `BlueprintLoader`, `AgentSession`, `AgentBlueprint` | YAML → Pydantic → Strands Agent builder (full lifecycle wiring) |
| `runtime/` | `AgentCoreApp`, `GenericHandler`, `SessionManager` | `@app.entrypoint` + dispatch + idempotency + marshalling |
| `gateway/` | `GatewayClient`, `DirectMCPClient`, `ToolDiscovery` | SigV4/JWT auth, Gateway tool consumption, Issue #809 bypass |
| `memory/` | `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager` | Short-term events + long-term semantic retrieval + multi-agent branching |
| `observability/` | `LangfuseHook`, `AuditLogWriter`, `XRayTracer`, `CostTracker` | Composable hook chain for tracing, audit, cost |
| `tools/` | `CodeInterpreterProvider`, `BrowserProvider`, `BuiltinToolWiring` | Gateway-mediated builtin tool access |
| `identity/` | `IdentityProvider`, `IdentityClient`, `CredentialCache` | Cognito/Entra/Okta providers + API key creds + `@requires` decorators |
| `evaluation/` | `EvaluationClient`, `BuiltinEvaluators` (13) | On-demand + online evaluation pipelines |
| `policy/` | `PolicyClient`, `CedarPolicyBuilder`, `PolicyTranslator` | Cedar policies + NL2Cedar + versioning + Gateway enforcement |
| `a2a/` | `A2AServerWrapper`, `A2AClient`, `A2AWiring` | Agent-to-Agent protocol (client + server + @tool wrappers) |
| `mcp/` | `BaseMCPServer`, `cache`, `resolve_provider`, `VersionedS3Store` | Base MCP server infrastructure |
| `schemas/` | `AgentBlueprint`, `StrategyBlueprint`, `WorkflowBlueprint` | Pydantic models for all configuration |
| `hooks/` | `CompositeObservabilityHook` | Factory that composes all observability hooks |
| `prompt/` | `PromptRegistryClient` | Lambda + HTTP + local fallback prompt resolution |
| `api/` | Artifacts REST API + MCP handler | Artifact store REST interface |

### How Domain Repos Consume This Platform

```
Domain repo
  └── agents/        → imports agent-core from CodeArtifact
  └── mcps/          → imports agent_core.mcp.* for base server, cache, routing
  └── infra/         → consumes modules/ via source = "git::repo.git//modules/platform"
```

Platform deploys FIRST. Domain repos deploy SECOND.

---

## 2. Runtime Contract

### AgentCore Runtime

Container contract: expose `POST /invocations` + `GET /ping` on port 8080. AgentCore provides:

- Per-session microVM isolation (Firecracker-based)
- Auto-scaling with warm container pools
- Session affinity with idle timeout (configurable, default 15min) and max lifetime (8hr)
- IAM SigV4 or JWT/Cognito inbound auth
- OTEL auto-instrumentation via `aws-opentelemetry-distro`
- MCP protocol support (`server_protocol: MCP`) on port 8000
- A2A protocol support on port 9000
- `network_mode: PRIVATE` for VPC-only deployments

**Constraints:**
- ARM64 only (Graviton). No x86
- No SSH. No sidecars. No custom networking beyond PUBLIC/PRIVATE
- Max 8hr session lifetime

**Port conventions:** 8080 (HTTP invocations), 8000 (MCP), 9000 (A2A)

### Blueprint-to-Runtime Flow

```
Blueprint YAML → BlueprintLoader → AgentCoreApp(@app.entrypoint) → Docker → ECR → AgentCore Runtime → microVM
```

One handler serves every agent. The YAML blueprint determines model, tools, prompts, memory strategies, identity providers, and Cedar policies.

### Why Not Lambda for Agents

Agents are stateful, long-running, session-oriented (multi-turn, tool-use loops with 5-20+ iterations, streaming SSE). Lambda is for tools — short, stateless, fast. Gateway bridges agents to Lambda-backed tools.

```
Agent (microVM, long-running, stateful) → Gateway (MCP proxy) → Lambda (short, fast, stateless)
```

---

## 3. Gateway — Universal Tool Bridge

Gateway auto-generates a single MCP interface regardless of backend type. Protocol translator, not just a proxy.

### Target Types

| Type | Config Key | Auth |
|------|-----------|------|
| Lambda | `mcp.lambda` | `GATEWAY_IAM_ROLE` |
| Runtime MCP Server | Target URL = runtime endpoint | OAuth2 credential provider |
| OpenAPI | `mcp.openApi` | Configurable |
| Smithy | `mcp.smithyApi` | Configurable |
| External MCP | `mcp.mcpServer` | Configurable |
| API Gateway | `mcp.apiGateway` | Configurable |

### Two Auth Layers

**Inbound:** Who can call the Gateway
- `AWS_IAM` — SigV4 signed requests (agents with correct IAM role)
- `CUSTOM_JWT` — JWT from Cognito (end-user identity flows through)

**Outbound:** How Gateway authenticates to targets
- `GATEWAY_IAM_ROLE` — Gateway assumes own IAM role for Lambda targets
- OAuth2 credential provider — M2M token for OAuth-protected targets

User identity flows as context, not as credentials.

### Tool Mixing Pattern

```python
tools = [
    internal_lookup,              # Local Python function
    browser.browser,              # AgentCore Browser (hosted Chromium)
    *mcp_client.list_tools_sync() # Gateway tools (Lambda/REST/OpenAPI behind MCP)
]
agent = Agent(model=model, tools=tools)
```

Agent sees all tools as equivalent — doesn't know or care where they run.

### Known Issue: Gateway MCP tools/call Bug (KI-001)

Gateway returns internal error for `tools/call` to MCP runtime targets. `tools/list` works. Workaround: `GATEWAY_DIRECT_MCP=true` bypasses Gateway for MCP tool calls using Cognito JWT directly. See `operator/KNOWN-ISSUES.md` for details.

---

## 4. Identity — Auth Patterns

### Pattern 1: Inbound Auth (JWT)
Runtime validates JWT before code runs. Invalid tokens get `AccessDeniedException`.

### Pattern 2: Outbound Auth — API Keys
`@requires_api_key(provider_name=...)` decorator injects key from Secrets Manager at runtime. Key never touches codebase or container image.

### Pattern 3: Outbound Auth — 3-Legged OAuth
Agent needs user's OAuth consent for external services (Google, GitHub). Uses nested function pattern so `@requires_access_token` doesn't expose `access_token` to LLM tool schema.

### Pattern 4: M2M Auth
Agent-to-agent via `client_credentials` grant. Each agent gets own Cognito client credentials. Identity service handles token refresh.

---

## 5. Memory — Persistence Across Sessions

### Two Tiers

**Short-term:** Raw event storage. Push conversation turns in, pull them back out. Buffer for continuing conversations. TTL: 7-365 days.

**Long-term:** Strategy-based extraction. Asynchronously extracts structured knowledge (~30s) into pgvector for semantic retrieval.

### Strategy Types

| Type | API Key | Status |
|------|---------|--------|
| `SEMANTIC` | `semanticMemoryStrategy` | Supported |
| `SUMMARY` / `SUMMARIZATION` | `summaryMemoryStrategy` | Supported |
| `USER_PREFERENCE` | `userPreferenceMemoryStrategy` | Supported |
| `EPISODIC` | `episodicMemoryStrategy` | **Not supported via simple type string** — requires compound dict with `reflectionConfiguration` |
| `CUSTOM` | `customMemoryStrategy` | Not supported via current TF resource |

### Wiring Flow

```
Blueprint YAML (memory.strategies[])
  → BlueprintLoader._wire_memory()
      → MemoryManager (wraps MemoryClient)
      → MemoryHookProvider → registered into Strands hooks
      → MemoryBranchManager → for multi-agent branching

At agent init (AgentInitializedEvent):
  → get_last_k_turns() + retrieve_memories()

At each message (MessageAddedEvent):
  → create_event()

Memory resource creation → Terraform ONLY (modules/agents/memory_strategies.tf)
```

### Namespacing

- `/preferences/{actorId}/` — per-user, shared across sessions
- `/facts/{actorId}/` — per-user, shared across sessions
- `/summaries/{actorId}/{sessionId}/` — per-session

### Memory Branching (Multi-Agent)

Coordinator writes to "main" branch. Sub-agents fork to own branches. Coordinator reads from any branch.

---

## 6. Observability

### Runtime-Hosted (Automatic)

Include `aws-opentelemetry-distro` in Docker image + wrap entrypoint with `opentelemetry-instrument`. No code changes.

### Captured Data

- Agent invocation sequences (full call graph)
- LLM calls (prompts, responses, token counts, model ID)
- Tool invocations (name, parameters, results, latency)
- Error paths and exceptions
- Custom spans and events

### Strands Integration

```python
agent = Agent(model=model, tools=[...],
    trace_attributes={"user.id": "...", "environment": "production"})
```

### Data Protection

1. **Bedrock Guardrails** — anonymize PII in responses before traces
2. **CloudWatch Logs Data Protection** — mask PII patterns at rest

---

## 7. Evaluation

### 13 Built-in Evaluators

| Category | Evaluators |
|----------|-----------|
| Response Quality | Correctness, Completeness, Faithfulness, Helpfulness, Harmlessness, Coherence, Relevance |
| Task Completion | GoalSuccessRate |
| Tool Level | ToolSelectionAccuracy, ToolParameterAccuracy |
| Safety | Harmfulness, Stereotyping |

### Modes

- **On-demand:** Score specific sessions after-the-fact via OTEL trace replay
- **Online (continuous):** Sample N% of live sessions, auto-score, feed to GenAI Observability dashboard
- **Custom LLM-as-judge:** Domain-specific evaluators with configurable rating scales

---

## 8. Policy — Cedar Access Control

Policy engine sits between Gateway and targets. **Default action is DENY.**

### How It Works

```
Agent → Gateway → Policy Engine (Cedar) → ALLOW/DENY → Target
```

Cedar evaluates: Principal (JWT claims), Action (tool name), Resource (gateway), Context (tool input parameters).

### Modes

- `ENFORCE` — blocks unauthorized calls
- `LOG_ONLY` — monitors without blocking (testing mode)

### Key Insight

Policy operates at Gateway level, not Runtime. Agent doesn't need to know about policies. Decisions based on end-user JWT claims, not agent identity.

---

## 9. Agent-to-Agent Communication (A2A)

### Two Patterns

**A2A Protocol:** Agent card discovery at `/.well-known/agent-card.json` + standardized messaging. Cross-framework interoperability. Auth via M2M OAuth.

**Direct boto3 invocation:** Simpler. `invoke_agent_runtime()` — no discovery, no standard protocol.

### A2A on AgentCore

Each agent runs A2A on port 9000. Agent URL: `https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations/.well-known/agent-card.json`

---

## 10. Infrastructure (Terraform)

### Module Architecture

```
platform/ (root composition)
  ├── modules/network/        VPC, subnets, NAT, security groups
  ├── modules/security/       5 KMS keys, Secrets Manager, WAF, VPC endpoints
  ├── modules/data/           5 DynamoDB tables, 4 S3 buckets, SQS, CloudFront
  ├── modules/agentcore/      Gateway, Memory, OAuth2, Cognito, builtins
  ├── modules/observability/  CloudWatch, SNS, X-Ray, dashboard
  ├── modules/api/            REST API Gateway, Lambda (artifacts)
  └── modules/prompt_registry/ Lambda + Function URL

agents/ (blueprint-driven for_each)
  ├── Per-agent IAM, ECR, CodeBuild, Runtime, Gateway targets
  ├── Memory strategies, Identity providers
  └── Docker builds

workflows/ (Step Functions from YAML)
  ├── YAML parsing + ref extraction
  ├── ASL generation
  └── Schedule + event triggers
```

### Provider Requirements

- Terraform >= 1.10
- AWS provider >= 6.21 (includes `aws_bedrockagentcore_*` resources)

### Terraform Resource Types

| Resource | Purpose |
|----------|---------|
| `aws_bedrockagentcore_agent_runtime` | Managed container runtime |
| `aws_bedrockagentcore_browser` | Hosted browser tool |
| `aws_bedrockagentcore_code_interpreter` | Sandboxed code execution |
| `aws_bedrockagentcore_memory` | Vector memory (pgvector) |
| `aws_bedrockagentcore_gateway` | MCP gateway |
| `aws_bedrockagentcore_gateway_target` | Backend target for gateway |

### Encryption

5 KMS keys: `data` (DynamoDB/SQS), `storage` (S3), `secrets` (Secrets Manager), `platform_artifacts`, `domain_artifacts`. Every data store must use the correct key. Never AES256 when KMS is available.

---

## 11. Dependencies

| Package | Required | Purpose |
|---------|----------|---------|
| `bedrock-agentcore` | **Hard** | Core SDK — Runtime, Memory, Identity, Tools |
| `strands-agents` | **Hard** | Primary agent framework — Agent, @tool, HookProvider, MCPClient |
| `strands-agents-tools` | Hard | Built-in tools — file ops, browser, memory tool provider |
| `bedrock-agentcore-starter-toolkit` | Hard | CLI + higher-level SDK — Runtime, Evaluation, PolicyClient |
| `aws-opentelemetry-distro` | Hard (Docker) | OTEL auto-instrumentation |
| `mcp` | Hard | MCP protocol SDK — FastMCP, streamablehttp_client |

**No fallbacks.** If `bedrock_agentcore` or `strands` are missing, fail loudly.

---

## 12. Constraints

1. **Zero domain contamination** — `domain-scan.sh` must return zero hits
2. **No hardcoded defaults** — All values from blueprints/env/config
3. **No backward compatibility** — No fallbacks, no dual paths, no `try/except ImportError`
4. **ARM64 only** — AgentCore Runtime uses Graviton. No x86 containers
5. **Configuration-driven** — All resource names from config, not hardcoded
6. **Claim-check pattern** — Large outputs in S3, only keys through Step Functions
7. **IaC: Terraform only** — `modules/` is the sole infrastructure source
8. **Blueprint-driven scaling** — `for_each` over YAML blueprints. Never hardcode agent counts

---

## 13. Not Yet Designed

| Area | Open Questions |
|------|---------------|
| EPISODIC memory strategy | TF resource doesn't support compound `episodicMemoryStrategy` shape. Needs custom resource or provider update |
| AG-UI Protocol | Standardized streaming for dashboard chat. March 2026 release, no SDK integration yet |
| Memory Streaming to Kinesis | Event-driven reactions to memory updates. March 2026 feature |
| Server-Side Tool Execution | Bedrock Responses API + Gateway eliminates client-side tool orchestration |
| Platform reusable modules | `modules/lambda`, `modules/scheduled_lambda`, `modules/lambda_alarms`, `modules/s3_encrypted_bucket` not yet built |
