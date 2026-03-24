---
title: Tools
parent: Concepts
nav_order: 5
---

# Tools

Built-in tools are AWS-managed services that agents access through the Gateway. The platform provides two built-in tool providers: **Code Interpreter** and **Browser**.

## Why Gateway-Mediated

Built-in tools are not instantiated locally. Instead, the Gateway proxies calls to managed AWS services. This means:

- No local SDK client for Code Interpreter or Browser
- The Gateway manages sandbox lifecycle (creation, teardown, timeouts)
- Tool discovery happens at runtime via the Gateway's tool listing API
- Agents never know the underlying implementation -- they see MCP tools

## Code Interpreter

The Code Interpreter is a sandboxed code execution environment managed by AWS. Agents use it to run Python code, generate charts, analyze data, or perform computations.

### How It Works

`CodeInterpreterProvider` connects to the Gateway and discovers tools whose names start with `code-interpreter::`. These tools are cached after first discovery to avoid repeated Gateway round-trips.

### Blueprint Declaration

```yaml
tools:
  builtin:
    - code_interpreter
```

When this appears in an agent blueprint, the runtime wires up `CodeInterpreterProvider` with the active `GatewayClient`. The provider calls `gateway.list_tools_sync()` and filters for Code Interpreter tools.

## Browser

The Browser tool provides web browsing capabilities through an AWS-managed browser service. Agents use it for web research, page interaction, and data extraction.

### How It Works

`BrowserProvider` follows the same pattern as Code Interpreter. It connects to the Gateway and discovers tools whose names start with `browser::`. Tools are cached after first discovery.

### Blueprint Declaration

```yaml
tools:
  builtin:
    - browser
```

## Provider Pattern

Both providers share an identical structure:

1. Accept a `GatewayClient` at construction
2. Expose a `tools` property that returns discovered tools
3. Provide `start()` and `stop()` methods (both no-ops since the Gateway manages lifecycle)
4. Use a `{target}::` prefix convention for tool name matching

This pattern ensures that adding new built-in tool types requires minimal code -- just a new provider class with the correct target name.

## Relationship to Gateway

Built-in tools are registered as Gateway targets. When you declare `builtin: code_interpreter` in a blueprint, the platform:

1. Registers `code-interpreter` as a Gateway target during infrastructure deployment
2. At runtime, the agent's `CodeInterpreterProvider` queries the Gateway for available tools
3. Tool calls flow through the Gateway, which handles authentication, sandboxing, and lifecycle
