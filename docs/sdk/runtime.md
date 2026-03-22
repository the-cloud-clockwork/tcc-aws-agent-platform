---
title: Runtime
nav_order: 1
---

# Runtime

The Runtime subsystem wraps Amazon Bedrock AgentCore's container execution model. It turns your agent logic into a standards-compliant HTTP server that AgentCore can invoke, health-check, and stream from.

## Key Classes

| Class | Purpose |
|-------|---------|
| `AgentCoreApp` | Main application container — blueprint loader, entrypoint registration, middleware chain |
| `GenericHandler` | Default invocation handler — marshals HTTP → agent context → HTTP |
| `SessionManager` | Per-invocation session isolation using AgentCore session tokens |
| `StreamBuffer` | Async buffer for token-by-token streaming responses |

## The `/invocations` + `/ping` Contract

AgentCore expects every runtime container to expose two HTTP endpoints:

- `POST /invocations` — receives the agent payload and returns the response
- `GET /ping` — returns `200 OK` when the container is healthy

`AgentCoreApp` registers both automatically. You only write the agent logic.

## The `@app.entrypoint` Pattern

```python
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp.from_blueprint("agent.yaml")

@app.entrypoint
async def handle(context):
    session = context.session
    message = context.input_text

    # Use Strands agent
    response = await session.agent.invoke(message)
    return response
```

The `@app.entrypoint` decorator registers your function as the handler for `/invocations`. The framework takes care of:

- Deserializing the AgentCore invocation payload
- Creating and injecting the `context` object
- Serializing the return value back to AgentCore's expected format
- Flushing the stream buffer if streaming is enabled

## Context Object

The `context` object injected into every entrypoint call contains:

| Attribute | Type | Description |
|-----------|------|-------------|
| `context.session` | `AgentSession` | Current session — Strands agent, memory, tool registry |
| `context.input_text` | `str` | The user's message text |
| `context.session_id` | `str` | AgentCore session token |
| `context.metadata` | `dict` | Additional invocation metadata |
| `context.stream` | `StreamBuffer` | Write tokens here for streaming responses |

## Streaming Support

Enable streaming in the blueprint and write chunks to `context.stream`:

```python
@app.entrypoint
async def handle(context):
    async for chunk in session.agent.stream(context.input_text):
        await context.stream.write(chunk)
    await context.stream.close()
```

Blueprint flag:

```yaml
runtime:
  streaming: true
```

## Middleware Chain

Register middleware with `@app.middleware` to intercept every invocation:

```python
@app.middleware
async def add_request_id(context, call_next):
    context.metadata["request_id"] = generate_id()
    return await call_next(context)
```

Middleware runs in registration order before the entrypoint. Use it for cross-cutting concerns: request logging, auth header injection, or rate-limit checks.

## Dockerfile Pattern

AgentCore expects a specific entry command. The standard Dockerfile for a runtime container:

```dockerfile
FROM public.ecr.aws/lambda/python:3.12

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "-m", "agent_core.runtime.entrypoint"]
```

The `agent_core.runtime.entrypoint` module starts the HTTP server on port 8080, which is what AgentCore routes traffic to.

## Loading from a Blueprint

`AgentCoreApp.from_blueprint` reads the YAML file and wires all subsystems automatically:

```python
app = AgentCoreApp.from_blueprint("agent.yaml")
```

This single call initializes memory, observability hooks, gateway client, policy client, and identity providers — everything declared in the blueprint. See [Blueprints](../blueprints/) for the full configuration schema.

## Session Lifecycle

`SessionManager` creates an isolated session for each invocation. Sessions are keyed by the AgentCore session token, ensuring that concurrent invocations do not share state. The Strands agent instance, tool registry, and in-progress memory writes are all scoped to the session.

When an invocation completes, the session manager flushes pending memory events and releases resources. Long-running streaming sessions maintain their session for the duration of the stream.
