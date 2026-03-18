

QUANTITATIVE INTELLIGENCE TRADING PLATFORM
QITP
Document 1: Platform Architecture & Technical Specification

Version: 1.0 — March 2026
Author: Nestor Colt | Status: DRAFT — For Coding Agents
Stack: AWS Strands Agents | Bedrock AgentCore | Step Functions | IBKR



# 1. Executive Summary
The Quantitative Intelligence Trading Platform (QITP) is a modular, blueprint-driven, AI-native algorithmic trading system. It operates as a personal Bloomberg Terminal, quantitative trading desk, and AI operating system — unified on AWS infrastructure, controlled via natural language, with enterprise-grade safety controls.

The platform is built around three core design principles:
Everything is versioned independently — agents, strategies, prompts, MCP skills each have their own lifecycle
The 2FA gate is a hard architectural boundary — no order reaches a broker without explicit human biometric/key approval in live mode
Three execution modes (backtest/paper/live) are controlled by a single environment variable — the same codebase runs in all modes

Primary use case: weekly gap analysis (Friday market close vs Monday market open) across a curated watchlist of 100 stocks, ETFs, and funds. The system identifies significant price gaps, applies multi-layer AI reasoning (sentiment, technical, ML prediction), evaluates strategies in parallel, and produces actionable trade recommendations — all governed by a deterministic orchestration layer.

Geography: Spain-based operator (CNMV regulatory context). Interactive Brokers as the broker. Multi-market capable (EU + US).

# 2. Architecture Overview
## 2.1 The Russian Doll Pattern
The architecture follows a layered containment model where each layer handles exactly one class of concern:


## 2.2 Full Stack Diagram

INTERACTION LAYER  →  Claude.ai / Custom UI / MCP-compatible client
↕
MCP SKILLS LAYER  →  ibkr-mcp | market-data-mcp | charting-mcp | artifacts-mcp | 2fa-mcp
↕
AGENT LAYER  →  Strands Agents SDK + Bedrock AgentCore Runtime
↕
ORCHESTRATION  →  AWS Step Functions (Standard Workflows)
↕
BROKER CONTROL  →  Interactive Brokers (TWS/Client Portal) + Risk Engine + 2FA Gate

## 2.3 Execution Modes
A single environment variable EXECUTION_MODE controls the entire system behavior. No code changes required to switch modes.



# 3. MCP Skills Layer
Every capability is exposed as an MCP server. Agents consume MCPs as tools. MCPs are versioned, containerized (Docker/ECS Fargate), and deployed independently from agent code.

## 3.1 ibkr-mcp — Interactive Brokers Control
The highest-risk MCP in the platform. Controls real money. Must be the most hardened, most tested component. Paper mode validation mandatory before live mode is enabled.

Exposed tools:
get_positions() — current open positions with P&L
get_account_summary() — cash, NAV, margin, buying power
get_market_data(symbol, fields) — real-time quote
place_order(symbol, action, qty, order_type, price, tif) — submit order (2FA gated in live)
cancel_order(order_id) — cancel pending order
get_order_status(order_id) — check order state
set_trailing_stop(symbol, trail_amount, trail_type) — attach trailing stop
get_executions() — filled orders history

Implementation notes:
ADR required: IB Client Portal API (REST) vs ib_insync (socket) — decision before coding
Spain/EU: ESMA leverage limits, MiFID II best execution logging, CNMV compliance
All tool calls logged: CloudWatch structured JSON with symbol, action, price, agent_reasoning_summary
Rate limiting + auto-reconnect on session expiry

## 3.2 market-data-mcp — Unified Market Data
Provider-agnostic data layer. In backtest mode routes to S3 parquet cache. In live mode routes to live feed. Redis caching prevents provider API abuse.

Exposed tools:
get_ohlcv(symbol, start, end, interval) — OHLCV bars
get_current_price(symbol) — latest trade price
get_friday_close(symbol, date) — Friday session close
get_monday_open(symbol, date) — Monday session open
get_gap(symbol, date) — Friday/Monday delta (absolute + %)
get_watchlist_gaps(date) — gaps for all 100 watchlist symbols ranked
get_volume_profile(symbol, date) — volume by price level

Supported providers (pluggable via config):
Historical: Polygon.io, Alpha Vantage, Yahoo Finance (free tier), IBKR historical
Real-time: IBKR market data subscriptions, Polygon.io WebSocket

## 3.3 artifacts-mcp — Universal Output Pipeline
Every output the system produces goes through this pipeline. Client receives artifact_id, polls for status, retrieves signed URL when ready.


## 3.4 2fa-mcp — Order Approval Gateway
Hard circuit breaker between agent order intent and IBKR submission. Implemented as Step Functions waitForTaskToken. Execution pauses until explicit human approval.

Phase 1: Telegram bot push notification with Approve/Reject buttons
Phase 2: Mobile push notification (SNS) + biometric unlock
Phase 3: Hardware key (YubiKey OTP)
Timeout: 5 minutes — auto-reject, no order submitted
Approval notification includes: symbol, action, quantity, estimated value EUR, agent rationale
Audit log: every gate event (request/approve/reject/timeout) written to DynamoDB

## 3.5 charting-mcp — Dynamic Chart Generation
Generates interactive React/Recharts artifacts delivered via artifacts-mcp pipeline.




# 4. Agent Layer
All agents are built on the Strands Agents SDK (AWS, Apache 2.0, v1.0+). Runtime is Bedrock AgentCore (Firecracker microVM isolation, up to 8h execution, session-scoped memory). Every agent definition is a YAML blueprint loaded at runtime — no hardcoded agent configuration in code.


## 4.1 Agent Blueprint Schema
Every agent is defined by a YAML blueprint. The blueprint is the source of truth. Runtime generates Strands agent instances from it.

id: gap_detector
version: 1.2.0
name: Gap Detection Agent
description: Scans watchlist for significant Friday/Monday price gaps
model:
provider: bedrock                        # bedrock | anthropic | vertex | litellm
model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
temperature: 0.2
max_tokens: 4096
cache_prompt: default
cache_tools: default
prompt_ref: gap_detector_v1.2              # from Prompt Registry
tools:
- mcp: market-data-mcp
tools: [get_watchlist_gaps, get_ohlcv, get_volume_profile]
- mcp: artifacts-mcp
tools: [create_artifact]
runtime:
type: agentcore                          # agentcore | lambda | fargate
max_iterations: 5
max_execution_time: 120
execution_modes:
backtest: enabled
paper: enabled
live: enabled
output_schema: gap_detection_v1            # validated JSON schema ref

## 4.2 Multi-Agent Patterns
Strands v1.0 provides four composable patterns. QITP uses three:


Critical distinction: within a single agent, routing is model-driven (non-deterministic). Between agents in a Graph, routing uses Python condition functions — fully deterministic. For end-to-end determinism, use Step Functions — not Strands.


# 5. Orchestration Layer — Step Functions
## 5.1 Weekly Analysis Workflow
The master Step Functions Standard Workflow. Runs every Monday at 08:30 CET via EventBridge Scheduler. This is the deterministic outer shell — every state transition is logged, auditable, and retryable.


## 5.2 Payload Management
Step Functions imposes a 256KB payload limit. Agent outputs (reasoning chains, document excerpts) routinely exceed this. Implement the claim-check pattern from day one.

All agent outputs stored in S3, only S3 key passed through Step Functions states
ResultPath pattern: $.agentResult appends task output without losing original input
ResultSelector: extracts only essential fields from Lambda response envelope
Large data: S3 Input/Output fields support up to 25MB for Bedrock-native integrations

## 5.3 Error Handling Pattern
Every agent invocation Task state uses this standard retry/catch pattern:

Retry:
- ErrorEquals: [Lambda.ServiceException, Lambda.TooManyRequestsException,
Bedrock.ThrottlingException]
IntervalSeconds: 3
MaxAttempts: 4
BackoffRate: 2.0
JitterStrategy: FULL
Catch:
- ErrorEquals: [States.ALL]
Next: NotifyError
ResultPath: $.error



# 6. Risk Engine & Safety Controls
The Risk Engine is a hard architectural boundary — not a soft guardrail. It runs as a dedicated Lambda before any order submission. No agent can override risk limits.

## 6.1 Risk Rules (all configurable via DynamoDB, none hardcoded)


## 6.2 Trailing Stop Manager
Runs as a separate EventBridge-triggered Lambda every 15 minutes during market hours (09:00-17:30 CET for EU, 14:30-21:00 CET for US).
Reads all open positions from IBKR via ibkr-mcp (read-only call)
Checks if trailing stop needs adjustment based on price movement
Ratchets stop upward for long positions — never downward
Updates IBKR order only if stop level needs to move
All stop adjustments logged to audit table


# 7. Data Layer
## 7.1 DynamoDB Tables


## 7.2 S3 Buckets
qitp-artifacts — generated artifacts (charts, reports, backtest results)
qitp-historical-data — OHLCV parquet files by symbol/date partition
qitp-prompt-registry — versioned prompt text files
qitp-strategy-blueprints — versioned strategy YAML files
qitp-model-artifacts — SageMaker model artifacts (Phase 2)


# 8. Infrastructure & Deployment
## 8.1 CDK Stack Structure


## 8.2 Environment Strategy

## 8.3 AgentCore vs Lambda Decision


# 9. Observability
Every agent invocation, every tool call, every order attempt, every risk check, every prompt version must be traceable end-to-end. Non-negotiable for a system managing real money.



# 10. POC Milestone & Success Criteria
The POC validates the core architecture in backtest mode only before any real money or live broker is involved. POC is complete only when ALL criteria pass.

## 10.1 POC Scope
Blueprint Engine loads gap_detection YAML blueprint and instantiates Strands agent
Gap Detection Agent scans 100 watchlist symbols for Monday 2024-11-04 using historical data
Sentiment Agent runs in Swarm pattern against top 10 gap symbols
gap_momentum_up strategy evaluated via Simulation Engine
Portfolio Recommender synthesizes all signals and produces recommendation JSON
Full pipeline orchestrated by Step Functions weekly workflow
All outputs stored as S3 artifacts, retrievable via signed URL
Equity curve chart rendered in Claude UI via charting-mcp

## 10.2 Explicit Success Criteria
Full pipeline runs end-to-end in <10 minutes for a single Monday date
Gap Detection output matches manually verified gaps for 2024-11-04
Sentiment scores directionally correct for 3 known news events in test period
Simulation Engine produces Sharpe ratio + equity curve for gap_momentum_up strategy
All artifacts retrievable via signed URL within 30 seconds of creation
Equity curve renders correctly in Claude UI as interactive React chart
Zero hardcoded prompts — all loaded from Prompt Registry
Execution mode switching: same pipeline runs in backtest and paper by env var only

## 10.3 POC Explicit Exclusions
IBKR connection (paper or live) — not in POC scope
2FA gate — not needed in backtest
ML prediction layer — Phase 2
Real-time data — historical only for POC



# Appendix A: Ticket Reference

# Appendix B: Key Architectural Decisions (ADRs Required)

| Layer | Technology | Responsibility | Determinism |
| --- | --- | --- | --- |
| Trigger | EventBridge Scheduler | Market schedule, cron triggers | Deterministic |
| Orchestration | AWS Step Functions | Workflow control, routing, retries | Deterministic |
| Agent Reasoning | Strands Agents SDK | Non-deterministic reasoning, tool use | Non-deterministic |
| Runtime | Bedrock AgentCore | Microvm isolation, session, memory | Infrastructure |
| Skills/Tools | MCP Servers (ECS Fargate) | Tool execution, broker, data, charts | Deterministic |
| Data | S3 + DynamoDB + SQS | Storage, state, queuing | Deterministic |


| Mode | Market Data | Order Execution | 2FA Required | Broker Connection |
| --- | --- | --- | --- | --- |
| backtest | Historical (S3/parquet) | Simulation engine only | No | None |
| paper | Live feed (Polygon/IBKR) | IBKR paper account | No | IBKR Paper |
| live | Live feed (Polygon/IBKR) | IBKR real account | YES — ALWAYS | IBKR Live (Spain) |


| Artifact Type | Format | Rendered In | Expiry |
| --- | --- | --- | --- |
| chart | React JSX (Recharts) | Claude UI (interactive) | 1 hour signed URL |
| report | Markdown / PDF | Claude UI / download | 1 hour signed URL |
| backtest_result | JSON + equity curve chart | Claude UI / download | 1 hour signed URL |
| recommendation | Structured JSON | Claude UI inline | 1 hour signed URL |
| image | PNG/JPEG | Claude UI inline | 1 hour signed URL |
| data_export | CSV / Parquet | Download only | 1 hour signed URL |


| Chart Type | Description | Primary Consumer |
| --- | --- | --- |
| candlestick | OHLCV with volume bars, SMA/EMA overlay | Gap Detection Agent |
| gap_scatter | Gap% vs subsequent return scatter plot | Weekly workflow report |
| equity_curve | Portfolio value over time + drawdown shading | Simulation Engine |
| portfolio_allocation | Pie/donut of position weights | Portfolio Recommender |
| sentiment_heatmap | Symbol x sentiment dimensions grid | Sentiment Agent |
| correlation_matrix | Watchlist symbol correlations | Risk Engine |
| pnl_bar | Weekly/monthly P&L bars | Observability dashboard |


| Agent | Pattern | Key Tools | Output |
| --- | --- | --- | --- |
| Gap Detection Agent | Single agent | market-data-mcp | ranked_gaps JSON artifact |
| Sentiment Analysis Agent | Strands Swarm | sentiment-mcp, market-data-mcp | sentiment_report artifact |
| Strategy Evaluation Agent | Strands Graph | backtest-mcp, market-data-mcp | strategy_scores artifact |
| Portfolio Recommender Agent | Single agent (extended thinking) | market-data-mcp, artifacts-mcp | recommendation artifact |
| Execution Agent | Single agent | ibkr-mcp (2FA gated) | order confirmation artifact |
| Risk/Guardrail Agent | Lambda (not Strands) | ibkr-mcp (read-only) | PASS/FAIL + reason |
| ML Prediction Agent | Single agent (Phase 2) | ml-predict-mcp, market-data-mcp | prediction artifact |
| Chart/Viz Agent | Single agent | charting-mcp, artifacts-mcp | chart artifact |


| Pattern | Used For | Key Property |
| --- | --- | --- |
| Agents-as-Tools | Portfolio Recommender calling Sentiment sub-agent | Hierarchical delegation, synchronous |
| Swarm | Sentiment Analysis: N per-ticker agents in parallel | Self-coordinating, shared memory |
| Graph | Strategy evaluation with conditional routing between agents | Deterministic inter-agent edges |
| Handoff | Risk Engine escalating to human review | Explicit control transfer with context |


| State | Type | Description | On Failure |
| --- | --- | --- | --- |
| ValidateMarketCalendar | Lambda Task | Check trading day validity, skip if holiday | Skip to NoOpComplete |
| FetchWatchlistGaps | Lambda Task (AgentCore) | Invoke Gap Detection Agent | Retry 3x, then NotifyError |
| CheckGapCount | Choice | If significant_gaps == 0 go to NoOpComplete | N/A |
| ParallelAnalysis | Parallel | Sentiment + Technical agents run simultaneously | Catch ALL → NotifyError |
| EvaluateStrategies | Map | Fan out: N strategies x M symbols in parallel | Catch throttling → retry |
| SynthesizeRecommendations | Lambda Task (AgentCore) | Portfolio Recommender Agent | Retry 3x, then NotifyError |
| RouteByMode | Choice | backtest → StoreResults; live/paper → OrderDecision | N/A |
| OrderDecision | Choice | action==none → Complete; else → 2FA Gate | N/A |
| TwoFactorGate | Wait (TaskToken) | Pause for human approval via Telegram | Timeout 5min → auto-reject |
| CheckRiskLimits | Lambda Task | Risk Engine: PASS/FAIL validation | FAIL → RiskViolationAlert |
| SubmitOrder | Lambda Task | Invoke ibkr-mcp place_order | Retry 2x, then NotifyError |
| SetTrailingStop | Lambda Task | Attach trailing stop via ibkr-mcp | Log warning, continue |
| StoreResults | Lambda Task | Save artifacts, update run history DynamoDB | Retry 3x |


| Rule | Default Value | Circuit Breaker? |
| --- | --- | --- |
| Max open positions | 5 | Yes — blocks new orders |
| Max single position size | 20% of NAV | Yes — blocks oversized orders |
| Max sector concentration | 40% | Yes — blocks sector-overweight orders |
| Daily loss circuit breaker | -3% portfolio | Yes — halts ALL trading 24h |
| Max drawdown circuit breaker | -10% from peak | Yes — halts ALL trading + alert |
| Trailing stop mandatory | All system-opened positions | Yes — order rejected without stop |
| CNMV CFD leverage limit | Per ESMA tiered rules | Yes — regulatory compliance |
| No naked short positions | Default: enabled | Configurable override required |


| Table | Partition Key | Sort Key | Purpose |
| --- | --- | --- | --- |
| qitp_watchlist | symbol | — | 100 symbols: metadata, sector, market, active flag |
| qitp_artifacts | artifact_id | — | Artifact metadata, status, S3 key, signed URL |
| qitp_audit_log | execution_id | timestamp | Every financial decision with full context |
| qitp_risk_state | account_id | — | Current positions, daily P&L, drawdown from peak |
| qitp_strategy_registry | strategy_id | version | Strategy blueprints: status, version history |
| qitp_prompt_registry | prompt_id | version | Prompt versions, S3 key, created_at, status |
| qitp_run_history | run_date | execution_id | Weekly run outcomes, artifact refs, summary |
| qitp_2fa_events | execution_id | event_type | Gate requests, approvals, rejections, timeouts |


| CDK Stack | Resources |
| --- | --- |
| QitpDataStack | S3 buckets, DynamoDB tables, SQS queues |
| QitpNetworkStack | VPC, subnets, security groups for AgentCore + IBKR Gateway |
| QitpAgentStack | Lambda functions (per agent), Lambda Layers (Strands SDK), AgentCore deployments |
| QitpMcpStack | ECS Fargate services per MCP, Service Discovery, ECR repos |
| QitpOrchestrationStack | Step Functions state machines, EventBridge rules |
| QitpObservabilityStack | CloudWatch dashboards, X-Ray, Langfuse integration, alarms |


| Environment | Deploy Trigger | IBKR Connection | Real Data |
| --- | --- | --- | --- |
| dev | Auto on merge to main | None (synthetic) | No |
| paper | Manual tag only | IBKR Paper Account | Yes |
| live | Manual approval gate after paper smoke tests | IBKR Live (Spain) | Yes + 2FA |


| Factor | Lambda | AgentCore Runtime |
| --- | --- | --- |
| Max execution time | 15 minutes | 8 hours |
| Payload limit | 6MB sync | 100MB |
| Cold start | Seconds (with layers) | ~23s first / ~9s warm |
| Session isolation | None (stateless) | Hardware (Firecracker microVM) |
| Memory management | External (DynamoDB/S3) | Built-in AgentCore Memory |
| Cost model | Per-invocation + duration | Per-second active compute (I/O wait free) |
| Recommendation | POC phase | Production |


| System | What it tracks |
| --- | --- |
| Langfuse (Anton instance) | Prompt versions, agent traces, token usage, latency per agent |
| AWS X-Ray | Distributed traces: Lambda, Step Functions, AgentCore end-to-end |
| CloudWatch | Metrics, alarms, dashboards — 8 key metrics in single view |
| Structured JSON logs | trace_id, execution_mode, agent_id, prompt_version, symbol, tokens_used |
| DynamoDB audit_log | Every financial decision: agent reasoning, signals, prompt version, order outcome |
| Telegram alerts | Circuit breaker, agent timeout >5min, Step Functions failure, Friday P&L report |


| Ticket | Title | Priority |
| --- | --- | --- |
| ROOT-46 | QITP Master Epic | Urgent |
| ROOT-47 | Blueprint Engine: YAML schema | Urgent |
| ROOT-48 | Prompt Registry: S3/DynamoDB + Bedrock caching | High |
| ROOT-49 | Execution Mode system: backtest/paper/live | Urgent |
| ROOT-50 | ibkr-mcp: Interactive Brokers MCP server | High |
| ROOT-51 | 2FA Order Gate: waitForTaskToken + Telegram | Urgent |
| ROOT-52 | market-data-mcp: unified market data | High |
| ROOT-53 | artifacts-mcp: S3 store + polling + charts | High |
| ROOT-54 | Gap Detection Agent | High |
| ROOT-55 | Sentiment Analysis Agent (Swarm) | High |
| ROOT-56 | Strategy Library: versioned YAML blueprints | High |
| ROOT-57 | Simulation Engine: parallel backtesting | High |
| ROOT-58 | Weekly Analysis Workflow: Step Functions | High |
| ROOT-59 | Portfolio Recommender Agent | High |
| ROOT-60 | Risk Engine: guardrails + circuit breakers | Urgent |
| ROOT-61 | CDK Infrastructure Stack | High |
| ROOT-62 | Observability: traces + audit log + P&L | High |
| ROOT-63 | POC Milestone: success criteria | Urgent |
| ROOT-64 | ML Prediction Agent: SageMaker Phase 2 | Medium |
| ROOT-65 | charting-mcp: React chart artifacts | Medium |
| ROOT-66 | GitHub repo + CI/CD + branch protection | High |


| ADR ID | Decision Required | Options |
| --- | --- | --- |
| ADR-001 | IBKR API: IB Client Portal API (REST) vs ib_insync (socket) | Must decide before ROOT-50 |
| ADR-002 | AgentCore Runtime vs Lambda for production agents | Cost model analysis required |
| ADR-003 | Historical data provider: Polygon.io vs Alpha Vantage vs IBKR | Cost + coverage analysis |
| ADR-004 | Prompt Registry backend: S3+DynamoDB vs dedicated service | Operational simplicity vs features |
| ADR-005 | Strategy evaluation: Step Functions Map vs Strands Swarm | Determinism requirements |
