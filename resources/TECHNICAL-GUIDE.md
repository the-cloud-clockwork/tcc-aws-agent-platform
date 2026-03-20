# Amazon Bedrock AgentCore — Complete Architecture & Integration Guide

> Comprehensive reference covering every AgentCore component, how Strands Agents integrates with each, Terraform/CDK infrastructure patterns, framework integrations, and end-to-end deployment.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Amazon Bedrock AgentCore                            │
│                                                                             │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐   │
│  │   AgentCore Runtime      │◄──►│  AgentCore Gateway                  │   │
│  │  ┌────────────────────┐  │    │  (Lambda → MCP, REST → MCP,         │   │
│  │  │ Framework Layer    │  │    │   OpenAPI → MCP, Smithy → MCP)      │   │
│  │  │ (Strands, LangGraph│  │    ├──────────────────────────────────────┤   │
│  │  │  CrewAI, PydanticAI│  │    │  AgentCore Browser                  │   │
│  │  │  AutoGen, ADK ...) │  │    │  (Hosted Chromium, CDP, Nova Act)   │   │
│  │  ├────────────────────┤  │    ├──────────────────────────────────────┤   │
│  │  │ Agent Instructions │  │    │  AgentCore Code Interpreter         │   │
│  │  │ Agent Local Tools  │  │    │  (Sandboxed Python/Shell, AWS CLI)  │   │
│  │  │ Agent Context      │  │    └──────────────┬───────────────────────┘   │
│  │  └────────────────────┘  │                   │                           │
│  └─────────┬────────────────┘                   │                           │
│            │                    ┌────────────────▼───────────────────┐      │
│            │                    │     AgentCore Identity             │      │
│  ┌─────────▼────────────────┐  │  (OAuth 2.0, Cognito, Okta,       │      │
│  │   AgentCore Memory       │  │   Entra, 3LO, M2M, API Keys)     │      │
│  │  (pgvector, TTL,         │  └────────────────────────────────────┘      │
│  │   namespaces, strategies)│                                               │
│  └─────────┬────────────────┘  ┌────────────────────────────────────┐      │
│            │                    │  CloudWatch GenAI Observability    │      │
│            └───────────────────►│  (OTEL traces, spans, metrics)    │      │
│                                 └────────────────────────────────────┘      │
│  ┌──────────────────────────┐  ┌────────────────────────────────────┐      │
│  │   AgentCore Evaluation   │  │     AgentCore Policy (Cedar)       │      │
│  │  (13 built-in evaluators,│  │  (FGAC, NL2Cedar, per-tool        │      │
│  │   custom LLM-as-judge)   │  │   access control per identity)    │      │
│  └──────────────────────────┘  └────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Table of Contents

1. [AgentCore Runtime](#1-agentcore-runtime)
2. [AgentCore Gateway](#2-agentcore-gateway)
3. [AgentCore Identity](#3-agentcore-identity)
4. [AgentCore Memory](#4-agentcore-memory)
5. [AgentCore Tools](#5-agentcore-tools)
6. [CloudWatch GenAI Observability](#6-cloudwatch-genai-observability)
7. [AgentCore Evaluation](#7-agentcore-evaluation)
8. [AgentCore Policy](#8-agentcore-policy-cedar)
9. [Framework Integrations](#9-framework-integrations)
10. [Agent-to-Agent Communication (A2A)](#10-agent-to-agent-communication-a2a)
11. [Infrastructure as Code (Terraform)](#11-infrastructure-as-code-terraform)
12. [Blueprints](#12-blueprints)
13. [End-to-End Use Cases](#13-end-to-end-use-cases)

---

## 1. AgentCore Runtime

Managed container hosting for any agent framework. Exposes `/invocations` on port 8080. Handles scaling, warm containers (microVM isolation per session), and routing.

### Core Pattern — `@app.entrypoint`

```python
# 01-tutorials/01-AgentCore-runtime/01-hosting-agent/01-strands-with-bedrock-model/strands_claude.py
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models import BedrockModel

app = BedrockAgentCoreApp()
model = BedrockModel(model_id="eu.anthropic.claude-sonnet-4-6")
agent = Agent(model=model, tools=[calculator, weather],
    system_prompt="You're a helpful assistant.")

@app.entrypoint
def strands_agent_bedrock(payload):
    return agent(payload.get("prompt")).message['content'][0]['text']

if __name__ == "__main__":
    app.run()
```

### Context Object — Session Tracking

```python
# 01-tutorials/01-AgentCore-runtime/03-advanced-concepts/02-understanding-runtime-context/
@app.entrypoint
def handler(payload, context):
    session_id = context.session_id          # Runtime session ID
    headers = context.request_headers        # Incoming HTTP headers
    # Each session = isolated microVM. 15min idle timeout (configurable), 8hr max.
```

### Streaming — `async def` + `yield`

```python
# 01-tutorials/01-AgentCore-runtime/03-advanced-concepts/01-streaming-agent-response/
@app.entrypoint
async def handler(payload):
    async for event in agent.stream_async(payload.get("prompt")):
        if "data" in event:
            yield event["data"]
# Client receives Content-Type: text/event-stream (SSE)
```

### Middleware (Starlette)

```python
# 01-tutorials/01-AgentCore-runtime/03-advanced-concepts/06-middleware-support/middleware_agent.py
app = BedrockAgentCoreApp(
    middleware=[
        Middleware(ErrorHandlingMiddleware),
        Middleware(ObservabilityMiddleware),
    ]
)
```

### Deployment CLI — 3-Step Workflow

```python
from bedrock_agentcore_starter_toolkit import Runtime

rt = Runtime()
rt.configure(entrypoint="agent.py", auto_create_execution_role=True,
    auto_create_ecr=True, requirements_file="requirements.txt",
    region="eu-west-1", agent_name="my_agent")
rt.launch()                           # Builds container, pushes ECR, creates runtime
rt.status()                            # endpoint.status -> 'READY'
rt.invoke({"prompt": "..."}, session_id=str(uuid.uuid4()))
```

### `.bedrock_agentcore.yaml` — Generated Config

```yaml
agents:
  my_agent:
    entrypoint: agent.py
    deployment_type: container
    platform: linux/arm64
    aws:
      network_configuration: { network_mode: PUBLIC }
      protocol_configuration: { server_protocol: HTTP }  # or MCP
      observability: { enabled: true }
    memory: { mode: NO_MEMORY }  # or MANAGED
    identity: { credential_providers: [] }
```

### Dockerfile Pattern

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
RUN uv pip install -r requirements.txt && uv pip install aws-opentelemetry-distro==0.12.2
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore
EXPOSE 9000 8000 8080
CMD ["opentelemetry-instrument", "python", "-m", "my_agent"]
```

Three ports: **8080** (invocations), **8000** (MCP), **9000** (A2A).

### boto3 Invocation (Data Plane)

```python
client = boto3.client('bedrock-agentcore', region_name='eu-west-1')
response = client.invoke_agent_runtime(
    agentRuntimeArn=arn, qualifier="DEFAULT",
    payload=json.dumps({"prompt": "..."})
)
client.stop_runtime_session(agentRuntimeArn=arn, runtimeSessionId=sid, qualifier='DEFAULT')
```

Two boto3 clients: `bedrock-agentcore` (data plane — invoke, stop), `bedrock-agentcore-control` (control plane — CRUD).

### DIY Pattern (No SDK)

```python
# 02-use-cases/AWS-operations-agent/agentcore-runtime/src/agents/diy_agent.py
app = FastAPI()

@app.post("/invocations")
async def invoke_agent(request: InvocationRequest):
    return StreamingResponse(stream_response(request.prompt), media_type="text/event-stream")

@app.get("/ping")
async def ping(): return {"status": "healthy"}

uvicorn.run(app, host="0.0.0.0", port=8080)
```

The entire runtime contract is `POST /invocations` + `GET /ping` on port 8080. Any framework works.

### Hosting MCP Servers on Runtime

```python
# 01-tutorials/01-AgentCore-runtime/02-hosting-MCP-server/mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

Set `server_protocol: MCP` in `.bedrock_agentcore.yaml`. Clients use SigV4-signed streamable HTTP or OAuth bearer tokens to invoke.

---

## 2. AgentCore Gateway

Auto-generates MCP tool interfaces from Lambda functions, REST APIs, OpenAPI specs, and Smithy APIs — zero adapter code.

### Gateway Creation

```python
# 02-use-cases/AWS-operations-agent/agentcore-runtime/gateway-ops-scripts/create-gateway.py
client = boto3.client('bedrock-agentcore-control', region_name='eu-west-1')
response = client.create_gateway(
    name='my-gateway',
    protocolType='MCP',
    roleArn=gateway_role_arn,
    authorizerType='CUSTOM_JWT',           # or 'AWS_IAM'
    authorizerConfiguration={
        'customJWTAuthorizer': {
            'discoveryUrl': cognito_discovery_url,
            'allowedAudience': [client_id]
        }
    }
)
# gateway_url = https://{gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp
```

### Gateway Target — Lambda to MCP

```python
# 01-tutorials/02-AgentCore-gateway/01-transform-lambda-into-mcp-tools/
response = client.create_gateway_target(
    gatewayIdentifier=gateway_id,
    name='OrderTools',
    targetConfiguration={
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [{
                        "name": "get_order",
                        "description": "Get order by ID",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"orderId": {"type": "string"}},
                            "required": ["orderId"]
                        }
                    }]
                }
            }
        }
    },
    credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
)
```

### Target Types

| Type | Config Key | Description |
|------|-----------|-------------|
| Lambda | `mcp.lambda` | Wraps Lambda functions as MCP tools |
| Runtime MCP | Target URL = runtime endpoint | Proxies to hosted MCP server |
| OpenAPI | `mcp.openApi` | Wraps REST APIs as MCP tools |
| Smithy | `mcp.smithyApi` | Wraps Smithy-defined APIs |
| MCP Server | `mcp.mcpServer` | Proxies to external MCP server |
| API Gateway | `mcp.apiGateway` | Wraps API Gateway endpoints |

### Strands Agent Consuming Gateway Tools

```python
# 02-use-cases/AWS-operations-agent/agentcore-runtime/src/agents/sdk_agent.py
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

access_token = get_m2m_token()
mcp_client = MCPClient(functools.partial(
    streamablehttp_client,
    url=gateway_url,
    headers={"Authorization": f"Bearer {access_token}"}
))

with mcp_client:
    tools = mcp_client.list_tools_sync()
    agent = Agent(model=model, tools=[local_tool] + tools)  # Mix local + MCP tools
    result = agent(prompt)
```

The agent doesn't know whether a tool is local or MCP — Strands `MCPClient` abstracts the protocol.

### Gateway with SigV4 Auth (IAM)

```python
# 01-tutorials/02-AgentCore-gateway/01-transform-lambda-into-mcp-tools/
from streamable_http_sigv4 import streamablehttp_client_with_sigv4

creds = sts_client.assume_role(RoleArn=invoke_role_arn, ...)["Credentials"]
mcp_client = MCPClient(lambda: create_streamable_http_transport_sigv4(
    gateway_url, creds["AccessKeyId"], creds["SecretAccessKey"],
    creds["SessionToken"], "bedrock-agentcore", region
))
```

### Multi-Framework Gateway Access

Same gateway, different frameworks:

```python
# Strands — 02-use-cases/healthcare-appointment-agent/strands_agent.py
mcp_client = MCPClient(lambda: streamablehttp_client(gateway_url, headers=auth_headers))

# LangGraph — 02-use-cases/healthcare-appointment-agent/langgraph_agent.py
mcp_client = MultiServerMCPClient({"healthcare": {
    "url": gateway_url, "transport": "streamable_http", "headers": auth_headers
}})
```

Gateway tools are framework-agnostic. Any MCP-compliant client works.

---

## 3. AgentCore Identity

Agent-native OAuth/OIDC. Two flows: **inbound** (validate callers) and **outbound** (agents accessing external services).

### SDK Surface

```python
from bedrock_agentcore.services.identity import IdentityClient, UserTokenIdentifier
from bedrock_agentcore.identity.auth import requires_access_token, requires_api_key
```

### Inbound Auth — JWT/Cognito

```python
# 01-tutorials/03-AgentCore-identity/03-Inbound Auth example/
rt = Runtime()
rt.configure(
    entrypoint="agent.py",
    agent_name="secure_agent",
    authorizer_configuration={
        "customJWTAuthorizer": {
            "discoveryUrl": cognito_discovery_url,
            "allowedClients": [client_id],
        }
    },
)
# Invoke with bearer token:
rt.invoke({"prompt": "..."}, bearer_token=cognito_token)
# Without token -> AccessDeniedException
```

### Outbound Auth — API Key Credential Provider

```python
# 01-tutorials/03-AgentCore-identity/04-Outbound Auth example/
identity_client = IdentityClient(region='eu-west-1')
identity_client.create_api_key_credential_provider({
    "name": "openai-apikey-provider",
    "apiKey": "<KEY>",
})

# Runtime retrieval via decorator:
@requires_api_key(provider_name="openai-apikey-provider")
async def need_api_key(*, api_key: str):
    os.environ["OPENAI_API_KEY"] = api_key
```

### Outbound Auth — 3-Legged OAuth (Google Calendar)

```python
# 01-tutorials/03-AgentCore-identity/05-Outbound_Auth_3lo/strands_claude_google_3lo.py
@tool(name="Get_calendar_events_today")
async def get_calendar():
    @requires_access_token(
        provider_name="google-cal-provider",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        auth_flow="USER_FEDERATION",          # 3LO
        on_auth_url=on_auth_url,              # Callback for auth URL display
        force_authentication=True,
        callback_url=os.environ["CALLBACK_URL"],
    )
    async def get_events(access_token: Optional[str] = "") -> str:
        creds = Credentials(token=access_token, scopes=SCOPES)
        service = build("calendar", "v3", credentials=creds)
        # ... Google Calendar API calls
```

### Outbound Auth — GitHub 3LO

```python
# 01-tutorials/03-AgentCore-identity/06-Outbound_Auth_Github/github_agent.py
@tool
def inspect_github_repos() -> str:
    @requires_access_token(
        provider_name="github-provider",
        scopes=["repo", "read:user"],
        auth_flow="USER_FEDERATION",
        on_auth_url=on_auth_url,
        callback_url=os.environ["CALLBACK_URL"],
    )
    def inner(access_token: Optional[str] = None) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        # ... GitHub API calls
```

Nested function pattern: `@requires_access_token` on an inner function so tool signature derivation doesn't expose the `access_token` parameter.

### M2M Auth (Machine-to-Machine)

```python
# 02-use-cases/A2A-multi-agent-incident-response/host_adk_agent/agent.py
@requires_access_token(
    provider_name=provider_name,
    scopes=[], auth_flow="M2M",
    into="bearer_token",
    force_authentication=True,
)
def _create_client(bearer_token: str = str()) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"Authorization": f"Bearer {bearer_token}"})
```

### `@requires_access_token` Parameters

| Parameter | Description |
|-----------|-------------|
| `provider_name` | Credential provider name |
| `scopes` | OAuth2 scopes |
| `auth_flow` | `"M2M"` or `"USER_FEDERATION"` |
| `on_auth_url` | Callback for auth URL display |
| `callback_url` | OAuth2 redirect URL |
| `force_authentication` | Force re-auth |
| `into` | Parameter name to inject token into |

### Workload Identity (boto3 CRUD)

```python
# 02-use-cases/AWS-operations-agent/agentcore-runtime/runtime-ops-scripts/identity_manager.py
client = boto3.client('bedrock-agentcore-control')
client.create_workload_identity(workloadIdentityName=name, principalArn=arn)
client.get_workload_identity(name=name)
client.update_workload_identity(workloadIdentityName=name, workloadIdentityConfiguration={...})
```

---

## 4. AgentCore Memory

Managed vector + semantic memory. Two tiers: **short-term** (raw conversation events, TTL) and **long-term** (strategy-based extraction — semantic, summary, user preferences, custom). Backend: pgvector.

### SDK Surface

```python
from bedrock_agentcore.memory import MemoryClient, MemorySessionManager
from bedrock_agentcore.memory.constants import StrategyType, ConversationalMessage, MessageRole
```

### Create Memory (Short-Term Only)

```python
# 01-tutorials/04-AgentCore-memory/01-short-term-memory/
client = MemoryClient(region_name='eu-west-1')
memory = client.create_memory_and_wait(
    name="MyAgentMemory",
    strategies=[],                  # No strategies = short-term only
    description="Conversation memory",
    event_expiry_days=7,            # TTL: up to 365 days
)
```

### Store & Retrieve Events

```python
# Store
client.create_event(
    memory_id=memory_id, actor_id="user_123", session_id="session_001",
    messages=[("Hello", "USER"), ("Hi there!", "ASSISTANT")]
)

# Retrieve last K turns
turns = client.get_last_k_turns(
    memory_id=memory_id, actor_id="user_123", session_id="session_001", k=5
)
```

### Long-Term Memory (Strategy-Based Extraction)

```python
# 01-tutorials/04-AgentCore-memory/02-long-term-memory/
memory = client.create_memory_and_wait(
    name="SmartMemory",
    strategies=[{
        StrategyType.USER_PREFERENCE.value: {
            "name": "UserPreferences",
            "description": "Captures user preferences",
            "namespaces": ["user/{actorId}/preferences/"]
        }
    }],
    event_expiry_days=7,
)
```

**Strategy Types:** `USER_PREFERENCE`, `SEMANTIC`, `SUMMARY`, `EPISODIC` (custom via CloudFormation).

When `create_event()` is called on a memory with strategies, extraction happens asynchronously (~30s). Extracted data lands in the configured namespace.

### Semantic Retrieval

```python
results = client.retrieve_memories(
    memory_id=memory_id,
    namespace=f"user/{actor_id}/preferences/",
    query="food preferences",
    top_k=3
)
# Returns: [{content: {text: "..."}, score: float}, ...]
```

### Memory Hook Pattern (Strands — Most Common)

```python
# 01-tutorials/04-AgentCore-memory/01-short-term-memory/.../personal-agent.ipynb
class MemoryHookProvider(HookProvider):
    def on_agent_initialized(self, event: AgentInitializedEvent):
        """Load history into system prompt on agent start"""
        recent_turns = self.memory_client.get_last_k_turns(
            memory_id=self.memory_id, actor_id=actor_id, session_id=session_id, k=5)
        if recent_turns:
            event.agent.system_prompt += f"\n\nRecent conversation:\n{format_turns(recent_turns)}"

    def on_message_added(self, event: MessageAddedEvent):
        """Store each message as it's added"""
        self.memory_client.create_event(
            memory_id=self.memory_id, actor_id=actor_id, session_id=session_id,
            messages=[(messages[-1]["content"][0]["text"], messages[-1]["role"])])

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(MessageAddedEvent, self.on_message_added)
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)

# Usage:
agent = Agent(hooks=[MemoryHookProvider(client, memory_id)],
    state={"actor_id": "user_123", "session_id": "session_001"})
```

### Multi-Namespace Retrieval (Production Pattern)

```python
# 02-use-cases/A2A-multi-agent-incident-response/monitoring_strands_agent/memory_hook.py
class MonitoringMemoryHooks(HookProvider):
    retrieval_config = {
        "/technical-issues/{actorId}": RetrievalConfig(top_k=3, relevance_score=0.3),
        "/knowledge/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.2),
    }
    def retrieve_monitoring_context(self, event):
        for namespace_template, config in self.retrieval_config.items():
            memories = self.client.retrieve_memories(
                memory_id=self.memory_id,
                namespace=namespace_template.format(actorId=self.actor_id),
                query=user_query, top_k=config.top_k)
```

### Memory Branching (Multi-Agent Conversations)

```python
# 01-tutorials/04-AgentCore-memory/04-memory-branching/
from bedrock_agentcore.memory import MemorySessionManager

manager = MemorySessionManager(memory_id=memory_id, region_name='eu-west-1')
session = manager.create_memory_session(actor_id, session_id)

session.add_turns(messages, branch={"name": "main"})
session.fork_conversation(root_event_id=event_id, branch_name="flight_agent_memory", messages=[...])
session.get_last_k_turns(k=5, branch_name="flight_agent_memory")
session.list_branches()
```

Coordinator on "main", specialist agents on their own branches.

### AgentCoreMemoryToolProvider (LLM-Callable Tools)

```python
# 01-tutorials/04-AgentCore-memory/02-long-term-memory/
from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider

provider = AgentCoreMemoryToolProvider(memory_id=memory_id, actor_id=actor_id,
    session_id=session_id, namespace=namespace)
agent = Agent(tools=provider.tools)  # Agent can now call retrieve/store directly
```

---

## 5. AgentCore Tools

### 5A. Code Interpreter

Sandboxed Python/Shell execution environment with file I/O and optional AWS CLI access.

```python
# 01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

code_client = CodeInterpreter('eu-west-1')
code_client.start()

# Write files into sandbox
code_client.invoke("writeFiles", {"content": [{"path": "data.csv", "text": csv_content}]})

# Execute code
response = code_client.invoke("executeCode", {
    "code": python_code, "language": "python", "clearContext": False
})
# response["stream"] -> {result: {content, structuredContent: {stdout, stderr, exitCode}}}

code_client.stop()
```

**As a Strands tool:**

```python
from bedrock_agentcore.tools.code_interpreter_client import code_session

@tool
def execute_python(code: str, description: str = "") -> str:
    """Execute Python code in the sandbox."""
    with code_session("eu-west-1") as code_client:
        response = code_client.invoke("executeCode", {"code": code, "language": "python"})
    for event in response["stream"]:
        return json.dumps(event["result"])
```

**Advanced: Shell Commands + AWS CLI:**

```python
# Via boto3 for more control (execution role enables AWS service access from sandbox)
cp_client = boto3.client("bedrock-agentcore-control")
cp_client.create_code_interpreter(name=name, executionRoleArn=role_arn,
    networkConfiguration={'networkMode': 'PUBLIC'})

dp_client = boto3.client("bedrock-agentcore")
dp_client.invoke_code_interpreter(codeInterpreterIdentifier=id, sessionId=sid,
    name="executeCommand", arguments={"command": "aws s3 ls"})
```

Available sandbox tools: `executeCode`, `executeCommand`, `writeFiles`, `listFiles`, `readFile`.

### 5B. Browser Tool

Hosted Chromium via CDP (Chrome DevTools Protocol). Three integration approaches:

**Nova Act (Amazon's browser automation):**

```python
# 01-tutorials/05-AgentCore-tools/02-Agent-Core-browser-tool/01-browser-with-NovaAct/
from bedrock_agentcore.tools.browser_client import browser_session
from nova_act import NovaAct

with browser_session(region) as client:
    ws_url, headers = client.generate_ws_headers()
    with NovaAct(cdp_endpoint_url=ws_url, cdp_headers=headers,
                 nova_act_api_key=key, starting_page="https://amazon.com/") as nova:
        result = nova.act("Search for macbooks and extract details of the first one")
```

**Browser-Use (open source):**

```python
# 01-tutorials/05-AgentCore-tools/02-Agent-Core-browser-tool/02-browser-with-browserUse/
from bedrock_agentcore.tools.browser_client import BrowserClient
from browser_use import Agent, Browser, BrowserProfile

client = BrowserClient(region)
client.start()
ws_url, headers = client.generate_ws_headers()
browser = Browser(cdp_url=ws_url, browser_profile=BrowserProfile(headers=headers))
agent = Agent(task="Search for a coffee maker", llm=bedrock_chat, browser_session=browser)
await agent.run()
```

**Strands Native:**

```python
# 01-tutorials/05-AgentCore-tools/02-Agent-Core-browser-tool/04-browser-with-Strands/
from strands_tools.browser import AgentCoreBrowser

browser = AgentCoreBrowser(region="eu-west-1")
agent = Agent(tools=[browser.browser], model="eu.anthropic.claude-sonnet-4-6")
agent("Analyze Tesla stock at https://www.marketwatch.com/investing/stock/tsla")
```

**Session Recording + Replay:**

```python
# 01-tutorials/05-AgentCore-tools/02-Agent-Core-browser-tool/03-browser-observability/
cp_client.create_browser(name="recorded_browser",
    networkConfiguration={'networkMode': 'PUBLIC'},
    recording={'enabled': True, 's3Location': {'bucket': bucket, 'prefix': 'replay-data'}})
```

Additional browser features: live view (DCV), web bot auth signing, private VPC, domain filtering, browser profiles, proxy support, extensions.

---

## 6. CloudWatch GenAI Observability

OTEL-compatible tracing: prompts, tool calls, token counts, latency. Auto-instrumented on Runtime, manual setup for self-hosted.

### Runtime-Hosted (Automatic)

```python
# 01-tutorials/06-AgentCore-observability/01-Agentcore-runtime-hosted/
# Just include in requirements.txt: aws-opentelemetry-distro==0.12.2
# Dockerfile CMD: ["opentelemetry-instrument", "python", "-m", "my_agent"]
# That's it. No code changes.
```

### Self-Hosted (Env Vars)

```bash
# 01-tutorials/06-AgentCore-observability/02-Agent-not-hosted-on-runtime/
OTEL_PYTHON_DISTRO=aws_distro
OTEL_PYTHON_CONFIGURATOR=aws_configurator
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-log-group=agents/my-agent,x-aws-log-stream=default,x-aws-metric-namespace=bedrock-agentcore
OTEL_RESOURCE_ATTRIBUTES=service.name=my-agent
AGENT_OBSERVABILITY_ENABLED=true
```

```python
# Create log group first:
cloudwatch_client.create_log_group(logGroupName='agents/my-agent')
cloudwatch_client.create_log_stream(logGroupName='agents/my-agent', logStreamName='default')

# Run: opentelemetry-instrument python my_agent.py
```

### Session Tracking

```python
from opentelemetry import baggage, context

ctx = baggage.set_baggage("session.id", session_id)
ctx = baggage.set_baggage("user.type", "premium")
token = context.attach(ctx)
# ... run agent ...
context.detach(token)
```

### Custom Span Creation

```python
# 01-tutorials/06-AgentCore-observability/03-advanced-concepts/01-custom-span-creation/
from opentelemetry import trace
tracer = trace.get_tracer("web_search", "1.0.0")

@tool
def web_search(query: str) -> str:
    with tracer.start_as_current_span("web_search_tool") as span:
        span.set_attribute("search.query", query)
        span.add_event("search_started", {"query": query})
        # ... do work ...
        span.set_status(trace.Status(trace.StatusCode.OK))
```

### Strands trace_attributes

```python
agent = Agent(model=model, tools=[web_search],
    trace_attributes={"user.id": "user@domain.com", "tags": ["production"]})
```

### Data Protection

```python
# 01-tutorials/06-AgentCore-observability/03-advanced-concepts/02-data-protection/
# Layer 1: Bedrock Guardrails (anonymize PII in responses)
model = BedrockModel(model_id=model_id, guardrail_id=guardrail_id,
    guardrail_version=version, guardrail_trace="enabled")

# Layer 2: CloudWatch Logs Data Protection (mask PII in logs)
cloudwatch_logs_client.put_data_protection_policy(
    logGroupIdentifier=log_group, policyDocument=json.dumps(data_protection_policy))
```

### Auto-Captured Data

- Agent invocation sequences (full call graph)
- LLM calls (prompts, responses, token counts, model ID)
- Tool invocations (name, parameters, results, latency)
- Error paths and exceptions
- Custom spans and events

### Partner Observability

Instana, Arize, OpenLIT, Braintrust, Langfuse — all supported via OTEL export.

---

## 7. AgentCore Evaluation

On-demand and continuous (online) evaluation pipelines. 13 built-in evaluators + custom LLM-as-judge.

### SDK Surface

```python
from bedrock_agentcore_starter_toolkit import Evaluation
eval_client = Evaluation(region='eu-west-1')
```

### Built-in Evaluators

| Category | Evaluators | Level |
|----------|-----------|-------|
| Response Quality | Correctness, Completeness, Faithfulness, Helpfulness, Harmlessness, Coherence, Relevance | TRACE |
| Task Completion | GoalSuccessRate | SESSION |
| Tool Level | ToolSelectionAccuracy, ToolParameterAccuracy | SPAN |
| Safety | Harmfulness, Stereotyping | TRACE |

### Custom Evaluator (LLM-as-Judge)

```python
# 01-tutorials/07-AgentCore-evaluations/01-creating-custom-evaluators/
custom = eval_client.create_evaluator(
    name="response_quality",
    level="TRACE",
    config={
        "llmAsAJudge": {
            "modelConfig": {"bedrockEvaluatorModelConfig": {
                "modelId": "eu.anthropic.claude-sonnet-4-6",
                "inferenceConfig": {"maxTokens": 500, "temperature": 1.0}
            }},
            "instructions": "Evaluate quality... {context} {assistant_turn}",
            "ratingScale": {"numerical": [
                {"value": 1, "label": "Very Good", "definition": "..."},
                {"value": 0.75, "label": "Good", "definition": "..."},
                {"value": 0, "label": "Very Poor", "definition": "..."},
            ]}
        }
    }
)
```

### On-Demand Evaluation

```python
# 01-tutorials/07-AgentCore-evaluations/02-running-evaluations/01-strands/01-on-demand-eval.ipynb
results = eval_client.run(
    agent_id=agent_id, session_id=session_id,
    evaluators=["Builtin.GoalSuccessRate", "Builtin.Correctness",
                "Builtin.ToolParameterAccuracy", custom_evaluator_id]
)
for r in results.results:
    print(r.label, r.value, r.explanation, r.token_usage)
```

### Online Evaluation (Continuous Production Monitoring)

```python
# 01-tutorials/07-AgentCore-evaluations/02-running-evaluations/01-strands/02-online-eval.ipynb
eval_client.create_online_config(
    agent_id=agent_id,
    config_name="prod_monitoring",
    sampling_rate=100,             # % of sessions
    evaluator_list=["Builtin.GoalSuccessRate", "Builtin.Correctness", custom_id],
    auto_create_execution_role=True
)
# Results appear automatically in GenAI Observability dashboard
```

---

## 8. AgentCore Policy (Cedar)

Fine-grained tool invocation access control using the Cedar policy language. Attaches to Gateway — **default action is DENY**.

### SDK Surface

```python
from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
```

### Create Policy Engine + Attach to Gateway

```python
# 01-tutorials/08-AgentCore-policy/01-Getting-Started/
client = boto3.client("bedrock-agentcore-control")
engine = client.create_policy_engine(name="MyPolicyEngine", description="...")

gateway_client = GatewayClient(region_name='eu-west-1')
gateway_client.update_gateway_policy_engine(
    gateway_identifier=gateway_id,
    policy_engine_arn=engine["policyEngineArn"],
    mode="ENFORCE",                # or "LOG_ONLY" for testing
)
```

### Cedar Policy Syntax

```python
policy_client = PolicyClient(region_name='eu-west-1')

# Input parameter constraints:
cedar = (
    'permit(principal, '
    'action == AgentCore::Action::"OrderTarget___get_order", '
    f'resource == AgentCore::Gateway::"{GATEWAY_ARN}") '
    'when { context.input.coverage_amount <= 1000000 };'
)

policy_client.create_or_get_policy(
    policy_engine_id=engine_id, name="limit_coverage",
    definition={"cedar": {"statement": cedar}})
```

### Cedar Policy Patterns

```cedar
-- Principal-based restriction
permit(principal == AgentCore::Principal::"test-user",
  action == AgentCore::Action::"RiskTarget___invoke",
  resource == AgentCore::Gateway::"<arn>");

-- Group-based with IdP claims
forbid(principal,
  action == AgentCore::Action::"ApprovalTarget___approve",
  resource == AgentCore::Gateway::"<arn>")
unless { principal has scope && principal.scope.contains("group:Controller") };

-- Multi-condition
permit(principal,
  action == AgentCore::Action::"AppTarget___create",
  resource == AgentCore::Gateway::"<arn>")
when {
  context.input.amount <= 1000000 &&
  (context.input.region == "US" || context.input.region == "CAN")
};
```

### Natural Language to Cedar (NL2Cedar)

```python
# 01-tutorials/08-AgentCore-policy/02-Natural-Language-Policy-Authoring/
result = policy_client.generate_policy(
    policy_engine_id=engine_id,
    name="nl_policy",
    resource={"arn": gateway_arn},
    content={"rawText": "Allow all users to invoke the application tool when coverage < 1M and region is US or CAN"},
    fetch_assets=True,      # Fetches gateway target schemas for context
)
# result["generatedPolicies"][0]["definition"]["cedar"]["statement"] -> Cedar output
```

---

## 9. Framework Integrations

Every framework implements the same contract: wrap your agent, wire to `@app.entrypoint`, call `app.run()`. All files under `03-integrations/agentic-frameworks/`.

### Strands Agents

```python
# strands_agent_file_system.py
from strands import Agent
from strands_tools import file_read, file_write, editor
app = BedrockAgentCoreApp()
agent = Agent(tools=[file_read, file_write, editor])

@app.entrypoint
def agent_invocation(payload, context):
    return {"result": agent(payload.get("prompt")).message}
app.run()
```

### LangGraph

```python
# langgraph_agent_web_search.py
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

llm = init_chat_model("eu.anthropic.claude-sonnet-4-6", model_provider="bedrock_converse")
graph = graph_builder.compile()

@app.entrypoint
def agent_invocation(payload, context):
    output = graph.invoke({"messages": [{"role": "user", "content": payload.get("prompt")}]})
    return {"result": output['messages'][-1].content}
```

### LlamaIndex

```python
# llama_agent_hello_world.py
from llama_index.core.agent.workflow import FunctionAgent

agent = FunctionAgent(tools=tools, llm=llm)

@app.entrypoint
async def main(payload):
    response = await agent.run(payload.get("prompt"))
    return response.response.content
```

### PydanticAI

```python
# pydantic_bedrock_claude.py
from pydantic_ai.models.bedrock import BedrockConverseModel

model = BedrockConverseModel('eu.anthropic.claude-sonnet-4-6')
agent = Agent(model=model, system_prompt="...")

@app.entrypoint
def main(payload):
    return agent.run_sync(payload.get("prompt")).output
```

### AutoGen

```python
# autogen_agent_hello_world.py
from autogen_agentchat.agents import AssistantAgent

agent = AssistantAgent(name="agent", model_client=model_client, tools=[get_weather])

@app.entrypoint
async def main(payload):
    result = await Console(agent.run_stream(task=payload.get("prompt")))
    return {"result": result.messages[-1].content}
```

### OpenAI Agents SDK (with Handoff)

```python
# openai_agents_handoff_example.py
from agents import Agent, Runner, WebSearchTool

travel_agent = Agent(name="Travel Expert", tools=[WebSearchTool()])
food_agent = Agent(name="Food Expert", tools=[WebSearchTool()])
triage = Agent(name="Triage", handoffs=[travel_agent, food_agent])

@app.entrypoint
async def agent_invocation(payload, context):
    result = await Runner.run(triage, payload.get("prompt"))
    return {"result": result.final_output}
```

### Claude Agent SDK (with Hooks + Sub-Agents)

```python
# claude-agent/claude-hooks/agent.py
from claude_agent_sdk import ClaudeAgentOptions, query

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(matcher="Bash|Write|Edit", hooks=[pre_tool_guard])],
        "PostToolUse": [HookMatcher(hooks=[post_tool_audit])],
    },
    agents={
        "code-analyzer": AgentDefinition(tools=["Read", "Grep", "Glob"], prompt="..."),
        "reporter": AgentDefinition(tools=["Read", "Write"], prompt="..."),
    },
)
```

### Google ADK (Python + Java)

```python
# adk/adk_agent_google_search.py
from google.adk.agents import Agent
from google.adk.runners import Runner

root_agent = Agent(model="gemini-2.0-flash", tools=[google_search])

@app.entrypoint
def agent_invocation(payload, context):
    return asyncio.run(call_agent_async(payload.get("prompt"), USER_ID, context.session_id))
```

Java: Spring Boot with manual `POST /invocations` + `GET /ping` contract.

### Mastra (TypeScript)

```typescript
// typescript_mastra/src/index.ts
app.post('/invocations', async (req, res) => {
    const agent = mastra.getAgent('utilityAgent');
    const stream = await agent.stream(req.body.prompt, { maxSteps: 5 });
    for await (const chunk of stream.textStream) { res.write(chunk); }
    res.end();
});
```

---

## 10. Agent-to-Agent Communication (A2A)

Two major patterns: **A2A Protocol** (agent card discovery + standardized messaging) and **boto3 direct invocation**.

### A2A Protocol — Strands

```python
# 02-use-cases/A2A-realestate-agentcore-multiagents/propertysearchagent_strands/agent_agentcore.py
from strands.multiagent.a2a import A2AServer

agent = Agent(tools=[search_properties, get_property_details], model=model_id)
a2a_server = A2AServer(agent=agent, http_url="http://0.0.0.0:9000/", serve_at_root=True)
app = a2a_server.to_fastapi_app()    # Serves at /.well-known/agent-card.json
uvicorn.run(app, host="0.0.0.0", port=9000)
```

### A2A Protocol — Coordinator Discovery + Invocation

```python
# 02-use-cases/A2A-realestate-agentcore-multiagents/realestate_coordinator/agent.py
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory

async def send_agent_message(message, agent_url, agent_name):
    resolver = A2ACardResolver(httpx_client=httpx_client, base_url=agent_url)
    agent_card = await resolver.get_agent_card()

    client = ClientFactory(ClientConfig(httpx_client=httpx_client, streaming=False)).create(agent_card)
    async for event in client.send_message(create_a2a_message(message)):
        # Extract response from Task artifacts
```

### A2A Protocol — ADK Host + Remote Agents

```python
# 02-use-cases/A2A-multi-agent-incident-response/host_adk_agent/agent.py
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

monitor_agent = RemoteA2aAgent(
    name="monitor_agent",
    agent_card=f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations/.well-known/agent-card.json",
    a2a_client_factory=_create_client_factory(provider_name=provider, session_id=sid)
)
root_agent = Agent(model=GOOGLE_MODEL_ID, sub_agents=[monitor_agent, websearch_agent])
```

Agent discovery via `.well-known/agent-card.json` on the AgentCore runtime endpoint. Auth via M2M OAuth.

### Direct Invocation (boto3 — simpler)

```python
# 04-infrastructure-as-code/terraform/multi-agent-runtime/agent-orchestrator-code/agent.py
@tool
def call_specialist_agent(query: str) -> Dict[str, Any]:
    """Call the specialist agent for detailed analysis"""
    client = boto3.client("bedrock-agentcore")
    response = client.invoke_agent_runtime(
        agentRuntimeArn=os.environ["SPECIALIST_ARN"],
        qualifier="DEFAULT",
        payload=json.dumps({"prompt": query}),
    )
    return {"status": "success", "content": [{"text": parse_response(response)}]}
```

Simpler than A2A but no agent card discovery, no standard protocol.

---

## 11. Infrastructure as Code (Terraform)

Four progressive Terraform stacks in `04-infrastructure-as-code/terraform/`. All share the same pipeline: **S3 (source) -> CodeBuild (ARM64 Docker) -> ECR -> AgentCore Runtime**.

### Provider Requirements

```hcl
# All stacks — versions.tf
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.21" }
  }
}
```

AWS provider `~> 6.21` includes `aws_bedrockagentcore_*` resources.

### 11A. Basic Runtime

**Path:** `04-infrastructure-as-code/terraform/basic-runtime/`

```hcl
# main.tf
resource "aws_bedrockagentcore_agent_runtime" "basic_agent" {
  agent_runtime_name = "my_agent"
  role_arn           = aws_iam_role.agent_execution.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent_ecr.repository_url}:latest"
    }
  }
  network_configuration { network_mode = "PUBLIC" }
  environment_variables = { AWS_REGION = var.aws_region }
}
```

**IAM trust policy** (all stacks use this):

```hcl
# iam.tf
assume_role_policy = jsonencode({
  Statement = [{
    Effect    = "Allow"
    Principal = { Service = "bedrock-agentcore.amazonaws.com" }
    Action    = "sts:AssumeRole"
    Condition = {
      StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.id }
      ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${region}:${account}:*" }
    }
  }]
})
```

**S3 change detection** (MD5 in key):

```hcl
# s3.tf
data "archive_file" "agent_source" {
  type        = "zip"
  source_dir  = "${path.module}/agent-code"
  output_path = "${path.module}/.terraform/agent-code.zip"
}
resource "aws_s3_object" "agent_source" {
  key  = "agent-code-${data.archive_file.agent_source.output_md5}.zip"
  # New key on code change -> triggers CodeBuild rebuild
}
```

### 11B. MCP Server Runtime (+ Cognito JWT)

**Path:** `04-infrastructure-as-code/terraform/mcp-server-agentcore-runtime/`

```hcl
# main.tf
resource "aws_bedrockagentcore_agent_runtime" "mcp_server" {
  protocol_configuration { server_protocol = "MCP" }
  authorizer_configuration {
    custom_jwt_authorizer {
      allowed_clients = [aws_cognito_user_pool_client.mcp_client.id]
      discovery_url   = "https://cognito-idp.${region}.amazonaws.com/${pool_id}/.well-known/openid-configuration"
    }
  }
}
```

```hcl
# cognito.tf
resource "aws_cognito_user_pool" "mcp_user_pool" { name = "${var.stack_name}-pool" }
resource "aws_cognito_user_pool_client" "mcp_client" {
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}
```

### 11C. Multi-Agent Runtime (A2A)

**Path:** `04-infrastructure-as-code/terraform/multi-agent-runtime/`

Two runtimes: specialist builds first, orchestrator gets specialist ARN as env var.

```hcl
# orchestrator.tf
resource "aws_bedrockagentcore_agent_runtime" "orchestrator" {
  environment_variables = {
    SPECIALIST_ARN = aws_bedrockagentcore_agent_runtime.specialist.agent_runtime_arn
  }
  depends_on = [aws_bedrockagentcore_agent_runtime.specialist]
}

# iam.tf — orchestrator needs InvokeAgentRuntime permission
resource "aws_iam_role_policy" "orchestrator_invoke_specialist" {
  policy = jsonencode({
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock-agentcore:InvokeAgentRuntime"]
      Resource = "arn:aws:bedrock-agentcore:${region}:${account}:runtime/*"
    }]
  })
}
```

### 11D. End-to-End Weather Agent (Full Stack)

**Path:** `04-infrastructure-as-code/terraform/end-to-end-weather-agent/`

All AgentCore resources:

```hcl
# browser.tf
resource "aws_bedrockagentcore_browser" "browser" {
  name = "weather_browser"
  network_configuration { network_mode = "PUBLIC" }
}

# code_interpreter.tf
resource "aws_bedrockagentcore_code_interpreter" "code_interpreter" {
  name = "weather_code_interpreter"
  network_configuration { network_mode = "PUBLIC" }
}

# memory.tf
resource "aws_bedrockagentcore_memory" "memory" {
  name                  = "weather_memory"
  event_expiry_duration = 30  # Days
}

# main.tf — wires everything
resource "aws_bedrockagentcore_agent_runtime" "weather_agent" {
  environment_variables = {
    BROWSER_ID          = aws_bedrockagentcore_browser.browser.browser_id
    CODE_INTERPRETER_ID = aws_bedrockagentcore_code_interpreter.code_interpreter.code_interpreter_id
    MEMORY_ID           = aws_bedrockagentcore_memory.memory.id
  }
}
```

**Observability (vended logs + X-Ray traces):**

```hcl
# observability.tf — Three-part vended log delivery pattern
resource "aws_cloudwatch_log_delivery_source" "logs" {
  log_type     = "APPLICATION_LOGS"
  resource_arn = aws_bedrockagentcore_agent_runtime.weather_agent.agent_runtime_arn
}
resource "aws_cloudwatch_log_delivery_destination" "logs" {
  delivery_destination_configuration {
    destination_resource_arn = aws_cloudwatch_log_group.agent_runtime_logs.arn
  }
}
resource "aws_cloudwatch_log_delivery" "logs" {
  delivery_source_name     = aws_cloudwatch_log_delivery_source.logs.name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.logs.arn
}

# X-Ray traces pipeline (same pattern, log_type = "TRACES", destination = XRAY)
```

### Terraform Resource Types Summary

| Resource | Purpose |
|----------|---------|
| `aws_bedrockagentcore_agent_runtime` | Managed container runtime |
| `aws_bedrockagentcore_browser` | Hosted browser tool |
| `aws_bedrockagentcore_code_interpreter` | Sandboxed code execution |
| `aws_bedrockagentcore_memory` | Vector memory (pgvector) |
| `aws_bedrockagentcore_gateway` | MCP gateway |
| `aws_bedrockagentcore_gateway_target` | Backend target for gateway |

---

## 12. Blueprints

### 12A. Customer Support Agent (CDK + Strands)

**Path:** `05-blueprints/customer-support-agent-with-agentcore/`

Full-stack: CDK TypeScript infra, Strands Python agent, Cognito auth (tiered groups), Gateway + Lambda MCP targets, Memory with 4 strategies, Policy Engine, versioned endpoints.

```typescript
// cdk/lib/stacks/agentcore-stack.ts — Gateway with Lambda MCP targets
this.agentCoreGateway = new bedrockagentcore.CfnGateway(this, 'Gateway', {
  protocolType: "MCP",
  authorizerType: "CUSTOM_JWT",
  authorizerConfiguration: {
    customJwtAuthorizer: {
      discoveryUrl: cognitoDiscoveryUrl,
      allowedClients: [clientId],
      allowedScopes: [`${appName}-api/invoke`],
    },
  },
});

// Memory with all 4 strategies
this.agentCoreMemory = new bedrockagentcore.CfnMemory(this, 'Memory', {
  eventExpiryDuration: 30,
  memoryStrategies: [
    { semanticMemoryStrategy: { name: "FactExtractor", namespaces: ["/facts/{actorId}/"] }},
    { userPreferenceMemoryStrategy: { name: "PreferenceLearner", namespaces: ["/preferences/{actorId}/"] }},
    { summaryMemoryStrategy: { name: "SessionSummarizer", namespaces: ["/summaries/{actorId}/{sessionId}/"] }},
    { episodicMemoryStrategy: { name: "EpisodeTracker", namespaces: ["/episodes/{actorId}/{sessionId}/"],
        reflectionConfiguration: { namespaces: ["/episodes/{actorId}/"] }}},
  ],
});

// Versioned endpoints
new bedrockagentcore.CfnRuntimeEndpoint(this, 'Prod', {
  agentRuntimeId: runtime.attrAgentRuntimeId, agentRuntimeVersion: "1", name: "PROD" });
new bedrockagentcore.CfnRuntimeEndpoint(this, 'Dev', {
  agentRuntimeId: runtime.attrAgentRuntimeId, agentRuntimeVersion: "1", name: "DEV" });
```

**Agent code (JWT extraction + Memory + MCP):**

```python
# src/main.py
@app.entrypoint
async def invoke(payload, context):
    user_token = _get_bearer_token(context)       # Extract from Authorization header
    claims = _decode_jwt(user_token)               # Runtime already validated
    actor_id = claims.get("sub")

    session_manager = AgentCoreMemorySessionManager(AgentCoreMemoryConfig(
        memory_id=MEMORY_ID, session_id=context.session_id, actor_id=actor_id,
        retrieval_config={
            "/facts/{actorId}/": RetrievalConfig(top_k=10, relevance_score=0.4),
            "/preferences/{actorId}/": RetrievalConfig(top_k=5, relevance_score=0.5),
        },
    ), REGION)

    mcp_client = get_streamable_http_mcp_client(user_token=user_token)
    with mcp_client as client:
        tools = client.list_tools_sync()
        agent = Agent(model=load_model(), session_manager=session_manager,
            tools=[shell, file_read] + tools)
        async for event in agent.stream_async(payload.get("prompt")):
            if "data" in event: yield event["data"]
```

### 12B. End-to-End Customer Service Agent (Terraform + LangGraph)

**Path:** `05-blueprints/end-to-end-customer-service-agent/`

Modular Terraform (7 modules), LangGraph backend, Streamlit frontend.

```hcl
# infra/main.tf — Module composition
module "container_image" { source = "./modules/container-image" }
module "bedrock_role"    { source = "./modules/agentcore-iam-role" }
module "kb_stack"        { source = "./modules/kb-stack" }
module "guardrail"       { source = "./modules/bedrock-guardrails" }
module "cognito"         { source = "./modules/cognito" }
module "parameters"      { source = "./modules/parameters" }
module "secrets"         { source = "./modules/secrets" }
```

**Guardrails:**

```hcl
# modules/bedrock-guardrails/main.tf
resource "aws_bedrock_guardrail" "guardrail" {
  content_policy_config {
    filters_config { input_strength = "MEDIUM"; output_strength = "MEDIUM"; type = "HATE" }
  }
  sensitive_information_policy_config {
    pii_entities_config { action = "ANONYMIZE"; type = "US_SOCIAL_SECURITY_NUMBER" }
  }
  topic_policy_config {
    topics_config { name = "investment_topic"; type = "DENY"; definition = "..." }
  }
  word_policy_config { managed_word_lists_config { type = "PROFANITY" } }
}
```

---

## 13. End-to-End Use Cases

All under `02-use-cases/`. Each combines multiple AgentCore components.

| Use Case | Components | Key Pattern |
|----------|-----------|-------------|
| **A2A Incident Response** | 3 runtimes (ADK Host + Strands Monitor + OpenAI WebSearch), M2M OAuth, Memory | Multi-framework A2A with Cognito per-agent clients |
| **A2A Real Estate** | Coordinator + Search + Booking agents, Strands A2A, OAuth passthrough | Strands `A2AServer` + `A2ACardResolver` |
| **Healthcare Appointment** | Gateway + Strands/LangGraph agents consuming same FHIR tools | Same Gateway, two framework implementations |
| **Farm Management** | Gateway + 5 Lambda tools + Runtime + Memory | Lambda -> MCP -> Strands agent pattern |
| **Finance Personal Assistant** | Budget + Investment + Tax agents -> Coordinator | Strands orchestrator with specialized sub-agents |
| **AWS Operations Agent** | Runtime, Gateway, Identity, DIY agent | Full-featured with CLI ops scripts |
| **SRE Agent** | Multi-agent (LangGraph), Gateway, Browser Tool | Supervisor pattern with approval workflows |
| **Customer Support** | Runtime, Gateway, Identity (Cognito), Lambda, Memory | Dual-namespace memory retrieval |
| **Customer Support VPC** | Same + VPC endpoints, Aurora, DynamoDB | Private deployment, no internet |
| **Market Trends** | Runtime, Memory, Browser Tool, LangGraph | Financial analysis with Playwright automation |
| **Slide Deck Generator** | Runtime, Memory | Memory comparison: basic vs memory-enhanced |
| **Text to Python IDE** | Runtime, Code Interpreter | Code generation + sandboxed execution |
| **Lakehouse Agent** | Runtime, Identity (OAuth), Row-level security | Federated identity for per-user data access |
| **Video Games Sales** | Runtime, Tools, Frontend (React) | Strands + PostgreSQL full web app |
| **Device Management** | Runtime, Gateway, Frontend (React) | IoT/smart home agent |
| **Observability Full-Stack** | Runtime, Memory, OTEL, Tools | Sales analyst with custom spans + memory hooks |

---

## Appendix A: SDK Dependencies

| Package | Purpose |
|---------|---------|
| `bedrock-agentcore` | Core SDK — `BedrockAgentCoreApp`, `MemoryClient`, `IdentityClient`, `CodeInterpreter`, `BrowserClient` |
| `bedrock-agentcore-starter-toolkit` | CLI + higher-level SDK — `Runtime`, `Evaluation`, `PolicyClient`, `GatewayClient` |
| `strands-agents` | Primary agent framework — `Agent`, `@tool`, `HookProvider`, `MCPClient`, `A2AServer` |
| `strands-agents-tools` | Built-in tools — `file_read`, `file_write`, `editor`, `AgentCoreBrowser`, `AgentCoreMemoryToolProvider` |
| `aws-opentelemetry-distro` | OTEL auto-instrumentation (installed in Dockerfile, not requirements.txt) |
| `mcp` | MCP protocol SDK — `FastMCP`, `ClientSession`, `streamablehttp_client` |

## Appendix B: Terraform Resource Types

| Resource | Purpose |
|----------|---------|
| `aws_bedrockagentcore_agent_runtime` | Managed container runtime |
| `aws_bedrockagentcore_browser` | Hosted browser tool |
| `aws_bedrockagentcore_code_interpreter` | Sandboxed code execution |
| `aws_bedrockagentcore_memory` | Vector memory (pgvector) |
| `aws_bedrockagentcore_gateway` | MCP gateway (Lambda/REST/OpenAPI -> MCP) |
| `aws_bedrockagentcore_gateway_target` | Backend target for gateway |
| `aws_bedrock_guardrail` | Content/PII/topic filtering |
| `bedrockagentcore.CfnRuntime` (CDK) | CloudFormation equivalent |
| `bedrockagentcore.CfnGateway` (CDK) | CloudFormation equivalent |
| `bedrockagentcore.CfnMemory` (CDK) | CloudFormation equivalent |
| `bedrockagentcore.CfnRuntimeEndpoint` (CDK) | Versioned endpoint (PROD/DEV) |

## Appendix C: Port Conventions

| Port | Protocol |
|------|----------|
| 8080 | HTTP — `/invocations` + `/ping` |
| 8000 | MCP — Streamable HTTP |
| 9000 | A2A — Agent-to-Agent protocol |
