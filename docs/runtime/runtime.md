---
title: Runtime
nav_order: 1
parent: "Runtime & Memory"
---

# AgentCore Runtime

AgentCore Runtime is the compute layer that runs each agent session inside an **isolated microVM**. Each inbound session gets its own microVM with isolated CPU, memory, and filesystem. Sessions are ephemeral — when a session ends the microVM is destroyed, which is why [Memory](memory) exists as a separate service.

The runtime contract is deliberately minimal: your container exposes two HTTP endpoints on port 8080, and AgentCore handles everything else — TLS termination, auth validation, session routing, scaling, and microVM lifecycle.

## The `/invocations` + `/ping` Contract

Every AgentCore Runtime container must expose exactly two HTTP endpoints:

- `POST /invocations` — receives the agent payload and returns the response
- `GET /ping` — returns `200 OK` when the container is healthy

These are both served on **port 8080**. `AgentCoreApp` registers both automatically. You only write the handler logic.

## `AgentCoreApp` and `@app.entrypoint`

`AgentCoreApp` wraps `BedrockAgentCoreApp` from the `bedrock_agentcore` SDK. It registers your handler via the `@app.entrypoint` decorator and adds default middleware (`CorrelationIdMiddleware`, `StructuredErrorMiddleware`) plus an OTel telemetry flush on every invocation (see [OTel Flush](#otel-telemetry-flush) below).

The decorated function receives two positional arguments:

- `payload` — a `dict` with the invocation data (prompt, parameters, etc.)
- `context` — an `InvocationContext` with `session_id` and `request_headers`

```python
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp()

@app.entrypoint
def handler(payload, context):
    session_id = context.session_id
    prompt = payload.get("prompt")
    result = agent(prompt)
    return result.message

if __name__ == "__main__":
    app.run()
```

All four handler shapes are supported: sync function, async coroutine, sync generator, and async generator. Use `async def` with `yield` for streaming responses.

```python
@app.entrypoint
async def handler(payload, context):
    async for event in agent.stream_async(payload.get("prompt")):
        if "data" in event:
            yield event["data"]
```

AgentCore handles SSE framing automatically. Each yielded value is sent as a Server-Sent Event to the caller.

## Blueprint-Driven Setup (Recommended)

The most common `app.py` pattern delegates entirely to `BlueprintLoader.build_entrypoint()`. This single call initializes memory, observability hooks, the gateway client, the policy client, and identity providers — everything declared in the blueprint YAML.

```python
from agent_core.blueprints import BlueprintLoader
from agent_core.runtime import AgentCoreApp

loader = BlueprintLoader("blueprints/")
app = AgentCoreApp.from_blueprint(loader, "my-agent")

if __name__ == "__main__":
    app.run()
```

`AgentCoreApp.from_blueprint(loader, agent_id)` is a thin alias that delegates to `loader.build_entrypoint()`. The 5-line `app.py` above is the standard pattern for all blueprint-driven agents. The manual `@app.entrypoint` approach is available for advanced cases requiring full control.

## GenericHandler

When you use `loader.build_entrypoint()`, the loader registers a `GenericHandler` as the entrypoint function. `GenericHandler` manages the full invocation lifecycle:

1. Normalizes the incoming payload
2. Looks up `AgentConfigRegistry` for the agent configuration
3. Applies defaults and validates required fields
4. Performs idempotency checking (if configured)
5. Builds a `BlueprintLoader` agent session with memory, tools, and observability wired
6. Runs the agent via the Strands SDK
7. Marshals the output schema (if `output_schema` is declared in the blueprint)
8. Returns an `AgentResult`

Domain developers declare behavior in the blueprint YAML; `GenericHandler` wires and executes it.

## OTel Telemetry Flush

AgentCore microVMs are **suspended immediately** after returning a response. The OTLP `BatchLogRecordProcessor` and `PeriodicExportingMetricReader` background threads never reach their flush interval — so buffered log records and metrics are discarded when the microVM suspends. Without intervention, agent `logger.*` output never reaches CloudWatch while traces export fine (because Strands already flushes the tracer provider per invocation).

`AgentCoreApp` wraps every registered entrypoint with `_wrap_with_flush()`, which force-flushes all three OTel providers — logger, meter, and tracer — in the `finally` block of every invocation. The flush is best-effort (a flush failure never breaks the response). All four handler shapes (sync, async, sync generator, async generator) are covered.

This is the fix for the missing CloudWatch logs issue on agent runtimes. MCP server runtimes (long-lived processes) are not affected.

## A2A Auto-Mount for Specialist Agents

`BlueprintLoader.build_entrypoint()` automatically mounts an A2A server when the blueprint declares `multi_agent.role: specialist` and `runtime.a2a_port` is set. The A2A server runs in a background daemon thread on that port, started before `self._sdk_app.run()` hands off control.

```yaml
# specialist-agent.yaml
runtime:
  a2a_port: 9000

multi_agent:
  role: specialist
```

No code changes are needed in `app.py` — the loader calls `A2AServerWrapper.from_blueprint()` and `app.mount_a2a()` automatically.

## Custom Middleware

`AgentCoreApp` accepts a Starlette middleware stack via the `middleware` constructor parameter:

```python
from starlette.middleware import Middleware

app = AgentCoreApp(
    middleware=[
        Middleware(MyLoggingMiddleware),
        Middleware(MyErrorMiddleware),
    ]
)
```

Middleware runs around every invocation. Use it for cross-cutting concerns: request logging, rate limiting, custom auth header injection.

## Dockerfile Pattern

AgentCore runs containers on ARM64 (Graviton) microVMs. Base images must support multi-architecture builds. The standard pattern:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

`app.run()` starts the HTTP server on port 8080. No additional uvicorn or gunicorn configuration is required — the SDK manages the server.

**ARM64 requirement**: all native dependencies must support Graviton. `python:3.12-slim` is multi-arch and works out of the box.

## Runtime Constraints

| Constraint | Value |
|-----------|-------|
| Port | 8080 (both `/invocations` and `/ping`) |
| Architecture | ARM64 (Graviton) only |
| Network modes | `PUBLIC` or `PRIVATE` (VPC-attached) |
| A2A port | Configurable via `runtime.a2a_port` or `A2A_PORT` env var |
| SSH / direct debugging | Not available on microVMs |
| Idle timeout | 15 minutes (configurable) |
| Maximum session lifetime | 8 hours |
| Pricing model | Per-session-second; idle time is billed until the session is stopped |

The A2A port has no fixed default — it must be explicitly set in the blueprint or `A2A_PORT` env var. The loader raises `ValueError` if neither is configured when A2A is needed.

## Why Not Lambda for Agents

Lambda is used throughout the platform — as Gateway targets, infrastructure utilities, and the Prompt Registry — but never as the deployment target for agents. Agents are stateful, long-running, and session-oriented: a single invocation may make 5–20 LLM calls in a tool-use loop, stream for 30+ seconds, and maintain browser session state. Lambda is designed for the opposite: short, stateless, fast functions.

```
Agent (microVM)            Gateway            Lambda tool
Long-running       -->   (MCP proxy)   -->   Short-lived
Stateful                                     < 30 seconds
Streaming                                    Returns data
```

Agents run on Runtime, tools run on Lambda, and the Gateway bridges them.

## See Also

- [Runtime SDK Reference](../sdk/runtime) — `AgentCoreApp`, `GenericHandler`, `SessionManager`, context object
- [Memory](memory) — persisting conversation state across microVM sessions
- [A2A Communication](a2a) — running the A2A server alongside the main runtime
- [Agent Blueprint — `runtime` block](../blueprints/agent-blueprint) — `a2a_port`, streaming, network mode
