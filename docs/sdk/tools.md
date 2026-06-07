---
title: Built-in Tools
nav_order: 5
parent: SDK Reference
---

# Built-in Tools

The Tools subsystem provides managed providers for Amazon Bedrock AgentCore's two built-in tool types: Code Interpreter and Browser. Both integrate as **Gateway targets** — the Gateway proxies calls to AWS-managed services. There is no local SDK client or lifecycle management in your agent code.

> **Architecture guide:** [Tools, MCP & Gateway](../tools.md)

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `CodeInterpreterProvider` | `agent_core.tools.code_interpreter` | Discovers Code Interpreter tools from the Gateway by `code-interpreter::` prefix |
| `BrowserProvider` | `agent_core.tools.browser` | Discovers Browser tools from the Gateway by `browser::` prefix |
| `BuiltinToolWiring` | `agent_core.tools.wiring` | Reads blueprint `tools:` block and wires both providers automatically |

## How It Works

Both providers follow the same pattern: receive a `GatewayClient`, call `list_tools_sync()`, and filter by namespace prefix. The agent sees these tools alongside domain tools:

```
Agent --> Gateway --> Code Interpreter (AWS-managed sandbox)
                 --> Browser (AWS-managed Chromium)
                 --> Domain MCP servers
```

`start()` and `stop()` on both providers are no-ops — lifecycle is managed entirely by AgentCore Gateway.

## Code Interpreter

Runs Python and shell commands in an isolated, ephemeral sandbox managed by AgentCore.

```python
from agent_core.tools import CodeInterpreterProvider

provider = CodeInterpreterProvider(gateway_client=gateway)
ci_tools = provider.tools   # Cached after first Gateway discovery

agent = Agent(model=model, tools=local_tools + ci_tools)
```

Tool names are discovered dynamically from the Gateway by filtering for the `code-interpreter::` prefix. Do not hardcode tool names — the available set is managed by AWS and may change.

Blueprint declaration:

```yaml
tools:
  - builtin: code_interpreter
    network_mode: PUBLIC    # PUBLIC (default) | PRIVATE
```

## Browser

Provides hosted Chromium access via CDP (Chrome DevTools Protocol) and Nova Act for natural-language navigation.

```python
from agent_core.tools import BrowserProvider

provider = BrowserProvider(gateway_client=gateway)
browser_tools = provider.tools   # Cached after first Gateway discovery

agent = Agent(model=model, tools=local_tools + browser_tools)
```

Tool names are discovered dynamically by filtering for the `browser::` prefix.

Blueprint declaration:

```yaml
tools:
  - builtin: browser
```

## `BuiltinToolWiring`

Automates registration of all declared built-in providers:

```python
from agent_core.tools import BuiltinToolWiring

wiring = BuiltinToolWiring(gateway_client=gateway, blueprint=blueprint)
builtin_tools = wiring.discover_tools()

agent = Agent(model=model, tools=local_tools + gateway_tools + builtin_tools)
```

When using `BlueprintLoader`, builtin tool wiring is handled automatically — the loader reads the `tools:` block and discovers tools without any code.

## Blueprint Declaration

All three tool declaration types in the blueprint `tools:` list:

```yaml
tools:
  # MCP server tools (via Gateway target)
  - mcp: my-domain-mcp
    tools: [get_record, search_records]   # Empty list = all tools

  # Built-in Gateway-managed tools
  - builtin: code_interpreter
  - builtin: browser

  # Remote agent as a tool (A2A)
  - a2a: summarization-agent             # Blueprint ID or URL
```

## See Also

- [Gateway SDK reference](gateway.md) — How tools are routed through Gateway
- [MCP Base Classes](mcp.md) — Building domain MCP servers
- [Tools, MCP & Gateway guide](../tools.md) — Architecture and mental model

# Built-in Tools

The Tools subsystem provides managed providers for Amazon Bedrock AgentCore's two built-in tool types: Code Interpreter and Browser. Both integrate as **Gateway targets** — the Gateway proxies calls to AWS-managed services, so there is no local SDK client or session management.

## Key Classes

| Class | Purpose |
|-------|---------|
| `CodeInterpreterProvider` | Discovers Code Interpreter tools from the Gateway and caches them |
| `BrowserProvider` | Discovers Browser tools from the Gateway and caches them |
| `BuiltinToolWiring` | Registers both providers as Gateway targets and wires them to the Strands agent |

## How It Works

Both providers follow the same pattern: they receive a `GatewayClient`, call `list_tools_sync()` to discover available tools, and filter for their target namespace. The agent sees these tools alongside domain tools — it doesn't know or care that they're AWS-managed services.

```
Agent --> Gateway --> Code Interpreter (AWS-managed sandbox)
                 --> Browser (AWS-managed Chromium + Nova Act)
                 --> Domain MCP servers
```

## Code Interpreter

The Code Interpreter runs Python and shell commands in an isolated, ephemeral sandbox managed by AgentCore. The Gateway proxies all calls — no local session management needed.

### Blueprint Declaration

```yaml
tools:
  - builtin: code_interpreter
  - mcp: my-domain-mcp
    tools: [custom_tool]
```

### Provider Pattern

```python
from agent_core.tools import CodeInterpreterProvider

# The provider discovers tools from Gateway — no session() or execute()
provider = CodeInterpreterProvider(gateway_client=gateway)
ci_tools = provider.tools  # Cached after first discovery

# Tools are added to the agent alongside other Gateway tools
agent = Agent(model=model, tools=local_tools + ci_tools)
```

Tool names are discovered dynamically from the Gateway at runtime by filtering for the `code-interpreter::` prefix — they are not defined in the platform code. The actual names exposed under this prefix are determined by the AWS AgentCore managed service. Refer to AWS AgentCore documentation for the current tool name list.

## Browser

The Browser provides hosted Chromium access via CDP (Chrome DevTools Protocol) and Nova Act for natural-language navigation. Like Code Interpreter, it's Gateway-mediated.

### Blueprint Declaration

```yaml
tools:
  - builtin: browser
  - builtin: code_interpreter
```

### Provider Pattern

```python
from agent_core.tools import BrowserProvider

provider = BrowserProvider(gateway_client=gateway)
browser_tools = provider.tools  # Cached after first discovery

agent = Agent(model=model, tools=local_tools + browser_tools)
```

Tool names are discovered dynamically from the Gateway by filtering for the `browser::` prefix. The actual names are determined by the AWS AgentCore managed Browser service — refer to AWS AgentCore documentation for the current tool list.

## BuiltinToolWiring

`BuiltinToolWiring` automates the registration of both providers when the blueprint declares them:

```python
from agent_core.tools import BuiltinToolWiring

wiring = BuiltinToolWiring(gateway_client=gateway, blueprint=blueprint)
builtin_tools = wiring.discover_tools()

# Returns combined tools from all declared builtins
agent = Agent(model=model, tools=local_tools + gateway_tools + builtin_tools)
```

When using `BlueprintLoader`, this wiring is handled automatically — the loader reads the `tools:` block and wires builtins without any code.

## See Also

- [Gateway](./gateway) — How tools are routed through Gateway
- [Tools, MCP & Gateway](../tools) — Architecture and mental model
