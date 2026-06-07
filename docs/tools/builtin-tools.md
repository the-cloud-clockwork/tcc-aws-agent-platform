---
title: Built-in Tools
nav_order: 3
parent: "Tools, MCP & Gateway"
---

# Built-in Tools

Built-in tools are AWS-managed services that agents access through the Gateway. The platform provides two built-in tool providers: **Code Interpreter** and **Browser**. Neither is instantiated locally — the Gateway proxies all calls to the managed AWS services, and the platform discovers available tools at runtime via the Gateway's MCP tool listing.

## Why Gateway-Mediated

Built-in tools are not local SDK clients. The Gateway manages sandbox lifecycle (creation, teardown, timeouts) for both services. This means:

- No local session management or cleanup in agent code
- Tool discovery happens at runtime via `gateway.list_tools_sync()` filtered by target namespace
- Agents call built-in tools by name just like any other MCP tool — they are indistinguishable from Lambda or domain MCP tools
- `start()` and `stop()` on both providers are no-ops; the Gateway is authoritative for lifecycle

## Code Interpreter

The Code Interpreter is a sandboxed execution environment managed by AWS. Agents use it to run code, generate charts, analyze data, and perform computations in an isolated environment.

### How It Works

`CodeInterpreterProvider` connects to the Gateway via a `GatewayClient`, calls `list_tools_sync()`, and filters for tools whose names start with `code-interpreter::`. Tools are cached after first discovery to avoid repeated Gateway round-trips.

The specific tool names exposed under the `code-interpreter::` prefix are defined by the AWS managed service and discovered dynamically at runtime — they are not hard-coded in the platform. Refer to the AWS AgentCore documentation for the current tool name list.

### Blueprint Declaration

```yaml
tools:
  - builtin: code_interpreter
```

When this appears in an agent blueprint, `BlueprintLoader` wires up `CodeInterpreterProvider` with the active `GatewayClient`. No additional configuration is needed in agent code.

### Manual Wiring

```python
from agent_core.tools import CodeInterpreterProvider

provider = CodeInterpreterProvider(gateway_client=gateway_client)

# Discovered tools are cached after the first call
ci_tools = provider.tools

agent = Agent(model=model, tools=local_tools + ci_tools)
```

## Browser

The Browser tool provides web browsing capabilities through an AWS-managed browser service. Agents use it for web research, page interaction, and data extraction.

### How It Works

`BrowserProvider` follows the same pattern as Code Interpreter. It connects to the Gateway and discovers tools whose names start with `browser::`. Tools are cached after first discovery.

As with Code Interpreter, the specific tool names exposed under `browser::` are defined by the AWS managed service and discovered dynamically.

### Blueprint Declaration

```yaml
tools:
  - builtin: browser
```

### Manual Wiring

```python
from agent_core.tools import BrowserProvider

provider = BrowserProvider(gateway_client=gateway_client)
browser_tools = provider.tools

agent = Agent(model=model, tools=local_tools + browser_tools)
```

## Declaring Multiple Tool Types Together

Built-in tools, MCP server tools, and custom local tools can be combined in a single blueprint:

```yaml
tools:
  - builtin: code_interpreter
  - builtin: browser
  - mcp: catalog-mcp
    tools: [search_catalog, get_item]
```

`BlueprintLoader` wires all declared tools and presents them as a flat list to the Strands `Agent`. The agent selects the right tool for each step without any knowledge of the source type.

## Provider Pattern

Both providers share an identical structure:

1. Accept a `GatewayClient` at construction via the `gateway_client=` keyword argument
2. Expose a `tools` property that returns the discovered tool list (cached after first call)
3. Provide `start()` and `stop()` methods — both are no-ops since the Gateway manages lifecycle
4. Use a `{target}::` prefix convention for tool name matching

This pattern means adding new built-in tool types requires minimal code — a new provider class with the correct `TARGET` constant.

## Relationship to Gateway Targets

Built-in tools are registered as Gateway targets during infrastructure deployment. The Terraform modules handle this automatically when `builtin: code_interpreter` or `builtin: browser` is declared in a blueprint.

At runtime:

1. `BlueprintLoader` creates a `GatewayClient` from the blueprint's `gateway:` block
2. `BuiltinToolWiring` instantiates `CodeInterpreterProvider` and/or `BrowserProvider` with the client
3. Each provider calls `gateway.list_tools_sync()` once and caches the filtered result
4. The Strands agent receives the discovered tools alongside its other tools

## Network Mode

The `BuiltinToolConfig` schema supports a `network_mode` field with values `PUBLIC` or `PRIVATE`. This controls whether the Code Interpreter or Browser sandbox has outbound network access. The default is `PUBLIC`. Set `network_mode: PRIVATE` in the blueprint when the tool should run air-gapped (no outbound internet from the sandbox).

```yaml
tools:
  - builtin: code_interpreter
    network_mode: PRIVATE
```

## See Also

- [Gateway](gateway) — the protocol bridge that mediates all built-in tool calls
- [Built-in Tools SDK Reference](../sdk/tools) — `CodeInterpreterProvider`, `BrowserProvider`, `BuiltinToolWiring`
- [Agent Blueprint](../blueprints/agent-blueprint) — full `tools:` block reference
