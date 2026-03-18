

QUANTITATIVE INTELLIGENCE TRADING PLATFORM
Document 3: Implementation Guide for Coding Agents

Version: 1.0 — March 2026
Audience: Claude Code CLI / AI coding agents implementing QITP



# 0. How to Use This Document
This document is written specifically for AI coding agents implementing the QITP platform. It provides implementation-ready patterns, exact Python code, and explicit constraints to follow.

⚠ Never hardcode prompts in agent code. Always load from Prompt Registry.
⚠ Never bypass the 2FA gate for live mode. This is a hard architectural constraint.
⚠ Never allow agents to directly access IBKR in backtest mode. Route through execution_mode env var.
ℹ Start with POC scope (ROOT-63) — backtest mode only. No broker integration until POC is validated.
ℹ Implement blueprint validation first (ROOT-47) — all other components depend on it.
ℹ Blueprint schemas, output schemas, and repo structure are defined in Document 2.

Build order for coding agents:
ROOT-66: GitHub repo structure + CI/CD (foundation)
ROOT-47: Blueprint Engine (all other components depend on this)
ROOT-49: Execution Mode system (backtest/paper/live switching)
ROOT-48: Prompt Registry (needed before any agent works)
ROOT-52: market-data-mcp (needed for POC)
ROOT-53: artifacts-mcp (needed for POC outputs)
ROOT-54: Gap Detection Agent (first agent in POC)
ROOT-55: Sentiment Analysis Agent
ROOT-56: Strategy Library
ROOT-57: Simulation Engine
ROOT-58: Weekly Analysis Workflow (Step Functions)
ROOT-59: Portfolio Recommender Agent
ROOT-63: POC validation

Then in Phase 2 (post-POC):
ROOT-50: ibkr-mcp + ROOT-51: 2FA gate
ROOT-60: Risk Engine
ROOT-61: CDK Infrastructure
ROOT-62: Observability

# 1. Blueprint Engine Implementation
## 1.1 Blueprint Loader
The blueprint loader reads YAML, validates with Pydantic, and returns typed Python objects. This is the entry point for all agents.

# agents/base/loader.py
import yaml
import os
from pathlib import Path
from pydantic import BaseModel, validator
from typing import List, Optional, Literal
from strands import Agent
from strands.models import BedrockModel
from .prompt_registry import PromptRegistry

class ModelConfig(BaseModel):
provider: Literal['bedrock', 'anthropic', 'vertex', 'litellm'] = 'bedrock'
model_id: str
temperature: float = 0.3
max_tokens: int = 4096
cache_prompt: str = 'default'
cache_tools: str = 'default'
extended_thinking: bool = False

class RuntimeConfig(BaseModel):
type: Literal['agentcore', 'lambda', 'fargate'] = 'lambda'
max_iterations: int = 10
max_execution_time: int = 300
memory_mb: int = 1024

class ToolConfig(BaseModel):
mcp: str
tools: List[str]

class ExecutionModes(BaseModel):
backtest: bool = True
paper: bool = True
live: bool = True

class AgentBlueprint(BaseModel):
id: str
version: str
name: str
description: str
model: ModelConfig
prompt_ref: str
tools: List[ToolConfig]
runtime: RuntimeConfig
hooks: List[str] = []
execution_modes: ExecutionModes = ExecutionModes()
output_schema: Optional[str] = None

class BlueprintLoader:
def __init__(self, blueprints_dir: str = 'blueprints'):
self.blueprints_dir = Path(blueprints_dir)
self.prompt_registry = PromptRegistry()

def load_agent(self, agent_id: str) -> AgentBlueprint:
path = self.blueprints_dir / 'agents' / f'{agent_id}.yaml'
with open(path) as f:
data = yaml.safe_load(f)
return AgentBlueprint(**data)

def build_strands_agent(self, agent_id: str, mcp_clients: dict) -> Agent:
blueprint = self.load_agent(agent_id)
execution_mode = os.environ.get('EXECUTION_MODE', 'backtest')

# Validate mode is enabled for this agent
mode_config = getattr(blueprint.execution_modes, execution_mode)
if not mode_config:
raise ValueError(f'Agent {agent_id} disabled for mode {execution_mode}')

# Load prompt from registry (never hardcoded)
system_prompt = self.prompt_registry.get(blueprint.prompt_ref)

# Build model (provider-agnostic)
model = self._build_model(blueprint.model)

# Collect tools from specified MCPs
tools = []
for tool_config in blueprint.tools:
mcp_client = mcp_clients.get(tool_config.mcp)
if not mcp_client:
raise ValueError(f'MCP {tool_config.mcp} not available')
mcp_tools = mcp_client.list_tools_sync()
# Filter to only specified tools
filtered = [t for t in mcp_tools if t.name in tool_config.tools]
tools.extend(filtered)

return Agent(
model=model,
system_prompt=system_prompt,
tools=tools,
max_iterations=blueprint.runtime.max_iterations,
max_execution_time=blueprint.runtime.max_execution_time,
)

def _build_model(self, config: ModelConfig):
if config.provider == 'bedrock':
return BedrockModel(
model_id=config.model_id,
temperature=config.temperature,
max_tokens=config.max_tokens,
cache_prompt=config.cache_prompt,
cache_tools=config.cache_tools,
)
elif config.provider == 'anthropic':
from strands.models import AnthropicModel
return AnthropicModel(model_id=config.model_id)
elif config.provider == 'litellm':
from strands.models import LiteLLMModel
return LiteLLMModel(model_id=config.model_id)
raise ValueError(f'Unknown provider: {config.provider}')

## 1.2 Lambda Handler Pattern
Every agent Lambda handler follows this exact pattern. Initialize agent OUTSIDE the handler for warm-start reuse.

# agents/gap_detector/handler.py
import json
import os
from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient
from agents.base.loader import BlueprintLoader

# Initialize OUTSIDE handler for warm-start reuse
LOADER = BlueprintLoader()
EXECUTION_MODE = os.environ.get('EXECUTION_MODE', 'backtest')

def get_mcp_clients():
"""Build MCP clients — scoped to invocation to prevent state leakage."""
return {
'market-data-mcp': MCPClient(lambda: stdio_client(
StdioServerParameters(
command='uvx',
args=['qitp-market-data-mcp'],
env={'EXECUTION_MODE': EXECUTION_MODE}
)
)),
'artifacts-mcp': MCPClient(lambda: stdio_client(
StdioServerParameters(command='uvx', args=['qitp-artifacts-mcp'])
)),
}

def handler(event, context):
scan_date = event.get('date', 'today')
threshold_pct = event.get('threshold_pct', 2.0)

mcp_clients = get_mcp_clients()

# CRITICAL: Always use context manager for MCP connections
with mcp_clients['market-data-mcp'] as market_mcp, \
mcp_clients['artifacts-mcp'] as artifacts_mcp:

clients = {
'market-data-mcp': market_mcp,
'artifacts-mcp': artifacts_mcp,
}
agent = LOADER.build_strands_agent('gap_detector', clients)
result = agent(
f'Scan watchlist for gap% >= {threshold_pct}% on {scan_date}. '
f'Return ranked gaps as structured JSON. Store as artifact.'
)

# Extract structured output — enforce 256KB limit
output_text = str(result)
response = json.loads(output_text) if output_text.startswith('{') else {
'raw_output': output_text[:200000],
'execution_mode': EXECUTION_MODE,
'success': True,
}
return response

⚠ Always use context managers (with mcp_client:) for MCP connections in Lambda. Never reuse connections across invocations — this leaks state between users.



# 2. MCP Server Implementation Pattern
## 2.1 Standard MCP Server Structure
All MCPs follow this structure. The execution mode routing is in the MCP — agents are mode-agnostic.

# mcps/market-data-mcp/server.py
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json

EXECUTION_MODE = os.environ.get('EXECUTION_MODE', 'backtest')

app = Server('market-data-mcp')

@app.list_tools()
async def list_tools():
return [
Tool(
name='get_watchlist_gaps',
description='Get all watchlist symbol gaps for a given date, ranked by gap%',
inputSchema={
'type': 'object',
'properties': {
'date': {'type': 'string', 'description': 'Date YYYY-MM-DD or today'},
'threshold_pct': {'type': 'number', 'description': 'Min gap% to include', 'default': 2.0}
},
'required': ['date']
}
),
# ... other tools
]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
if name == 'get_watchlist_gaps':
return await get_watchlist_gaps(**arguments)
raise ValueError(f'Unknown tool: {name}')

async def get_watchlist_gaps(date: str, threshold_pct: float = 2.0):
# EXECUTION_MODE routing — agents never know which mode
if EXECUTION_MODE == 'backtest':
data = await _fetch_historical_gaps(date, threshold_pct)
else:
data = await _fetch_live_gaps(date, threshold_pct)

return [TextContent(type='text', text=json.dumps(data))]

async def _fetch_historical_gaps(date: str, threshold_pct: float):
# Read from S3 parquet cache — zero live API calls in backtest
import boto3, pandas as pd, io
s3 = boto3.client('s3')
# ... load parquet from qitp-historical-data bucket
pass

async def _fetch_live_gaps(date: str, threshold_pct: float):
# Polygon.io or IBKR live feed
pass

if __name__ == '__main__':
import asyncio
asyncio.run(stdio_server(app))

## 2.2 MCP Dockerfile Pattern

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
CMD ["python", "server.py"]


# 3. Step Functions CDK Patterns
## 3.1 Reusable Agent Task Construct
Use this construct for every state that invokes a Strands agent. It wraps the Lambda invocation with standard retry/catch, claim-check pattern, and X-Ray tracing.

# infra/constructs/strands_agent.py
from aws_cdk import Duration, aws_stepfunctions as sfn, aws_stepfunctions_tasks as tasks
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

class StrandsAgentTask(Construct):
def __init__(self, scope: Construct, id: str, *,
agent_fn: lambda_.Function,
agent_id: str,
input_path: str = '$',
result_path: str,
**kwargs):
super().__init__(scope, id, **kwargs)

self.task = tasks.LambdaInvoke(
self, f'Invoke{agent_id.title().replace("_", "")}',
lambda_function=agent_fn,
payload=sfn.TaskInput.from_object({
'agent_id': agent_id,
'input': sfn.JsonPath.string_at(input_path),
'execution_id': sfn.JsonPath.string_at('$$.Execution.Id'),
'execution_mode': sfn.JsonPath.string_at('$$.Execution.Input.execution_mode'),
}),
result_selector={
'artifact_id.$': '$.Payload.artifact_id',
'success.$': '$.Payload.success',
's3_key.$': '$.Payload.s3_key',
},
result_path=result_path,
)

# Standard retry for all agent tasks
self.task.add_retry(
errors=['Lambda.ServiceException', 'Lambda.TooManyRequestsException',
'Bedrock.ThrottlingException'],
interval=Duration.seconds(3),
max_attempts=4,
backoff_rate=2.0,
jitter_strategy=sfn.JitterType.FULL,
)

## 3.2 2FA Gate Pattern (waitForTaskToken)

# infra/constructs/two_fa_gate.py
from aws_cdk import Duration, aws_stepfunctions as sfn, aws_stepfunctions_tasks as tasks
from aws_cdk import aws_sqs as sqs
from constructs import Construct

class TwoFaGate(Construct):
def __init__(self, scope: Construct, id: str, *,
approval_queue: sqs.Queue, **kwargs):
super().__init__(scope, id, **kwargs)

self.task = tasks.SqsSendMessage(
self, 'SendApprovalRequest',
queue=approval_queue,
message_body=sfn.TaskInput.from_object({
'task_token': sfn.JsonPath.task_token,
'recommendations': sfn.JsonPath.string_at('$.recommendations'),
'execution_id': sfn.JsonPath.string_at('$$.Execution.Id'),
}),
integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
heartbeat=Duration.minutes(5),  # Auto-reject after 5 minutes
)

self.task.add_catch(
handler=sfn.Fail(self, 'ApprovalTimeout',
cause='2FA approval timed out or rejected'),
errors=['States.HeartbeatTimeout', 'OrderRejectedByUser'],
result_path='$.approval_error',
)

⚠ The 2FA gate MUST be in the Step Functions workflow, not inside agent code. Agents cannot gate themselves.


# 4. Risk Engine Implementation

# risk/handler.py
import boto3
import json
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
risk_table = dynamodb.Table('qitp_risk_state')
config_table = dynamodb.Table('qitp_risk_config')

def handler(event, context):
"""Risk Engine Lambda. Returns PASS or FAIL with reason."""
account_id = event.get('account_id', 'default')
recommendation = event.get('recommendation', {})

# Load current risk state
state = risk_table.get_item(Key={'account_id': account_id}).get('Item', {})
config = config_table.get_item(Key={'config_id': 'default'}).get('Item', {})

# Run all rules
checks = [
check_max_positions(state, config, recommendation),
check_position_size(state, config, recommendation),
check_sector_concentration(state, config, recommendation),
check_daily_loss_circuit_breaker(state, config),
check_drawdown_circuit_breaker(state, config),
check_trailing_stop_present(recommendation),
check_cnmv_leverage(recommendation, config),
]

failed = [c for c in checks if c['result'] == 'FAIL']

if failed:
return {
'result': 'FAIL',
'failures': failed,
'primary_reason': failed[0]['reason'],
}

return {'result': 'PASS', 'failures': []}

def check_max_positions(state, config, rec):
max_pos = int(config.get('max_open_positions', 5))
current = int(state.get('open_position_count', 0))
if current >= max_pos:
return {'result': 'FAIL', 'rule': 'max_positions',
'reason': f'Already at max positions ({current}/{max_pos})'}
return {'result': 'PASS', 'rule': 'max_positions'}

def check_daily_loss_circuit_breaker(state, config):
max_loss_pct = float(config.get('max_daily_loss_pct', -3.0))
daily_pnl_pct = float(state.get('daily_pnl_pct', 0.0))
if daily_pnl_pct <= max_loss_pct:
return {'result': 'FAIL', 'rule': 'daily_loss_circuit_breaker',
'reason': f'Daily loss {daily_pnl_pct:.2f}% exceeds limit {max_loss_pct:.2f}%',
'circuit_breaker': True}
return {'result': 'PASS', 'rule': 'daily_loss_circuit_breaker'}



# 5. Critical Gotchas for Coding Agents



# 6. Testing Strategy
## 6.1 Unit Test Pattern for Agents

# tests/unit/test_gap_detector.py
import pytest
from unittest.mock import MagicMock, patch
from agents.base.loader import BlueprintLoader

@pytest.fixture
def mock_market_data_mcp():
mock = MagicMock()
mock.list_tools_sync.return_value = [
# Mock tool objects that match Strands tool format
]
return mock

def test_gap_detector_filters_below_threshold(mock_market_data_mcp, mock_artifacts_mcp):
with patch('agents.base.loader.PromptRegistry') as mock_registry:
mock_registry.return_value.get.return_value = 'Test prompt'
loader = BlueprintLoader()

with patch.dict('os.environ', {'EXECUTION_MODE': 'backtest'}):
agent = loader.build_strands_agent('gap_detector', {
'market-data-mcp': mock_market_data_mcp,
'artifacts-mcp': mock_artifacts_mcp,
})
assert agent is not None

## 6.2 Backtest Validation Test
Critical: the gap detection output must match known historical data for 2024-11-04. This is the POC acceptance test.

# tests/backtest/test_poc_validation.py
import pytest
import json
from agents.gap_detector.handler import handler

KNOWN_GAPS_2024_11_04 = {
# Pre-verified against manual data pull
# Populate this before running POC validation
}

def test_gap_detection_matches_known_data():
event = {'date': '2024-11-04', 'threshold_pct': 2.0}
result = handler(event, {})

assert result['significant_gaps'] > 0
assert result['execution_mode'] == 'backtest'
assert result['success'] == True

# Verify specific symbols match known data
gap_symbols = {g['symbol'] for g in result['ranked_gaps']}
for symbol, expected_gap in KNOWN_GAPS_2024_11_04.items():
assert symbol in gap_symbols, f'{symbol} missing from results'
actual = next(g for g in result['ranked_gaps'] if g['symbol'] == symbol)
assert abs(actual['gap_pct'] - expected_gap) < 0.1, \
f'{symbol}: expected {expected_gap}, got {actual["gap_pct"]}'


# 7. Environment Variables Reference



| Gotcha | Impact | Solution |
| --- | --- | --- |
| 256KB Step Functions payload limit | Agent reasoning chains exceed this immediately | Claim-check: store in S3, pass only S3 key through SFN |
| Lambda 15-min timeout for complex agents | Portfolio Recommender with extended thinking can take >15min | Use AgentCore Runtime (8h) for complex agents in production |
| MCP connection reuse across Lambda invocations | State leakage between users in warm Lambda | Always use 'with mcp_client:' context manager per invocation |
| Agent non-determinism on Step Functions retry | Retry triggers different reasoning path with different tool calls | All tool side-effects MUST be idempotent with idempotency keys |
| Step Functions 25K event history limit | Agent retry loops exhaust this quickly | Implement 'continue as new execution' for long-running workflows |
| Strands Graph: no branch cancellation | In-flight branches cannot be cancelled once started | Design graph branches to be independent and idempotent |
| AgentCore cold start ~23 seconds | First session of the day has noticeable latency | Warm-up Lambda or accept cold start — document SLA accordingly |
| IBKR session expiry | IB Client Portal sessions expire every 24h | Implement auto-reconnect + heartbeat in ibkr-mcp |
| Bedrock throttling on parallel Map state | 50 parallel Lambda jobs all hitting Bedrock simultaneously | Add jitter to retry, implement per-agent token bucket rate limiting |
| MCP retry not configurable (Strands issue #675) | MCP failures go back to LLM not retried at transport level | Implement retry at MCP tool layer using tenacity decorator |


| Variable | Values | Default | Scope | Description |
| --- | --- | --- | --- | --- |
| EXECUTION_MODE | backtest | paper | live | backtest | All components | Primary mode switch |
| AWS_DEFAULT_REGION | e.g. eu-west-1 | — | All AWS components | AWS region |
| BEDROCK_REGION | e.g. us-west-2 | us-west-2 | Agent Layer | Bedrock model region (Claude models) |
| IBKR_ACCOUNT_ID | string | — | ibkr-mcp | IBKR account identifier |
| IBKR_HOST | hostname | localhost | ibkr-mcp | IB Gateway / TWS host |
| IBKR_PORT | 4001 | 4002 | 7496 | 4002 | ibkr-mcp | 4001=paper, 4002=live, 7496=TWS |
| MARKET_DATA_PROVIDER | polygon | alphaVantage | ibkr | polygon | market-data-mcp | Historical data provider |
| POLYGON_API_KEY | string | — | market-data-mcp | Polygon.io API key |
| ARTIFACTS_BUCKET | s3 bucket name | qitp-artifacts | artifacts-mcp | S3 bucket for artifacts |
| PROMPT_REGISTRY_BUCKET | s3 bucket name | qitp-prompt-registry | Blueprint Engine | S3 bucket for prompts |
| TELEGRAM_BOT_TOKEN | string | — | 2fa-mcp | Telegram bot token for 2FA |
| TELEGRAM_CHAT_ID | string | — | 2fa-mcp | Your Telegram chat ID |
| LANGFUSE_PUBLIC_KEY | string | — | All agents | Langfuse observability |
| LANGFUSE_SECRET_KEY | string | — | All agents | Langfuse observability |
| LANGFUSE_HOST | URL | — | All agents | Langfuse host (Anton instance) |
