#!/usr/bin/env bash
# Domain contamination scanner
# Usage:
#   ./scripts/domain-scan.sh                  # scan with default terms
#   ./scripts/domain-scan.sh trading risk     # add extra terms to scan
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Base terms (always scanned) ──────────────────────────────────────
# Sourced from tccw-qitp domain vocabulary. Case-insensitive.
TERMS=(
  # ─── Project/org branding ───
  qitp
  tccw
  "The.Cloud.Clock.Work"
  "/home/iamroot"

  # ─── Trading domain — core concepts ───
  trading
  backtest
  paper
  broker
  ibkr
  ohlcv
  ticker
  portfolio
  watchlist
  trailing_stop
  drawdown
  equity_curve
  sharpe
  sortino
  calmar
  slippage
  commission
  nav
  pnl
  trade
  trades

  # ─── Trading domain — instruments & markets ───
  forex
  cfd
  etf
  isin
  dividend
  earnings
  spread
  eur
  usd
  currency
  exchange

  # ─── Trading domain — signals & strategies ───
  sentiment
  sentiment_score
  market-data
  market_data
  bullish
  bearish
  momentum
  reversion
  breakout
  continuation
  exhaustion
  gap_pct
  gap_momentum
  gap
  volume_ratio
  rsi
  macd
  bollinger
  atr
  sma
  ema
  composite
  signal
  neutral

  # ─── Trading domain — orders & execution ───
  place_order
  order_type
  order_id
  order_details
  limit_price
  stop_price
  short_sell
  trailing_stop
  position_size
  buy
  sell
  short
  long
  side
  quantity
  fill

  # ─── Trading domain — symbols & tickers ───
  AAPL
  SPY
  TSLA
  symbol
  symbols

  # ─── Trading domain — risk & portfolio ───
  risk
  risk_config
  risk_state
  circuit_breaker
  breaker
  threshold_pct
  sector
  concentration
  leverage
  margin
  initial_capital
  nav
  position
  positions

  # ─── Trading domain — time/schedule ───
  market_calendar
  trading_day
  monday
  weekly_analysis

  # ─── Trading domain — backtest/simulation ───
  equity_curve
  strategy
  strategy_id
  walk_forward
  win_rate
  profit_factor
  holding_days
  entry_price
  exit_price
  bars
  bar
  candle

  # ─── Trading domain — tax & reporting ───
  tax
  irpf
  cost_basis
  capital_gains
  tax_lot

  # ─── Regulatory ───
  cnmv
  esma
  mifid
  "RTS 25"

  # ─── Auth — domain-specific implementations ───
  telegram
  yubikey
  webauthn
  biometric
  2fa
  twofa
  approval
  approval_id
  task_token

  # ─── QITP module names (should never appear) ───
  qitp_agents
  qitp_simulation
  qitp_risk_engine
  qitp_mcp_market_data
  qitp_mcp_ibkr
  qitp_mcp_backtest
  qitp_mcp_sentiment
  qitp_mcp_technical
  qitp_mcp_charting
  qitp_mcp_2fa
  qitp_mcp_ml_predict

  # ─── QITP agent/MCP names ───
  gap-detector
  sentiment-analyzer
  strategy-evaluator
  portfolio-recommender
  technical-analyzer
  ml-predictor
  watchlist-screener
  tax-reporter
  market-data-mcp
  sentiment-mcp
  backtest-mcp
  ibkr-mcp
  charting-mcp
  twofa-mcp
  ml-predict-mcp
  technical-mcp

  # ─── Chart/rendering domain ───
  recharts
  candlestick
  chart

  # ─── Broker-specific ───
  interactive_brokers
  ib_gateway
  tws
)

# ── Append CLI args ──────────────────────────────────────────────────
for arg in "$@"; do
  TERMS+=("$arg")
done

# ── Build grep pattern ──────────────────────────────────────────────
pattern=""
for t in "${TERMS[@]}"; do
  [[ -n "$pattern" ]] && pattern+="\|"
  pattern+="$t"
done

# ── Excludes ─────────────────────────────────────────────────────────
EXCLUDES=(
  --exclude-dir=__pycache__
  --exclude-dir=.git
  --exclude-dir=cdk.out
  --exclude-dir=.mypy_cache
  --exclude-dir=node_modules
  --exclude-dir=dist
  --exclude-dir=.scannerwork
  --exclude="CLAUDE.md"
  --exclude="domain-scan.sh"
  --exclude="*.lock"
)

# ── Run ──────────────────────────────────────────────────────────────
echo "═══ Domain Scan: ${REPO_ROOT} ═══"
echo "Terms: ${TERMS[*]}"
echo "────────────────────────────────────"

hits=$(grep -rni "${pattern}" "${REPO_ROOT}/" \
  --include="*.py" \
  --include="*.yaml" \
  --include="*.yml" \
  --include="*.toml" \
  --include="*.md" \
  --include="*.txt" \
  --include="*.json" \
  --include="*.properties" \
  --include="*.cfg" \
  "${EXCLUDES[@]}" \
  2>/dev/null || true)

if [[ -z "$hits" ]]; then
  echo "CLEAN — zero hits"
  exit 0
fi

count=$(echo "$hits" | wc -l)
echo "$hits"
echo "────────────────────────────────────"
echo "Total: ${count} hits"
