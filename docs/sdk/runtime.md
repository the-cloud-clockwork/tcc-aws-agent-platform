---
title: Runtime
nav_order: 1
parent: SDK Reference
---

# Runtime

The Runtime subsystem wraps Amazon Bedrock AgentCore's container execution model. It turns your agent logic into a standards-compliant HTTP server that AgentCore can invoke, health-check, and stream from.

## Key Classes

| Class | Purpose |
|-------|---------|
| `AgentCoreApp` | Main application container — entrypoint registration, middleware stack, A2A mounting |
| `GenericHandler` | Default invocation handler — marshals HTTP to agent context to HTTP |
| `SessionManager` | Per-invocation session isolation using AgentCore session tokens |

## The `/invocations` + `/ping` Contract

AgentCore expects every runtime container to expose two HTTP endpoints:

- `POST /invocations` — receives the agent payload and returns the response
- `GET /ping` — returns `200 OK` when the container is healthy

`AgentCoreApp` registers both automatically. You only write the agent logic.

## The `@app.entrypoint` Pattern

```python
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp()

@app.entrypoint
def handler(payload, context):
    session_id = context.session_id
    prompt = payload.get("prompt")

    # Use Strands agent
    result = agent(prompt)
    return result.message

if __name__ == "__main__":
    app.run()
```

The `@app.entrypoint` decorator registers your function as the handler for `/invocations`. The decorated function receives two positional arguments:

- `payload` — a `dict` containing the invocation data (prompt, parameters, etc.)
- `context` — an SDK context object with session metadata

The framework takes care of:

- Deserializing the AgentCore invocation payload into the `payload` dict
- Creating and injecting the `context` object
- Serializing the return value back to AgentCore's expected format

## Context Object

The `context` object injected into every entrypoint call contains:

| Attribute | Type | Description |
|-----------|------|-------------|
| `context.session_id` | `str` | AgentCore session token |
| `context.request_headers` | `dict` | HTTP request headers from the invocation |

## Streaming Support

For streaming responses, use `async def` with `yield`. Each yielded value is sent as an SSE event to the caller:

```python
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp()

@app.entrypoint
async def handler(payload, context):
    async for event in agent.stream_async(payload.get("prompt")):
        if "data" in event:
            yield event["data"]

if __name__ == "__main__":
    app.run()
```

The framework handles SSE framing and connection lifecycle automatically. No manual stream management is required.

## Middleware

`AgentCoreApp` accepts a Starlette middleware stack via the `middleware` constructor parameter. Middleware runs around every invocation:

```python
from agent_core.runtime import AgentCoreApp
from starlette.middleware import Middleware

class ErrorHandlingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        except Exception:
            # Handle error
            raise

class LoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Log request
        await self.app(scope, receive, send)

app = AgentCoreApp(
    middleware=[
        Middleware(ErrorHandlingMiddleware),
        Middleware(LoggingMiddleware),
    ]
)
```

Use middleware for cross-cutting concerns: error handling, request logging, auth header injection, or rate-limit checks.

## Dockerfile Pattern

AgentCore runs agents as containers on microVMs. The standard Dockerfile:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

The `AgentCoreApp.run()` call in your entrypoint script starts the HTTP server on port 8080, which is what AgentCore routes traffic to.

## MCP Server Hosting

AgentCore Runtime can also host MCP servers directly. Set `server_protocol: MCP` in your runtime configuration to expose your agent as an MCP endpoint instead of the default invocation protocol. This allows other agents to consume your agent's capabilities as MCP tools through the Gateway.

## Loading from a Blueprint

`AgentCoreApp.from_blueprint` reads the blueprint via a `BlueprintLoader` and wires all subsystems automatically:

```python
from agent_core.blueprints import BlueprintLoader
from agent_core.runtime import AgentCoreApp

loader = BlueprintLoader("blueprints/")
app = AgentCoreApp.from_blueprint(loader, "my-agent")

if __name__ == "__main__":
    app.run()
```

This single call initializes memory, observability hooks, gateway client, policy client, and identity providers — everything declared in the blueprint. See [Blueprints](../blueprints/) for the full configuration schema.

## Complete Example

```python
from agent_core.runtime import AgentCoreApp
from starlette.middleware import Middleware
from strands import Agent

agent = Agent(model=model)

app = AgentCoreApp(
    middleware=[Middleware(LoggingMiddleware)],
)

@app.entrypoint
def handler(payload, context):
    session_id = context.session_id
    prompt = payload.get("prompt")
    result = agent(prompt)
    return result.message

if __name__ == "__main__":
    app.run()
```

## Session Lifecycle

`SessionManager` creates an isolated session for each invocation. Sessions are keyed by the AgentCore session token (`context.session_id`), ensuring that concurrent invocations do not share state. The Strands agent instance, tool registry, and in-progress memory writes are all scoped to the session.

When an invocation completes, the session manager flushes pending memory events and releases resources. Long-running streaming sessions maintain their session for the duration of the stream.
