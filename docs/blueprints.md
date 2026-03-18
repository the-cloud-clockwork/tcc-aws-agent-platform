

QUANTITATIVE INTELLIGENCE TRADING PLATFORM
Document 2: Blueprint Schemas, Configuration Reference & YAML Examples

Version: 1.0 — March 2026 | For Coding Agents



# 1. Blueprint System Overview
The Blueprint Engine is the single source of truth for the entire QITP platform. Every agent, workflow, and strategy is defined as a YAML blueprint. The runtime generates all downstream artifacts from these blueprints — Strands agent instances, Step Functions state machines, AgentCore deployments, Lambda packaging.

Three blueprint types:
Agent Blueprint — defines a Strands agent: model, prompt reference, tools, runtime config
Workflow Blueprint — defines a Step Functions state machine: states, transitions, agent task references
Strategy Blueprint — defines a trading strategy: entry/exit conditions, risk params, required agents

Core constraints that apply to ALL blueprints:
Provider-agnostic: model provider (bedrock/vertex/anthropic/litellm) is an env var override, never hardcoded
Execution mode (backtest/paper/live) is a single env var — no mode-specific logic in blueprints
Prompts referenced by ID from Prompt Registry — never inline in blueprint
All blueprint versions tracked in Git — semver (major.minor.patch)
Schema validated with Pydantic on every load — invalid blueprints fail fast at startup

# 2. Agent Blueprint Schema
## 2.1 Full Schema Reference


## 2.2 Agent Blueprint Examples
### Gap Detection Agent

# blueprints/agents/gap_detector.yaml
id: gap_detector
version: 1.2.0
name: Gap Detection Agent
description: Scans watchlist for significant Friday/Monday price gaps

model:
provider: bedrock
model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
temperature: 0.2
max_tokens: 4096
cache_prompt: default
cache_tools: default

prompt_ref: gap_detector_v1.2

tools:
- mcp: market-data-mcp
tools:
- get_watchlist_gaps
- get_ohlcv
- get_volume_profile
- mcp: artifacts-mcp
tools:
- create_artifact

runtime:
type: agentcore
max_iterations: 5
max_execution_time: 120

execution_modes:
backtest: true
paper: true
live: true

output_schema: gap_detection_output_v1

### Portfolio Recommender Agent (with extended thinking)

# blueprints/agents/portfolio_recommender.yaml
id: portfolio_recommender
version: 2.0.0
name: Portfolio Recommender Agent
description: Multi-signal synthesis with portfolio constraints and extended reasoning

model:
provider: bedrock
model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
temperature: 0.1
max_tokens: 8192
extended_thinking: true
cache_prompt: default

prompt_ref: portfolio_recommender_v2.0

tools:
- mcp: market-data-mcp
tools: [get_ohlcv, get_current_price]
- mcp: artifacts-mcp
tools: [create_artifact, get_artifact]

runtime:
type: agentcore
max_iterations: 8
max_execution_time: 300

hooks:
- QitpObservabilityHook
- PortfolioConstraintHook

output_schema: portfolio_recommendation_v2

### Sentiment Analysis Agent (Swarm)

# blueprints/agents/sentiment_analyzer.yaml
id: sentiment_analyzer
version: 1.0.0
name: Sentiment Analysis Agent
description: Market-wide + per-ticker sentiment scoring using Swarm pattern

model:
provider: bedrock
model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
temperature: 0.3
max_tokens: 2048

prompt_ref: sentiment_analyzer_v1.0

tools:
- mcp: sentiment-mcp
tools:
- get_news_sentiment
- get_analyst_ratings
- get_macro_sentiment
- get_earnings_context
- mcp: artifacts-mcp
tools: [create_artifact]

runtime:
type: agentcore
max_iterations: 5
max_execution_time: 90

multi_agent:
pattern: swarm
execution_timeout: 90
node_timeout: 30
max_handoffs: 20

output_schema: sentiment_report_v1



# 3. Workflow Blueprint Schema
## 3.1 Schema Reference


## 3.2 Weekly Analysis Workflow Blueprint

# blueprints/workflows/weekly_analysis.yaml
id: weekly_gap_analysis
version: 1.0.0
name: Weekly Gap Analysis Pipeline
description: Monday morning gap analysis, sentiment, strategy evaluation, recommendations

trigger:
type: schedule
schedule: cron(30 8 ? * MON *)  # 08:30 UTC every Monday (adjust for CET)
timezone: Europe/Madrid

timeout_minutes: 60

states:
- id: ValidateMarketCalendar
type: task
lambda_ref: qitp-market-calendar-validator
result_path: $.calendar
retry:
- errors: [Lambda.ServiceException]
interval_seconds: 5
max_attempts: 3
next: CheckTradingDay

- id: CheckTradingDay
type: choice
choices:
- condition: {path: $.calendar.is_trading_day, op: eq, value: false}
next: NoOpComplete
- condition: {path: $.calendar.is_trading_day, op: eq, value: true}
next: FetchWatchlistGaps

- id: FetchWatchlistGaps
type: task
agent_ref: gap_detector
input_path: $.calendar
result_path: $.gaps
retry:
- errors: [Lambda.TooManyRequestsException, Bedrock.ThrottlingException]
interval_seconds: 3
max_attempts: 4
backoff_rate: 2.0
jitter: FULL
catch:
- errors: [States.ALL]
next: NotifyError
next: CheckGapCount

- id: CheckGapCount
type: choice
choices:
- condition: {path: $.gaps.significant_gaps, op: eq, value: 0}
next: NoOpComplete
default: ParallelAnalysis

- id: ParallelAnalysis
type: parallel
branches:
- states: [SentimentAnalysis]
- states: [TechnicalIndicators]
result_path: $.analysis
next: EvaluateStrategies

- id: EvaluateStrategies
type: map
items_path: $.gaps.ranked_gaps
max_concurrency: 10
iterator_workflow: strategy_evaluation
result_path: $.strategy_results
next: SynthesizeRecommendations

- id: SynthesizeRecommendations
type: task
agent_ref: portfolio_recommender
result_path: $.recommendations
next: RouteByMode

- id: RouteByMode
type: choice
choices:
- condition: {env: EXECUTION_MODE, op: eq, value: backtest}
next: StoreResults
default: OrderDecision

- id: OrderDecision
type: choice
choices:
- condition: {path: $.recommendations.action, op: eq, value: none}
next: StoreResults
default: CheckRiskLimits

- id: CheckRiskLimits
type: task
lambda_ref: qitp-risk-engine
result_path: $.risk_check
next: RouteByRisk

- id: RouteByRisk
type: choice
choices:
- condition: {path: $.risk_check.result, op: eq, value: FAIL}
next: RiskViolationAlert
default: TwoFactorGate

- id: TwoFactorGate
type: wait
wait_type: task_token
heartbeat_seconds: 300
resource: arn:aws:states:::sqs:sendMessage.waitForTaskToken
next: SubmitOrder

- id: SubmitOrder
type: task
agent_ref: execution_agent
result_path: $.order_result
retry:
- errors: [IBKR.RateLimitError]
interval_seconds: 5
max_attempts: 2
next: SetTrailingStop

- id: StoreResults
type: task
lambda_ref: qitp-results-store
next: Complete

- id: Complete
type: succeed

- id: NoOpComplete
type: succeed

- id: NotifyError
type: task
lambda_ref: qitp-telegram-notifier
next: WorkflowFailed

- id: WorkflowFailed
type: fail
cause: Workflow execution failed



# 4. Strategy Blueprint Schema
## 4.1 Schema Reference


## 4.2 Strategy Examples
### Gap Momentum Up Strategy

# blueprints/strategies/gap_momentum_up.yaml
id: gap_momentum_up
version: 1.0.0
name: Gap Momentum Up
description: Buy gap-up symbols with bullish sentiment confirmation. Exit on trailing stop or max holding days.

asset_types: [stock, etf]
markets: [US, EU, ES]
required_signals: [gap, sentiment]

entry_conditions:
logic: AND
conditions:
- field: gap_pct
op: gte
value: 2.0
- field: gap_direction
op: eq
value: up
- field: sentiment_score
op: gte
value: 0.60
- field: volume_ratio
op: gte
value: 1.2
- field: macro_alignment
op: in
value: [risk_on, neutral]

exit_conditions:
logic: OR
conditions:
- type: trailing_stop
- field: holding_days
op: gte
value: 5
- field: sentiment_score
op: lte
value: 0.30

trailing_stop:
type: percent
value: 3.0

position_sizing:
method: risk_pct
value: 1.0   # risk 1% of portfolio per trade

max_holding_days: 5
max_concurrent_positions: 3
min_gap_pct: 2.0
min_volume_ratio: 1.2

required_agents:
- gap_detector
- sentiment_analyzer
- portfolio_recommender

required_mcps:
- market-data-mcp
- sentiment-mcp
- ibkr-mcp

### Mean Reversion Gap Strategy

# blueprints/strategies/mean_reversion_gap.yaml
id: mean_reversion_gap
version: 1.0.0
name: Mean Reversion Gap Fade
description: Fade large gaps expecting reversion within 2 days. Contrarian strategy.

asset_types: [stock]
markets: [US, EU]
required_signals: [gap, technical]

entry_conditions:
logic: AND
conditions:
- field: gap_pct
op: gte
value: 5.0   # Only large gaps qualify for mean reversion
- field: rsi_pre_gap
op: gte
value: 70   # Overbought before gap — reversion more likely
- field: earnings_upcoming_days
op: gt
value: 10   # Avoid earnings gaps

exit_conditions:
logic: OR
conditions:
- type: trailing_stop
- field: holding_days
op: gte
value: 2
- field: price_change_pct
op: lte
value: -2.0   # Take profit on 2% reversion

trailing_stop:
type: percent
value: 2.0   # Tight stop for fade strategy

position_sizing:
method: risk_pct
value: 0.5   # Smaller size for contrarian bet

max_holding_days: 2
max_concurrent_positions: 2
min_gap_pct: 5.0


# 5. Prompt Registry
## 5.1 Architecture
Prompts are first-class versioned artifacts, independent of agent code. A prompt change does not trigger an agent redeployment. Prompts are referenced in blueprints by ID with an optional pinned version.


## 5.2 Prompt Reference Format in Blueprints

# Pin to specific version
prompt_ref: gap_detector_v1.2

# Always resolve to latest stable
prompt_ref: gap_detector

# With explicit version tag
prompt_ref: portfolio_recommender@2.0.0

## 5.3 Prompt File Naming Convention
File: prompts/{agent_id}/{version}.txt — e.g. prompts/gap_detector/1.2.0.txt
S3 key: {prompt_id}/{version}.txt
DynamoDB key: {prompt_id} + sort key {version}
Status values: draft | stable | deprecated
Only stable prompts resolve for paper/live mode — draft only in backtest/dev

## 5.4 CLI Operations
# Push new prompt version
qitp prompt push prompts/gap_detector/1.3.0.txt \
--id gap_detector \
--version 1.3.0 \
--description 'Improved gap filtering with volume confirmation'

# Promote to stable
qitp prompt promote gap_detector 1.3.0

# Diff two versions
qitp prompt diff gap_detector 1.2.0 1.3.0

# Rollback
qitp prompt rollback gap_detector 1.2.0



# 6. Agent Output Schemas
## 6.1 Gap Detection Output

{
"date": "2025-03-10",
"scan_count": 100,
"significant_gaps": 12,
"threshold_pct": 2.0,
"execution_mode": "backtest",
"artifact_id": "art_abc123",
"ranked_gaps": [
{
"symbol": "NVDA",
"name": "NVIDIA Corporation",
"friday_close": 850.20,
"monday_open": 878.50,
"gap_abs": 28.30,
"gap_pct": 3.32,
"gap_direction": "up",
"volume_ratio": 1.8,
"sector": "Technology",
"asset_type": "stock",
"market": "US"
}
]
}

## 6.2 Sentiment Report Output

{
"date": "2025-03-10",
"macro": {
"vix_level": 18.5,
"fear_greed_index": 62,
"regime": "risk_on",
"sector_rotation": "growth"
},
"per_ticker": [
{
"symbol": "NVDA",
"sentiment_score": 0.72,
"sentiment_label": "bullish",
"news_score": 0.80,
"news_count": 14,
"analyst_consensus": "buy",
"analyst_target": 950.00,
"analyst_upgrades_7d": 2,
"earnings_upcoming": false,
"macro_alignment": "risk_on"
}
]
}

## 6.3 Portfolio Recommendation Output

{
"date": "2025-03-10",
"execution_mode": "paper",
"market_conditions": "risk_on",
"portfolio_constraints_applied": true,
"recommendations": [
{
"symbol": "NVDA",
"action": "buy",
"strategy": "gap_momentum_up",
"entry_price": 878.50,
"position_size_eur": 2000,
"position_size_shares": 2,
"trailing_stop_pct": 3.0,
"trailing_stop_price": 852.15,
"expected_holding_days": 3,
"composite_score": 0.84,
"gap_score": 0.80,
"sentiment_score": 0.72,
"strategy_confidence": 0.91,
"rationale": "Strong gap-up (3.32%) with bullish macro (risk_on), analyst upgrades, high volume confirmation. gap_momentum_up strategy conditions fully met."
}
],
"no_action_symbols": [
{"symbol": "AAPL", "reason": "sentiment_score 0.45 below threshold 0.60"},
{"symbol": "TSLA", "reason": "earnings_upcoming in 3 days"}
]
}


# 7. Repository Structure

qitp/
├── blueprints/
│   ├── agents/                 # Agent YAML blueprints
│   │   ├── gap_detector.yaml
│   │   ├── sentiment_analyzer.yaml
│   │   ├── portfolio_recommender.yaml
│   │   ├── execution_agent.yaml
│   │   └── ml_predictor.yaml
│   ├── workflows/              # Step Functions workflow blueprints
│   │   ├── weekly_analysis.yaml
│   │   └── strategy_evaluation.yaml
│   └── strategies/             # Strategy YAML blueprints
│       ├── gap_momentum_up.yaml
│       ├── gap_fade_down.yaml
│       ├── gap_continuation.yaml
│       ├── mean_reversion_gap.yaml
│       └── sentiment_driven.yaml
├── prompts/                    # Prompt text files for registry push
│   ├── gap_detector/
│   │   ├── 1.0.0.txt
│   │   └── 1.2.0.txt
│   └── portfolio_recommender/
│       └── 2.0.0.txt
├── infra/                      # CDK Python stacks
│   ├── app.py
│   ├── stacks/
│   │   ├── data_stack.py
│   │   ├── network_stack.py
│   │   ├── agent_stack.py
│   │   ├── mcp_stack.py
│   │   ├── orchestration_stack.py
│   │   └── observability_stack.py
│   └── constructs/
│       ├── strands_agent.py    # Reusable CDK construct for Strands agents
│       ├── mcp_service.py      # Reusable CDK construct for MCP ECS services
│       └── sfn_workflow.py     # Construct: blueprint YAML -> Step Functions
├── agents/                     # Strands agent Python implementations
│   ├── base/
│   │   ├── loader.py           # Blueprint loader: YAML -> Strands Agent
│   │   ├── hooks.py            # QitpObservabilityHook, PortfolioConstraintHook
│   │   └── schemas.py          # Pydantic output schema validators
│   ├── gap_detector/
│   │   └── handler.py          # Lambda/AgentCore entrypoint
│   ├── sentiment_analyzer/
│   │   └── handler.py
│   └── portfolio_recommender/
│       └── handler.py
├── mcps/
│   ├── ibkr-mcp/
│   │   ├── Dockerfile
│   │   ├── server.py           # MCP server entrypoint
│   │   ├── tools/
│   │   │   ├── orders.py
│   │   │   ├── positions.py
│   │   │   └── market_data.py
│   │   └── tests/
│   ├── market-data-mcp/
│   ├── sentiment-mcp/
│   ├── backtest-mcp/
│   ├── charting-mcp/
│   └── artifacts-mcp/
├── engine/                     # Simulation engine library (no agent dependency)
│   ├── backtest.py
│   ├── metrics.py              # Sharpe, Sortino, drawdown, etc.
│   ├── slippage.py
│   └── commission.py           # IBKR tiered EU pricing model
├── risk/                       # Risk engine Lambda
│   ├── handler.py
│   ├── rules.py
│   └── trailing_stop_manager.py
├── cli/                        # qitp CLI tool
│   ├── main.py
│   ├── prompt.py               # prompt push/get/list/diff/rollback
│   └── strategy.py             # strategy list/validate/promote
├── schemas/                    # JSON Schema files for output validation
│   ├── gap_detection_output_v1.json
│   ├── sentiment_report_v1.json
│   └── portfolio_recommendation_v2.json
├── tests/
│   ├── unit/
│   ├── integration/
│   └── backtest/               # Backtest validation fixtures
└── docs/
├── adr/
│   ├── 000-template.md
│   └── 001-ibkr-api-choice.md
└── runbooks/


| Field | Type | Required | Description |
| --- | --- | --- | --- |
| id | string | Yes | Unique agent identifier (snake_case) |
| version | semver | Yes | Blueprint version e.g. 1.2.0 |
| name | string | Yes | Human-readable name |
| description | string | Yes | What this agent does |
| model.provider | enum | Yes | bedrock | anthropic | vertex | litellm |
| model.model_id | string | Yes | Provider-specific model ID |
| model.temperature | float 0-1 | No | Default: 0.3 |
| model.max_tokens | int | No | Default: 4096 |
| model.cache_prompt | string | No | default | disabled. Enables Bedrock prompt caching |
| model.cache_tools | string | No | default | disabled. Enables Bedrock tool caching |
| model.extended_thinking | bool | No | Default: false. Enable for complex synthesis agents |
| prompt_ref | string | Yes | Prompt Registry ID + optional pinned version |
| tools[].mcp | string | Yes | MCP server ID (matches deployed service) |
| tools[].tools | list[string] | Yes | Specific tools to expose from this MCP |
| runtime.type | enum | Yes | agentcore | lambda | fargate |
| runtime.max_iterations | int | No | Default: 10. Hard stop on agent loop |
| runtime.max_execution_time | int | No | Default: 300. Seconds. Hard timeout |
| runtime.memory_mb | int | No | Lambda/Fargate only. Default: 1024 |
| hooks[] | list[string] | No | Hook provider class names to attach |
| execution_modes.backtest | bool | No | Default: true |
| execution_modes.paper | bool | No | Default: true |
| execution_modes.live | bool | No | Default: true |
| output_schema | string | No | JSON schema ID for output validation |


| Field | Type | Required | Description |
| --- | --- | --- | --- |
| id | string | Yes | Unique workflow identifier |
| version | semver | Yes | Blueprint version |
| name | string | Yes | Human-readable name |
| trigger.type | enum | Yes | schedule | manual | event |
| trigger.schedule | cron string | No | EventBridge cron expression |
| trigger.event_source | string | No | EventBridge event source pattern |
| states[].id | string | Yes | State identifier (unique within workflow) |
| states[].type | enum | Yes | task | choice | parallel | map | wait | succeed | fail |
| states[].agent_ref | string | No (task) | Agent blueprint ID to invoke |
| states[].lambda_ref | string | No (task) | Lambda function name for non-agent tasks |
| states[].retry | list | No | Retry config: errors, interval, maxAttempts, backoffRate |
| states[].catch | list | No | Catch config: errors, next state |
| states[].choices | list | No (choice) | Choice conditions and next states |
| states[].branches | list | No (parallel) | Parallel branch definitions |
| states[].max_concurrency | int | No (map) | Map state max concurrency (default: 40) |
| timeout_minutes | int | No | Workflow-level timeout (default: 60) |
| execution_modes | object | No | Per-mode enable/disable |


| Field | Type | Required | Description |
| --- | --- | --- | --- |
| id | string | Yes | Unique strategy identifier (snake_case) |
| version | semver | Yes | Strategy version |
| name | string | Yes | Human-readable name |
| asset_types | list[enum] | Yes | stock | etf | fund | crypto |
| markets | list[string] | Yes | US | EU | ES — market context |
| required_signals | list[enum] | Yes | gap | sentiment | technical | fundamental | ml |
| entry_conditions | list[condition] | Yes | AND/OR logic conditions for entry |
| exit_conditions | list[condition] | Yes | AND/OR conditions for exit |
| trailing_stop.type | enum | Yes | percent | atr | dollar |
| trailing_stop.value | float | Yes | Stop value (% or $ depending on type) |
| position_sizing.method | enum | Yes | fixed | kelly | risk_pct |
| position_sizing.value | float | Yes | Size value per method |
| max_holding_days | int | Yes | Maximum days to hold position |
| max_concurrent_positions | int | No | Max positions from this strategy (default: 3) |
| required_agents | list[string] | Yes | Agent blueprint IDs required |
| required_mcps | list[string] | Yes | MCP server IDs required |
| min_gap_pct | float | No | Minimum gap % to qualify (default: 2.0) |
| min_volume_ratio | float | No | Min volume vs 20d avg (default: 1.2) |


| Component | Service | Purpose |
| --- | --- | --- |
| Prompt text storage | S3 (qitp-prompt-registry bucket) | Versioned prompt files at s3://qitp-prompt-registry/{id}/{version}.txt |
| Prompt metadata index | DynamoDB (qitp_prompt_registry table) | prompt_id, version, created_at, description, tags, status, s3_key |
| Version resolution | Lambda (qitp-prompt-resolver) | Resolves prompt_ref to latest stable version if version not pinned |
| Bedrock caching | Strands BedrockModel cache_prompt param | Auto-enabled for prompts >1000 tokens |
| CLI tool | Python Typer CLI | push, get, list, diff, rollback commands |
