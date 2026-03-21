# Amazon Bedrock AgentCore — Concepts & Architecture Decisions

> Answers to the "why" and "how" questions that the code samples don't explain directly. Companion to SUMMARY.md — covers the mental model behind each AgentCore component, how they connect, and practical Strands-focused examples.

---

## Table of Contents

1. [What Is AgentCore Runtime, Really?](#1-what-is-agentcore-runtime-really)
2. [Deploying an Agent on AgentCore Runtime](#2-deploying-an-agent-on-agentcore-runtime)
3. [Why Not Lambda for Agent Hosting?](#3-why-not-lambda-for-agent-hosting)
4. [AgentCore Gateway — The Universal Tool Bridge](#4-agentcore-gateway--the-universal-tool-bridge)
5. [AgentCore Identity — How Auth Flows Through the System](#5-agentcore-identity--how-auth-flows-through-the-system)
6. [AgentCore Memory — Persistence Across Sessions](#6-agentcore-memory--persistence-across-sessions)
7. [CloudWatch GenAI Observability — Tracing Agent Behavior](#7-cloudwatch-genai-observability--tracing-agent-behavior)
8. [AgentCore Evaluation — Measuring Agent Quality](#8-agentcore-evaluation--measuring-agent-quality)
9. [AgentCore Policy — Fine-Grained Access Control with Cedar](#9-agentcore-policy--fine-grained-access-control-with-cedar)
10. [Strands Agents on AgentCore — The Full Integration](#10-strands-agents-on-agentcore--the-full-integration)
11. [Agent-to-Agent Communication (A2A) with Strands](#11-agent-to-agent-communication-a2a-with-strands)

---

## 1. What Is AgentCore Runtime, Really?

AgentCore Runtime is its own managed compute layer that runs your agent inside an **isolated microVM per session**.

The contract is dead simple: your container exposes `POST /invocations` and `GET /ping` on port 8080. That's it. AgentCore handles everything else — scaling, warm container pools, session routing, TLS termination, IAM/JWT auth, and microVM lifecycle management. Each user session gets its own microVM with isolated CPU, memory, and filesystem. Sessions auto-terminate after 15 minutes of idle time (configurable) or 8 hours maximum lifetime.

Under the hood, this is almost certainly AWS Firecracker (the same microVM tech behind Lambda), but the samples never confirm this explicitly. What the samples *do* confirm is that sessions are fully isolated — no shared state between sessions unless you explicitly use AgentCore Memory.

```python
# The entire runtime contract — with SDK:
@app.entrypoint
def handler(payload, context):
    session_id = context.session_id  # Each session = its own microVM
    return agent(payload.get("prompt")).message

# Or without the SDK — raw FastAPI:
app = FastAPI()

@app.post("/invocations")
async def invoke(request): return StreamingResponse(...)

@app.get("/ping")
async def ping(): return {"status": "healthy"}

uvicorn.run(app, host="0.0.0.0", port=8080)
```

Both deploy identically. The SDK is a convenience, not a requirement.

---

## 2. Deploying an Agent on AgentCore Runtime

Build a Docker image, push to ECR, call `create_agent_runtime()`. AgentCore takes it from there.

```
Your Code -> Docker Image -> ECR -> AgentCore Runtime -> microVM per session
```

**What you get for free:**
- Per-session microVM isolation (no noisy neighbors, no shared state leaks)
- Auto-scaling with warm container pools (sub-second cold starts after initial)
- Built-in `/invocations` routing with session affinity
- IAM SigV4 or JWT/Cognito inbound auth — zero code
- OTEL auto-instrumentation — just include `aws-opentelemetry-distro` and wrap with `opentelemetry-instrument`
- Session lifecycle management (idle timeout, max lifetime, explicit stop)
- MCP protocol support (`server_protocol: MCP`) for hosting MCP servers
- A2A protocol support on port 9000
- `network_mode: PRIVATE` for VPC-only deployments

**Constraints:**
- No SSH into the microVM. No debugging a running session in-place.
- No custom networking beyond PUBLIC/PRIVATE. No sidecar containers.
- Pricing is per-session-second. Can be expensive for long-running idle sessions if you forget to call `stop_runtime_session()`.
- ARM64 only (Graviton). x86 containers are not supported.
- Max 8-hour session lifetime. Not suitable for persistent background workers.

### Practical Example: Strands Agent -> AgentCore Runtime

**The agent code:**

```python
from strands import Agent, tool
from strands.models import BedrockModel

model = BedrockModel(model_id="eu.anthropic.claude-sonnet-4-6")

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city"""
    return f"Weather in {city}: 22C, sunny"

agent = Agent(model=model, tools=[get_weather],
    system_prompt="You are a helpful weather assistant.")
```

**Wire it to the runtime — add 5 lines:**

```python
# agent.py
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload):
    return agent(payload.get("prompt")).message['content'][0]['text']

if __name__ == "__main__":
    app.run()
```

**Deploy via CLI:**

```bash
agentcore configure -e agent.py
agentcore launch
agentcore invoke '{"prompt": "Weather in London?"}'
```

---

## 3. Why Not Lambda for Agent Hosting?

Lambda appears throughout the codebase but **never** as a deployment target for agents themselves. It's used exclusively as:

- **Gateway targets** — Lambda functions wrapped by AgentCore Gateway into MCP tools
- **Infrastructure** — OAuth token rotation, Cognito triggers, utility functions
- **Invokers** — A Lambda calling *into* an AgentCore-hosted agent

The reason is architectural: agents are **stateful, long-running, and session-oriented**. A single agent invocation can make multiple LLM calls (tool-use loops with 5-20+ iterations), hold browser sessions open for minutes, stream responses over SSE for 30+ seconds, and maintain conversation state across a multi-turn session. Lambda's execution limits and lack of persistent connections make it fundamentally unsuitable.

Lambda is *perfect* for the tools that agents call — short, stateless, fast functions that return structured data. That's exactly what AgentCore Gateway does.

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Agent (microVM) │────>│   Gateway    │────>│  Lambda fn   │
│  Long-running    │     │  (MCP proxy) │     │  Short, fast │
│  Stateful        │     │              │     │  Stateless   │
│  Streaming       │     │              │     │  < 30s       │
└─────────────────┘     └──────────────┘     └──────────────┘
```

**The mental model: agents live on Runtime, tools live on Lambda, Gateway bridges them.**

---

## 4. AgentCore Gateway — The Universal Tool Bridge

### What Problem Does Gateway Solve?

Agents need tools. Tools live everywhere — Lambda functions, REST APIs, OpenAPI services, other MCP servers. Without Gateway, every agent needs custom adapter code for each tool backend. Gateway eliminates that by auto-generating a **single MCP interface** regardless of what's behind it.

The key insight: Gateway is not just an API proxy. It's a **protocol translator** that makes any backend look like an MCP server with typed tool schemas. Your agent speaks MCP to Gateway; Gateway speaks whatever the backend needs.

### Where Gateway Sits in the Architecture

```
                           ┌──────────────────────┐
                           │   AgentCore Gateway   │
                           │   (MCP interface)     │
                           │                       │
Agent ──── MCP ────>       │  ┌─── Lambda Target   │ ──── IAM Role ────> Lambda fn
                           │  ├─── OpenAPI Target  │ ──── HTTP ────────> REST API
                           │  ├─── MCP Target      │ ──── MCP ─────────> MCP Server on Runtime
                           │  ├─── Smithy Target   │ ──── HTTP ────────> Smithy API
                           │  └─── API GW Target   │ ──── HTTP ────────> API Gateway
                           └──────────────────────┘
```

### Two Auth Layers

Gateway has **inbound** and **outbound** auth — they solve different problems:

**Inbound auth** controls who can call the Gateway. Two options:
- `AWS_IAM` — callers sign requests with SigV4. Agents running on Runtime with the right IAM role just work.
- `CUSTOM_JWT` — callers provide a JWT (typically from Cognito). This is how you authenticate end-users through the gateway — their Cognito token flows from the frontend, through the agent, to the gateway.

**Outbound auth** controls how the Gateway authenticates to its targets:
- `GATEWAY_IAM_ROLE` — Gateway assumes its own IAM role to invoke Lambda targets. No token needed.
- OAuth2 credential provider — Gateway gets an M2M token to call OAuth-protected targets (like a Runtime-hosted MCP server).

This separation is powerful: an end-user authenticates to the agent with their Cognito JWT, but the agent calls Gateway tools using the gateway's own IAM role. The user's identity flows as context, not as credentials.

### How Gateway Turns a Lambda into MCP Tools

You define the tool schema inline when creating the target. Gateway maps each tool name to a Lambda invocation with the corresponding input:

```python
client.create_gateway_target(
    gatewayIdentifier=gateway_id,
    name='OrderTools',
    targetConfiguration={
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [
                        {
                            "name": "get_order",
                            "description": "Get order details by ID",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"orderId": {"type": "string"}},
                                "required": ["orderId"]
                            }
                        },
                        {
                            "name": "process_refund",
                            "description": "Process a refund for an order",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "orderId": {"type": "string"},
                                    "reason": {"type": "string"}
                                },
                                "required": ["orderId", "reason"]
                            }
                        }
                    ]
                }
            }
        }
    },
    credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
)
```

When a Strands agent calls `get_order(orderId="123")`, the chain is: Strands -> MCPClient -> Gateway -> Lambda(event={"orderId": "123"}) -> response back through the same chain. The agent has no idea it's calling Lambda.

### Strands Agent Consuming Gateway Tools

```python
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

# Point MCPClient at the Gateway URL with auth
mcp_client = MCPClient(lambda: streamablehttp_client(
    url=gateway_url,
    headers={"Authorization": f"Bearer {cognito_token}"}
))

with mcp_client:
    gateway_tools = mcp_client.list_tools_sync()  # Discovers all tools across all targets
    agent = Agent(
        model=model,
        tools=[local_tool_1, local_tool_2] + gateway_tools  # Mix local + remote
    )
    result = agent("Get details for order ORD-456 and process a refund")
```

The agent sees `get_order` and `process_refund` as regular tools alongside its local tools. Gateway handles the routing, auth, and protocol translation transparently.

### Gateway as MCP Proxy for Runtime MCP Servers

Gateway can also front a Runtime-hosted MCP server. This is useful when you want a single gateway URL to aggregate tools from multiple MCP servers:

```
Agent -> Gateway (single URL) -> Runtime MCP Server A (math tools)
                               -> Runtime MCP Server B (weather tools)
                               -> Lambda Target C (order tools)
```

The agent connects to one gateway URL and gets all tools from all targets. No need to manage multiple MCP connections.

---

## 5. AgentCore Identity — How Auth Flows Through the System

### The Core Concept: Delegation, Not Impersonation

AgentCore Identity operates on **delegation**. Agents authenticate as themselves while carrying verifiable user context. The agent never pretends to be the user — it proves that the user authorized it to act, and the backend decides what the agent can do on that user's behalf.

This matters because agents are autonomous — they make decisions about which tools to call, in what order, with what parameters. You need to know both *who the user is* (for authorization decisions) and *that the agent is legitimately acting for them* (for audit and trust).

### Three Auth Patterns

```
Pattern 1: Inbound Auth (who can call my agent?)
┌────────┐      JWT/SigV4      ┌──────────┐
│  User  │ ──────────────────> │  Runtime  │ ── validates token, passes to @app.entrypoint
└────────┘                     └──────────┘

Pattern 2: Outbound Auth - API Keys (agent needs an API key)
┌──────────┐     @requires_api_key     ┌───────────────────┐     GetSecretValue     ┌──────────────────┐
│  Agent   │ ────────────────────────> │ Identity Service   │ ──────────────────── > │ Secrets Manager  │
└──────────┘                           └───────────────────┘                         └──────────────────┘

Pattern 3: Outbound Auth - OAuth 3LO (agent needs user's token for external service)
┌────────┐   auth URL   ┌──────────┐   @requires_access_token   ┌───────────────────┐   OAuth flow   ┌──────────┐
│  User  │ <─────────── │  Agent   │ ─────────────────────────> │ Identity Service   │ ────────────> │ Google   │
│        │ ── consent ─> │          │                            │                    │ <── token ─── │ GitHub   │
└────────┘               └──────────┘                            └───────────────────┘               └──────────┘
```

### Pattern 1: Inbound Auth — Protecting Your Agent

When you configure a Runtime with JWT auth, the Runtime validates the token before your code even runs. Invalid or missing tokens get `AccessDeniedException` — your `@app.entrypoint` never fires.

```python
# During deployment — configure Cognito JWT validation:
rt.configure(
    entrypoint="agent.py",
    authorizer_configuration={
        "customJWTAuthorizer": {
            "discoveryUrl": f"https://cognito-idp.eu-west-1.amazonaws.com/{pool_id}/.well-known/openid-configuration",
            "allowedClients": [client_id],
        }
    },
)

# Inside your agent — extract user identity from the validated token:
@app.entrypoint
async def invoke(payload, context):
    user_token = context.request_headers.get("authorization", "").replace("Bearer ", "")
    claims = jwt.decode(user_token, options={"verify_signature": False})  # Already validated by Runtime
    user_id = claims.get("sub")
    user_email = claims.get("email")
    # Now you know WHO is calling and can scope memory, tools, etc. to that user
```

### Pattern 2: Outbound Auth — API Keys

When your agent needs a third-party API key (OpenAI, Tavily, etc.), you don't hardcode it. Identity stores it in Secrets Manager and injects it at runtime via a decorator:

```python
# One-time setup — store the key:
from bedrock_agentcore.services.identity import IdentityClient
identity_client = IdentityClient(region='eu-west-1')
identity_client.create_api_key_credential_provider({
    "name": "openai-apikey-provider",
    "apiKey": "sk-..."
})

# In your agent code — retrieve at runtime:
from bedrock_agentcore.identity.auth import requires_api_key

@requires_api_key(provider_name="openai-apikey-provider")
async def init_model(*, api_key: str):
    os.environ["OPENAI_API_KEY"] = api_key  # Injected by Identity service
```

The key never touches your codebase, environment variables, or container image. It's fetched from Secrets Manager at runtime by the Identity service and injected into the decorated function.

### Pattern 3: Outbound Auth — 3-Legged OAuth (User Consent)

This is the most complex flow. Your agent needs to access a user's Google Calendar or GitHub repos — which requires the *user's* OAuth consent, not just the agent's credentials.

The flow:
1. Agent calls a tool decorated with `@requires_access_token`
2. Identity service generates an OAuth authorization URL
3. Agent presents the URL to the user (via `on_auth_url` callback)
4. User clicks the link, consents, and is redirected to the callback server
5. Callback server completes the OAuth flow with Identity service
6. Identity service returns the access token to the decorated function
7. Agent uses the token to call the external API

```python
@tool(name="Get_calendar_events")
async def get_calendar():
    @requires_access_token(
        provider_name="google-cal-provider",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        auth_flow="USER_FEDERATION",
        on_auth_url=lambda url: print(f"Please visit: {url}"),  # Show to user
        callback_url=os.environ["CALLBACK_URL"],
    )
    async def get_events(access_token: Optional[str] = "") -> str:
        service = build("calendar", "v3", credentials=Credentials(token=access_token))
        events = service.events().list(calendarId='primary').execute()
        return json.dumps(events.get('items', []))
    return await get_events()
```

The nested function pattern is intentional — `@requires_access_token` goes on the inner function so Strands' tool schema derivation doesn't expose the `access_token` parameter to the LLM.

### Pattern 4: M2M Auth — Agent-to-Agent

When agents call other agents (A2A), they need machine-to-machine tokens. No user consent required — it's service-to-service:

```python
@requires_access_token(
    provider_name="monitor-agent-provider",
    scopes=[], auth_flow="M2M",
    into="bearer_token",
    force_authentication=True,
)
def create_a2a_client(bearer_token: str = "") -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={
        "Authorization": f"Bearer {bearer_token}",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id
    })
```

Each agent gets its own Cognito client credentials. The Identity service handles token refresh automatically.

---

## 6. AgentCore Memory — Persistence Across Sessions

### The Problem Memory Solves

Without Memory, every Runtime session is a blank slate. The microVM is isolated — nothing persists after the session ends. If a user says "I prefer vegetarian food" in session 1, session 2 has no idea. Memory bridges that gap by providing managed storage *outside* the microVM.

### Two Tiers: Short-Term and Long-Term

**Short-term memory** is raw event storage. You push conversation turns in, you pull them back out. It's a buffer — useful for continuing a conversation within or across sessions, but it doesn't *understand* anything.

**Long-term memory** adds intelligence. When you configure strategies, the system asynchronously extracts structured knowledge from raw events — user preferences, facts, summaries, episodic memories. This extracted data is stored with vector embeddings in pgvector for semantic retrieval.

```
                    Short-Term (Events)                Long-Term (Strategies)
                    ┌──────────────────┐               ┌───────────────────────┐
create_event() ───> │  Raw turns       │ ──async───>   │ Semantic extraction   │
                    │  TTL: 7-365 days │   (~30s)      │ pgvector embeddings   │
                    │  get_last_k_turns│               │ Namespaced retrieval  │
                    └──────────────────┘               │                       │
                                                       │ /facts/{actorId}/     │
                                        retrieve_ ──── │ /preferences/{actorId}│
                                        memories()     │ /summaries/...        │
                                                       │ /episodes/...         │
                                                       └───────────────────────┘
```

### How It Works in Practice

**Step 1:** Create a memory resource with strategies:

```python
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType

client = MemoryClient(region_name='eu-west-1')
memory = client.create_memory_and_wait(
    name="CustomerAgent",
    strategies=[
        { StrategyType.USER_PREFERENCE.value: {
            "name": "PreferenceLearner",
            "namespaces": ["user/{actorId}/preferences/"]
        }},
        { StrategyType.SEMANTIC.value: {
            "name": "FactExtractor",
            "namespaces": ["user/{actorId}/facts/"]
        }},
        { StrategyType.SUMMARY.value: {
            "name": "Summarizer",
            "namespaces": ["user/{actorId}/{sessionId}/summaries/"]
        }},
    ],
    event_expiry_days=30,
)
```

**Step 2:** Wire it into your Strands agent via hooks. This is the canonical pattern — a `HookProvider` that loads history when the agent starts and saves messages as they're added:

```python
from strands import Agent, HookProvider, HookRegistry
from strands.agent.agent_result import AgentInitializedEvent, MessageAddedEvent

class MemoryHookProvider(HookProvider):
    def __init__(self, memory_client, memory_id):
        self.client = memory_client
        self.memory_id = memory_id

    def on_agent_initialized(self, event: AgentInitializedEvent):
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")

        # Load short-term history
        turns = self.client.get_last_k_turns(
            memory_id=self.memory_id, actor_id=actor_id,
            session_id=session_id, k=5)

        # Retrieve long-term context via semantic search
        preferences = self.client.retrieve_memories(
            memory_id=self.memory_id,
            namespace=f"user/{actor_id}/preferences/",
            query="user preferences", top_k=5)

        # Inject into system prompt
        if turns or preferences:
            event.agent.system_prompt += f"\n\nRecent history:\n{format_turns(turns)}"
            event.agent.system_prompt += f"\n\nKnown preferences:\n{format_memories(preferences)}"

    def on_message_added(self, event: MessageAddedEvent):
        messages = event.agent.messages
        last = messages[-1]
        if last.get("content", [{}])[0].get("text"):
            self.client.create_event(
                memory_id=self.memory_id,
                actor_id=event.agent.state["actor_id"],
                session_id=event.agent.state["session_id"],
                messages=[(last["content"][0]["text"], last["role"])])

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self.on_message_added)

# Usage:
agent = Agent(
    model=model, tools=[...],
    hooks=[MemoryHookProvider(client, memory_id)],
    state={"actor_id": "user_123", "session_id": "session_abc"}
)
```

### Namespacing and Multi-Agent Memory

Namespaces use `{actorId}` and `{sessionId}` placeholders that resolve at runtime. This means:
- `/preferences/{actorId}/` — per-user preferences, shared across all sessions
- `/facts/{actorId}/` — per-user facts, shared across all sessions
- `/summaries/{actorId}/{sessionId}/` — per-session summaries

In multi-agent setups, you can use **memory branching** — each sub-agent writes to its own branch, and the coordinator reads from all branches:

```python
from bedrock_agentcore.memory import MemorySessionManager

manager = MemorySessionManager(memory_id=memory_id, region_name='eu-west-1')
session = manager.create_memory_session(actor_id, session_id)

# Coordinator writes to "main"
session.add_turns(messages, branch={"name": "main"})

# Sub-agent writes to its own branch
session.fork_conversation(root_event_id=event_id, branch_name="flight_agent")

# Coordinator reads from any branch
flight_context = session.get_last_k_turns(k=5, branch_name="flight_agent")
```

---

## 7. CloudWatch GenAI Observability — Tracing Agent Behavior

### What Gets Traced

AgentCore's observability layer captures the complete execution graph of every agent invocation:

```
Trace: session_abc / invocation_1
├── Agent Invocation (2.3s total)
│   ├── LLM Call #1 (0.8s) — prompt: "Weather in London?", tokens: 142 in / 67 out
│   │   └── Tool Decision: get_weather(city="London")
│   ├── Tool Call: get_weather (0.1s) — input: {city: "London"}, output: "22C, sunny"
│   ├── LLM Call #2 (0.6s) — prompt: [tool result + continuation], tokens: 203 in / 89 out
│   │   └── Final Response
│   └── Response: "The weather in London is 22C and sunny."
```

Every LLM call captures: model ID, full prompt, full response, input/output token counts, latency. Every tool call captures: tool name, parameters, result, latency. Errors capture: exception type, stack trace, which step failed.

### How to Enable It

**On AgentCore Runtime — automatic.** Just include `aws-opentelemetry-distro` in your Docker image and wrap your entrypoint:

```dockerfile
RUN pip install aws-opentelemetry-distro==0.12.2
CMD ["opentelemetry-instrument", "python", "-m", "my_agent"]
```

That's it. No code changes. The OTEL auto-instrumentation hooks into Strands' internal execution and exports traces to CloudWatch.

**For custom spans** (when you want to trace your own tool internals):

```python
from opentelemetry import trace

tracer = trace.get_tracer("my_tools", "1.0.0")

@tool
def complex_search(query: str) -> str:
    with tracer.start_as_current_span("database_search") as span:
        span.set_attribute("search.query", query)
        results = db.search(query)
        span.set_attribute("search.results_count", len(results))
        span.add_event("search_completed")
        return json.dumps(results)
```

**For session correlation** (track a user across multiple invocations):

```python
from opentelemetry import baggage, context

ctx = baggage.set_baggage("session.id", user_session_id)
ctx = baggage.set_baggage("user.id", user_email)
token = context.attach(ctx)
result = agent(prompt)
context.detach(token)
```

### Strands-Specific: trace_attributes

Strands has native OTEL integration — you can attach metadata at the agent level:

```python
agent = Agent(
    model=model, tools=[...],
    trace_attributes={
        "user.id": "nestor@cloudclockwork.com",
        "environment": "production",
        "agent.version": "2.1.0",
        "tags": ["customer-support", "tier-1"],
    }
)
```

These attributes appear on every span the agent produces, making filtering and dashboarding straightforward.

### Data Protection

Two layers protect sensitive data from appearing in traces:

1. **Bedrock Guardrails** — anonymize PII in agent responses before they reach the trace:
   ```python
   model = BedrockModel(model_id=model_id,
       guardrail_id=guardrail_id, guardrail_version="1",
       guardrail_trace="enabled")
   ```

2. **CloudWatch Logs Data Protection** — mask PII patterns (SSN, credit cards, etc.) in the log streams themselves, so even if PII makes it into a trace, it's masked at rest.

---

## 8. AgentCore Evaluation — Measuring Agent Quality

### The Problem

How do you know if your agent is good? Not just "does it run" but "does it give correct answers, use the right tools, and avoid harmful content?" AgentCore Evaluation answers this with **LLM-as-judge** — a separate model evaluates your agent's behavior by reviewing its traces.

### How It Works

Evaluation reads the OTEL traces that Observability captures. It replays the agent's behavior — what was asked, what tools were called, what was returned — and a judge model scores it. You never need to re-run the agent.

```
Agent runs -> OTEL traces captured -> Evaluation reads traces -> Judge model scores
```

### 13 Built-in Evaluators

| Category | Evaluators | What They Measure |
|----------|-----------|-------------------|
| Response Quality | Correctness, Completeness, Faithfulness, Helpfulness, Harmlessness, Coherence, Relevance | Did the agent answer well? |
| Task Completion | GoalSuccessRate | Did the agent achieve the user's goal? |
| Tool Usage | ToolSelectionAccuracy, ToolParameterAccuracy | Did the agent pick the right tools with the right inputs? |
| Safety | Harmfulness, Stereotyping | Did the agent produce dangerous or biased content? |

### On-Demand Evaluation (Score a Specific Session)

```python
from bedrock_agentcore_starter_toolkit import Evaluation

eval_client = Evaluation(region='eu-west-1')

results = eval_client.run(
    agent_id=agent_id,
    session_id=session_id,
    evaluators=[
        "Builtin.GoalSuccessRate",
        "Builtin.Correctness",
        "Builtin.ToolSelectionAccuracy",
    ]
)

for r in results.results:
    print(f"{r.evaluator_name}: {r.label} ({r.value}) — {r.explanation}")
    # GoalSuccessRate: Achieved (1.0) — The agent successfully retrieved weather data...
    # Correctness: Correct (1.0) — The response accurately reflects the tool output...
    # ToolSelectionAccuracy: Accurate (1.0) — The agent correctly selected get_weather...
```

### Custom Evaluators (Domain-Specific)

When built-in evaluators aren't enough — say you need to check "did the agent follow our company's refund policy?" — create a custom LLM-as-judge:

```python
custom = eval_client.create_evaluator(
    name="refund_policy_compliance",
    level="TRACE",
    config={
        "llmAsAJudge": {
            "modelConfig": {"bedrockEvaluatorModelConfig": {
                "modelId": "eu.anthropic.claude-sonnet-4-6",
                "inferenceConfig": {"maxTokens": 500, "temperature": 1.0}
            }},
            "instructions": """Evaluate whether the agent followed the refund policy:
                1. Did it verify the order exists?
                2. Did it check eligibility (within 30 days)?
                3. Did it confirm with the user before processing?
                Context: {context}
                Agent response: {assistant_turn}""",
            "ratingScale": {"numerical": [
                {"value": 1.0, "label": "Fully Compliant"},
                {"value": 0.5, "label": "Partially Compliant"},
                {"value": 0.0, "label": "Non-Compliant"},
            ]}
        }
    }
)
```

### Online Evaluation (Continuous Production Monitoring)

Instead of manually running evaluations, you can set up continuous scoring of a percentage of live sessions:

```python
eval_client.create_online_config(
    agent_id=agent_id,
    config_name="prod_monitoring",
    sampling_rate=100,  # Evaluate 100% of sessions (adjust for cost)
    evaluator_list=["Builtin.GoalSuccessRate", "Builtin.Correctness", custom_evaluator_id],
    auto_create_execution_role=True
)
```

Results feed directly into the GenAI Observability dashboard. You get real-time quality metrics alongside latency and token counts.

---

## 9. AgentCore Policy — Fine-Grained Access Control with Cedar

### The Problem

Gateway gives agents access to tools. But not every user should be able to call every tool, or call it with any parameters. A junior analyst shouldn't approve a $10M insurance claim. A customer shouldn't access another customer's data.

Policy solves this by inserting a **Cedar policy engine** between the Gateway and its targets. Every tool call goes through policy evaluation before reaching the backend.

### How It Works

```
Agent -> Gateway -> Policy Engine (Cedar) -> ALLOW/DENY -> Target
```

When a Policy Engine is attached to a Gateway, the **default action is DENY**. An empty engine blocks everything. You explicitly permit what's allowed.

Cedar policies evaluate three things:
- **Principal** — who is calling (from the JWT claims)
- **Action** — which tool is being called
- **Resource** — which gateway is being accessed
- **Context** — the tool's input parameters

### Setting It Up

```python
# 1. Create the engine
client = boto3.client("bedrock-agentcore-control")
engine = client.create_policy_engine(name="InsurancePolicies")

# 2. Attach to Gateway (ENFORCE mode blocks unauthorized calls; LOG_ONLY monitors without blocking)
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
gateway_client = GatewayClient(region_name='eu-west-1')
gateway_client.update_gateway_policy_engine(
    gateway_identifier=gateway_id,
    policy_engine_arn=engine["policyEngineArn"],
    mode="ENFORCE",
)

# 3. Add Cedar policies
from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient
policy_client = PolicyClient(region_name='eu-west-1')
```

### Cedar Policy Patterns

**Allow a tool with parameter constraints:**
```cedar
permit(principal,
  action == AgentCore::Action::"OrderTarget___process_refund",
  resource == AgentCore::Gateway::"<gateway_arn>")
when { context.input.amount <= 500 };
```
Anyone can process refunds, but only up to $500.

**Restrict by user group (from JWT claims):**
```cedar
forbid(principal,
  action == AgentCore::Action::"ApprovalTarget___approve_claim",
  resource == AgentCore::Gateway::"<gateway_arn>")
unless { principal has scope && principal.scope.contains("group:Managers") };
```
Only managers can approve claims. Everyone else is denied.

**Multi-condition with geography:**
```cedar
permit(principal,
  action == AgentCore::Action::"AppTarget___create_application",
  resource == AgentCore::Gateway::"<gateway_arn>")
when {
  context.input.coverage_amount <= 1000000 &&
  (context.input.applicant_region == "US" || context.input.applicant_region == "CAN")
};
```

### Natural Language to Cedar

For teams that don't want to write Cedar by hand, there's NL2Cedar — describe the policy in plain English and the system generates Cedar:

```python
result = policy_client.generate_policy(
    policy_engine_id=engine_id,
    name="auto_policy",
    resource={"arn": gateway_arn},
    content={"rawText": "Allow users to create applications only when coverage is under 1 million and the region is US or Canada"},
    fetch_assets=True,  # Fetches tool schemas from Gateway for context
)
# result["generatedPolicies"][0]["definition"]["cedar"]["statement"] -> valid Cedar
```

### The Key Insight

Policy operates at the **Gateway level**, not the Runtime level. This means:
- Tools behind the same Gateway share the same policy engine
- The agent doesn't need to know about policies — it calls tools normally, and policy silently allows or denies
- Policy decisions are based on the end-user's JWT claims, not the agent's identity
- You can use `LOG_ONLY` mode to see what *would* be blocked without actually blocking it — useful for testing policies before enforcement

---

## 10. Strands Agents on AgentCore — The Full Integration

### Why Strands Is the Primary Framework

Strands is AWS's own agent framework, built specifically to work with Bedrock and AgentCore. While AgentCore supports 10+ frameworks, Strands has the deepest integration:

- Native `BedrockModel` — direct Bedrock Converse API, no adapter layer
- `HookProvider` system — lifecycle hooks for Memory, Observability, custom logic
- `MCPClient` — first-class MCP protocol support for Gateway tools
- `A2AServer` — built-in Agent-to-Agent protocol server
- `AgentCoreBrowser` — native Browser Tool wrapper
- `AgentCoreMemoryToolProvider` — memory as agent-callable tools
- `trace_attributes` — native OTEL metadata on all spans

### The Complete Strands + AgentCore Stack

Here's what a production Strands agent on AgentCore looks like when it uses everything:

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from strands_tools.browser import AgentCoreBrowser

app = BedrockAgentCoreApp()

# Model
model = BedrockModel(model_id="eu.anthropic.claude-sonnet-4-6")

# Memory (see Section 6 for MemoryHookProvider)
memory_client = MemoryClient(region_name='eu-west-1')
memory_hook = MemoryHookProvider(memory_client, os.environ["MEMORY_ID"])

# Browser tool
browser = AgentCoreBrowser(region="eu-west-1")

# Local tools
@tool
def internal_lookup(customer_id: str) -> str:
    """Look up customer in internal database"""
    return db.query(customer_id)

@app.entrypoint
async def invoke(payload, context):
    # Extract user identity from JWT (Runtime validated it)
    user_token = context.request_headers.get("authorization", "").replace("Bearer ", "")
    claims = jwt.decode(user_token, options={"verify_signature": False})

    # Gateway tools (authenticated with user's token for policy evaluation)
    mcp_client = MCPClient(lambda: streamablehttp_client(
        url=os.environ["GATEWAY_URL"],
        headers={"Authorization": f"Bearer {user_token}"}
    ))

    with mcp_client:
        gateway_tools = mcp_client.list_tools_sync()

        agent = Agent(
            model=model,
            tools=[internal_lookup, browser.browser] + gateway_tools,
            hooks=[memory_hook],
            state={"actor_id": claims["sub"], "session_id": context.session_id},
            system_prompt="You are a customer support agent...",
            trace_attributes={"user.id": claims["sub"], "environment": "production"},
        )

        async for event in agent.stream_async(payload.get("prompt")):
            if "data" in event:
                yield event["data"]

if __name__ == "__main__":
    app.run()
```

This single file uses: **Runtime** (microVM hosting), **Gateway** (remote tools), **Identity** (JWT auth passthrough), **Memory** (conversation persistence), **Browser** (web browsing), **Observability** (auto + trace_attributes), and **Policy** (enforced at the Gateway level transparently).

### Tool Mixing

A key Strands pattern: mix local tools, MCP tools from Gateway, and built-in AgentCore tools in a single agent. The LLM sees them all as equivalent — it doesn't know or care where a tool runs:

```python
tools = [
    internal_lookup,              # Local Python function
    browser.browser,              # AgentCore Browser (hosted Chromium)
    *mcp_client.list_tools_sync() # Gateway tools (Lambda/REST/OpenAPI behind MCP)
]
agent = Agent(model=model, tools=tools)
```

---

## 11. Agent-to-Agent Communication (A2A) with Strands

### The Concept

A2A lets agents discover and talk to each other using a standardized protocol. Each agent publishes an **agent card** at `/.well-known/agent-card.json` that describes its capabilities. Other agents resolve that card, establish a connection, and send messages.

```
┌─────────────────┐          ┌─────────────────┐
│  Coordinator     │   A2A    │  Specialist      │
│  Agent           │ ──────> │  Agent           │
│                  │          │                  │
│  Port 9000       │          │  Port 9000       │
│  /.well-known/   │          │  /.well-known/   │
│  agent-card.json │          │  agent-card.json │
└─────────────────┘          └─────────────────┘
         │                            │
    Runtime A                    Runtime B
    (microVM)                    (microVM)
```

### Why Not Just Call invoke_agent_runtime() Directly?

You *can* call agents directly via boto3 — it's simpler for basic cases:

```python
@tool
def call_specialist(query: str) -> str:
    client = boto3.client("bedrock-agentcore")
    response = client.invoke_agent_runtime(
        agentRuntimeArn=specialist_arn, qualifier="DEFAULT",
        payload=json.dumps({"prompt": query}))
    return parse_response(response)
```

But A2A adds: agent discovery (no hardcoded ARNs), capability negotiation (agent cards describe what an agent can do), standardized message format (structured tasks with artifacts), and cross-framework interoperability (a Strands agent can talk to an ADK agent via A2A).

### Strands A2A Server (Making Your Agent Discoverable)

```python
from strands import Agent
from strands.multiagent.a2a import A2AServer

agent = Agent(
    model=model,
    tools=[search_properties, get_property_details],
    system_prompt="You are a property search specialist..."
)

# Wrap the agent in an A2A server
a2a_server = A2AServer(
    agent=agent,
    http_url="http://0.0.0.0:9000/",
    serve_at_root=True  # Required for AgentCore deployment
)

# Mount as FastAPI app (runs on port 9000, separate from Runtime's 8080)
app = a2a_server.to_fastapi_app()
uvicorn.run(app, host="0.0.0.0", port=9000)
```

This agent now publishes `/.well-known/agent-card.json` and accepts A2A messages.

### Strands A2A Client (Calling Another Agent)

```python
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory

async def call_specialist(message: str, agent_url: str) -> str:
    # 1. Discover the agent
    httpx_client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})
    resolver = A2ACardResolver(httpx_client=httpx_client, base_url=agent_url)
    agent_card = await resolver.get_agent_card()

    # 2. Create a client from the card
    config = ClientConfig(httpx_client=httpx_client, streaming=False)
    client = ClientFactory(config).create(agent_card)

    # 3. Send a message and get the response
    msg = create_a2a_message(message)
    async for event in client.send_message(msg):
        if hasattr(event, 'result') and event.result.artifacts:
            return event.result.artifacts[0].parts[0].text
```

### A2A with Runtime: The Auth Flow

When agents talk across Runtimes, they need M2M OAuth tokens. Each agent gets its own Cognito client credentials:

```
Coordinator Agent                    Specialist Agent
(Runtime A)                          (Runtime B, OAuth-protected)
     │                                      │
     │  1. @requires_access_token(M2M)      │
     │  2. Get M2M token from Identity      │
     │  3. Call /.well-known/agent-card.json │
     │ ────────── Bearer token ───────────> │
     │  4. Send A2A message                  │
     │ ────────── Bearer token ───────────> │
     │  5. Get response                      │
     │ <─────────── response ─────────────  │
```

The agent URL on a deployed Runtime follows this pattern:
```
https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations/.well-known/agent-card.json
```

### Multi-Agent Architecture Example

A real estate coordinator with two specialist agents:

```python
# Coordinator agent — calls specialists as tools
@tool
async def search_properties(criteria: str) -> str:
    """Search available properties matching criteria"""
    return await call_specialist(criteria, property_search_url)

@tool
async def book_viewing(property_id: str, date: str) -> str:
    """Book a property viewing"""
    return await call_specialist(f"Book viewing for {property_id} on {date}", booking_url)

coordinator = Agent(
    model=model,
    tools=[search_properties, book_viewing],
    system_prompt="You are a real estate coordinator..."
)
```

The coordinator doesn't know how the specialists work internally. It just sends messages and gets responses. Each specialist can be a different framework, a different model, even a different AWS account — A2A abstracts all of that.
