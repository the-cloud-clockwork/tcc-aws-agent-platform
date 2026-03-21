# Progress — AWS Agent Platform

> Tracks implementation status against the 12 building blocks defined in [VISION.md](./VISION.md).
> Each block lists what exists today, what's missing, and what needs to change to align with the vision.

---

## Block 1: Runtime — Where Agents Live

**Vision:** Agents run on AgentCore Runtime (microVM per session, port 8080, `@app.entrypoint`). NOT Lambda.

- [x] `runtime/entrypoint.py` — `AgentCoreApp` wraps `BedrockAgentCoreApp` with `@app.entrypoint` decorator
- [x] `runtime/handler.py` — `GenericHandler` dispatches by `agent_id` from event payload
- [x] `runtime/session.py` — `SessionManager` + `SessionState` for session lifecycle
- [x] `runtime/idempotency.py` — DynamoDB-backed idempotency store
- [x] `runtime/agent_config.py` — `AgentConfig` + `AgentConfigRegistry` for per-agent prompt builders
- [x] `runtime/adapter.py` — `InvocationContext` + `AgentPayload` + `AgentResult` for AgentCore Runtime
- [x] `runtime/marshal.py` — Output marshalling
- [x] Align `AgentCoreApp` with `BedrockAgentCoreApp` contract (`@app.entrypoint` decorator pattern)
- [x] Expose `POST /invocations` + `GET /ping` on port 8080 (Runtime contract)
- [x] Support `context.session_id` and `context.request_headers` in entrypoint
- [x] Add streaming support (`async def` + `yield` for SSE responses)
- [x] Add middleware support (Starlette middleware stack)
- [x] Add `.bedrock_agentcore.yaml` generation from blueprint YAML
- [x] Dockerfile template generation (ARM64, OTEL wrapper, port 8080/8000/9000)
- [x] Remove Lambda-as-agent-host assumptions — Lambda is for tools only
- [x] Add `runtime.type: agentcore` blueprint field (vs current `lambda`)
- [x] Add `idle_timeout_minutes`, `network_mode`, `protocol` to `RuntimeConfig` schema

---

## Block 2: Gateway — The Universal Tool Bridge

**Vision:** Agents consume all tools through a single Gateway URL via `MCPClient`. Gateway routes to Lambda, REST, OpenAPI, MCP servers. No direct MCP connections.

- [x] `gateway/client.py` — `GatewayClient` with `invoke_tool()`, `list_tools()`, `search_tools()`, `health_check()`
- [x] `gateway/target_registry.py` — `TargetRegistry` with `register_target()`, `synchronize_all()`, `load_targets_from_file()`
- [x] `gateway/tool_discovery.py` — `ToolDiscovery` with `find_tools()`, `find_tools_for_task()`
- [x] Replace custom HTTP `GatewayClient` with Strands `MCPClient` → Gateway URL pattern
- [x] Agent should consume Gateway as single MCP endpoint, not invoke tools via custom HTTP
- [x] Support `streamablehttp_client` with auth header injection (user JWT passthrough)
- [x] Support all 5 target types: Lambda, OpenAPI, MCP Server, Smithy, API Gateway
- [x] Wire `gateway_url` from platform infrastructure outputs (SSM/Terraform)
- [x] Support inbound auth on Gateway: `AWS_IAM` and `CUSTOM_JWT`
- [x] Support outbound auth: `GATEWAY_IAM_ROLE` and OAuth2 credential provider
- [x] Register domain MCP servers as Gateway targets (not direct ECS connections)
- [x] Add `gateway-targets.yaml` format for domain repos to declare their targets
- [x] Export `GatewayClient`, `ToolDiscovery` from `gateway/__init__.py` (currently empty)

---

## Block 3: Identity — Auth Flows Through the System

**Vision:** Four auth patterns (inbound JWT, outbound API key, 3LO OAuth, M2M) all declared in blueprint YAML. Platform injects `@requires_access_token` / `@requires_api_key` decorators.

- [x] `identity/providers.py` — `IdentityProvider` ABC, `Credential` dataclass, `ProviderRegistry`
- [x] `identity/__init__.py` — Exports `Credential`, `CredentialError`, `IdentityProvider`, `ProviderRegistry`
- [x] Implement concrete `IdentityProvider` subclasses (Cognito, Okta, Entra)
- [x] Implement `@requires_access_token` decorator (3LO OAuth + M2M patterns)
- [x] Implement `@requires_api_key` decorator (Secrets Manager retrieval)
- [x] Add `IdentityClient` wrapper for AgentCore Identity service CRUD
- [x] Wire inbound JWT validation into Runtime configuration (`authorizer_configuration`)
- [x] Wire outbound credential providers from blueprint `identity.credentials[]`
- [x] Support `auth_flow: USER_FEDERATION` (3LO) and `auth_flow: M2M` patterns
- [x] Add `on_auth_url` callback for user consent flow
- [x] Add credential caching layer (avoid repeated Secrets Manager calls)
- [x] Add `identity:` block to `AgentBlueprint` Pydantic schema
- [x] Blueprint → decorator injection in `BlueprintLoader.build_agent_session()`

---

## Block 4: Memory — Persistence Across Sessions

**Vision:** AgentCore Memory with short-term (events + TTL) and long-term (strategy extraction + pgvector + semantic retrieval). Wired via Strands `HookProvider` pattern.

- [x] `memory/manager.py` — `MemoryManager` with three tiers (short/long/episodic), semantic search
- [x] `memory/session_bridge.py` — SFN execution ID ↔ session ID mapping
- [x] `memory/branching.py` — `MemoryBranchManager` wrapping `MemorySessionManager`
- [x] Replace in-memory fallback with AgentCore Memory client (`bedrock_agentcore.memory.MemoryClient`)
- [x] Implement Strands `HookProvider` pattern for memory (not custom hooks)
  - [x] `on_agent_initialized` → load last K turns + retrieve semantic memories → inject into system prompt
  - [x] `on_message_added` → persist each turn via `create_event()`
- [x] Implement `create_memory_and_wait()` with strategy configuration
- [x] Support 4 strategy types: `USER_PREFERENCE`, `SEMANTIC`, `SUMMARY`, `EPISODIC`
- [x] Support namespace templates with `{actorId}` and `{sessionId}` placeholders
- [x] Implement memory branching via `MemorySessionManager` (replace in-memory POC)
  - [x] `fork_conversation()` for sub-agent branches
  - [x] `list_branches()` for coordinator reads
- [x] Implement `AgentCoreMemoryToolProvider` (memory as agent-callable tools)
- [x] Add `memory:` block to `AgentBlueprint` Pydantic schema
- [x] Wire `event_expiry_days`, `short_term_k` from blueprint config
- [x] Export `MemoryManager` from `memory/__init__.py` (currently empty)

---

## Block 5: Tools — Code Interpreter & Browser

**Vision:** AWS-managed tools (Code Interpreter, Browser) registered as Gateway targets. Agent sees them as regular tools alongside domain tools.

- [x] `tools/mcp_factory.py` — `create_mcp_client()` factory for Strands MCPClient
- [x] Add `builtin: code_interpreter` blueprint tool type
- [x] Add `builtin: browser` blueprint tool type
- [x] Register Code Interpreter as Gateway target (not custom integration)
- [x] Register Browser Tool as Gateway target
- [x] Support `AgentCoreBrowser` wrapper from `strands_tools.browser`
- [x] Support Code Interpreter sandboxed execution (`executeCode`, `executeCommand`, `writeFiles`)
- [x] Add tool mixing in `BlueprintLoader`: local + Gateway + builtin tools in single agent
- [x] Export `create_mcp_client` from `tools/__init__.py` (currently empty)

---

## Block 6: Observability — Tracing Agent Behavior

**Vision:** OTEL auto-instrumentation via `opentelemetry-instrument` wrapper. `trace_attributes` on every span. CloudWatch GenAI Observability.

- [x] `observability/__init__.py` — Lazy imports for 7 modules
- [x] `observability/langfuse_hook.py` — Strands callback for Langfuse tracing with cost tracking
- [x] `observability/audit_log.py` — DynamoDB audit event logging with TTL + dedup
- [x] `observability/cost_tracker.py` — Bedrock model token cost computation
- [x] `observability/xray_tracing.py` — X-Ray instrumentation
- [x] `observability/structured_logger.py` — Structured JSON logging
- [x] `observability/alerts.py` — SNS alert publishing
- [x] `hooks/observability.py` — `ObservabilityHook` Strands callback (lifecycle events)
- [x] `hooks/observability_hooks.py` — `CompositeObservabilityHook`
- [x] Add OTEL auto-instrumentation support (`aws-opentelemetry-distro`)
- [x] Generate Dockerfile with `opentelemetry-instrument` wrapper
- [x] Add `trace_attributes` support on Strands `Agent` constructor
- [x] Support OTEL baggage for session correlation (`session.id`, `user.id`)
- [x] Support custom span creation via `opentelemetry.trace.get_tracer()`
- [x] Add CloudWatch GenAI Observability dashboard generation
- [x] Add data protection layer (Bedrock Guardrails PII anonymization + CloudWatch masking)
- [x] Add `observability:` block to `AgentBlueprint` Pydantic schema
- [x] Wire `trace_attributes`, `langfuse.enabled`, `audit_log.ttl_years` from blueprint config

---

## Block 7: Evaluation — Measuring Agent Quality

**Vision:** AgentCore Evaluation reads OTEL traces, scores with LLM-as-judge. 13 built-in evaluators + custom domain judges. Online (continuous) and on-demand evaluation.

- [x] Create `evaluation/` subsystem directory
- [x] Implement `EvaluationClient` wrapper for AgentCore Evaluation service
- [x] Support on-demand evaluation: `run(agent_id, session_id, evaluators)`
- [x] Support 13 built-in evaluators:
  - [x] Response Quality: Correctness, Completeness, Faithfulness, Helpfulness, Harmlessness, Coherence, Relevance
  - [x] Task Completion: GoalSuccessRate
  - [x] Tool Usage: ToolSelectionAccuracy, ToolParameterAccuracy
  - [x] Safety: Harmfulness, Stereotyping
- [x] Support custom LLM-as-judge evaluators (`create_evaluator()`)
- [x] Support online evaluation (`create_online_config()` with sampling rate)
- [x] Add `evaluation:` block to `AgentBlueprint` Pydantic schema
- [x] Wire evaluator selection and sampling rate from blueprint config
- [x] Add `agentcli eval run` CLI command for on-demand evaluation
- [x] Add `agentcli eval status` CLI command for online eval results

---

## Block 8: Policy — Cedar Access Control

**Vision:** Cedar policies on Gateway control per-tool, per-user, per-parameter access. Simplified YAML rules → Cedar generation → Gateway attachment.

- [x] `policy/cedar_policies.py` — `CedarPolicy` dataclass, `CedarPolicyBuilder`, `PolicyEffect`/`PolicyAction` enums
- [x] Implement `PolicyClient` wrapper for AgentCore Policy Engine CRUD
- [x] Implement Gateway policy engine attachment (`update_gateway_policy_engine()`)
- [x] Support `ENFORCE` and `LOG_ONLY` modes
- [x] Implement simplified YAML → Cedar translation
  - [x] `allow` / `deny` rules with `when` / `unless` conditions
  - [x] Principal group matching from JWT claims
  - [x] Parameter constraints (`context.input.*`)
- [x] Implement NL2Cedar wrapper (`generate_policy()` from natural language)
- [x] Add `policy:` block to `AgentBlueprint` Pydantic schema
- [x] Wire policy rules from blueprint config → CedarPolicyBuilder → Gateway attachment
- [x] Export `CedarPolicy`, `CedarPolicyBuilder` from `policy/__init__.py` (currently empty)
- [x] Add `agentcli policy lint` CLI command for Cedar validation

---

## Block 9: Strands Integration — The Full Stack

**Vision:** `BlueprintLoader` produces a fully wired Strands `Agent` with BedrockModel + Gateway MCPClient + Memory HookProvider + Identity decorators + OTEL trace_attributes, all wrapped in `@app.entrypoint`.

- [x] `blueprints/loader.py` — `BlueprintLoader` loads YAML, resolves prompts, builds agent
- [x] `blueprints/agent.py` — `AgentBlueprint` Pydantic model (model, tools, runtime, hooks, multi_agent)
- [x] `blueprints/workflow.py` — `WorkflowBlueprint` (states, triggers, retry/catch)
- [x] `blueprints/session.py` — Agent session management
- [x] `blueprints/condition_parser.py` — Condition evaluation for choice states
- [x] `blueprints/workflow_executor.py` — Workflow state machine execution
- [x] Extend `build_agent_session()` to wire all 12 blocks from blueprint:
  - [x] `BedrockModel` from `model:` block (native Bedrock Converse API)
  - [x] Gateway tools via `MCPClient` from `tools:` block
  - [x] Memory `HookProvider` from `memory:` block
  - [x] Identity decorators from `identity:` block
  - [x] `trace_attributes` from `observability:` block
  - [x] Wrap in `@app.entrypoint` for AgentCore Runtime
- [x] Support tool mixing: local `@tool` + Gateway MCP + builtin tools in single agent
- [x] Add streaming agent support (`agent.stream_async()` with SSE)
- [x] Add multi-turn conversation support within a session
- [x] Add Strands `HookProvider` and `HookRegistry` integration
- [x] Export `AgentBlueprint`, `BlueprintLoader`, `WorkflowBlueprint` from `blueprints/__init__.py` (currently empty)

---

## Block 10: Agent-to-Agent Communication (A2A)

**Vision:** Agents discover and call each other via A2A protocol on port 9000. Agent cards at `/.well-known/agent-card.json`. M2M OAuth for cross-agent auth.

- [x] `blueprints/agent.py` — `MultiAgentConfig` with swarm/graph types, `GraphNodeConfig`, `GraphEdgeConfig`
- [x] Create `a2a/` subsystem directory
- [x] Implement `A2AServer` wrapper (Strands `A2AServer` on port 9000)
- [x] Implement agent card generation from blueprint metadata
- [x] Implement `A2AClient` for calling remote agents
  - [x] `A2ACardResolver` for agent discovery
  - [x] `ClientFactory` from agent card
  - [x] `send_message()` with streaming support
- [x] Wrap remote agent calls as Strands `@tool` functions (coordinator sees specialists as tools)
- [x] Wire M2M credential providers for cross-agent auth
- [x] Support direct `invoke_agent_runtime()` fallback (simple cases without A2A)
- [x] Add `multi_agent.role: coordinator | specialist` to blueprint
- [x] Add `multi_agent.nodes[].a2a_url` for remote agent endpoints
- [x] Generate A2A server in Dockerfile (expose port 9000)
- [x] Blueprint → A2AServer generation in `BlueprintLoader`

---

## Block 11: Infrastructure as Code — Terraform Modules

**Vision:** Migrate from CDK to Terraform modules. Domain repos consume via `module "platform" { ... }`. The platform is a deployable bundle.

- [x] `infra/stacks/` — 8 CDK stacks (Data, Network, Security, Agent, MCP, Observability, API, Workflow)
- [x] `infra/constructs_/` — 7 reusable CDK constructs
- [x] `infra/config/` — `dev.yaml`, `staging.yaml`, `production.yaml` environment configs
- [x] `infra/scripts/` — `build_mcps.sh`, `package_agents.sh`
- [ ] Create `modules/` directory for Terraform modules
- [ ] Create `modules/platform/` — Core platform infrastructure module
  - [ ] VPC, security groups, NAT
  - [ ] AgentCore Runtime configuration
  - [ ] AgentCore Gateway creation
  - [ ] AgentCore Memory resource
  - [ ] Cognito user pool + identity providers
  - [ ] KMS CMKs + Secrets Manager
  - [ ] CloudWatch dashboards + SNS alerts
  - [ ] DynamoDB tables (audit, idempotency, prompts, artifacts)
  - [ ] S3 buckets (prompts, artifacts)
  - [ ] ECR repositories
- [ ] Create `modules/agents/` — Agent deployment module
  - [ ] Read blueprint YAML → configure AgentCore Runtime per agent
  - [ ] Register Gateway targets from `gateway-targets.yaml`
  - [ ] Configure Memory strategies per agent
  - [ ] Attach Cedar policies per agent
  - [ ] Configure evaluation per agent
  - [ ] Build + push Docker images to ECR
- [ ] Create `modules/workflows/` — Workflow deployment module
  - [ ] Read workflow YAML → generate Step Functions state machines
- [ ] Output platform values via SSM parameters and Terraform outputs
- [ ] Support `terraform apply -var="environment=production"` workflow
- [ ] Document migration path from CDK → Terraform

---

## Block 12: Blueprints — The Configuration Abstraction

**Vision:** YAML files declare everything an agent needs across all 12 blocks. Three types: Agent, Strategy, Workflow. The platform assembles the full stack from configuration.

- [x] `blueprints/agent.py` — `AgentBlueprint` with model, tools, runtime, execution_modes, hooks, multi_agent, artifacts
- [x] `blueprints/loader.py` — `BlueprintLoader` with `load_agent()`, `load_strategy()`, `load_workflow()`, `build_agent_session()`
- [x] `blueprints/workflow.py` — `WorkflowBlueprint` with states, triggers, retry/catch, parallel branches
- [x] `schemas/model_config.py` — `ModelConfig` (provider, model_id, temperature, max_tokens)
- [x] `schemas/tool_config.py` — `ToolConfig` (mcp server name, tool list)
- [x] `schemas/execution_modes.py` — `ExecutionModes` with alias support
- [x] `schemas/runtime_config.py` — `RuntimeConfig`
- [ ] Add `identity:` block to AgentBlueprint schema
  - [ ] `authorizer` (type, user_pool_id, client_id)
  - [ ] `credentials[]` (name, type, provider, scopes)
- [x] Add `memory:` block to AgentBlueprint schema
  - [x] `strategies[]` (type, name, namespace)
  - [x] `event_expiry_days`, `short_term_k`
- [ ] Add `observability:` block to AgentBlueprint schema
  - [ ] `trace_attributes`, `langfuse.enabled`, `audit_log.enabled`
- [ ] Add `evaluation:` block to AgentBlueprint schema
  - [ ] `online.sampling_rate`, `online.evaluators[]`
  - [ ] `custom_evaluators[]` (name, instructions, scale)
- [ ] Add `policy:` block to AgentBlueprint schema
  - [ ] `engine`, `mode`, `rules[]` (name, allow/deny, when/unless)
- [ ] Extend `tools:` to support `builtin: code_interpreter | browser`
- [ ] Extend `runtime:` with `type: agentcore`, `idle_timeout_minutes`, `network_mode`, `protocol`
- [ ] Extend `multi_agent:` with `role`, `nodes[].a2a_url`
- [ ] Add `StrategyBlueprint` Pydantic model (currently parsed but not fully validated)
- [ ] Add full blueprint validation in `agentcli blueprint lint` (all 12 blocks)
- [ ] Add `agentcli deploy` command that reads blueprint → builds container → pushes ECR → creates Runtime
