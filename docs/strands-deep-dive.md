

QUANTITATIVE INTELLIGENCE TRADING PLATFORM
Document 4: Strands Agents SDK Deep Dive + QITP-Specific Patterns

Version: 1.0 — March 2026 | Extends Strands Research Core document



# 1. Strands Core Concepts Applied to QITP
## 1.1 The Model-Driven Loop
Strands delegates all routing decisions to the LLM. You define prompt + tools. The model decides what to call, in what order, and when to stop. For QITP, this means:

Gap Detection Agent receives date + threshold → model decides to call get_watchlist_gaps, then enrich each result with get_ohlcv, then create_artifact
Portfolio Recommender receives gap artifact + sentiment artifact → model synthesizes, applies constraints, produces recommendation
The agent does NOT follow a hardcoded pipeline — it reasons about what to do

The loop terminates when the model returns text without requesting tool calls, OR when max_iterations or max_execution_time is hit. Always set both.


## 1.2 Tool Definition in QITP
QITP agents use MCP tools exclusively — no @tool decorated Python functions in agent code. All tool implementation is in MCP servers. This enforces the MCP boundary and makes tool versioning independent of agent versioning.

# CORRECT — tools come from MCP, not agent code
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

with MCPClient(lambda: stdio_client(
StdioServerParameters(command='uvx', args=['qitp-market-data-mcp'])
)) as market_mcp:
agent = Agent(
tools=market_mcp.list_tools_sync(),
system_prompt=prompt_registry.get('gap_detector_v1.2'),
)

# WRONG — never put QITP tool logic in agent code
# @tool
# def get_watchlist_gaps(date: str) -> dict:  # NO


# 2. Multi-Agent Patterns in QITP
## 2.1 Agents-as-Tools (Hierarchical Delegation)
Used when: Portfolio Recommender needs Sentiment scores but doesn't want to manage the full sentiment workflow. It calls the Sentiment Agent as a tool.

# Portfolio Recommender calls Sentiment Agent as a sub-agent tool
from strands import Agent, tool

# Sentiment agent defined separately
sentiment_agent = Agent(
system_prompt=prompt_registry.get('sentiment_analyzer_v1.0'),
tools=[...sentiment_mcp_tools],
)

# Wrap as tool for Portfolio Recommender
@tool
def analyze_sentiment(symbol: str, context: str) -> dict:
"""Run sentiment analysis for a specific symbol.
Args:
symbol: Stock ticker symbol (e.g. NVDA)
context: Market context for the analysis
"""
result = sentiment_agent(f'Analyze sentiment for {symbol}. Context: {context}')
return {'symbol': symbol, 'sentiment': str(result)}

# Portfolio Recommender has analyze_sentiment as one of its tools
portfolio_agent = Agent(
system_prompt=prompt_registry.get('portfolio_recommender_v2.0'),
tools=[analyze_sentiment, *market_data_tools, *artifact_tools],
)

## 2.2 Swarm (Parallel Self-Organizing)
Used when: Sentiment Analysis needs to analyze 20 gap symbols in parallel. Each symbol gets its own agent instance, they self-coordinate, results merge.

# Sentiment Swarm — all 20 symbols analyzed in parallel
from strands.multiagent import swarm

gap_symbols = ['NVDA', 'AAPL', 'MSFT', ...]  # From gap detector output

tasks = [
f'Analyze full sentiment for {symbol}: news, analyst ratings, earnings context'
for symbol in gap_symbols
]

results = await swarm(
agent_factory=lambda: Agent(
system_prompt=prompt_registry.get('sentiment_analyzer_v1.0'),
tools=[...sentiment_tools],
),
tasks=tasks,
execution_timeout=90,
node_timeout=30,
max_handoffs=20,
)
# results is a list of individual agent outputs, one per symbol

## 2.3 Graph (Deterministic Inter-Agent Routing)
Used when: Strategy evaluation requires different agents based on which signals are needed. Technical strategy → Technical Indicator Agent. Sentiment strategy → Sentiment Agent. Graph routes deterministically between them.

# Strategy Evaluation Graph — deterministic routing between specialist agents
from strands.multiagent import GraphBuilder

# Define specialist agents
gap_agent = Agent(system_prompt=prompt_registry.get('gap_detector_v1.2'), ...)
tech_agent = Agent(system_prompt=prompt_registry.get('technical_analyzer_v1.0'), ...)
sentiment_agent = Agent(system_prompt=prompt_registry.get('sentiment_analyzer_v1.0'), ...)
strategy_agent = Agent(system_prompt=prompt_registry.get('strategy_evaluator_v1.0'), ...)

# Build graph
builder = GraphBuilder()
builder.add_node(gap_agent, 'gap')
builder.add_node(tech_agent, 'technical')
builder.add_node(sentiment_agent, 'sentiment')
builder.add_node(strategy_agent, 'strategy')
builder.set_entry_point('gap')

# Deterministic routing based on strategy requirements
builder.add_edge('gap', 'technical',
condition=lambda state: 'technical' in state.get('required_signals', []))
builder.add_edge('gap', 'sentiment',
condition=lambda state: 'sentiment' in state.get('required_signals', []))
builder.add_edge('technical', 'strategy',
condition=lambda state: state.get('technical_analysis_done', False))
builder.add_edge('sentiment', 'strategy',
condition=lambda state: state.get('sentiment_analysis_done', False))

graph = builder.build()
result = graph({
'symbol': 'NVDA',
'strategy_id': 'gap_momentum_up',
'required_signals': ['gap', 'sentiment']  # Drives routing
})

Critical: The condition functions are pure Python — no LLM involved. This is where QITP gets deterministic behavior between agents while still having model-driven behavior within each agent.


# 3. Hooks System in QITP
QITP uses hooks for observability, constraint enforcement, and guardrails. Two custom hook providers are defined for all agents.

# agents/base/hooks.py
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import (
BeforeAgentInvocationEvent,
AfterAgentInvocationEvent,
BeforeToolInvocationEvent,
AfterToolInvocationEvent,
AfterModelInvocationEvent,
)
import json, os, boto3
from datetime import datetime

class QitpObservabilityHook(HookProvider):
"""Logs every agent invocation and tool call to CloudWatch + Langfuse."""

def register_hooks(self, registry: HookRegistry):
registry.add_callback(BeforeAgentInvocationEvent, self.on_agent_start)
registry.add_callback(AfterAgentInvocationEvent, self.on_agent_end)
registry.add_callback(AfterToolInvocationEvent, self.on_tool_end)

def on_agent_start(self, event: BeforeAgentInvocationEvent):
self.start_time = datetime.utcnow()
print(json.dumps({
'event': 'agent_start',
'agent_id': os.environ.get('AGENT_ID'),
'execution_mode': os.environ.get('EXECUTION_MODE'),
'timestamp': self.start_time.isoformat(),
}))

def on_tool_end(self, event: AfterToolInvocationEvent):
if event.exception:
# Log tool failures but don't auto-retry
# (MCP retry handled at tool layer, not hook layer)
print(json.dumps({
'event': 'tool_error',
'tool_name': event.tool_use.name,
'error': str(event.exception),
}))

class PortfolioConstraintHook(HookProvider):
"""Enforces portfolio constraints on Portfolio Recommender output."""
MAX_RECOMMENDATIONS = 5

def register_hooks(self, registry: HookRegistry):
registry.add_callback(AfterAgentInvocationEvent, self.enforce_constraints)

def enforce_constraints(self, event: AfterAgentInvocationEvent):
# Parse output and truncate if agent recommended too many positions
# This is a safety net — Portfolio Recommender prompt also enforces this
pass


# 4. Session Management & AgentCore Memory
## 4.1 Session ID Convention
QITP maps Step Functions execution IDs to AgentCore session IDs. This enables cross-step context persistence and end-to-end traceability.

# In Step Functions state machine definition (CDK)
payload=sfn.TaskInput.from_object({
'session_id': sfn.JsonPath.string_at('$$.Execution.Id'),  # SFN exec ID = session ID
'actor_id': 'qitp-weekly-pipeline',
'input': sfn.JsonPath.string_at('$.gaps'),
})

# In agent Lambda handler
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

def handler(event, context):
session_id = event.get('session_id')  # = Step Functions execution ID
actor_id = event.get('actor_id', 'qitp-weekly-pipeline')

config = AgentCoreMemoryConfig(
memory_id=os.environ['AGENTCORE_MEMORY_ID'],
session_id=session_id,
actor_id=actor_id,
batch_size=10,
)

with AgentCoreMemorySessionManager(config, region_name='eu-west-1') as session_mgr:
agent = Agent(
model=model,
system_prompt=prompt_registry.get('portfolio_recommender_v2.0'),
tools=tools,
session_manager=session_mgr,
)
result = agent(event.get('prompt'))
# Session auto-flushed on context exit


# 5. Deploying Strands Agents on AgentCore
## 5.1 Minimal AgentCore App

# agents/gap_detector/agentcore_app.py
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agents.base.loader import BlueprintLoader
import os, json

app = BedrockAgentCoreApp()
loader = BlueprintLoader()

@app.entrypoint
def invoke(payload):
# Build agent from blueprint — fresh per invocation (AgentCore handles isolation)
from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient

with MCPClient(lambda: stdio_client(
StdioServerParameters(command='uvx', args=['qitp-market-data-mcp'],
env={'EXECUTION_MODE': os.environ.get('EXECUTION_MODE', 'backtest')})
)) as market_mcp, MCPClient(lambda: stdio_client(
StdioServerParameters(command='uvx', args=['qitp-artifacts-mcp'])
)) as artifacts_mcp:

agent = loader.build_strands_agent('gap_detector', {
'market-data-mcp': market_mcp,
'artifacts-mcp': artifacts_mcp,
})

result = agent(payload.get('prompt', 'Scan watchlist for gaps today'))
return {'output': str(result), 'success': True}

if __name__ == '__main__':
app.run()

## 5.2 AgentCore Deployment with Starter Toolkit

# Install
pip install bedrock-agentcore-starter-toolkit

# Configure
agentcore configure \
--entrypoint agents/gap_detector/agentcore_app.py \
--requirements-file agents/gap_detector/requirements.txt \
--region eu-west-1

# Launch
agentcore launch --name qitp-gap-detector --env EXECUTION_MODE=backtest

# Invoke
agentcore invoke --agent-id <id> \
--payload '{"prompt": "Scan for gaps on 2024-11-04"}'


# 6. Strands Limitations & QITP Workarounds



# 7. Why Strands for QITP
Decision summary for the ADR record. This answers why Strands was chosen over LangGraph, CrewAI, and AutoGen for the agent reasoning layer.


The key insight: Step Functions provides determinism. Strands provides reasoning. The two layers don't compete — they complement. Strands was not chosen INSTEAD of deterministic orchestration. It was chosen as the inner reasoning layer, with Step Functions as the outer control layer.

| Control | Purpose | QITP Default |
| --- | --- | --- |
| max_iterations | Hard stop on number of model+tool cycles | 5 (gap), 8 (recommender) |
| max_execution_time | Hard timeout in seconds regardless of iterations | 120s (gap), 300s (recommender) |
| temperature | Model creativity/determinism tradeoff | 0.2-0.3 for financial analysis |
| extended_thinking | Claude "thinks" before responding — better for complex synthesis | Only Portfolio Recommender |


| Limitation | GitHub Issue | QITP Workaround |
| --- | --- | --- |
| No native conditional branching within single agent loop | By design — model decides | Use Strands Graph for inter-agent routing. Use Step Functions for pipeline-level routing. |
| No branch cancellation in Graph patterns | In-flight branches run to completion | Design branches as idempotent units. Use Step Functions Map state for cancellable parallel work. |
| No checkpoint/resume for long-running agents | #1369 | Step Functions provides outer durability. If agent task fails, SFN retries the entire task. |
| No configurable MCP retry at transport level | #675 | Wrap MCP tool calls with tenacity retry decorator in MCP server implementation. |
| No multi-agent hooks for Graph/Swarm | #791 | Use QitpObservabilityHook on each individual agent. Correlate via execution_id in logs. |
| Context window growth is linear | By design | Set max_iterations to bound context size. Implement summarization for long conversations. |
| Agent quality degrades with weaker models | By design | Use Claude Sonnet 4 minimum for financial analysis. Never use Haiku for recommendation agents. |
| No structured output enforcement | #348 | Use output_schema field in blueprint + validate in Lambda handler. Retry once on schema failure. |


| Criterion | Strands | LangGraph | Why Strands Wins for QITP |
| --- | --- | --- | --- |
| MCP native support | First-class, out of box | Partial, requires config | ibkr-mcp, market-data-mcp plug in directly with zero integration code |
| AWS/Bedrock integration | Native, same org | Community, indirect | AgentCore, Bedrock models, IAM all work natively |
| Boilerplate for simple agents | Minimal — 5 lines | Significant graph setup | Gap Detector is a simple agent. Strands is correct abstraction. |
| Multi-agent patterns | Swarm, Graph, Workflow built-in | Graph only (state machine) | Sentiment Swarm pattern needs parallel execution without graph wiring overhead |
| Production runtime | AgentCore (managed) | DIY deployment | AgentCore handles microVM isolation, session, memory — not DIY |
| Determinism when needed | Graph edges use Python conditions | Full graph is deterministic | Step Functions handles determinism. Strands doesn't need to. |
| A2A protocol | Built-in v1.0 | Not native | Future multi-platform agent interop |
