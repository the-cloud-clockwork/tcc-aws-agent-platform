# QITP — Platform Reading Guide & Repository Map

> Read this before opening any repo. It tells you what each repo does, why it exists, how it connects to the others, and the exact order to read them so nothing is confusing.

---

## The Mental Model (read this first)

QITP is a **Russian Doll** — 6 concentric layers, each wrapping the next:

```
┌─────────────────────────────────────────────────────┐
│  LAYER 6 — INTERFACE                                 │
│  tccw-qitp-dashboard  (web UI)                       │
│  ┌───────────────────────────────────────────────┐   │
│  │  LAYER 5 — AGENTS                             │   │
│  │  tccw-qitp-agents  (reasoning & decisions)    │   │
│  │  ┌─────────────────────────────────────────┐  │   │
│  │  │  LAYER 4 — ENHANCEMENT MCPs             │  │   │
│  │  │  technical · ml-predict · charting       │  │   │
│  │  │  ┌───────────────────────────────────┐  │  │   │
│  │  │  │  LAYER 3 — SAFETY & EXECUTION     │  │  │   │
│  │  │  │  risk-engine · ibkr · 2fa          │  │  │   │
│  │  │  │  ┌─────────────────────────────┐  │  │  │   │
│  │  │  │  │  LAYER 2 — DATA MCPs        │  │  │  │   │
│  │  │  │  │  artifacts · market-data    │  │  │  │   │
│  │  │  │  │  sentiment · backtest        │  │  │  │   │
│  │  │  │  │  ┌───────────────────────┐  │  │  │  │   │
│  │  │  │  │  │  LAYER 1 — SERVICES   │  │  │  │  │   │
│  │  │  │  │  │  prompt-registry      │  │  │  │  │   │
│  │  │  │  │  │  simulation · cli     │  │  │  │  │   │
│  │  │  │  │  │  ┌─────────────────┐  │  │  │  │  │   │
│  │  │  │  │  │  │  LAYER 0        │  │  │  │  │  │   │
│  │  │  │  │  │  │  agent-core     │  │  │  │  │  │   │
│  │  │  │  │  │  │  agent-infra    │  │  │  │  │  │   │
│  │  │  │  │  │  └─────────────────┘  │  │  │  │  │   │
│  │  │  │  │  └───────────────────────┘  │  │  │  │   │
│  │  │  │  └─────────────────────────────┘  │  │  │   │
│  │  │  └───────────────────────────────────┘  │  │   │
│  │  └─────────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**The rule**: lower layers have zero knowledge of higher layers. `agent-core` doesn't know agents exist. Agents don't know the dashboard exists. Data flows upward, control flows downward.

---

## Reading Order — The 17 Repos

Read in this exact sequence. Each repo references concepts from the ones before it.

### LAYER 0 — Bedrock (2 repos)
*Read these first. Everything else is built on top of them.*

| # | Repo | One sentence | Read time |
|---|---|---|---|
| 1 | `tccw-agent-core` | The shared SDK — blueprint engine, execution modes, hooks, observability, and AgentCore integration used by every other repo. | ~30 min |
| 2 | `tccw-agent-infra` | Every AWS resource in the platform — all DynamoDB tables, S3 buckets, Lambda functions, ECS services, and the Step Functions pipeline. | ~30 min |

**After these two, you will understand**: what a Blueprint is, what `EXECUTION_MODE` does, what every table and bucket is for, and how the Step Functions pipeline flows.

---

### LAYER 1 — Platform Services (3 repos)
*The plumbing that all agents and MCPs rely on.*

| # | Repo | One sentence | Connects to |
|---|---|---|---|
| 3 | `tccw-prompt-registry` | Versioned prompt storage (Lambda + API GW + DynamoDB + S3) — enforces that zero prompts are hardcoded anywhere in the platform. | Used by ALL agents via `agent-core`'s `PromptRegistryClient` |
| 4 | `tccw-agent-cli` | Developer CLI (`agentcli` command) for validating blueprints, managing prompts, rendering workflow graphs, and promoting strategies. | Talks to `prompt-registry`; reads blueprints from any repo |
| 5 | `tccw-qitp-simulation` | Pure Python backtest engine — event-driven portfolio simulation with FIFO settlement, slippage models, and walk-forward validation. | Consumed as a library by `backtest-mcp`; provides training data for `ml-predict-mcp` |

**After these three, you will understand**: how prompts get into agents, how to use the CLI, and how backtesting works at the math level.

---

### LAYER 2 — Data MCPs (4 repos)
*The "inputs" — what agents read to make decisions.*

| # | Repo | One sentence | Connects to |
|---|---|---|---|
| 6 | `tccw-mcp-artifacts` | Universal output bus — every agent stores its results in S3 via this MCP, and passes only the S3 key (not the payload) through Step Functions. | ALL agents write here; Step Functions reads keys; `charting-mcp` outputs here |
| 7 | `tccw-qitp-mcp-market-data` | Unified OHLCV, gap detection, and volume data — routes to S3 parquet in backtest, Polygon.io/yfinance in live. | Used by Gap Detection Agent, Strategy Evaluation Agent, ML feature inputs |
| 8 | `tccw-qitp-mcp-sentiment` | News (40%) + analyst ratings (40%) + macro/VIX (20%) → composite sentiment score 0–100. | Used by Sentiment Analysis Agent (Swarm pattern — N agents in parallel, one per ticker) |
| 9 | `tccw-qitp-mcp-backtest` | Wraps `qitp-simulation` as an MCP server — provides async backtest jobs, strategy loading, walk-forward validation, and result storage. | Used by Strategy Evaluation Agent (Graph pattern); depends on `qitp-simulation` and `artifacts-mcp` |

**After these four, you will understand**: where market data comes from, how sentiment is scored, how backtests run asynchronously, and why outputs are in S3 not in memory.

---

### LAYER 3 — Safety & Execution (3 repos)
*The "outputs" — what happens after a decision is made. This is where real money is at risk.*

| # | Repo | One sentence | Connects to |
|---|---|---|---|
| 10 | `tccw-qitp-risk-engine` | Hard Lambda gate (NOT a Strands agent) — evaluates 8 risk rules against DynamoDB thresholds before any order; pipeline halts if this fails. | Called by Step Functions `CheckRiskLimits` state; reads `qitp_risk_config` and `qitp_risk_state`; reads positions from `ibkr-mcp` |
| 11 | `tccw-qitp-mcp-ibkr` | Interactive Brokers broker integration — 8 tools for positions, orders, trailing stops; routes to simulation/paper/live based on `EXECUTION_MODE`. | Used by Execution Agent and Risk Engine (read-only); only reachable after Risk Engine PASS + 2FA approval |
| 12 | `tccw-qitp-mcp-2fa` | Progressive approval gate — Tier 1 Telegram (<€5K), Tier 2 WebAuthn (€5K–25K), Tier 3 YubiKey (>€25K) — Step Functions waits via `waitForTaskToken`. | Lives in Step Functions between `CheckRiskLimits` and the order states; only active in live mode |

**After these three, you will understand**: how the safety stack works, why no agent can place an order unilaterally, and the exact sequence: Risk Engine PASS → 2FA approval → IBKR order.

---

### LAYER 4 — Enhancement MCPs (3 repos)
*Phase 2/3 additions that improve prediction quality. Not required for Phase 1 backtest.*

| # | Repo | One sentence | Connects to |
|---|---|---|---|
| 13 | `tccw-qitp-mcp-technical` | 7 technical indicators (RSI, MACD, Bollinger, ATR, MAs, trend, S/R) + composite score — contributes 20% weight to Phase 2 ranking. | Used by Technical Analysis Agent in `qitp-agents`; reads price data from `market-data-mcp` |
| 14 | `tccw-qitp-mcp-ml-predict` | XGBoost price direction prediction across T+1/T+3/T+5 horizons with SHAP explainability — contributes 20% weight to Phase 2 ranking. | Used by ML Prediction Agent; trained on data from `qitp-simulation`; reads live features from `market-data-mcp` and `sentiment-mcp` |
| 15 | `tccw-qitp-mcp-charting` | Generates interactive React/Recharts JSX charts (7 types) stored as artifacts — renders directly in Claude UI. | Used by Portfolio Recommender Agent and reporting; stores outputs in `artifacts-mcp` |

**After these three, you will understand**: how Phase 2 composite scoring works and how the platform generates the charts you see in Claude.

---

### LAYER 5 — Agents (1 repo)
*The reasoning layer — where the LLM actually makes decisions.*

| # | Repo | One sentence | Connects to |
|---|---|---|---|
| 16 | `tccw-qitp-agents` | All 8 Strands agents (Gap Detection, Sentiment Swarm, Strategy Graph, Portfolio Recommender, Execution, Risk, ML Prediction, Technical Analysis) plus IRPF tax reporter, watchlist screener, and A2A protocol. | Consumes ALL MCPs; deployed as Lambda functions by `agent-infra`; loads prompts from `prompt-registry`; stores outputs in `artifacts-mcp` |

**After this one, you will understand**: how the LLM-driven reasoning layer orchestrates all the MCPs, how the three Strands patterns (Single, Swarm, Graph) are applied, and the full end-to-end data flow.

---

### LAYER 6 — Interface (1 repo)
*The surface you interact with.*

| # | Repo | One sentence | Connects to |
|---|---|---|---|
| 17 | `tccw-qitp-dashboard` | Next.js 15 web app — 8 pages (Dashboard, Portfolio, Strategies, Pipeline, Risk, Watchlist, Approvals, Settings), real-time WebSocket, Cognito auth. | Reads from ALL DynamoDB tables and S3 via API Gateway; monitors Step Functions; provides web 2FA approval UI for Tier 2+ orders |

---

## Composite Scoring Cheat Sheet

How the platform ranks 100 symbols each week:

```
PHASE 1 (active now):
  composite = gap_score(45%) + sentiment_score(35%) + technical_score(20%)

PHASE 2 (when ml-predict is deployed):
  composite = gap_score(35%) + sentiment_score(25%) + technical_score(20%) + ml_score(20%)

  ml_score = predict_t1(0.5) + predict_t3(0.3) + predict_t5(0.2)
  technical_score = rsi(20%) + macd(20%) + bollinger(15%) + trend(25%) + support_resistance(20%)
```

---

## The Execution Pipeline (what actually happens on Monday morning)

```
EventBridge (Monday 07:00 CET)
    │
    ▼
Step Functions: WeeklyAnalysisWorkflow
    │
    ├─► GapDetectionAgent ──► market-data-mcp ──► [100 gap results] ──► artifacts-mcp
    │
    ├─► SentimentSwarm ──► sentiment-mcp (N parallel) ──► [100 sentiment scores] ──► artifacts-mcp
    │
    ├─► StrategyEvaluationAgent (Graph) ──► backtest-mcp ──► simulation ──► artifacts-mcp
    │
    ├─► PortfolioRecommenderAgent ──► reads all 3 artifacts ──► recommendation ──► artifacts-mcp
    │
    ├─► CheckRiskLimits (Lambda) ──► PASS / FAIL
    │         │ FAIL → RiskEngineFailedEscalate → Telegram alert → STOP
    │         │ PASS ↓
    ├─► 2FA Gate (waitForTaskToken) ──► Telegram/WebAuthn/YubiKey ──► APPROVED
    │         │ REJECT/TIMEOUT → pipeline STOP
    │         │ APPROVED ↓
    └─► ExecutionAgent ──► ibkr-mcp ──► IBKR order ──► RTS 25 report ──► audit log
```

---

## The 5 Rules That Connect Everything

Every design decision traces back to one of these:

| Rule | What it means practically |
|---|---|
| **No hardcoded prompts** | `prompt-registry` must be seeded before any agent runs. Agents call `PromptRegistryClient.resolve()` — if registry is empty, they crash intentionally. |
| **No order without 2FA in live** | 2FA gate is a Step Functions state — `waitForTaskToken`. It cannot be bypassed by agent code. Agents have no path around it. |
| **No order without Risk Engine PASS** | `CheckRiskLimits` Lambda runs as a Step Functions state. `Catch: States.ALL → RiskEngineFailedEscalate`. Agent code never sees the error — the pipeline just stops. |
| **EXECUTION_MODE controls everything** | `backtest` = S3 parquet + simulation. `paper` = live data + IBKR paper. `live` = live data + IBKR real + 2FA. Same codebase, zero code changes. |
| **Claim-check pattern** | Step Functions has a 256KB payload limit. All agent outputs go to S3 via `artifacts-mcp`. Only S3 keys travel through the pipeline. |

---

## Dependency Map (who imports who)

```
agent-core  ◄─────────────────── imported by ALL other repos

agent-infra ──deploys──► all Lambda functions
            ──deploys──► all ECS Fargate services (MCPs)
            ──deploys──► Step Functions state machine
            ──creates──► all DynamoDB tables + S3 buckets

prompt-registry ◄─── agent-core's PromptRegistryClient
                ◄─── agent-cli (push/get/diff/rollback commands)

simulation ◄─── backtest-mcp (wraps as MCP tools)
           ◄─── ml-predict-mcp (training data generation)

artifacts-mcp ◄─── ALL agents (claim-check outputs)
              ◄─── charting-mcp (stores JSX chart artifacts)

market-data-mcp ◄─── Gap Detection Agent
                ◄─── Strategy Evaluation Agent
                ◄─── ml-predict-mcp (live feature inputs)
                ◄─── technical-mcp (price data for indicators)

sentiment-mcp ◄─── Sentiment Analysis Agent (Swarm)
              ◄─── ml-predict-mcp (sentiment_score feature)

backtest-mcp ◄─── Strategy Evaluation Agent (Graph)

risk-engine ◄─── Step Functions (CheckRiskLimits state, every run)
            ──reads──► ibkr-mcp (positions, account — read-only)

ibkr-mcp ◄─── Execution Agent (write: orders, trailing stops)
         ◄─── Risk Engine (read: positions, account summary)

2fa-mcp ◄─── Step Functions (waitForTaskToken)

technical-mcp ◄─── Technical Analysis Agent
ml-predict-mcp ◄─── ML Prediction Agent
charting-mcp ◄─── Portfolio Recommender Agent

qitp-agents ──uses──► ALL MCPs listed above
            ──deploys via──► agent-infra (Lambda functions)
            ──loads prompts from──► prompt-registry
            ──stores outputs in──► artifacts-mcp

dashboard ──reads──► DynamoDB tables (via API Gateway)
          ──reads──► S3 artifacts (signed URLs from artifacts-mcp)
          ──monitors──► Step Functions executions
          ──approves──► 2fa-mcp (Tier 2 web approval UI)
```

---

## What Each Repo Owns (single responsibility)

| Repo | Owns | Does NOT own |
|---|---|---|
| `agent-core` | Contracts, patterns, shared types | Business logic, market data |
| `agent-infra` | AWS resources, deployment | Application code |
| `prompt-registry` | Prompt versions and resolution | Agent reasoning |
| `agent-cli` | Developer workflow | Production runtime |
| `simulation` | Backtest math | MCP protocol, live data |
| `artifacts-mcp` | S3 storage protocol | What gets stored |
| `market-data-mcp` | OHLCV, gaps, watchlist | Sentiment, technicals |
| `sentiment-mcp` | News/analyst/macro scoring | Price data |
| `backtest-mcp` | Async job management | Simulation math |
| `risk-engine` | Risk rule evaluation | Agent reasoning, UI |
| `ibkr-mcp` | Broker communication | Risk decisions, 2FA |
| `2fa-mcp` | Approval flow | Risk rules, orders |
| `technical-mcp` | Indicator computation | Prediction, news |
| `ml-predict-mcp` | XGBoost inference + SHAP | Portfolio decisions |
| `charting-mcp` | JSX chart generation | Data fetching |
| `agents` | LLM reasoning + orchestration | Infrastructure, data math |
| `dashboard` | Web UI + real-time display | Business logic |

---

## Before You Start Reading: The 3 Things to Internalize

**1. Blueprint = Agent definition**
A Blueprint is a YAML file that defines an agent: which model, which prompt (by registry ID), which MCP tools, which execution mode restrictions. `agent-core` loads it, validates it with Pydantic, and builds the Strands agent from it. No blueprint = no agent.

**2. EXECUTION_MODE = environment selector**
This single env var rewires the entire platform. In `backtest`, market data comes from your S3 parquet files and orders go to a simulation engine. In `paper`, data is live but orders go to IBKR paper. In `live`, everything is real and 2FA is mandatory. The MCPs implement this switch internally — agents don't know which mode they're in.

**3. The claim-check pattern = why S3 keys travel, not data**
AWS Step Functions has a hard 256KB payload limit. Agent outputs (equity curves, recommendations, backtest results) are megabytes. So every agent calls `create_artifact()` on `artifacts-mcp`, gets back a small key like `artifacts/2024-11-04/recommendation_v1.json`, and that key is what travels through Step Functions. The next agent calls `get_artifact(key)` to get the full content.

---

## Quick-Reference: All 17 Repos in 1 Table

| Layer | Repo | Package | Type | Phase | Port |
|---|---|---|---|---|---|
| 0 | `tccw-agent-core` | `agent-core` | Python library | 1+ | — |
| 0 | `tccw-agent-infra` | — | CDK stacks | 1+ | — |
| 1 | `tccw-prompt-registry` | `qitp-prompt-registry` | Lambda + API GW | 1 | — |
| 1 | `tccw-agent-cli` | `agent-cli` | CLI tool | 1 | — |
| 1 | `tccw-qitp-simulation` | `qitp-simulation` | Python library | 1 | — |
| 2 | `tccw-mcp-artifacts` | `mcp-artifacts` | MCP server | 1 | 8004 |
| 2 | `tccw-qitp-mcp-market-data` | `qitp-mcp-market-data` | MCP server | 1 | 8002 |
| 2 | `tccw-qitp-mcp-sentiment` | `qitp-mcp-sentiment` | MCP server | 1 | 8003 |
| 2 | `tccw-qitp-mcp-backtest` | `qitp-mcp-backtest` | MCP server | 1 | 8005 |
| 3 | `tccw-qitp-risk-engine` | `qitp-risk-engine` | Lambda | 2 | — |
| 3 | `tccw-qitp-mcp-ibkr` | `qitp-mcp-ibkr` | MCP server | 2 | 8001 |
| 3 | `tccw-qitp-mcp-2fa` | `qitp-mcp-2fa` | MCP server | 2 | 8007 |
| 4 | `tccw-qitp-mcp-technical` | `qitp-mcp-technical` | MCP server | 3 | 8009 |
| 4 | `tccw-qitp-mcp-ml-predict` | `qitp-mcp-ml-predict` | MCP server | 2 | 8008 |
| 4 | `tccw-qitp-mcp-charting` | `qitp-mcp-charting` | MCP server | 2 | 8006 |
| 5 | `tccw-qitp-agents` | `qitp-agents` | Lambda handlers | 1+ | — |
| 6 | `tccw-qitp-dashboard` | — | Next.js web app | 3 | 3000 |

---

*This document lives in `tccw-strand-package` — the specs/planning repo.*
*For deep dives: `QITP_Doc1_Architecture.md` through `QITP_Doc9_ForensicAudit.md`.*
*For implementation plans: `plans/P01` through `plans/P25`.*
