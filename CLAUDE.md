# QITP — Quantitative Intelligence Trading Platform

> **THIS REPO IS SPECS AND PLANNING ONLY — NO APPLICATION CODE LIVES HERE.**
> All application code lives in separate repos under `~/dev/tccw-*`.
> This repo contains: design docs, research notes, CLAUDE.md, and `/plans/` (the source of truth for all implementation work).

## Repo Registry

### Generic Platform Repos (no qitp prefix)

| Repo | Path | Type | Phase | Package |
|---|---|---|---|---|
| `tccw-strand-package` | `~/tccw-strand-package` | Specs/planning (THIS REPO) | — | — |
| `tccw-agent-core` | `~/dev/tccw-agent-core` | Python library (CodeArtifact) | 1 | `agent_core` |
| `tccw-mcp-artifacts` | `~/dev/tccw-mcp-artifacts` | MCP server (Docker) | 1 | `mcp_artifacts` |
| `tccw-prompt-registry` | `~/dev/tccw-prompt-registry` | Service (Lambda+API GW) | 1 | `prompt_registry` |
| `tccw-agent-cli` | `~/dev/tccw-agent-cli` | CLI tool (pip) | 1 | `agent_cli` |
| `tccw-agent-infra` | `~/dev/tccw-agent-infra` | CDK stacks | 1 | — |

### Domain-Specific Repos (qitp prefix)

| Repo | Path | Type | Phase | Package |
|---|---|---|---|---|
| `tccw-qitp-simulation` | `~/dev/tccw-qitp-simulation` | Python library (CodeArtifact) | 1 | `qitp_simulation` |
| `tccw-qitp-mcp-market-data` | `~/dev/tccw-qitp-mcp-market-data` | MCP server (Docker) | 1 | `qitp_mcp_market_data` |
| `tccw-qitp-mcp-sentiment` | `~/dev/tccw-qitp-mcp-sentiment` | MCP server (Docker) | 1 | `qitp_mcp_sentiment` |
| `tccw-qitp-mcp-backtest` | `~/dev/tccw-qitp-mcp-backtest` | MCP server (Docker) | 1 | `qitp_mcp_backtest` |
| `tccw-qitp-agents` | `~/dev/tccw-qitp-agents` | Lambda handlers | 1 | `qitp_agents` |
| `tccw-qitp-mcp-ibkr` | `~/dev/tccw-qitp-mcp-ibkr` | MCP server (Docker) | 2 | `qitp_mcp_ibkr` |
| `tccw-qitp-mcp-2fa` | `~/dev/tccw-qitp-mcp-2fa` | MCP server (Docker) | 2 | `qitp_mcp_2fa` |
| `tccw-qitp-risk-engine` | `~/dev/tccw-qitp-risk-engine` | Lambda | 2 | `qitp_risk_engine` |
| `tccw-qitp-mcp-charting` | `~/dev/tccw-qitp-mcp-charting` | MCP server (Docker) | 2 | `qitp_mcp_charting` |
| `tccw-qitp-mcp-ml-predict` | `~/dev/tccw-qitp-mcp-ml-predict` | MCP server (Docker) | 2 | `qitp_mcp_ml_predict` |
| `tccw-qitp-mcp-technical` | `~/dev/tccw-qitp-mcp-technical` | MCP server (Docker) | 3 | `qitp_mcp_technical` |
| `tccw-qitp-dashboard` | `~/dev/tccw-qitp-dashboard` | Next.js web app | 3 | — |

---

## Implementation Status

All 25 plans executed. 17 repos implemented. ~1,250 tests passing. Full forensic audit completed.

### CI/CD & Quality

| Service | Status | Details |
|---------|--------|---------|
| GitHub | 17 private repos | The-Cloud-Clock-Work org |
| AWS CodeArtifact | Domain: tccw, Repo: tccw-python | 3 packages: agent-core, qitp-simulation, prompt-registry |
| SonarQube | 17 projects scanned | sonar.homeofanton.com (Cloudflare Zero Trust) |
| GitHub Actions | All repos | sonar-scan.yml (reusable), publish.yml (libraries), ci.yml |

### Naming Convention

Generic platform repos use non-prefixed names (`agent_core`, `mcp_artifacts`, `prompt_registry`, `agent_cli`).
Domain-specific repos use `qitp_` prefix (`qitp_simulation`, `qitp_agents`, `qitp_mcp_*`).
CDK stacks have no prefix (`DataStack`, `NetworkStack`, etc.).
DynamoDB tables use `qitp_` prefix for domain resources (`qitp_audit_log`, `qitp_risk_state`).

---

## Project Identity

- **What**: AI-native algorithmic trading platform — personal Bloomberg Terminal + quantitative trading desk
- **Owner**: Nestor Colt | Spain-based | CNMV regulatory context
- **Broker**: Interactive Brokers (EU + US markets)
- **Stack**: AWS Strands Agents SDK | Bedrock AgentCore | Step Functions | MCP | CDK (Python)
- **Primary use case**: Weekly gap analysis (Friday close vs Monday open) across 100 symbols
- **Repo**: `qitp/` monorepo — blueprints, agents, MCPs, infra, engine, risk, CLI, tests

---

## Architecture: The Russian Doll (5 Layers)

```
INTERACTION    →  Claude.ai / Custom UI / MCP-compatible client
     ↕
MCP SKILLS     →  ibkr-mcp | market-data-mcp | sentiment-mcp | artifacts-mcp
               →  backtest-mcp | charting-mcp | 2fa-mcp | ml-predict-mcp
     ↕
AGENTS         →  Strands Agents SDK (model-driven reasoning, multi-agent patterns)
               →  Bedrock AgentCore Runtime (Firecracker microVM, session memory)
     ↕
ORCHESTRATION  →  AWS Step Functions Standard Workflows (deterministic control flow)
     ↕
BROKER CONTROL →  Interactive Brokers + Risk Engine + 2FA Gate
```

**Core design rule**: Determinism outward, autonomy inward. Step Functions handles all decisions expressible as JSON conditions. Strands agents handle judgment, synthesis, and multi-step reasoning. The boundary between them is the most important architectural decision.

---

## Non-Negotiable Constraints

These are hard rules. No exceptions. No workarounds.

1. **No hardcoded prompts** — All prompts loaded from Prompt Registry (S3 + DynamoDB). `grep` for inline `system_prompt=` with literal text must return empty.
2. **No order without 2FA** — In live mode, every order passes through `waitForTaskToken` → Telegram approval → biometric. The 2FA gate is in Step Functions, never in agent code.
3. **No order without Risk Engine PASS** — `CheckRiskLimits` Lambda runs before any order state in Step Functions. Agents cannot override.
4. **Execution mode via env var** — `EXECUTION_MODE=backtest|paper|live` controls everything. Same codebase, zero code changes between modes. Mode routing lives in MCPs, not agents.
5. **All tool side-effects must be idempotent** — Agent retries invoke different reasoning paths. Use idempotency keys on all write operations.
6. **Claim-check pattern from day one** — All agent outputs stored in S3, only S3 keys pass through Step Functions (256KB payload limit).
7. **MCP connections scoped per invocation** — Always use `with mcp_client:` context managers in Lambda. Never reuse across warm invocations.
8. **CNMV ban list dynamically synced** — Short-sell ban list refreshed daily via EventBridge Lambda from CNMV. Never hardcoded. Risk Engine rejects SSHORT if list unavailable.
9. **RTS 25 transaction reporting before live** — All executed orders must be reported to ESMA Approved Reporting Mechanism (ARM). Lambda hook post-order in Step Functions.
10. **Corporate action monitoring** — Stock splits and special dividends must adjust trailing stops and position quantities. Daily check via EventBridge at 07:00 CET.
11. **IRPF tax lot tracking from day one** — Every position tracks acquisition date, cost basis (FIFO), FX rate at entry/exit (ECB daily). Required for Spanish IRPF 2-month homogeneous securities rule.
12. **All risk rules configurable via DynamoDB** — Zero hardcoded thresholds. `qitp_risk_config` table is source of truth. Risk Engine reads config at invocation, never caches.
13. **Idempotency keys on all write operations** — Format: `{agent_id}:{execution_id}:{operation}:{param_hash}`. Stored in `qitp_idempotency` DynamoDB table with 24h TTL. All agent handlers must check-before-write.
14. **Risk Engine failure halts pipeline** — If `CheckRiskLimits` Lambda fails (500, timeout, DynamoDB error), Step Functions MUST NOT proceed to order. Explicit `Catch` on `States.ALL` → `RiskEngineFailedEscalate`.

---

## Domain Isolation Rules

These rules govern cross-repo dependencies and are enforced by audit.

### Generic Platform Repos (no `qitp_` prefix)
- **Zero `qitp_*` imports** — `agent_core`, `mcp_artifacts`, `prompt_registry`, `agent_cli`, `agent_infra` must never import from any `qitp_*` package. These repos form the agnostic control plane and must remain domain-independent.

### QITP Domain Repos (`qitp_` prefix)
- **No cross-imports between domain repos** — QITP MCP servers and domain libraries must not import each other's application code directly.
- **No MCP-to-MCP calls** — An MCP server must never call another MCP server's endpoint. Tool orchestration belongs to agents and Step Functions, not MCPs.

### Architectural Exception: `backtest-mcp` → `qitp-simulation`
`tccw-qitp-mcp-backtest` declares `qitp-simulation` as a runtime dependency (consumed via CodeArtifact). This is intentional and permitted: `backtest-mcp` IS the designated MCP service boundary for the simulation library. Consuming a published CodeArtifact package from a sibling domain is acceptable when the importing MCP is the designated service boundary for that library. This is a package dependency, not a cross-MCP call.

---


## Blueprint-Driven Architecture

Everything is YAML. The Blueprint Engine is the single source of truth.

| Blueprint Type | Defines | Location |
|---|---|---|
| Agent Blueprint | Model, prompt ref, tools, runtime, hooks, execution modes | `blueprints/agents/{id}.yaml` |
| Workflow Blueprint | Step Functions state machine: states, transitions, agent refs | `blueprints/workflows/{id}.yaml` |
| Strategy Blueprint | Entry/exit conditions, trailing stop, position sizing, required agents | `blueprints/strategies/{id}.yaml` |

- Blueprints validated with **Pydantic** on every load — invalid = fail fast at startup
- Provider-agnostic: `model.provider` is an env var override (`bedrock|anthropic|vertex|litellm`)
- All versions tracked in Git with semver

---

## Execution Modes

| Mode | Market Data | Orders | 2FA | Broker |
|---|---|---|---|---|
| `backtest` | Historical (S3 parquet) | Simulation engine only | No | None |
| `paper` | Live feed (Polygon/IBKR) | IBKR paper account | No | IBKR Paper |
| `live` | Live feed (Polygon/IBKR) | IBKR real account | **YES — ALWAYS** | IBKR Live |

---

## Agents

All agents built on Strands Agents SDK v1.0+. Every agent defined by YAML blueprint loaded at runtime.

| Agent | Pattern | Key Tools | Output |
|---|---|---|---|
| Gap Detection | Single agent | market-data-mcp | ranked_gaps JSON |
| Sentiment Analysis | **Strands Swarm** (N parallel per ticker) | sentiment-mcp | sentiment_report |
| Strategy Evaluation | **Strands Graph** (deterministic routing) | backtest-mcp, market-data-mcp | strategy_scores |
| Portfolio Recommender | Single agent (extended thinking) | market-data-mcp, artifacts-mcp | recommendation JSON |
| Execution | Single agent | ibkr-mcp (2FA gated) | order confirmation |
| Risk Engine | Plain Lambda (not Strands) | ibkr-mcp (read-only) | PASS/FAIL |
| ML Prediction | Single agent (Phase 2) | ml-predict-mcp | prediction scores |

### Multi-Agent Control Model

```
WITHIN a single agent:    Model decides (non-deterministic)
BETWEEN agents in Graph:  Python conditions decide (deterministic)
ABOVE agents in SFN:      JSON Choice states decide (deterministic)
```

---

## MCP Servers (8 total)

All MCPs containerized (Docker/ECS Fargate), versioned independently, deployed independently from agents. Streamable HTTP transport in production, stdio in dev.

| MCP | Port | Phase | Ticket | Purpose |
|---|---|---|---|---|
| ibkr-mcp | 8001 | 2 | ROOT-50 | Broker control — positions, orders, trailing stops |
| market-data-mcp | 8002 | 1 | ROOT-52 | Unified OHLCV, gaps, volume (provider-agnostic) |
| sentiment-mcp | 8003 | 1 | ROOT-55 | News + analyst + macro sentiment scoring |
| artifacts-mcp | 8004 | 1 | ROOT-53 | S3 artifact store, signed URLs, polling |
| backtest-mcp | 8005 | 1 | ROOT-57 | Simulation engine, walk-forward validation |
| charting-mcp | 8006 | 2 | ROOT-65 | React/Recharts chart generation |
| 2fa-mcp | 8007 | 2 | ROOT-51 | Telegram approval gateway (waitForTaskToken) |
| ml-predict-mcp | 8008 | 2 | ROOT-64 | SageMaker XGBoost price prediction |
| technical-mcp | 8009 | 3 | ROOT-68 | RSI, MACD, Bollinger, trend, support/resistance |

---

## Risk Engine

Hard architectural boundary — not a soft guardrail. Runs as dedicated Lambda before any order submission.

| Rule | Default | Circuit Breaker? |
|---|---|---|
| Max open positions | 5 | Yes — blocks new orders |
| Max single position size | 20% NAV | Yes — blocks oversized |
| Max sector concentration | 40% | Yes — blocks overweight |
| Daily loss breaker | -3% portfolio | Yes — halts ALL trading 24h |
| Drawdown breaker | -10% from peak | Yes — halts ALL, manual resume |
| Trailing stop mandatory | All positions | Yes — order rejected without |

---

## Data Layer

### DynamoDB Tables
`qitp_watchlist`, `qitp_artifacts`, `qitp_audit_log`, `qitp_risk_state`, `qitp_strategy_registry`, `qitp_prompt_registry`, `qitp_run_history`, `qitp_2fa_events`

### S3 Buckets
`qitp-artifacts`, `qitp-historical-data`, `qitp-prompt-registry`, `qitp-strategy-blueprints`, `qitp-model-artifacts`

---

## Observability

| Layer | Technology | Captures |
|---|---|---|
| Prompt Tracking | Langfuse | Prompt version, token usage, latency, cost per agent |
| Distributed Tracing | AWS X-Ray | Cross-service: EventBridge → SFN → Lambda → AgentCore → MCP |
| Infra Metrics | CloudWatch + Grafana | Lambda duration, error rate, SFN count, ECS health |
| Audit Log | DynamoDB `qitp_audit_log` | Every financial decision (5-year retention, MiFID II) |
| Alerting | CloudWatch → SNS → Telegram | Circuit breakers, failures, weekly P&L |

---

## AgentCore Integration Strategy

### Phase 1 (POC): Direct Lambda + MCP

POC runs on Lambda with direct MCP connections. No AgentCore Runtime dependency. This is faster to iterate and debug.

- Agents deployed as Lambda functions with Strands SDK Lambda Layer
- MCPs run as local Docker containers (dev) or ECS Fargate (deployed)
- Session state in DynamoDB/S3 (no AgentCore Memory)
- Auth via IAM roles (no AgentCore Identity)
- Observability via X-Ray + Langfuse (no AgentCore native observability)

### Phase 2: AgentCore Graduation

After POC validates, migrate to AgentCore managed infrastructure:

| Component | POC (Phase 1) | Production (Phase 2) |
|---|---|---|
| **Runtime** | Lambda (15min max) | AgentCore Runtime (8h, Firecracker microVM, session isolation) |
| **Gateway** | Direct MCP connections hardwired in blueprints | AgentCore Gateway fronts all MCPs — unified tool registry, semantic search, outbound auth injection |
| **Memory** | DynamoDB/S3 manual | AgentCore Memory (short/long/episodic tiers, semantic retrieval, cross-agent shared context) |
| **Identity** | IAM roles + env var secrets | AgentCore Identity (OAuth/OIDC to IBKR, Polygon, Telegram — managed token flows) |
| **Policy** | Code-level enforcement (AI-DLC FIN-* rules) | Cedar policies — infra-level: "only execution_agent can call place_order", "backtest agents cannot touch ibkr-mcp" |
| **Evaluations** | Manual backtest comparison | AgentCore Evaluations (13 built-in evaluators + custom domain: gap classification accuracy, prompt quality scoring) |
| **Observability** | X-Ray + Langfuse + CloudWatch | AgentCore native OTEL spans + existing stack |

### Gateway Architecture (Phase 2)

Gateway becomes the MCP control plane:

```
Strands Agent → AgentCore Gateway (single URL)
                    ├── Target: market-data-mcp (MCP server)
                    ├── Target: sentiment-mcp (MCP server)
                    ├── Target: ibkr-mcp (MCP server, Cedar-gated)
                    ├── Target: Polygon.io (OpenAPI spec → auto-converted tools)
                    ├── Target: IBKR REST API (OpenAPI spec → auto-converted tools)
                    └── Semantic search across ALL tools from ALL targets
```

- Gateway auto-converts OpenAPI specs to MCP tools (Polygon.io, IBKR REST, news APIs)
- Gateway handles outbound auth: API keys (Polygon), OAuth (IBKR), mTLS (internal MCPs)
- Gateway provides semantic tool search — agents discover relevant tools dynamically
- Gateway caches tool definitions — `synchronize_gateway_targets()` on MCP redeploy
- Supports 10,000 tools per target with namespace prefixes

### Cedar Policy Examples (Phase 2)

```cedar
// Only execution_agent can submit orders in live mode
permit(
    principal == Agent::"execution_agent",
    action == Action::"invoke_tool",
    resource == Tool::"ibkr-mcp::place_order"
) when { context.execution_mode == "live" };

// Backtest agents cannot access ibkr-mcp at all
forbid(
    principal in AgentGroup::"backtest_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"ibkr-mcp"
);

// Risk Engine can only read positions (no write)
permit(
    principal == Agent::"risk_engine",
    action == Action::"invoke_tool",
    resource in [Tool::"ibkr-mcp::get_positions", Tool::"ibkr-mcp::get_account_summary"]
);
```

### Design-For-AgentCore Rules (Apply During POC)

Even though POC uses Lambda, design interfaces so AgentCore graduation is a config change, not a rewrite:

1. **Agent handlers must work with both Lambda `event` and AgentCore `payload`** — use a thin adapter
2. **MCP tool lists come from blueprint YAML, not hardcoded** — Gateway will replace the loader
3. **Session IDs map to SFN execution IDs** — AgentCore Memory uses the same session_id convention
4. **All secrets via env vars** — AgentCore Identity will replace them, but the interface is the same
5. **Structured logs include `agent_id`, `prompt_version`, `execution_mode`** — AgentCore Observability consumes these fields

---

## Regulatory Compliance (Spain / CNMV)

- **ESMA CFD leverage limits** enforced at Risk Engine level
- **MiFID II best execution** — all orders logged: timestamp (ms), symbol, ISIN, venue, price, qty, rationale
- **CNMV short-sell restrictions** — checked before any SSHORT on IBEX35 symbols
- **Spanish IRPF tax reporting** — all closed positions logged with acquisition/disposal dates, P&L EUR, commissions
- **5-year audit retention** — DynamoDB TTL minimum 157,680,000 seconds

---

## Development Methodology: AI-DLC

QITP uses AWS AI-Driven Development Life Cycle (AI-DLC) as its engineering process.

- **Bolts** replace sprints (hours to 1-2 days)
- Three phases: INCEPTION (what/why) → CONSTRUCTION (how) → OPERATIONS (deploy)
- Each Plane ticket = one bolt. Trigger: `Using AI-DLC, [intent]`
- Custom extensions: `FIN-001` to `FIN-008` (financial), `COMP-001` to `COMP-005` (compliance)
- All artifacts version-controlled in `aidlc-docs/`

---

## Build Order

### Phase 1: POC (Backtest Only)

```
P01: Repo scaffold + CI/CD + AI-DLC setup
P02: Blueprint Engine (YAML → Pydantic → Strands Agent)
P03: Execution Mode system (EXECUTION_MODE env var)
P04: Prompt Registry (S3 + DynamoDB + CLI)
P05: market-data-mcp (historical gaps from S3 parquet)
P06: artifacts-mcp (S3 store + signed URLs)
P07: sentiment-mcp (news + analyst + macro scoring)
P08: Gap Detection Agent (first Strands agent)
P09: Sentiment Analysis Agent (Swarm pattern)
P10: Strategy Library + Simulation Engine
P11: Portfolio Recommender Agent (extended thinking)
P12: Weekly Analysis Workflow (Step Functions CDK)
P13: POC Integration & Validation (end-to-end backtest)
```

### Phase 2: Production

```
P14: ibkr-mcp (IBKR broker control — orders, positions, trailing stops)
P15: 2FA Gate (waitForTaskToken + Telegram approval gateway)
P16: Risk Engine (8 rules, circuit breakers, trailing stop manager)
P17: Full Production Infra (multi-env CDK, WAF, Secrets Manager, auto-scaling)
P18: Observability (Langfuse + X-Ray + CloudWatch + audit log + Telegram alerts)
P19: AgentCore Integration (Runtime + Gateway + Memory + Identity + Cedar)
P20: charting-mcp (React/Recharts chart generation — 7 chart types)
P21: ML Prediction (SageMaker XGBoost + SHAP explainability)
```

### Phase 3: Platform Evolution

```
P22: Technical Analysis Agent + MCP (RSI, MACD, Bollinger, trend, S/R — fills 20% composite weight)
P23: Advanced 2FA (progressive tiers: Telegram → WebAuthn/biometric → YubiKey)
P24: QITP Dashboard (Next.js web app — 8 pages, real-time portfolio, 2FA web approval)
P25: Platform Expansion (AI screener, multi-market, A2A protocol, IRPF tax, CFD risk, multi-tenant)
```

---

## POC Success Criteria (ROOT-63)

All must pass. Backtest mode only. No real money. No IBKR.

1. Full pipeline runs end-to-end in <10 minutes for Monday 2024-11-04
2. Gap Detection output matches manually verified gaps
3. Sentiment scores directionally correct for 3 known news events
4. Simulation Engine produces Sharpe ratio + equity curve for `gap_momentum_up`
5. All artifacts retrievable via signed URL within 30 seconds
6. Equity curve renders in Claude UI as interactive React chart
7. Zero hardcoded prompts — all loaded from Prompt Registry
8. Execution mode switching: same pipeline runs backtest and paper by env var only

---

## Plans Directory

Implementation plans live in `/plans/`. Each plan is a self-contained spec that a fresh Claude Code agent can execute independently in a worktree.

- `plans/TODO.md` — master index with TLDRs, dependency order, and batch parallelization (13 batches)
- `plans/P01-repo-scaffold.md` through `plans/P13-poc-validation.md` — Phase 1 POC plans (13 plans)
- `plans/P14-mcp-ibkr.md` through `plans/P21-ml-prediction.md` — Phase 2 Production plans (8 plans)
- `plans/P22-technical-analysis-agent.md` through `plans/P25-platform-expansion.md` — Phase 3 Evolution plans (4 plans)

Each plan contains: objective, Plane ticket refs, dependencies, exact file paths, code patterns, acceptance criteria, and test expectations.

---

## AWS Configuration

| Setting | Value |
|---|---|
| Account | `835618032093` |
| Primary Region | `eu-west-1` |
| Bedrock Region | `us-west-2` (Claude models) |
| Auth | IAM |
| Default Model | `us.anthropic.claude-sonnet-4-20250514-v1:0` (Bedrock) |
| Inference Profiles (eu-west-1) | `eu.anthropic.claude-sonnet-4-6` / `eu.anthropic.claude-opus-4-6-v1` |
| CodeArtifact Domain | `tccw` |
| CodeArtifact Repo | `tccw-python` |

---

## Key Reference Documents

| Document | Content |
|---|---|
| `QITP_Doc1_Architecture.md` | Platform architecture, stack diagram, execution modes, all tables |
| `QITP_Doc2_Blueprints.md` | YAML schemas, agent/workflow/strategy examples, repo structure |
| `QITP_Doc3_ImplementationGuide.md` | Python code patterns, build order, Lambda handlers, CDK constructs |
| `QITP_Doc4_StrandsDeepDive.md` | Strands SDK patterns (Swarm, Graph, Handoff), hooks, AgentCore deployment |
| `QITP_Doc5_FinancialSpec.md` | Gap trading, watchlist, 5 strategies, signals, risk rules, IBKR integration |
| `QITP_Doc6_MCPCatalog.md` | All 8 MCP servers: tool signatures, schemas, error codes, deployment |
| `QITP_Doc7_OpsRunbook.md` | Observability, audit log, alerting, circuit breakers, incident playbooks |
| `QITP_Doc8_AIDLC.md` | AI-DLC methodology, custom extensions, bolt workflow, adoption roadmap |
| `QITP_Doc9_ForensicAudit.md` | Pre-production forensic audit: security, compliance, consistency, cost, failure modes, SDK correctness |
| `strands-rs-core.md` | Deep technical research on Strands + AgentCore + Step Functions integration |
