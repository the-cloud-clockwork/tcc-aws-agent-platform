#!/usr/bin/env bash
# Domain contamination scanner
# Usage:
#   ./scripts/domain-scan.sh          # HARD terms only (must be zero)
#   ./scripts/domain-scan.sh --full   # HARD + SOFT terms (context-dependent)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── HARD terms (always a violation — must be ZERO) ─────────────────────
HARD_TERMS=(
  # Project/org branding
  qitp
  tccw
  "The.Cloud.Clock.Work"
  "/home/iamroot"

  # Broker-specific
  ibkr
  interactive_brokers
  ib_gateway
  tws

  # Regulatory
  cnmv
  esma
  mifid
  "RTS 25"
  irpf

  # Domain data format
  ohlcv

  # Specific tickers (domain examples)
  AAPL
  SPY
  TSLA

  # Auth — domain-specific implementations
  telegram
  yubikey
  webauthn
  biometric
  twofa
  2fa

  # Domain-specific field names
  trailing_stop
  gap_pct
  gap_momentum
  watchlist
  equity_curve
  holding_days
  volume_ratio
  cost_basis
  capital_gains
  tax_lot
  weekly_analysis
  trading_day
  market_calendar
  short_sell
  position_size

  # QITP agent/MCP names
  gap-detector
  sentiment-analyzer
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

  # QITP module names
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

  # Chart/rendering domain
  recharts
  candlestick

  # Domain strategy names
  gap_momentum_up
  gap_momentum_down
  mean_reversion
  breakout_continuation
  exhaustion_reversal

  # Domain-specific config
  "qitp-artifacts"
  "qitp-historical"
  risk_state
  risk_config
  strategy_registry

  # Ratios specific to trading
  sharpe
  sortino
  calmar
  slippage
  profit_factor
  win_rate
  walk_forward
  entry_price
  exit_price
  initial_capital

  # Tax
  tax
)

# ── SOFT terms (context-dependent — only with --full) ──────────────────
SOFT_TERMS=(
  symbol
  symbols
  strategy
  strategy_id
  bar
  bars
  candle
  risk
  position
  positions
  trade
  trades
  signal
  short
  long
  gap
  momentum
  reversion
  breakout
  continuation
  exhaustion
  sector
  currency
  exchange
  paper
  spread
  margin
  composite
  neutral
  quantity
  buy
  sell
  side
  fill
  leverage
  backtest
  sentiment
  sentiment_score
  portfolio
  broker
  trading
  market-data
  market_data
  ticker
  bullish
  bearish
  order_type
  order_id
  order_details
  limit_price
  stop_price
  place_order
  circuit_breaker
  breaker
  threshold_pct
  concentration
  nav
  pnl
  drawdown
  commission
  approval
  approval_id
  task_token
  chart
  forex
  cfd
  etf
  isin
  dividend
  earnings
  eur
  usd
  rsi
  macd
  bollinger
  atr
  sma
  ema
  volume
  monday
)

# ── Parse flags ────────────────────────────────────────────────────────
FULL=false
EXTRA_TERMS=()
for arg in "$@"; do
  if [[ "$arg" == "--full" ]]; then
    FULL=true
  else
    EXTRA_TERMS+=("$arg")
  fi
done

# ── Build term list ────────────────────────────────────────────────────
TERMS=("${HARD_TERMS[@]}")
if $FULL; then
  TERMS+=("${SOFT_TERMS[@]}")
fi
TERMS+=("${EXTRA_TERMS[@]}")

# ── Build grep pattern ────────────────────────────────────────────────
pattern=""
for t in "${TERMS[@]}"; do
  [[ -n "$pattern" ]] && pattern+="\|"
  pattern+="$t"
done

# ── Excludes ──────────────────────────────────────────────────────────
EXCLUDES=(
  --exclude-dir=__pycache__
  --exclude-dir=.git
  --exclude-dir=cdk.out
  --exclude-dir=.mypy_cache
  --exclude-dir=node_modules
  --exclude-dir=dist
  --exclude-dir=.scannerwork
  --exclude-dir=.pytest_cache
  --exclude-dir=lambda/agents/dist
  --exclude="CLAUDE.md"
  --exclude="domain-scan.sh"
  --exclude="*.lock"
  --exclude="sonar-project.properties"
  --exclude="publish.yml"
)

# ── Run ───────────────────────────────────────────────────────────────
MODE="HARD only"
$FULL && MODE="HARD + SOFT (--full)"

echo "═══ Domain Scan: ${REPO_ROOT} ═══"
echo "Mode: ${MODE}"
echo "Terms: ${#TERMS[@]} patterns"
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
files=$(echo "$hits" | cut -d: -f1 | sort -u | wc -l)
echo "$hits"
echo "────────────────────────────────────"
echo "Total: ${count} hits across ${files} files"
