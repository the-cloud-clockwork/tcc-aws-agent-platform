---
title: Runtime
nav_order: 1
parent: SDK Reference
---

# Runtime

The Runtime subsystem wraps Amazon Bedrock AgentCore's container execution model. It turns your agent logic into a standards-compliant HTTP server that AgentCore can invoke, health-check, and stream from.

> **Architecture guide:** [Runtime & Memory](../runtime.md)

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `AgentCoreApp` | `agent_core.runtime.entrypoint` | Main application container — entrypoint registration, A2A mounting, OTel flush |
| `GenericHandler` | `agent_core.runtime.handler` | Default invocation handler — payload normalization, idempotency, blueprint agent session |

## The `/invocations` + `/ping` Contract

AgentCore expects every runtime container to expose two HTTP endpoints:

- `POST /invocations` — receives the agent payload and returns the response
- `GET /ping` — returns `200 OK` when the container is healthy

`AgentCoreApp` registers both automatically by wrapping `BedrockAgentCoreApp` from `bedrock_agentcore.runtime`. You only write the agent logic.

## Standard Pattern — `loader.build_entrypoint()`

The recommended entry point for blueprint-driven agents. One call wires all subsystems declared in the blueprint:

```python
from agent_core.blueprints import BlueprintLoader

loader = BlueprintLoader("blueprints/")
app = loader.build_entrypoint("my-agent")

if __name__ == "__main__":
    app.run()
```

`AgentCoreApp.from_blueprint(loader, agent_id)` is an equivalent alias:

```python
from agent_core.blueprints import BlueprintLoader
from agent_core.runtime import AgentCoreApp

loader = BlueprintLoader("blueprints/")
app = AgentCoreApp.from_blueprint(loader, "my-agent")
```

## `AgentCoreApp`

```python
class AgentCoreApp:
    def __init__(
        self,
        middleware: list | None = None,
    ) -> None: ...

    def entrypoint(self, fn: Callable) -> Callable:
        """Register fn as the /invocations handler.
        Supports four handler shapes:
          async def handler(payload, context) -> Any          # coroutine
          async def handler(payload, context) -> AsyncGen     # streaming (yield)
          def handler(payload, context) -> Any                # sync
          def handler(payload, context) -> Generator          # sync streaming
        OTel telemetry is force-flushed in the finally block of every shape.
        """
        ...

    @classmethod
    def from_blueprint(
        cls,
        loader: BlueprintLoader,
        agent_id: str,
        *,
        local_tools: list | None = None,
        middleware: list | None = None,
    ) -> AgentCoreApp: ...

    def mount_a2a(self, a2a_app: Any, a2a_port: int) -> None:
        """Mount an A2A ASGI app. Called automatically by build_entrypoint()
        when blueprint.multi_agent.role == 'specialist'."""
        ...

    def run(self) -> None:
        """Start the HTTP server on port 8080.
        If an A2A app is mounted, starts it in a daemon thread on a2a_port first."""
        ...
```

## The `@app.entrypoint` Decorator

```python
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp()

@app.entrypoint
def handler(payload: dict, context) -> str:
    session_id = context.session_id
    prompt = payload.get("prompt")
    result = agent(prompt)
    return result.message

if __name__ == "__main__":
    app.run()
```

The decorated function receives:

| Parameter | Type | Description |
|-----------|------|-------------|
| `payload` | `dict` | Deserialized invocation body |
| `context` | `InvocationContext` | Session metadata — see below |

## Context Object

| Attribute | Type | Description |
|-----------|------|-------------|
| `context.session_id` | `str` | AgentCore session token |
| `context.request_headers` | `dict` | HTTP request headers from the invocation |

## Streaming

Yield from an `async def` handler to stream SSE events:

```python
@app.entrypoint
async def handler(payload: dict, context):
    async for event in agent.stream_async(payload.get("prompt")):
        if "data" in event:
            yield event["data"]
```

Sync generator and async generator shapes are both supported. OTel flush runs in the `finally` block of each shape.

> **Note on OTel flush:** AgentCore microVMs are suspended immediately after the response is returned. `AgentCoreApp` force-flushes the OTel logger, meter, and tracer providers after every invocation so telemetry is not dropped. This is handled transparently — no application code is needed.

## Middleware

Pass a Starlette middleware stack to `AgentCoreApp.__init__()`:

```python
from starlette.middleware import Middleware
from agent_core.runtime import AgentCoreApp

app = AgentCoreApp(
    middleware=[
        Middleware(ErrorHandlingMiddleware),
        Middleware(LoggingMiddleware),
    ]
)
```

## Dockerfile Pattern

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["python", "app.py"]
```

`AgentCoreApp.run()` starts the HTTP server on port 8080. When `runtime.observability_enabled: true` is set in the blueprint, the generated Dockerfile wraps the entrypoint with `opentelemetry-instrument` instead.

## A2A Auto-Mount

`build_entrypoint()` automatically mounts an A2A server when `blueprint.multi_agent.role == 'specialist'` and `blueprint.runtime.a2a_port` is set. The A2A port is configured via `runtime.a2a_port` in the blueprint or the `A2A_PORT` env var. No manual `mount_a2a()` call is needed in the standard blueprint-driven pattern.

## `BlueprintLoader` Reference

```python
class BlueprintLoader:
    def __init__(
        self,
        blueprints_dir: str | Path,
        *,
        hook_registry: dict | None = None,
        schema_registry: dict | None = None,
        gateway_client: GatewayClient | None = None,
        prompt_client: PromptRegistryClient | None = None,
    ) -> None: ...

    def load_agent(self, agent_id: str) -> AgentBlueprint: ...
    def load_workflow(self, workflow_id: str) -> WorkflowBlueprint: ...
    def load_strategy(self, strategy_id: str) -> StrategyBlueprint: ...
    def load_agent_from_path(self, path: str | Path) -> AgentBlueprint: ...
    def load_strategy_from_path(self, path: str | Path) -> StrategyBlueprint: ...

    def build_entrypoint(self, agent_id: str, *, local_tools: list | None = None) -> AgentCoreApp:
        """Preferred entry point. Wires all subsystems from the blueprint
        and returns a fully configured AgentCoreApp."""
        ...

    def build_agent_session(self, agent_id: str) -> ContextManager:
        """Context manager that builds and tears down a full agent session.
        Used for on-demand invocations outside the runtime container."""
        ...

    def build_strands_agent(self, agent_id: str, **overrides) -> Agent:
        """Build a bare Strands agent from the blueprint without the runtime wrapper."""
        ...
```

Blueprint file discovery: `blueprints_dir/agents/{agent_id}.yaml` (falls back to `.yml`, then scans for a matching `id:` field).
