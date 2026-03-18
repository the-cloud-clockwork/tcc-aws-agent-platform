QUANTITATIVE INTELLIGENCE TRADING PLATFORM
QITP
Document 5: Financial Platform Specification
Gap Analysis • Strategy Library • Watchlist • Sentiment • Risk Engine • IBKR Integration


# 1. The Core Market Concept: Gap Trading
A price gap occurs when a security opens significantly higher or lower than its previous session close with no trading activity in between. The most reliable and actionable gaps occur at the weekly boundary: Friday market close versus Monday market open. This weekend gap is the primary signal source for QITP.

## 1.1 Why Weekend Gaps Matter
Weekend gaps are structurally different from intraday gaps:
Information asymmetry: 2.5 days of news, earnings, analyst revisions, geopolitical events, and macroeconomic data accumulate with zero price discovery
Volume confirmation: Monday opening volume is a primary signal — high volume gaps are continuation candidates; low volume gaps are fade candidates
Institutional re-positioning: Fund managers adjust positions at week open based on mandate changes, index rebalancing, and risk limits
Retail reaction: Retail investors react to weekend news, amplifying institutional moves

## 1.2 Gap Classification

## 1.3 Gap Threshold Configuration
Not all gaps are worth analyzing. QITP applies a minimum threshold filter before passing symbols to downstream agents:
Default threshold: abs(gap_pct) >= 2.0%
Configurable per watchlist segment: ETFs may use 1.5%, individual stocks 2.5%
Historical data shows 2%+ gaps on individual stocks have statistically significant follow-through on high volume
Threshold stored in DynamoDB watchlist config — changeable without code deployment



# 2. Watchlist Management
The watchlist is the universe of securities QITP monitors. Initial size: 100 symbols. Curated manually by the operator. Future versions may include dynamic expansion via screener agents.

## 2.1 Watchlist Composition (Initial 100 Symbols)

## 2.2 Watchlist Schema (DynamoDB)
Table: qitp_watchlist
PK: symbol (string, e.g. 'NVDA')
SK: 'config'
Fields:
name: string           // 'NVIDIA Corporation'
asset_type: enum       // stock | etf | fund
market: enum           // us | es | eu
sector: string         // Technology, Finance, Energy...
currency: string       // USD | EUR
ibkr_symbol: string    // IBKR-specific symbol if different
ibkr_exchange: string  // SMART | NASDAQ | BME | XETRA
gap_threshold_pct: float  // per-symbol override (optional)
active: bool           // false = excluded from scans
tags: list[string]     // ['sp500', 'mag7', 'growth']
added_at: timestamp
notes: string


# 3. Strategy Library
Each strategy is a versioned YAML blueprint. The Strategy Library is the collection of all available strategies. Strategies define when to enter, when to exit, and how to manage risk — not how to analyze (that is the agents' job).

## 3.1 Initial Strategy Set
### Strategy 1: gap_momentum_up


### Strategy 2: mean_reversion_gap


### Strategy 3: gap_continuation


### Strategy 4: sentiment_driven


### Strategy 5: gap_etf_momentum



# 4. Signal System
QITP operates a multi-signal scoring system. Each agent produces a signal. Signals are combined into a composite score that drives the Portfolio Recommender's final recommendation.

## 4.1 Signal Hierarchy

## 4.2 Composite Score Formula

## 4.3 Macro Alignment Override
When macro conditions are 'risk_off', all momentum and sentiment strategies are blocked regardless of individual scores. This is a hard override, not a weight adjustment.
risk_off triggers: VIX > 30, Fear & Greed < 20, SPY gap down > 2%
risk_on: VIX < 20, Fear & Greed > 60, no major macro event within 48h
neutral: everything else — strategies run normally but with reduced position sizes (50% of normal)


# 5. Risk Engine Specification
The Risk Engine is independent of agent reasoning. Agents make recommendations. The Risk Engine decides if they are safe to execute. No agent can override Risk Engine limits. Rules are configurable but cannot be disabled in live mode.

## 5.1 Portfolio-Level Risk Rules

## 5.2 Trailing Stop Manager
All positions opened by QITP must have a trailing stop. The Trailing Stop Manager runs every 15 minutes during market hours to update stop levels as price moves.
Long positions: trailing stop ratchets UP when price increases. Never moves down.
Short positions: trailing stop ratchets DOWN when price decreases. Never moves up.
Stop type: ATR-based (default) or percentage (configurable per strategy)
Implementation: IBKR native trailing stop orders — not managed externally
EventBridge rule: every 15 minutes Mon-Fri 09:00-22:00 CET (covers both EU and US market hours)

## 5.3 CNMV Regulatory Compliance (Spain)
QITP operates from Spain under CNMV (Comision Nacional del Mercado de Valores) oversight via IBKR. Key constraints:
ESMA CFD leverage limits: max 2:1 for crypto, 5:1 for indices, 10:1 for major forex, 20:1 for major indices, 30:1 for major forex pairs — enforced at Risk Engine level
MiFID II best execution: all orders logged with timestamp, venue, price, rationale
Short selling restrictions: CNMV may impose temporary short-sell bans on Spanish stocks — Risk Engine checks CNMV emergency measures API before approving short orders on IBEX35 symbols
Tax reporting: all closed positions logged for Spanish IRPF capital gains reporting (19-26% rate)


# 6. Interactive Brokers Integration

## 6.1 Account Configuration

## 6.2 Order Types Supported
Market Order (MKT) — used for immediate execution at open
Limit Order (LMT) — used for gap_continuation strategy (entry after confirmation window)
Trailing Stop Order (TRAIL) — attached to all positions, managed by Trailing Stop Manager
Stop Loss Order (STP) — used for fixed stop strategies (mean_reversion_gap)
QITP does NOT use: bracket orders, OCA groups, complex multi-leg options, or futures. Equity and ETF only for Phase 1.

## 6.3 Order Execution Flow (Live Mode)
Agent produces recommendation JSON (Portfolio Recommender)
Step Functions routes to CheckRiskLimits Lambda
Risk Engine validates all portfolio-level rules
If PASS: Step Functions pauses at TwoFactorGate (waitForTaskToken)
Telegram bot sends order details + approve/reject buttons to operator
Operator reviews on phone, approves with biometric unlock
Token released, Step Functions resumes
Order submitted to IBKR via ibkr-mcp place_order()
IBKR returns order_id — logged to audit_log DynamoDB
Trailing stop attached via set_trailing_stop()
Position added to active positions tracker



# 7. Weekly Execution Cycle

## 7.1 Schedule

## 7.2 Market Holiday Handling
EventBridge triggers always fire on schedule regardless of market hours
ValidateMarketCalendar Lambda checks market-data-mcp for trading day status before proceeding
If market is closed: workflow terminates at step 1 with status=skipped_holiday
Half-days (e.g. US Thanksgiving Friday): workflow runs with reduced US universe
EU and US holidays do not coincide — EU-only or US-only scans run when one market is closed


# 8. Performance Measurement

## 8.1 Strategy Performance Metrics
Every strategy is tracked independently. Metrics updated after each closed position:

## 8.2 Backtest vs Live Performance Tracking
A critical quality signal is the delta between backtest performance and live performance. Large deltas indicate overfitting, slippage mis-modelling, or execution issues.
Backtest results stored per strategy per date range
Live results stored per trade with full execution metadata (entry/exit price, slippage, commissions)
Monthly delta report auto-generated: backtest expected return vs actual return
Alert trigger: if live Sharpe ratio is less than 50% of backtest Sharpe for any strategy over a 4-week window


# 9. Data Pipeline Architecture

## 9.1 Historical Data Store
All historical data is stored in S3 as Parquet files. This is the backtest mode data source and the primary caching layer for paper/live modes.
S3 path: s3://qitp-data-{env}/historical/{symbol}/{year}/{month}.parquet
Schema: date, open, high, low, close, volume, adjusted_close, split_factor
Granularities stored: daily (primary), 1-hour (secondary), 5-minute (tertiary)
Initial load: minimum 5 years of daily data for all 100 watchlist symbols
Update schedule: daily at 23:00 CET — fetch previous day's data from Polygon.io
Gap feature store: pre-computed gap metrics stored separately for fast retrieval

## 9.2 Data Provider Priority

# 10. POC Validation Criteria (ROOT-63)
The POC runs in backtest mode only. No real money. No IBKR connection. Success criteria are binary pass/fail.



END OF DOCUMENT 5 — QITP Financial Platform Specification

| Version: 1.0 — March 2026 | Author: Nestor Colt | Status: DRAFT |
| --- | --- |
| Geography: Spain (EU) + US markets | Broker: Interactive Brokers (IBKR) |


| Gap Type | Definition | Typical Behavior | QITP Strategy |
| --- | --- | --- | --- |
| Breakaway Gap | Gaps out of consolidation/range on high volume | Continuation — strong directional move | gap_momentum_up / gap_momentum_down |
| Runaway Gap | Gaps in direction of existing trend on moderate volume | Continuation — trend acceleration | gap_continuation |
| Exhaustion Gap | Large gap near end of extended trend on high volume | Reversal — last buyers/sellers entering | mean_reversion_gap |
| Common Gap | Small gap (<1%) with no major catalyst | Fill within 1-3 days | Filtered out — below threshold |


| Gap Formula
gap_pct = ((monday_open - friday_close) / friday_close) * 100
Positive = gap up (bullish bias). Negative = gap down (bearish bias).
abs(gap_pct) is used for threshold filtering (direction-agnostic filter). |
| --- |


| Segment | Count | Examples | Rationale |
| --- | --- | --- | --- |
| US Large Cap (S&P500) | 30 | AAPL, NVDA, MSFT, TSLA, AMZN | Highest liquidity, most gap opportunities |
| US Growth / Tech | 15 | META, GOOGL, CRM, SNOW, PLTR | High volatility, frequent significant gaps |
| Spanish IBEX35 | 20 | SAN, BBVA, ITX, REP, TEF | Home market, operator expertise, EU context |
| EU Blue Chip | 10 | ASML, SAP, MC.PA, SIE.DE, LVMH | European exposure, different session dynamics |
| US Sector ETFs | 15 | XLK, XLF, XLE, XLV, XLI, ARKK | Sector rotation signals, lower single-stock risk |
| Broad Market ETFs | 5 | SPY, QQQ, IWM, EFA, VWO | Market-wide context, macro positioning |
| Thematic ETFs | 5 | BOTZ, ICLN, DRIV, HERO, CLOU | Emerging themes, higher beta |


| Intent
Buy gap-up symbols where gap is driven by genuine catalyst (earnings beat, analyst upgrade, product launch) confirmed by above-average volume. Ride the momentum through the week with a trailing stop. |
| --- |


| Parameter | Value |
| --- | --- |
| Entry Condition | gap_pct >= +2.0% AND volume_ratio >= 1.5 AND sentiment_score >= 0.6 AND macro_alignment != 'risk_off' |
| Entry Timing | Market open (09:30 ET / 09:00 CET) — first 15 minutes |
| Position Size | Risk 1% of portfolio NAV per trade (Kelly-inspired, conservative) |
| Trailing Stop | 3% ATR-based from entry — ratchets up, never down |
| Take Profit | None — let trailing stop close the trade |
| Max Holding | 5 trading days (close by Friday) |
| Exit Override | Close if sentiment_score drops below 0.3 on subsequent days |
| Asset Types | Stocks only (not ETFs — ETFs use gap_etf_momentum) |


| Intent
Fade large gaps (>5%) that occur on low volume or without a genuine fundamental catalyst. Markets statistically revert on uncatalyzed large gaps within 1-2 trading days. |
| --- |


| Parameter | Value |
| --- | --- |
| Entry Condition | abs(gap_pct) >= 5.0% AND volume_ratio < 1.2 AND no_earnings_within_7_days AND sentiment_score < 0.4 (for gap up) or > 0.6 (for gap down) |
| Direction | Gap up: short. Gap down: long. (Note: EU short-sell rules apply — check ESMA regulations per symbol) |
| Position Size | 0.5% of portfolio NAV (smaller — counter-trend is higher risk) |
| Stop Loss | Fixed 2% from entry (not trailing — reversion trade needs tight stop) |
| Take Profit | Target: 50% gap fill |
| Max Holding | 2 trading days |
| Blacklist | Never apply to symbols within 7 days of earnings announcement |


| Intent
Enter in the direction of the gap after the first 30 minutes confirm the move is holding. Reduces entry risk by waiting for confirmation versus jumping in at open. |
| --- |


| Parameter | Value |
| --- | --- |
| Entry Condition | gap_pct >= +2.0% AND price at 10:00 ET still within 0.5% of open AND volume in first 30min >= 40% of average daily volume |
| Entry Timing | 10:00 ET / 10:00 CET (30 min confirmation window) |
| Position Size | 1% of portfolio NAV |
| Trailing Stop | 2.5% from entry |
| Max Holding | 3 trading days |


| Intent
Pure sentiment play — no gap required. When sentiment score is extremely high or low (>0.85 or <0.15) with analyst consensus alignment, take a small position in the sentiment direction. |
| --- |


| Parameter | Value |
| --- | --- |
| Entry Condition (Long) | sentiment_score >= 0.85 AND analyst_consensus = 'strong_buy' AND no gap filter required |
| Entry Condition (Short) | sentiment_score <= 0.15 AND analyst_consensus = 'sell' / 'strong_sell' |
| Position Size | 0.5% of portfolio NAV (pure sentiment = smaller size) |
| Trailing Stop | 4% (wider — sentiment moves can be volatile) |
| Max Holding | 5 trading days |
| Runs | Monday + Thursday (twice weekly for this strategy only) |


| Intent
Simplified gap_momentum for ETFs. ETFs have tighter spreads, no earnings risk, and better liquidity. Use slightly different parameters optimized for ETF characteristics. |
| --- |


| Parameter | Value |
| --- | --- |
| Entry Condition | gap_pct >= +1.5% (lower threshold for ETFs) AND volume_ratio >= 1.3 AND macro_alignment = 'risk_on' |
| Position Size | 1.5% of portfolio NAV (larger — lower single-name risk) |
| Trailing Stop | 2% (tighter — ETFs are less volatile per unit) |
| Max Holding | 5 trading days |


| Signal | Source Agent | Weight (default) | Description |
| --- | --- | --- | --- |
| Gap Score | Gap Detection Agent | 35% | Normalized gap size, volume ratio, gap type classification |
| Sentiment Score | Sentiment Agent | 25% | Composite of news (40%), analyst consensus (40%), social (20%) |
| Technical Score | Technical Agent (future) | 20% | RSI, MACD, Bollinger Band position, trend alignment |
| ML Prediction | ML Agent (Phase 2) | 20% | SageMaker model confidence score (Phase 2 only) |
| Macro Alignment | Sentiment Agent | Override | risk_on / risk_off / neutral — can block entry regardless of other scores |


| Composite Score Calculation
composite_score = (gap_score * 0.35) + (sentiment_score * 0.25) + (technical_score * 0.20) + (ml_confidence * 0.20)

Phase 1 (no ML): composite_score = (gap_score * 0.45) + (sentiment_score * 0.35) + (technical_score * 0.20)

Threshold for recommendation: composite_score >= 0.65
High conviction threshold: composite_score >= 0.80 (larger position size) |
| --- |


| Rule | Default Value | Behavior on Violation |
| --- | --- | --- |
| Max open positions | 5 | Block new orders until position count drops |
| Max position size (% NAV) | 20% | Order rejected: RiskViolation.POSITION_TOO_LARGE |
| Max sector concentration | 40% | Order rejected if sector would exceed limit |
| Daily loss circuit breaker | -3% portfolio | Halt ALL trading for 24h, Telegram alert sent |
| Drawdown circuit breaker | -10% from peak NAV | Halt ALL trading, manual resume required |
| Trailing stop mandatory | Yes | All system-opened positions must have trailing stop |
| Naked shorts allowed | No (default) | Short orders rejected unless flag explicitly enabled |
| Max leverage (EU CFDs) | ESMA limits | CFD orders exceeding ESMA leverage caps rejected |


| Parameter | Value |
| --- | --- |
| Account Type | Individual IBKR Pro (Spain-based) |
| Base Currency | EUR (Spanish operator) |
| Markets | EU (BME, XETRA, Euronext) + US (NASDAQ, NYSE, BATS) |
| Paper Account | Separate IBKR paper account for paper mode |
| API Method | IB Client Portal API (REST) — TBD in ADR-001 |
| Connection | IBKR Gateway container — persistent, auto-reconnect |
| Market Data | IBKR real-time subscription (Level 1) |
| Historical Data | IBKR Historical Data API (supplemented by Polygon.io) |


| Critical Safety Rule
No order ever reaches IBKR without passing: (1) Risk Engine PASS, (2) 2FA human approval. These are sequential, not parallel. Either failure = order never submitted. This is non-negotiable and not configurable in live mode. |
| --- |


| Time (CET) | Trigger | Action |
| --- | --- | --- |
| Friday 17:30 | EventBridge | Record Friday close prices for all watchlist symbols — store to S3/DynamoDB |
| Friday 18:00 | EventBridge | Weekly P&L report generated and sent via Telegram |
| Monday 08:30 | EventBridge | Main pipeline trigger — Step Functions weekly workflow starts |
| Monday 09:00 | Market open | EU markets open — gap confirmation window begins for EU symbols |
| Monday 15:30 | Market open | US markets open — gap confirmation window for US symbols |
| Daily 15:00 | EventBridge | Trailing Stop Manager runs (covers both EU and US sessions) |
| Daily 22:00 | EventBridge | Daily position check — flag positions approaching max holding days |
| Thursday 14:00 | EventBridge | sentiment_driven strategy re-evaluation (runs twice weekly) |


| Metric | Definition |
| --- | --- |
| Total Return % | Sum of all closed P&L / initial NAV |
| Annualized Return % | Total Return normalized to 365-day equivalent |
| Win Rate % | # winning trades / # total trades |
| Profit Factor | Gross profit / Gross loss (>1 = net profitable) |
| Sharpe Ratio | (Strategy return - risk-free rate) / Strategy std dev |
| Sortino Ratio | Like Sharpe but only penalizes downside volatility |
| Max Drawdown % | Largest peak-to-trough NAV decline |
| Avg Holding Days | Average number of trading days per position |
| Avg Win / Avg Loss | Expectancy ratio — should be > 1.5 for viability |
| Calmar Ratio | Annualized Return / Max Drawdown — composite quality metric |


| Provider | Data Type | Cost | Use |
| --- | --- | --- | --- |
| IBKR Historical API | OHLCV, all markets | Free with account | Primary for live + paper |
| Polygon.io (Starter) | US OHLCV, news | $29/month | US historical, news sentiment |
| Yahoo Finance (yfinance) | OHLCV, basic fundamentals | Free | POC fallback only |
| Alpha Vantage | OHLCV, fundamentals, forex | Free tier + paid | EU market supplement |


| # | Criterion | Test Date | Pass Condition |
| --- | --- | --- | --- |
| 1 | Gap Detection produces correct ranked_gaps JSON | 2024-11-04 | Manual verification of top 10 gaps |
| 2 | Sentiment scores directionally correct | 2024-11-04 | 3 known news events verified |
| 3 | gap_momentum_up strategy backtest produces Sharpe ratio | 2024 full year | Sharpe > 0 (any positive) |
| 4 | Portfolio Recommender produces valid JSON | 2024-11-04 | Schema validation passes |
| 5 | All artifacts retrievable via signed URL | Any run | URL accessible within 30s |
| 6 | Equity curve renders in Claude UI | Any backtest run | Chart visible in conversation |
| 7 | Zero hardcoded prompts in agent code | Code review | Grep finds no prompt strings in agent files |
| 8 | Execution mode switching works | Any run | Same code runs backtest and paper by env var only |
| 9 | Full pipeline runtime < 10 minutes | Any run | Step Functions execution history |
| 10 | No live API calls in backtest mode | Any run | Zero IBKR/Polygon live calls in CloudWatch |
