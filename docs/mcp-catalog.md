QUANTITATIVE INTELLIGENCE TRADING PLATFORM
Document 6: MCP Skills Catalog
Complete specification for all 8 MCP servers — tool signatures, schemas, deployment, error codes


# 1. MCP Skills Architecture Overview
All QITP agents consume capabilities exclusively through MCP (Model Context Protocol) servers — never through inline Python functions or direct API calls inside agent code. This enforces clean separation between agent reasoning and tool implementation, and enables independent versioning of each skill.

## 1.1 MCP Server Registry

## 1.2 MCP Transport Standards
All MCPs use Streamable HTTP transport (not stdio) for production — containerized Fargate services
stdio transport allowed in dev/local only — easier debugging
All MCP servers authenticate via mTLS — client cert issued per agent deployment
Each MCP server exposes a /health endpoint for ECS health checks
All tool calls logged: tool_name, input_hash, duration_ms, success, error_code



# 2. ibkr-mcp
## 2.1 ibkr-mcp Overview


### Exposed Tools

### place_order Input Schema
PlaceOrderRequest:
symbol: str              # e.g. 'NVDA'
action: Literal['BUY', 'SELL', 'SSHORT']
quantity: int            # Number of shares
order_type: Literal['MKT', 'LMT', 'STP', 'TRAIL']
limit_price: float | None   # Required if order_type = LMT
stop_price: float | None    # Required if order_type = STP
time_in_force: Literal['DAY', 'GTC', 'OPG', 'IOC']
currency: str            # 'USD' | 'EUR'
exchange: str            # 'SMART' | 'NASDAQ' | 'BME'
2fa_token: str           # Required in live mode. Ignored in paper/backtest.
idempotency_key: str     # UUID — prevents duplicate orders on retry

### Error Codes


# 3. market-data-mcp
## 3.1 market-data-mcp Overview


### Exposed Tools

### GapResult Schema
GapResult:
symbol: str
date: date              # Monday date
friday_close: float
monday_open: float
gap_pct: float          # Signed: positive=up, negative=down
gap_abs_pct: float      # abs(gap_pct)
direction: Literal['up', 'down']
volume_ratio: float     # Monday volume / 20-day avg volume
significant: bool       # True if abs(gap_pct) >= threshold
gap_type: str | None    # breakaway | runaway | exhaustion | common (Phase 2)


# 4. sentiment-mcp
## 4.1 sentiment-mcp Overview


### Exposed Tools

### CompositeSentiment Schema
CompositeSentiment:
symbol: str
composite_score: float   # 0.0 (very bearish) to 1.0 (very bullish)
sentiment_label: str     # very_bearish | bearish | neutral | bullish | very_bullish
news_score: float        # 0.0-1.0
news_article_count: int
analyst_score: float     # 0.0-1.0 (normalized from buy/sell/hold)
analyst_consensus: str   # strong_buy | buy | hold | sell | strong_sell
analyst_target_price: float
macro_alignment: str     # risk_on | neutral | risk_off
earnings_upcoming: bool  # True if earnings within 7 days
earnings_date: date | None
confidence: float        # 0.0-1.0 based on data completeness
data_staleness_hours: int # How old is the most recent data


# 5. artifacts-mcp
## 5.1 artifacts-mcp Overview


### Exposed Tools

### ArtifactType Enum


# 6. backtest-mcp
## 6.1 backtest-mcp Overview


### Exposed Tools

### BacktestResult Schema
BacktestResult:
run_id: str
strategy_id: str
strategy_version: str
symbols: list[str]
start_date: date
end_date: date
total_trades: int
winning_trades: int
losing_trades: int
win_rate_pct: float
total_return_pct: float
annualized_return_pct: float
max_drawdown_pct: float
sharpe_ratio: float
sortino_ratio: float
calmar_ratio: float
profit_factor: float
avg_holding_days: float
avg_win_pct: float
avg_loss_pct: float
equity_curve: list[{date, portfolio_value}]   # For chart generation
trades: list[Trade]                           # Full trade log
slippage_model: str
commission_model: str
artifact_id: str | None   # If equity curve chart was generated


# 7. charting-mcp
## 7.1 charting-mcp Overview


### Exposed Tools



# 8. 2fa-mcp
## 8.1 2fa-mcp Overview


### Exposed Tools

### Telegram Approval Message Format

### Security Rules
Approval tokens are single-use — cannot be reused
Tokens expire after 5 minutes — auto-reject on expiry
Request and approval events both logged to DynamoDB audit_log
Telegram chat ID validated — messages only accepted from registered operator chat
In paper and backtest mode: request_approval is a no-op returning auto_approved=True


# 9. ml-predict-mcp (Phase 2)
## 9.1 ml-predict-mcp Overview


### Exposed Tools

### FeatureVector Schema
FeatureVector:
gap_pct: float
volume_ratio: float
sentiment_score: float
vix_level: float
day_of_week: int          # 0=Monday
sector_encoded: int       # One-hot encoded sector
prior_week_return_pct: float
analyst_revision_7d: float  # Net analyst upgrades minus downgrades
earnings_days_until: int    # Days until next earnings (-1 if unknown)


END OF DOCUMENT 6 — QITP MCP Skills Catalog

| Version: 1.0 — March 2026 | Author: Nestor Colt | Status: DRAFT |
| --- | --- |


| MCP Server | Priority | Phase | Plane Ticket | Primary Consumers |
| --- | --- | --- | --- | --- |
| ibkr-mcp | High | 1 | ROOT-50 | Execution Agent, Risk Engine |
| market-data-mcp | High | 1 | ROOT-52 | Gap Detection, Portfolio Recommender |
| sentiment-mcp | High | 1 | ROOT-55 | Sentiment Agent |
| artifacts-mcp | High | 1 | ROOT-53 | All agents (output) |
| backtest-mcp | High | 1 | ROOT-57 | Simulation Engine, Strategy Agent |
| charting-mcp | Medium | 1.5 | ROOT-65 | Portfolio Recommender, Reporting |
| 2fa-mcp | Urgent | 1 | ROOT-51 | Step Functions 2FA Gate |
| ml-predict-mcp | Medium | 2 | ROOT-64 | ML Prediction Agent |


| EXECUTION_MODE Routing Rule
Every MCP server reads EXECUTION_MODE env var on startup. In backtest mode: all write operations (place_order, cancel_order) are no-ops that return simulated responses. In paper mode: connects to IBKR paper account. In live mode: connects to IBKR live account and requires 2FA token for destructive operations. Agents never need to know the execution mode. |
| --- |


| Purpose
Interactive Brokers control plane. The highest-risk MCP in the platform. Wraps IBKR TWS/Client Portal API. All order operations require EXECUTION_MODE awareness and 2FA token in live mode. This MCP is the only path to IBKR — nothing else touches the broker. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8001 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| get_positions() | (no params) | list[Position] | Returns all open positions with symbol, qty, avg_cost, market_value, unrealized_pnl |
| get_account_summary() | (no params) | AccountSummary | NAV, cash, buying_power, maintenance_margin, daily_pnl |
| get_market_data(symbol, fields) | symbol: str, fields: list[str] | dict | Real-time quote fields: last, bid, ask, volume, high, low |
| place_order(symbol, action, qty, order_type, price, tif, 2fa_token) | See schema below | OrderResult | LIVE MODE: requires valid 2fa_token. Returns order_id or raises AwaitingApprovalError |
| cancel_order(order_id, 2fa_token) | order_id: str, 2fa_token: str | CancelResult | LIVE MODE: requires 2fa_token. Cancels pending order. |
| get_order_status(order_id) | order_id: str | OrderStatus | filled, partial, pending, cancelled, rejected + fill details |
| get_executions(date_range) | start: date, end: date | list[Execution] | Filled orders history with price, qty, commission, exchange |
| set_trailing_stop(order_id, trail_amount, trail_type) | order_id: str, trail: float, type: 'pct'|'dollar' | TrailingStopResult | Attaches TRAIL order to existing position |


| Error Code | Meaning |
| --- | --- |
| AwaitingApprovalError | Live mode order submitted without 2fa_token — must go through 2FA gate |
| RiskViolationError | Order violates Risk Engine rules — details in error.rule field |
| IBKRConnectionError | IBKR Gateway not reachable — retry after reconnect |
| IBKRRateLimitError | IBKR API rate limit hit — retry after 1 second |
| InsufficientFundsError | Account does not have sufficient buying power |
| SymbolNotFoundError | Symbol not found on specified exchange |
| ESMALeverageLimitError | CFD order exceeds ESMA maximum leverage for this instrument |


| Purpose
Unified market data access layer. Routes to historical S3 store (backtest mode) or live provider API (paper/live mode). Provider-agnostic — data source configured via env var. Primary data providers: IBKR Historical API + Polygon.io. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8002 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| get_ohlcv(symbol, start, end, interval) | symbol: str, start: date, end: date, interval: '1d'|'1h'|'5m' | list[Bar] | Returns OHLCV bars. In backtest mode, served from S3 parquet cache. |
| get_current_price(symbol) | symbol: str | float | Last trade price. Backtest: raises BacktestModeError (no current price concept) |
| get_friday_close(symbol, date) | symbol: str, date: date (any Mon) | float | Returns Friday close preceding the given Monday date |
| get_monday_open(symbol, date) | symbol: str, date: date (Mon) | float | Returns Monday open for given date |
| get_gap(symbol, date) | symbol: str, date: date (Mon) | GapResult | Returns: gap_pct, direction, friday_close, monday_open, volume_ratio |
| get_watchlist_gaps(date) | date: date (Mon) | list[GapResult] | Gaps for all active watchlist symbols. Sorted by abs(gap_pct) desc. |
| get_watchlist() | (no params) | list[WatchlistItem] | All active watchlist symbols with metadata |
| get_volume_profile(symbol, date) | symbol: str, date: date | VolumeProfile | Volume by price level for given session |


| Purpose
Sentiment signal aggregator. Combines news sentiment, analyst ratings, and macro indicators into normalized scores. News sourced from Polygon.io News API. Analyst ratings from Financial Modeling Prep or similar. Macro from FRED API and Yahoo Finance. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8003 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| get_news_sentiment(symbol, days) | symbol: str, days: int (default 7) | NewsSentiment | Scrapes recent news, scores each article, returns aggregate score + top headlines |
| get_analyst_ratings(symbol) | symbol: str | AnalystRatings | Consensus rating, mean target price, # analysts, recent upgrades/downgrades |
| get_macro_sentiment() | (no params) | MacroSentiment | VIX level, Fear&Greed index, SPY 5-day return, risk_on/risk_off/neutral classification |
| get_earnings_context(symbol) | symbol: str | EarningsContext | Next earnings date, expected move (options-implied), last 4 EPS surprises |
| get_composite_sentiment(symbol) | symbol: str | CompositeSentiment | Weighted composite of news (40%) + analyst (40%) + macro alignment. Primary signal for agents. |


| Purpose
Universal output pipeline. Every artifact produced by the system — charts, reports, backtest results, recommendations, images — flows through this MCP. S3 is the storage backend. Clients receive a polling queue entry and resolve to a signed URL when ready. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8004 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| create_artifact(type, content, metadata) | type: ArtifactType, content: str|dict, metadata: dict | CreateResult | Stores artifact, returns artifact_id immediately. Signed URL generated async by Lambda trigger. |
| get_artifact(artifact_id) | artifact_id: str (UUID) | ArtifactResult | Returns signed URL if ready (status=ready), else current status (processing|error) |
| poll_artifact(artifact_id, timeout_s) | artifact_id: str, timeout_s: int (default 60) | ArtifactResult | Blocks until artifact is ready or timeout. Returns signed URL. |
| list_artifacts(filter) | type: str?, agent_id: str?, date: date?, limit: int | list[ArtifactMeta] | Returns artifact metadata list. Does not return content or URLs. |


| Type | Content Format | Typical Size |
| --- | --- | --- |
| chart | React JSX string (Recharts) | <50KB |
| report | Markdown or HTML string | <500KB |
| backtest_result | JSON with metrics + equity curve data | <2MB |
| recommendation | JSON (RecommendationReport schema) | <50KB |
| image | Base64 PNG/JPEG or S3 key | <10MB |
| data_export | CSV or Parquet (S3 key reference) | Any size |


| Purpose
Simulation engine interface. Runs strategy blueprints against historical data. The primary iteration validation loop — every strategy change must pass backtest before paper/live. Parallel execution via Lambda Map state for multi-strategy evaluation. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8005 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| run_backtest(strategy_id, symbols, start, end, config) | strategy_id: str, symbols: list[str], start: date, end: date, config: BacktestConfig | BacktestRunResult | Starts backtest job. Returns run_id immediately (async). Poll get_backtest_result for completion. |
| get_backtest_result(run_id) | run_id: str (UUID) | BacktestResult | StatusResult | Returns full results if complete. Returns status=running if still processing. |
| run_walk_forward(strategy_id, symbols, config) | strategy_id: str, symbols: list[str], config: WalkForwardConfig | WalkForwardResult | Runs rolling-window walk-forward validation to detect overfitting. |
| compare_strategies(run_ids) | run_ids: list[str] | ComparisonResult | Side-by-side comparison of multiple backtest runs with ranking |


| Purpose
Visual output generator. Produces React/Recharts components as chart artifacts. Charts rendered inline in Claude UI as interactive React components. Non-Claude clients receive signed URL to static HTML fallback. All charts stored via artifacts-mcp. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8006 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| generate_candlestick(symbol, bars, indicators) | symbol: str, bars: list[Bar], indicators: list[str] | str (artifact_id) | Candlestick + volume bars. Indicators: SMA20, SMA50, EMA9, BB, VWAP |
| generate_equity_curve(equity_series, drawdown_series, metadata) | equity: list[{date,value}], dd: list[{date,value}], meta: dict | str (artifact_id) | Line chart with drawdown shading. Benchmark overlay optional. |
| generate_gap_scatter(gaps) | gaps: list[GapResult] | str (artifact_id) | Scatter: gap_pct (x) vs subsequent_return (y). Colored by direction. |
| generate_sentiment_heatmap(sentiment_data) | data: list[CompositeSentiment] | str (artifact_id) | Symbol x dimension heatmap. Dimensions: news, analyst, macro. |
| generate_pnl_bar(pnl_series) | pnl: list[{period, value}] | str (artifact_id) | Weekly/monthly P&L bar chart. Green positive, red negative. |
| generate_portfolio_allocation(positions) | positions: list[Position] | str (artifact_id) | Donut chart of current position weights by symbol and sector. |
| generate_chart(type, data, config) | type: ChartType, data: dict, config: dict | str (artifact_id) | Generic chart generator. Use convenience methods above when possible. |


| Purpose
Human approval gateway for destructive operations in live mode. Implements the waitForTaskToken pattern — Step Functions pauses execution and waits for human approval before releasing the token. Phase 1: Telegram bot with approve/reject buttons. Phase 2: mobile push with biometric unlock. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8007 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| request_approval(operation, details, task_token) | operation: str, details: OrderDetails, task_token: str (SFN token) | ApprovalRequest | Sends Telegram message with order details and approve/reject buttons. Returns request_id. |
| verify_token(approval_token) | approval_token: str (from Telegram callback) | VerifyResult | Verifies the approval token is valid and not expired. Returns the SFN task token to release. |
| get_approval_status(request_id) | request_id: str | ApprovalStatus | pending | approved | rejected | expired |
| reject_pending(request_id, reason) | request_id: str, reason: str | RejectResult | Manually reject a pending approval (e.g. circuit breaker triggered after request sent) |


| Example Approval Message
QITP LIVE ORDER REQUEST

Action: BUY 23 shares of NVDA
Estimated Value: EUR 2,047.00
Strategy: gap_momentum_up v1.2.0
Entry Price: ~$878.50 (market order)
Trailing Stop: 3.0% ATR
Composite Score: 0.84

Rationale: Strong gap-up of 3.32% with 1.8x volume. Bullish analyst revision yesterday. Macro: risk_on.

[APPROVE] [REJECT]

Expires in 5 minutes. |
| --- |


| Purpose
SageMaker inference interface for the ML Prediction Agent. Phase 2 only — not required for POC. Wraps a trained XGBoost model that predicts price direction at T+1, T+3, T+5 days based on gap, sentiment, and technical features. Returns direction confidence score + SHAP feature importance. |
| --- |


| Property | Value | Notes |
| --- | --- | --- |
| Transport | Streamable HTTP | MCP protocol transport type |
| Default Port | 8008 | Configurable via env var |
| Deployment | ECS Fargate (production) / Docker Compose (dev) |  |
| Versioning | Independent semver — does not follow agent versions |  |
| Auth | mTLS between agent Lambda and MCP container |  |


| Tool Name | Signature | Returns | Notes |
| --- | --- | --- | --- |
| predict(symbol, features) | symbol: str, features: FeatureVector | PredictionResult | Invokes SageMaker endpoint. Returns direction prediction + confidence for T+1/T+3/T+5. |
| get_model_metadata() | (no params) | ModelMetadata | Current model version, training date, validation accuracy, feature list |
| get_feature_importance(symbol, features) | symbol: str, features: FeatureVector | SHAPResult | Returns SHAP values for explainability — which features drove this prediction |
