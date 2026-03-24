---
title: Agent Blueprint
nav_order: 1
---

# Agent Blueprint

An agent blueprint is a YAML file that fully declares an AI agent. Every configurable aspect -- the model it uses, how it runs, which tools it calls, how it remembers, who can invoke it, and how it is observed -- is expressed here. The platform reads this file at both SDK load time and Terraform plan time.

---

## Identity Fields

```yaml
id: researcher                  # Unique agent identifier (snake_case). Used as resource name key.
name: Research Agent            # Human-readable name displayed in dashboards.
version: "1.0.0"               # Semantic version. Stamped on Runtime and ECR tags.
description: Researches topics  # Optional. Used as Runtime description in AWS console.
prompt_ref: researcher-system-v1  # Required. Reference key for the Prompt Registry (a string).
```

The `prompt_ref` field is a **required string** referencing a versioned prompt in the Prompt Registry (e.g., `researcher-system-v1`). It is not a nested object.

---

## `model:` Block

Declares the LLM this agent uses. `model_id`, `temperature`, and `max_tokens` are all **required** -- the platform never assumes a default model or sampling parameters.

```yaml
model:
  provider: bedrock                               # bedrock | anthropic | litellm | vertex
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0  # Fully qualified model ID. Required.
  temperature: 0.3                                # 0.0-1.0. Required.
  max_tokens: 4096                                # Maximum output tokens. Required.
  cache_prompt: default                           # Prompt caching policy: default | none | <key>
  cache_tools: default                            # Tool-result caching policy
```

{: .warning }
> There is no `region` field in `ModelConfig`. The Bedrock region is resolved from the `BEDROCK_REGION` environment variable.

---

## `runtime:` Block

Controls how the agent runs on AgentCore Runtime (microVM per session, port 8080).

```yaml
runtime:
  type: agentcore                 # Always agentcore -- the only supported runtime type
  max_iterations: 10              # Maximum agentic loop iterations per session
  max_execution_time: 300         # Hard timeout in seconds
  idle_timeout_minutes: 30        # Session idle timeout before microVM terminates
  network_mode: PUBLIC            # PUBLIC (internet-facing) | PRIVATE (VPC-only)
  protocol: HTTP                  # HTTP (standard agents) | MCP (hosted MCP servers)
  port: 8080                      # Container listen port for /invocations and /ping
  a2a_port: 8081                  # A2A server port. 0 = disabled. Used when role=specialist.
  platform: linux/arm64           # linux/arm64 (Graviton, required for AgentCore) | linux/amd64
  observability_enabled: true     # Enable OTEL auto-instrumentation via opentelemetry-instrument
```

For PRIVATE network mode, VPC subnet IDs and security group IDs are resolved from the platform module outputs and wired automatically by Terraform -- no additional YAML is needed.

---

## `tools:` Block

Declares which tools the agent can call. Two tool declaration types are supported and can be mixed freely.

### MCP Tools (via Gateway)

```yaml
tools:
  - mcp: data-service-mcp         # MCP server name registered as a Gateway target
    tools:
      - query_records              # Individual tool names to expose
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
  - builtin: code_interpreter      # Sandboxed Python execution environment
    network_mode: PUBLIC            # PUBLIC | PRIVATE
    region: null                    # null = resolved from config/env

  - builtin: browser               # Headless browser for web research
    network_mode: PUBLIC
```

Built-in tools must also be enabled in the platform module via `builtin_code_interpreter_enabled` and `builtin_browser_enabled` variables.

---

## `gateway:` Block

Configures how the agent connects to AgentCore Gateway for tool access. All tool calls route through the Gateway -- no direct MCP connections.

```yaml
gateway:
  url: null                        # Gateway URL. Falls back to AGENTCORE_GATEWAY_URL env var.
  auth_type: aws_iam               # aws_iam | custom_jwt | none
  jwt_env_var: null                # Env var holding the JWT (for custom_jwt auth)
  region: null                     # AWS region for SigV4 signing. Falls back to AWS_REGION.
  service_name: bedrock-agentcore  # AWS service name for SigV4 signing
```

---

## `identity:` Block

Controls inbound authorisation (who can call this agent) and outbound credentials (what external services the agent can authenticate to).

### Authorizer

```yaml
identity:
  authorizer:
    type: custom_jwt               # custom_jwt | cognito_jwt | aws_iam
    discovery_url: https://auth.example.com/.well-known/openid-configuration
    allowed_clients:
      - client-app-id-1
      - client-app-id-2

  # For cognito_jwt type:
  # authorizer:
  #   type: cognito_jwt
  #   user_pool_id: ${COGNITO_USER_POOL_ID}
  #   client_id: ${COGNITO_CLIENT_ID}
```

### Outbound Credentials

Only two credential types are supported: `api_key` and `oauth2`.

```yaml
identity:
  credentials:
    # API key credential
    - name: data-api-key
      type: api_key                # api_key | oauth2 (only these two types)
      provider: DataServiceApiKey  # Provider name registered in AgentCore Identity

    # OAuth2 credential (M2M -- machine-to-machine)
    - name: internal-service-token
      type: oauth2
      provider: InternalServiceOAuth
      scopes:
        - read:records
        - write:records
      auth_flow: M2M               # M2M | USER_FEDERATION

    # OAuth2 credential (USER_FEDERATION -- three-legged)
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

Configures long-term memory integration via AgentCore Memory. There is no `mode` field -- the presence of strategies enables memory automatically.

The canonical strategy type for summarization is `SUMMARY`. The alias `SUMMARIZATION` is accepted and automatically normalized to `SUMMARY`.

```yaml
memory:
  strategies:
    - type: SEMANTIC              # SEMANTIC | SUMMARY | USER_PREFERENCE | EPISODIC
      name: knowledge-base        # Human-readable strategy name
      namespace: "{actorId}/knowledge"  # Namespace template with {actorId}/{sessionId} placeholders

    - type: USER_PREFERENCE
      name: preferences
      namespace: "{actorId}/preferences"

    - type: SUMMARY               # Canonical name. SUMMARIZATION accepted as alias.
      name: session-summaries
      namespace: "{actorId}/{sessionId}/summary"

  event_expiry_days: 30           # Memory event retention (1-365 days)
  short_term_k: 5                 # Number of recent memories to surface per turn
  enable_tool_provider: true      # Expose memory_recall and memory_record as agent tools
  retrieval:
    - namespace: "{actorId}/knowledge"   # Namespaces queried on agent initialisation
      top_k: 10
      relevance_score: 0.4
```

---

## `observability:` Block

Controls tracing, audit logging, dashboards, and data protection.

```yaml
observability:
  enabled: true
  trace_attributes:              # Static key-value pairs attached to every OTEL span
    team: platform
    tier: core

  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY   # Env var holding the Langfuse public key
    secret_key_env: LANGFUSE_SECRET_KEY   # Env var holding the Langfuse secret key
    host_env: LANGFUSE_HOST
    tags:
      - production
      - researcher-agent

  audit_log:
    enabled: true
    ttl_days: 1825                         # ~5 years retention (field is ttl_days, not ttl_years)
    table_env: AUDIT_LOG_TABLE             # Env var holding DynamoDB table name

  dashboard:
    metric_namespace: AgentPlatform
    log_group_prefix: agents/
    custom_metrics:
      - custom_tool_latency_ms
      - domain_specific_score

  data_protection:
    guardrail_id_env: BEDROCK_GUARDRAIL_ID
    guardrail_version_env: BEDROCK_GUARDRAIL_VERSION
    cloudwatch_masking_identifiers:
      - EmailAddress
      - USPhoneNumber
```

---

## `evaluation:` Block

Configures online (continuous production) evaluation and custom LLM-as-judge evaluators.

```yaml
evaluation:
  online:
    sampling_rate: 20             # Evaluate 20% of production sessions
    evaluators:
      - Builtin.Correctness       # 12 built-in evaluators available
      - Builtin.Helpfulness
      - Builtin.Harmlessness
      - Builtin.GoalSuccessRate
      - custom-quality-judge      # Reference a custom evaluator by name
    auto_create_execution_role: true

  custom_evaluators:
    - name: custom-quality-judge
      level: TRACE                # TRACE | SESSION | SPAN
      model_id: us.anthropic.claude-haiku-4-20250514-v1:0
      max_tokens: 512
      temperature: 0.0
      instructions: |
        Evaluate the assistant response for quality given the conversation context.
        Context: {context}
        Response: {assistant_turn}
        Rate from 1 to 5 where 5 is excellent.
      scale: [1, 5]

  persistence:
    enabled: true
    table_env: EVALUATION_TABLE
    retention_days: 90
```

Available built-in evaluators:

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

Configures Cedar access-control policies attached to the AgentCore Gateway. The platform translates simplified YAML rules into Cedar and attaches them to the Gateway policy engine.

```yaml
policy:
  engine: ResearchServicePolicies   # Policy engine name
  mode: ENFORCE                     # ENFORCE | LOG_ONLY
  target_prefix: ResearchTarget     # Actions become ResearchTarget___<tool_name>

  rules:
    - name: allow_public_query
      allow: query_public_records

    - name: restrict_bulk_writes
      allow: write_record
      when: "context.input.record_count <= 100"

    - name: admin_only_delete
      deny: delete_record
      unless: "principal.scope.contains('group:Admins')"

    - name: managers_approve
      allow: approve_action
      principal: 'AgentCore::Principal::"manager-role"'

  versioning:
    enabled: true
    table_env: POLICY_VERSIONS_TABLE
    max_versions: 10
```

---

## `multi_agent:` Block

Configures multi-agent coordination when this agent participates in a graph or swarm topology.

The field is `pattern` (not `type`). Nodes use `agent_ref` and `node_id` (not `id`).

```yaml
multi_agent:
  pattern: graph                 # Orchestration pattern: swarm | graph
  role: coordinator              # coordinator | specialist | standalone
  execution_timeout: 180         # Total execution timeout in seconds
  node_timeout: 60               # Per-node timeout in seconds
  max_handoffs: 10               # Maximum handoff count
  max_iterations: 30             # Maximum iterations
  entry_point: data_collection   # Node ID to start execution from (must be in nodes)
  nodes:
    - agent_ref: simple-agent    # Blueprint ID to load for this node
      node_id: data_collection   # Unique node identifier within the graph
    - agent_ref: analyzer-agent
      node_id: deep_analysis
  edges:
    - from_node: data_collection
      to_node: deep_analysis
      condition: null             # Optional safe expression, or null for unconditional
```

For specialist agents:

```yaml
multi_agent:
  pattern: swarm
  role: specialist
  # a2a_port in runtime: block must be non-zero for A2A server to start
```

### Remote Node Options

For cross-runtime A2A communication, nodes support remote addressing:

```yaml
nodes:
  - agent_ref: remote-specialist
    node_id: remote_step
    a2a_url_env: REMOTE_SPECIALIST_A2A_URL   # Env var holding the A2A URL
  - agent_ref: another-specialist
    node_id: direct_invoke
    runtime_arn_env: SPECIALIST_RUNTIME_ARN   # Env var holding the Runtime ARN
```

---

## Complete Annotated Example

```yaml
id: researcher
name: Research Agent
version: "1.2.0"
description: Researches topics using web search and internal knowledge bases

prompt_ref: researcher-system-v1

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.2
  max_tokens: 8192
  cache_prompt: default
  cache_tools: default

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
    agent: researcher
  langfuse:
    enabled: true
    public_key_env: LANGFUSE_PUBLIC_KEY
    secret_key_env: LANGFUSE_SECRET_KEY
    host_env: LANGFUSE_HOST
  audit_log:
    enabled: true
    ttl_days: 1825
    table_env: AUDIT_LOG_TABLE

evaluation:
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
```
