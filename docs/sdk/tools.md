---
title: Built-in Tools
nav_order: 5
---

# Built-in Tools

The Tools subsystem provides managed providers for Amazon Bedrock AgentCore's two built-in tool types: Code Interpreter and Browser. Both integrate as Gateway targets, so they appear in the agent's tool registry alongside custom tools and MCP servers.

## Key Classes

| Class | Purpose |
|-------|---------|
| `CodeInterpreterProvider` | Manages Code Interpreter sessions — file upload, execution, result retrieval |
| `BrowserProvider` | Manages browser sessions — CDP control and Nova Act natural-language navigation |
| `BuiltinToolWiring` | Registers both providers as Gateway targets and wires them to the Strands agent |

## Code Interpreter

The Code Interpreter runs Python in an isolated, ephemeral compute environment managed by AgentCore. Each session is sandboxed — network access, execution time, and memory are all bounded.

### Starting a Session

```python
from agent_core.tools import CodeInterpreterProvider

provider = CodeInterpreterProvider.from_blueprint("agent.yaml")

# Start a session (returns a session context manager)
async with provider.session() as session:
    result = await session.execute("import pandas as pd; pd.DataFrame({'a': [1,2,3]}).describe()")
    print(result.stdout)
    print(result.artifacts)  # Any generated files
```

### File Upload

Upload files into the session before execution:

```python
async with provider.session() as session:
    # Upload a CSV for analysis
    await session.upload_file("data.csv", content=csv_bytes, mime_type="text/csv")

    result = await session.execute("""
        import pandas as pd
        df = pd.read_csv('data.csv')
        print(df.describe())
    """)
```

### As a Strands Tool

When wired through `BuiltinToolWiring`, Code Interpreter is exposed to the Strands agent as a named tool. The agent can call it directly without session management code:

```python
# The agent calls this automatically when it needs to run code
# Tool name: "code_interpreter"
# Parameters: { "code": "...", "files": [...] }
```

## Browser

The Browser provider creates managed browser sessions using Amazon Bedrock AgentCore's browser service. Two control modes are available:

| Mode | Interface | Use Case |
|------|-----------|---------|
| CDP | Raw Chrome DevTools Protocol | Fine-grained control, scraping, form interaction |
| Nova Act | Natural language commands | High-level browser automation |

### CDP Mode

```python
from agent_core.tools import BrowserProvider

provider = BrowserProvider.from_blueprint("agent.yaml")

async with provider.session(mode="cdp") as browser:
    await browser.navigate("https://example.com")
    content = await browser.get_text("body")
    screenshot = await browser.screenshot()
```

### Nova Act Mode

```python
async with provider.session(mode="nova_act") as browser:
    # Natural language instructions
    result = await browser.act("Go to the login page and sign in with the test credentials")
    result = await browser.act("Find the latest report and download it as PDF")
```

### Blueprint Configuration

```yaml
tools:
  code_interpreter:
    enabled: true
    timeout_seconds: 120
    max_sessions: 5

  browser:
    enabled: true
    mode: nova_act             # cdp | nova_act
    timeout_seconds: 60
```

## BuiltinToolWiring

`BuiltinToolWiring` handles the plumbing between the provider instances and the Strands agent. Call it during app initialization:

```python
from agent_core.tools import BuiltinToolWiring

wiring = BuiltinToolWiring.from_blueprint("agent.yaml")

# Returns list of Strands-compatible tool objects
tools = await wiring.get_tools()

agent = Agent(model=model, tools=tools)
```

Under the hood, `BuiltinToolWiring`:

1. Reads the blueprint to determine which tools are enabled
2. Registers each enabled tool as a Gateway target (so it appears in discovery)
3. Creates a Strands tool wrapper that manages the session lifecycle per call
4. Returns the wrapper list ready for `Agent(tools=[...])`

## Gateway Registration

Both built-in tools are registered as Gateway targets with type `BUILTIN`. This means:

- They appear in `ToolDiscovery` results alongside custom tools
- They respect the same policy engine rules as other tools
- Invocation metadata (latency, token count for code, navigation steps for browser) is recorded in observability

See [Gateway](gateway.md) for details on target registration and tool discovery.
