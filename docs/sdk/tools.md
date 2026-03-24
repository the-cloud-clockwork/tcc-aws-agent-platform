---
title: Built-in Tools
nav_order: 5
---

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

The agent calls Code Interpreter tools by name (e.g. `code-interpreter::executeCode`). The Gateway routes the call to the managed service. Available tools include `executeCode`, `executeCommand`, `writeFiles`, `listFiles`, and `readFile`.

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

The agent calls Browser tools by name (e.g. `browser::navigate`, `browser::screenshot`). The Gateway routes to the managed Chromium service.

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
- [Concepts: Tools](../concepts/tools) — Architecture and mental model
