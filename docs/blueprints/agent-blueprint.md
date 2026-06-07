---
title: Agent Blueprint
nav_order: 1
parent: Blueprints
---

# Agent Blueprint

An agent blueprint is a YAML file that fully declares an AI agent. Every configurable aspect — the model and inference provider, runtime configuration, tools, memory, identity, observability, and access-control policy — is expressed here. The platform reads this file at both SDK load time (for runtime wiring) and Terraform plan time (for infrastructure provisioning).

**Required fields:** `id`, `version`, `name`, `model`, `prompt_ref`. Every other top-level block is optional and has a safe default.

---

## Identity Fields

```yaml
id: researcher                  # Unique agent identifier. Kebab-case by convention.
name: Research Agent            # Human-readable name displayed in dashboards.
version: "1.0.0"               # Semantic version. Stamped on Runtime and ECR tags.
description: Researches topics  # Optional. Used as Runtime description in AWS console.
prompt_ref: researcher-system-v1  # Required. Prompt Registry key (string).
```

`prompt_ref` is a **required plain string** referencing a versioned prompt in the Prompt Registry. It is not a nested object.

---

## `model:` Block

Declares the LLM this agent uses. **`model_id`, `temperature`, and `max_tokens` are required** — the platform never assumes defaults for sampling parameters. `provider` defaults to `bedrock`.

### Provider: `bedrock` (default)

```yaml
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.3
  max_tokens: 4096
  cache_prompt: default          # Prompt caching policy. default | none | <custom key>
  cache_tools: default           # Tool-result caching policy.
```

The Bedrock region is resolved from the `BEDROCK_REGION` environment variable, which **must** be set — `BlueprintLoader` raises `BlueprintLoadError` if it is absent. There is no `region` field on `ModelConfig`.

### Provider: `anthropic`

Calls the Anthropic API directly (not via Bedrock).

```yaml
model:
  provider: anthropic
  model_id: claude-sonnet-4-5
  temperature: 0.3
  max_tokens: 4096
  api_key_env: ANTHROPIC_API_KEY   # Optional. Env var holding the Anthropic API key.
```

{: .note }
> `temperature` is required by the schema but is **not forwarded** to `AnthropicModel` at runtime — only `model_id` and `max_tokens` are passed. Declare it for schema compliance; it has no effect on Anthropic inference.

### Provider: `litellm`

Routes requests through any LiteLLM-compatible proxy (LiteLLM server, vLLM, Ollama with OpenAI adapter, etc.).

```yaml
model:
  provider: litellm
  model_id: claude-sonnet-4-6           # Model name as the proxy expects it.
  temperature: 0.3
  max_tokens: 4096
  base_url: https://llm.example.com     # Proxy base URL. Required for proxy routing.
  api_key_env: LITELLM_API_KEY          # Optional. Env var holding the proxy API key.
  extra_headers_env:                    # Optional. Header name → env var name map.
    CF-Access-Client-Id: CF_CLIENT_ID   # Header resolved from $CF_CLIENT_ID at runtime.
    CF-Access-Client-Secret: CF_CLIENT_SECRET
```

**How `base_url` works:** When `base_url` is set, the loader sets `custom_llm_provider="openai"` in the LiteLLM client arguments. This tells the litellm library to treat the endpoint as OpenAI-compatible and route all requests to `base_url`, regardless of what the model name looks like. Without this flag, litellm's model-name heuristic would detect `claude-*` or `gemini-*` and attempt to route to the native provider endpoint instead of your proxy.

`model_id` is passed through unchanged — set it to the exact string your proxy expects.

`temperature` and `max_tokens` are passed as LiteLLM `params`, not as constructor arguments.

`extra_headers_env` is a map of HTTP header name to environment variable name. Each entry is resolved at runtime: if the env var is set and non-empty, the header is included in every request. This is the correct way to pass Cloudflare Access service tokens or similar per-request credentials.

**Version constraint:** The platform pins `litellm>=1.83.0,<2`. Versions 1.82.7 and 1.82.8 were subject to a supply-chain attack (CVE-2026-33634) and must not be used.

### Provider: `vertex`

Uses the Strands `GeminiModel` backed by Google Vertex AI.

```yaml
model:
  provider: vertex
  model_id: gemini-2.0-flash    # Supports ${VAR} expansion via os.path.expandvars.
  temperature: 0.3              # Required by schema; not forwarded to GeminiModel.
  max_tokens: 4096              # Required by schema; not forwarded to GeminiModel.
```

{: .note }
> For `vertex`, only `model_id` is forwarded to `GeminiModel`. `temperature`, `max_tokens`, `api_key_env`, `base_url`, and `extra_headers_env` are not wired by the loader. Vertex credentials are resolved from the environment via `GOOGLE_APPLICATION_CREDENTIALS`, `VERTEX_PROJECT`, and `VERTEX_LOCATION` — set these in your Runtime environment, not in the blueprint.

### `model:` Field Reference

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `provider` | `str` | No | `bedrock` | `bedrock` \| `anthropic` \| `litellm` \| `vertex` |
| `model_id` | `str` | **Yes** | — | Supports `${VAR:-default}` expansion |
| `temperature` | `float` | **Yes** | — | `0.0`–`1.0` |
| `max_tokens` | `int` | **Yes** | — | Must be `> 0` |
| `cache_prompt` | `str` | No | `default` | `default` \| `none` \| custom key |
| `cache_tools` | `str` | No | `default` | Tool-result caching policy |
| `base_url` | `str` | No | `null` | Used by `litellm`; ignored by others |
| `api_key_env` | `str` | No | `null` | Env var name holding the API key |
| `extra_headers_env` | `dict[str,str]` | No | `null` | Header → env var name map; `litellm` only |

---

## `runtime:` Block

Controls how the agent runs on AgentCore Runtime (microVM, one per session, port 8080).

```yaml
runtime:
  type: agentcore                 # Always agentcore — the only supported runtime type.
  max_iterations: 10              # Maximum agentic loop iterations per session.
  max_execution_time: 300         # Hard timeout in seconds.
  idle_timeout_minutes: 30        # Session idle timeout before microVM terminates.
  network_mode: PUBLIC            # PUBLIC (internet-facing) | PRIVATE (VPC-only).
  protocol: HTTP                  # HTTP (standard agents) | MCP (hosted MCP servers).
  port: 8080                      # Container listen port for /invocations and /ping.
  a2a_port: 8081                  # A2A server port. 0 = disabled. Required for role=specialist.
  platform: linux/arm64           # linux/arm64 (Graviton, required for AgentCore) | linux/amd64.
  observability_enabled: true     # Enable OTEL auto-instrumentation in the container image.
```

For `PRIVATE` network mode, VPC subnet IDs and security group IDs are resolved from platform module outputs and wired automatically by Terraform.

`observability_enabled` controls the OTEL `opentelemetry-instrument` wrapper in the Dockerfile — this is the infrastructure-level telemetry toggle. Application-level observability (Langfuse, audit log, cost tracking) is controlled separately by `observability.enabled`.

---

## `tools:` Block

Declares which tools the agent can call. Three tool declaration types are supported and can be mixed freely.

### MCP Tools (via Gateway)

```yaml
tools:
  - mcp: data-service-mcp          # MCP server name registered as a Gateway target.
    tools:
      - query_records              # Individual tool names to expose from this server.
      - list_schemas
      - describe_table

  - mcp: content-mcp
    tools:
      - fetch_document
      - summarize_text
```

### Built-in AWS Managed Tools

```yaml
tools:
  - builtin: code_interpreter      # Sandboxed Python execution environment.
    network_mode: PRIVATE          # PUBLIC | PRIVATE (default: PUBLIC).

  - builtin: browser               # Headless browser for web research.
    network_mode: PUBLIC
```

Built-in tools are discovered dynamically from the Gateway at runtime — the platform filters Gateway tools by the `code-interpreter::` and `browser::` name prefixes respectively. Their lifecycle is fully managed by AgentCore; the platform makes no local SDK calls. Both must also be enabled in the platform module via `builtin_code_interpreter_enabled` and `builtin_browser_enabled` variables.

### A2A Remote Agent Tools

```yaml
tools:
  - a2a: specialist-agent          # Blueprint ID or A2A URL of a remote agent.
```

Wraps a remote A2A-capable agent as a callable tool within this agent's tool list. The platform resolves the agent card from `/.well-known/agent.json` on the remote endpoint and surfaces its skills as tools.

---

## `gateway:` Block

Configures how the agent connects to AgentCore Gateway for tool access.

```yaml
gateway:
  url: null                        # Gateway URL. Defaults to AGENTCORE_GATEWAY_URL env var.
  auth_type: aws_iam               # aws_iam | custom_jwt | none
  jwt_env_var: null                # Env var holding the JWT (for custom_jwt auth only).
  region: null                     # AWS region for SigV4 signing. Defaults to AWS_REGION.
  service_name: bedrock-agentcore  # AWS service name for SigV4 signing.
```

`auth_type: aws_iam` uses SigV4 signing. The platform prefers the `mcp-proxy-for-aws` library for SigV4 transport when available, and falls back to a bundled implementation if not installed.

`auth_type: none` is for local development only and must not be used in production.

---

## `identity:` Block

Controls inbound authorisation (who can call this agent) and outbound credentials (what external services the agent can authenticate to).

### Inbound Authorizer

```yaml
identity:
  authorizer:
    type: custom_jwt               # custom_jwt | cognito_jwt | aws_iam
    discovery_url: https://auth.example.com/.well-known/openid-configuration
    allowed_clients:
      - client-app-id-1
      - client-app-id-2
```

For `cognito_jwt`, both `user_pool_id` and `client_id` are required (schema-enforced):

```yaml
  authorizer:
    type: cognito_jwt
    user_pool_id: ${USER_POOL_ID}
    client_id: ${COGNITO_CLIENT_ID}
```

### Outbound Credentials

Two credential types are supported: `api_key` and `oauth2`. All credential resolution delegates to AgentCore Identity — there is no local env-var fallback.

```yaml
identity:
  credentials:
    # API key credential
    - name: data-api-key
      type: api_key
      provider: DataServiceApiKey  # Provider name registered in AgentCore Identity.

    # OAuth2 M2M (machine-to-machine / client credentials)
    - name: internal-service-token
      type: oauth2
      provider: InternalServiceOAuth
      scopes:
        - read:records
        - write:records
      auth_flow: M2M

    # OAuth2 USER_FEDERATION (three-legged / delegated user auth)
    - name: user-delegated-token
      type: oauth2
      provider: UserDelegatedOAuth
      scopes:
        - openid
        - profile
      auth_flow: USER_FEDERATION
      callback_url_env: OAUTH_CALLBACK_URL
```

---

## `memory:` Block

Configures AgentCore Memory integration. Memory is enabled automatically when `strategies` is non-empty — there is no `mode` field. The `AGENTCORE_MEMORY_ID` environment variable must be set at runtime; `BlueprintLoader` raises `BlueprintLoadError` if it is absent when strategies are declared.

The canonical strategy type for summarisation is `SUMMARY`. `SUMMARIZATION` is accepted as an alias and normalised automatically.

```yaml
memory:
  strategies:
    - type: SEMANTIC              # SEMANTIC | SUMMARY | USER_PREFERENCE | EPISODIC
      name: knowledge-base
      namespace: "{actorId}/knowledge"   # Supports {actorId} and {sessionId} placeholders.

    - type: USER_PREFERENCE
      name: preferences
      namespace: "{actorId}/preferences"

    - type: SUMMARY               # SUMMARIZATION is accepted as an alias.
      name: session-summaries
      namespace: "{actorId}/{sessionId}/summary"

  event_expiry_days: 30           # Short-term event TTL. Range: 1–365. Default: 30.
  short_term_k: 5                 # Last-K turns injected at agent init. Default: 5.
  enable_tool_provider: false     # Expose memory_recall / memory_record as agent tools.
  retrieval:
    - namespace: "{actorId}/knowledge"   # Namespaces queried on agent initialisation.
      top_k: 10                          # Default: 5. Range: 1–100.
      relevance_score: 0.4              # Default: 0.3. Range: 0.0–1.0.
```

Long-term memory extraction is asynchronous — strategy results typically appear within ~30 seconds of the source conversation turn. Short-term events respect the `event_expiry_days` TTL; long-term strategy-extracted memories persist until explicitly deleted.

---

## `observability:` Block

Controls application-level tracing, audit logging, dashboards, and data protection. Setting `enabled: false` skips all hooks in this section (Langfuse, audit log, structured logger, cost tracker).

```yaml
observability:
  enabled: true                   # Master toggle for all application-level observability.
  trace_attributes:               # Static key-value pairs on every OTEL span.
    team: platform
    tier: core

  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY   # Env var holding the Langfuse public key.
    secret_key_env: LANGFUSE_SECRET_KEY
    host_env: LANGFUSE_HOST
    tags:
      - production

  audit_log:
    enabled: true
    ttl_days: 1825                         # Retention period. Default: 1825 (~5 years).
    table_env: AUDIT_LOG_TABLE             # Env var holding DynamoDB table name.

  dashboard:
    metric_namespace: AgentPlatform
    log_group_prefix: agents/
    custom_metrics:
      - custom_tool_latency_ms

  data_protection:
    provider: bedrock              # bedrock | presidio | none
    guardrail_id_env: BEDROCK_GUARDRAIL_ID
    guardrail_version_env: BEDROCK_GUARDRAIL_VERSION
    cloudwatch_masking_identifiers:
      - EmailAddress
      - USPhoneNumber
```

### Data Protection Providers

The `data_protection.provider` field selects the in-process PII filtering mechanism:

| Provider | Mechanism | Requirements |
|----------|-----------|-------------|
| `bedrock` | AWS Bedrock Guardrails API (`ApplyGuardrail`) | `model.provider: bedrock` **and** `BEDROCK_GUARDRAIL_ID` env var set. If either is absent the hook is a no-op — no crash. |
| `presidio` | Local Microsoft Presidio redaction (no AWS dependency) | `pip install 'agent-core[presidio]'`. Works with any inference provider. |
| `none` | No in-process PII filter | — |

For `presidio`, configure which entity types to detect and the analyzer language:

```yaml
  data_protection:
    provider: presidio
    presidio_entities:            # Empty list = Presidio default entity set.
      - EMAIL_ADDRESS
      - PHONE_NUMBER
      - CREDIT_CARD
      - US_SSN
    presidio_language: en
```

Presidio engines are lazy-loaded on the first hook invocation — there is no startup cost unless the hook actually fires.

**CloudWatch Data Protection** (`cloudwatch_masking_identifiers`) is a separate Layer 2 mechanism that masks PII patterns in CloudWatch log streams at storage time. It is independent of the `provider` selection and is always active when the list is non-empty.

---

## `evaluation:` Block

Configures continuous production monitoring and custom LLM-as-judge evaluators. The `provider` field selects the evaluation backend.

```yaml
evaluation:
  provider: agentcore             # agentcore | langfuse. Default: agentcore.

  online:
    sampling_rate: 20             # Percentage of sessions to evaluate. Range: 1–100.
    evaluators:
      - Builtin.Correctness       # 12 built-in evaluators available (see table below).
      - Builtin.Helpfulness
      - Builtin.Harmlessness
      - Builtin.GoalSuccessRate
      - custom-quality-judge      # Reference a custom evaluator by name.
    auto_create_execution_role: true

  custom_evaluators:
    - name: custom-quality-judge
      level: TRACE                # TRACE | SESSION | SPAN
      model_id: ${EVAL_JUDGE_MODEL_ID}
      max_tokens: 512
      temperature: 0.0
      instructions: |
        Evaluate the assistant response for quality given the conversation.
        Context: {context}
        Response: {assistant_turn}
        Rate from 1 to 5 where 5 is excellent.
      scale: [1, 5]

  persistence:
    enabled: true
    table_env: EVALUATION_TABLE   # Env var holding the DynamoDB table name.
    retention_days: 90
```

**`provider: agentcore`** wraps `bedrock_agentcore_starter_toolkit.Evaluation` and requires `AWS_REGION`. The judge model must be a Bedrock model ARN.

**`provider: langfuse`** wraps `LangfuseEvaluationClient` and requires `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY`. Online evaluation rules are configured in the Langfuse dashboard — `create_online_config` is a no-op stub that logs a reminder. This provider is agnostic to the inference provider used by the agent.

`persistence` stores evaluation scores independently in DynamoDB and is available regardless of which `provider` is selected.

### 12 Built-in Evaluators

| Category | Evaluator | Level |
|----------|-----------|-------|
| Response Quality | `Builtin.Correctness` | TRACE |
| Response Quality | `Builtin.Completeness` | TRACE |
| Response Quality | `Builtin.Faithfulness` | TRACE |
| Response Quality | `Builtin.Helpfulness` | TRACE |
| Response Quality | `Builtin.Harmlessness` | TRACE |
| Response Quality | `Builtin.Coherence` | TRACE |
| Response Quality | `Builtin.Relevance` | TRACE |
| Task Completion | `Builtin.GoalSuccessRate` | SESSION |
| Tool Usage | `Builtin.ToolSelectionAccuracy` | SPAN |
| Tool Usage | `Builtin.ToolParameterAccuracy` | SPAN |
| Safety | `Builtin.Harmfulness` | TRACE |
| Safety | `Builtin.Stereotyping` | TRACE |

---

## `policy:` Block

Configures Cedar access-control policies attached to the AgentCore Gateway. The platform translates YAML rules into Cedar and attaches them to a per-agent policy engine.

```yaml
policy:
  engine: ResearchServicePolicies   # Policy engine name.
  mode: ENFORCE                     # ENFORCE | LOG_ONLY
  target_prefix: ResearchTarget     # Actions become ResearchTarget___<tool_name>.

  rules:
    - name: allow_public_query
      allow: query_public_records

    - name: restrict_bulk_writes
      allow: write_record
      when: "context.input.record_count <= 100"

    - name: admin_only_delete
      deny: delete_record
      unless: "principal.scope.contains('group:Admins')"

  versioning:
    enabled: true
    table_env: POLICY_VERSIONS_TABLE
    max_versions: 10
```

`ENFORCE` mode blocks unauthorised calls — the agent receives an authorization error. `LOG_ONLY` mode allows all calls through and logs the unauthorized decisions only.

Cedar uses a **default-deny** model: an empty policy engine blocks all tool calls. Any `permit` match with no `forbid` match allows the call; any `forbid` match overrides all permits.

See [Identity, Policy & IAM](../policy) for the full Cedar semantics reference.

---

## `multi_agent:` Block

Configures this agent's role in a multi-agent coordination topology. The field is `pattern` (not `type`). Nodes use `agent_ref` and `node_id`.

```yaml
multi_agent:
  pattern: graph                 # swarm | graph
  role: coordinator              # coordinator | specialist | standalone
  execution_timeout: 180         # Total execution timeout in seconds.
  node_timeout: 60               # Per-node timeout in seconds.
  max_handoffs: 10               # Maximum handoff count.
  max_iterations: 30             # Maximum agentic loop iterations.
  entry_point: data_collection   # node_id to start from (must exist in nodes).
  nodes:
    - agent_ref: collector-agent  # Blueprint ID to load for this node.
      node_id: data_collection    # Unique identifier within the graph.
    - agent_ref: analyzer-agent
      node_id: deep_analysis
  edges:
    - from_node: data_collection
      to_node: deep_analysis
      condition: null             # Condition expression or null for unconditional.
```

For **specialist** agents that expose an A2A server, set `role: specialist` and set `a2a_port` in the `runtime:` block to a non-zero port (e.g. 8081). `BlueprintLoader` detects this combination and auto-mounts an A2A server on that port.

### Remote Node Addressing

```yaml
nodes:
  - agent_ref: remote-specialist
    node_id: remote_step
    a2a_url_env: REMOTE_SPECIALIST_A2A_URL   # Env var holding the A2A URL.
  - agent_ref: another-specialist
    node_id: direct_invoke
    runtime_arn_env: SPECIALIST_RUNTIME_ARN  # Env var holding the Runtime ARN.
```

### Gate Nodes

Gate nodes evaluate a condition rather than running an agent:

```yaml
nodes:
  - node_id: confidence_gate
    type: gate
    trip_condition: "confidence >= 0.8"
    fallback: low_confidence_handler   # node_id to route to when condition is not met.
```

---

## `output_schema:` Field

Declares the name of a structured output schema registered in `BlueprintLoader`'s schema registry. When set, the platform wires Strands native structured output (`structured_output_model` kwarg) so the agent's final response is validated against the schema.

```yaml
output_schema: AnalysisOutput    # Schema name registered in BlueprintLoader.
```

Strands native structured output (forced-tool pattern) is used for all providers as of strands-agents 1.41.0. The minimum required version is `strands-agents>=1.0.0,<2`.

---

## `thinking:` Block

Enables extended thinking for agents that require deeper reasoning steps. Supported on models that implement Anthropic's extended thinking API.

```yaml
thinking:
  enabled: true
  budget_tokens: 10000           # Token budget for reasoning. Default: 10000.
```

---

## `artifacts:` Block

Configures mandatory artifact storage for agent outputs. Artifacts are persisted via the claim-check pattern — large outputs land in S3 with a reference key passed through the workflow.

```yaml
artifacts:
  tier: platform                 # platform | domain. Selects the S3 bucket.
  type: report                   # Artifact type label (e.g. report, analysis_result).
```

---

## `execution_modes:` Block

Controls in which execution environments the agent is active. Defaults: `simulation: true`, `staging: false`, `production: false`.

```yaml
execution_modes:
  simulation: true               # Active in simulation / testing environment.
  staging: true                  # Active in staging environment.
  production: false              # Disabled in production until promoted.
```

---

## `hooks:` Field

Lists custom hook names resolved via `BlueprintLoader`'s hook registry. The observability hook is auto-wired from the `observability:` block and must **not** be declared here.

```yaml
hooks:
  - my-custom-validation-hook
  - domain-specific-audit-hook
```

---

## `tags:` Field

`tags` on `AgentBlueprint` is a **list of strings**, not a key-value map:

```yaml
tags:
  - production
  - researcher
  - v2
```

---

## Complete Annotated Example

The example below shows all major blocks wired together using the `litellm` provider. For a `bedrock` equivalent, replace the `model:` block and set `data_protection.provider: bedrock`.

```yaml
id: research-agent
name: Research Agent
version: "1.2.0"
description: Researches topics using web search and internal knowledge bases.

prompt_ref: research-agent-system-v1

model:
  provider: litellm
  model_id: ${AGENT_MODEL_ID:-claude-sonnet-4-6}
  temperature: 0.2
  max_tokens: 8192
  base_url: https://llm.example.com
  api_key_env: LITELLM_API_KEY
  extra_headers_env:
    CF-Access-Client-Id: CF_CLIENT_ID
    CF-Access-Client-Secret: CF_CLIENT_SECRET

runtime:
  type: agentcore
  max_iterations: 15
  max_execution_time: 600
  idle_timeout_minutes: 20
  network_mode: PRIVATE
  protocol: HTTP
  port: 8080
  platform: linux/arm64
  observability_enabled: true

tools:
  - mcp: knowledge-mcp
    tools:
      - search_documents
      - retrieve_by_id
      - list_collections
  - builtin: browser
    network_mode: PUBLIC

gateway:
  auth_type: aws_iam

identity:
  authorizer:
    type: custom_jwt
    discovery_url: https://auth.example.com/.well-known/openid-configuration
    allowed_clients:
      - research-portal-client
  credentials:
    - name: knowledge-api-key
      type: api_key
      provider: KnowledgeServiceApiKey

memory:
  strategies:
    - type: SEMANTIC
      name: research-knowledge
      namespace: "{actorId}/research"
    - type: USER_PREFERENCE
      name: user-preferences
      namespace: "{actorId}/preferences"
  event_expiry_days: 90
  short_term_k: 8
  enable_tool_provider: true
  retrieval:
    - namespace: "{actorId}/research"
      top_k: 10
      relevance_score: 0.4

observability:
  enabled: true
  trace_attributes:
    team: platform
    agent: research-agent
  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY
    secret_key_env: LANGFUSE_SECRET_KEY
    host_env: LANGFUSE_HOST
  audit_log:
    enabled: true
    ttl_days: 1825
    table_env: AUDIT_LOG_TABLE
  data_protection:
    provider: presidio            # Provider-agnostic PII filtering.
    presidio_entities:
      - EMAIL_ADDRESS
      - PHONE_NUMBER

evaluation:
  provider: langfuse              # Provider-agnostic evaluation backend.
  online:
    sampling_rate: 10
    evaluators:
      - Builtin.Correctness
      - Builtin.Helpfulness
      - Builtin.GoalSuccessRate

policy:
  engine: ResearchPolicies
  mode: ENFORCE
  rules:
    - name: allow_search
      allow: search_documents
    - name: allow_retrieve
      allow: retrieve_by_id

execution_modes:
  simulation: true
  staging: true
  production: false
```

---

## Top-Level Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | `str` | **Yes** | — | Unique agent identifier (kebab-case recommended) |
| `version` | `str` | **Yes** | — | Semantic version string |
| `name` | `str` | **Yes** | — | Human-readable display name |
| `description` | `str` | No | `""` | Runtime description in AWS console |
| `model` | `ModelConfig` | **Yes** | — | Inference provider + model parameters |
| `prompt_ref` | `str` | **Yes** | — | Prompt Registry key |
| `tools` | `list[ToolDeclaration]` | No | `[]` | MCP tools, built-ins, and A2A remote agents |
| `gateway` | `GatewayConfig` | No | auth_type=aws_iam | Gateway connection config |
| `identity` | `IdentityConfig` | No | empty | Inbound authoriser and outbound credentials |
| `memory` | `MemoryConfig` | No | empty | AgentCore Memory strategies |
| `observability` | `ObservabilityConfig` | No | enabled=true | OTEL, Langfuse, audit, data protection |
| `runtime` | `RuntimeConfig` | No | sensible defaults | Runtime type, timeouts, network mode |
| `evaluation` | `EvaluationConfig` | No | provider=agentcore | Online evaluation configuration |
| `policy` | `PolicyConfig` | No | `null` | Cedar access-control policy |
| `execution_modes` | `ExecutionModes` | No | simulation=true | Environment gates |
| `output_schema` | `str` | No | `null` | Structured output schema name |
| `hooks` | `list[str]` | No | `[]` | Custom hook names (not observability) |
| `multi_agent` | `MultiAgentConfig` | No | `null` | Multi-agent topology configuration |
| `tags` | `list[str]` | No | `[]` | Arbitrary string tags |
| `thinking` | `ThinkingConfig` | No | `null` | Extended thinking configuration |
| `artifacts` | `ArtifactConfig` | No | tier=platform | Artifact storage configuration |
