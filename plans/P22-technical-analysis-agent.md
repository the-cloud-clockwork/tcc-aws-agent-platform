# P22 — Technical Analysis Agent + MCP

## Objective
Build `technical-mcp`: an MCP server providing technical analysis indicators (RSI, MACD, Bollinger Bands, ATR, moving averages, trend alignment, support/resistance), and the Technical Analysis Agent that fills the 20% `technical_score` weight in the composite scoring formula. Currently referenced in the composite but never built.

Composite formula: `composite = gap(35%) + sentiment(25%) + technical(20%) + ml(20%)`

## Plane Tickets
ROOT-68

## Target Repos
- `~/dev/tccw-qitp-mcp-technical` (NEW — MCP server)
- `~/dev/tccw-qitp-agents` (existing — agent handler addition)

## Dependencies
P05 (market-data-mcp for OHLCV), P02 (core schemas for BlueprintLoader, ExecutionMode)

## Repo Structure (MCP)
```
tccw-qitp-mcp-technical/
├── src/
│   └── qitp_mcp_technical/
│       ├── __init__.py
│       ├── server.py              # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── momentum.py        # compute_rsi, compute_macd
│       │   ├── volatility.py      # compute_bollinger_bands, compute_atr
│       │   ├── trend.py           # compute_moving_averages, compute_trend_alignment
│       │   ├── levels.py          # compute_support_resistance
│       │   └── composite.py       # compute_technical_score (composite 0-100)
│       ├── indicators/
│       │   ├── __init__.py
│       │   ├── rsi.py             # RSI calculation (14-period default)
│       │   ├── macd.py            # MACD (12,26,9) + signal + histogram
│       │   ├── bollinger.py       # Bollinger Bands (20,2)
│       │   ├── atr.py             # Average True Range
│       │   ├── moving_avg.py      # SMA, EMA, WMA with configurable periods
│       │   ├── trend.py           # Trend alignment (multi-timeframe)
│       │   └── support_resistance.py # Pivot points, local min/max detection
│       ├── schemas.py             # TechnicalIndicatorResult, TechnicalScore, etc.
│       └── scoring.py             # Technical score computation logic (sub-weights)
├── tests/
│   ├── conftest.py
│   ├── test_rsi.py
│   ├── test_macd.py
│   ├── test_bollinger.py
│   ├── test_trend.py
│   ├── test_scoring.py
│   └── fixtures/
│       └── sample_ohlcv.json
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Agent Handler (in tccw-qitp-agents)
```
tccw-qitp-agents/
├── blueprints/
│   └── agents/
│       └── technical_analyzer.yaml
├── src/
│   └── qitp_agents/
│       └── technical_analyzer/
│           ├── __init__.py
│           └── handler.py
└── tests/
    └── unit/
        └── test_technical_analyzer.py
```

---

## Full Inline Code

---

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-technical"
version = "0.1.0"
description = "QITP Technical Analysis MCP Server — RSI, MACD, Bollinger, ATR, trend, support/resistance, composite scoring"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0",
    "numpy>=1.26",
    "pandas>=2.1",
    "httpx>=0.27",
    "uvicorn>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
]

[project.scripts]
technical-mcp = "qitp_mcp_technical.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_technical"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### `src/qitp_mcp_technical/__init__.py`

```python
"""QITP Technical Analysis MCP Server."""

__version__ = "0.1.0"
```

---

### `src/qitp_mcp_technical/schemas.py`

```python
"""Shared data schemas for technical analysis MCP server."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Bar(BaseModel):
    """Single OHLCV bar (lightweight copy — avoids hard dependency on market-data-mcp)."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class RSIResult(BaseModel):
    """RSI indicator result."""

    symbol: str
    date: date
    period: int
    value: float = Field(..., ge=0.0, le=100.0)
    signal: Literal["overbought", "oversold", "neutral"]
    description: str


class MACDResult(BaseModel):
    """MACD indicator result."""

    symbol: str
    date: date
    fast_period: int
    slow_period: int
    signal_period: int
    macd_line: float
    signal_line: float
    histogram: float
    crossover: Literal["bullish", "bearish", "none"]
    histogram_direction: Literal["expanding", "contracting"]
    description: str


class BollingerResult(BaseModel):
    """Bollinger Bands indicator result."""

    symbol: str
    date: date
    period: int
    std_dev: float
    upper_band: float
    middle_band: float
    lower_band: float
    percent_b: float  # (close - lower) / (upper - lower)
    bandwidth: float  # (upper - lower) / middle
    squeeze: bool  # True if bandwidth is in lowest 20% of recent history
    signal: Literal["near_upper", "near_lower", "mid_range", "squeeze"]
    description: str


class ATRResult(BaseModel):
    """Average True Range indicator result."""

    symbol: str
    date: date
    period: int
    value: float
    atr_pct: float  # ATR as percentage of closing price
    volatility_level: Literal["low", "moderate", "high"]
    description: str


class MovingAverageResult(BaseModel):
    """Moving average result for a single period."""

    ma_type: Literal["SMA", "EMA", "WMA"]
    period: int
    value: float


class MovingAveragesResult(BaseModel):
    """Moving averages result with cross detection."""

    symbol: str
    date: date
    current_price: float
    averages: list[MovingAverageResult]
    golden_cross: bool  # Short MA crosses above long MA
    death_cross: bool   # Short MA crosses below long MA
    price_vs_ma200: Literal["above", "below", "at"]
    description: str


class TrendAlignmentResult(BaseModel):
    """Multi-timeframe trend alignment result."""

    symbol: str
    date: date
    daily_trend: Literal["bullish", "bearish", "neutral"]
    weekly_trend: Literal["bullish", "bearish", "neutral"]
    monthly_trend: Literal["bullish", "bearish", "neutral"]
    alignment_score: float = Field(..., ge=0.0, le=1.0)  # 1.0 = all aligned
    aligned: bool  # True if all timeframes agree
    dominant_direction: Literal["bullish", "bearish", "mixed"]
    description: str


class SupportResistanceLevel(BaseModel):
    """A single support or resistance level."""

    price: float
    level_type: Literal["support", "resistance"]
    strength: Literal["weak", "moderate", "strong"]
    source: Literal["pivot", "local_extrema", "moving_average"]
    touches: int = 1  # Number of times price has touched this level


class SupportResistanceResult(BaseModel):
    """Support and resistance levels result."""

    symbol: str
    date: date
    current_price: float
    levels: list[SupportResistanceLevel]
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    support_distance_pct: float | None = None  # Distance to nearest support as % of price
    resistance_distance_pct: float | None = None  # Distance to nearest resistance as % of price
    signal: Literal["near_support", "near_resistance", "mid_range"]
    description: str


class TechnicalScore(BaseModel):
    """Composite technical analysis score (0-100)."""

    symbol: str
    date: date
    composite_score: float = Field(..., ge=0.0, le=100.0)
    rsi_component: float = Field(..., ge=0.0, le=100.0)  # Sub-score before weighting
    macd_component: float = Field(..., ge=0.0, le=100.0)
    bollinger_component: float = Field(..., ge=0.0, le=100.0)
    trend_component: float = Field(..., ge=0.0, le=100.0)
    sr_component: float = Field(..., ge=0.0, le=100.0)
    signal: Literal["strong_buy", "buy", "neutral", "sell", "strong_sell"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    description: str

    # Sub-weights used for transparency
    weights: dict[str, float] = Field(default_factory=lambda: {
        "rsi": 0.20,
        "macd": 0.20,
        "bollinger": 0.15,
        "trend": 0.25,
        "sr": 0.20,
    })
```

---

### `src/qitp_mcp_technical/indicators/__init__.py`

```python
"""Technical indicator calculation implementations."""
```

---

### `src/qitp_mcp_technical/indicators/rsi.py`

```python
"""RSI (Relative Strength Index) calculation.

Formula:
    RSI = 100 - (100 / (1 + RS))
    RS  = avg_gain / avg_loss  (Wilder's smoothing)

Default period: 14.
Overbought threshold: 70. Oversold threshold: 30.
"""

from __future__ import annotations

import numpy as np

from qitp_mcp_technical.schemas import Bar


def compute_rsi_values(bars: list[Bar], period: int = 14) -> list[float | None]:
    """Compute RSI for a series of bars.

    Returns a list of RSI values aligned with the input bars.
    The first `period` values will be None (insufficient data).

    Args:
        bars: OHLCV bars sorted by date ascending.
        period: RSI lookback period (default 14).

    Returns:
        List of RSI values (0-100) or None for insufficient data.
    """
    if len(bars) < period + 1:
        return [None] * len(bars)

    closes = np.array([b.close for b in bars], dtype=np.float64)
    deltas = np.diff(closes)

    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    result: list[float | None] = [None] * (period)

    # Initial average using simple mean of first `period` changes
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(round(100.0 - (100.0 / (1.0 + rs)), 4))

    # Wilder's smoothing for subsequent values
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(round(100.0 - (100.0 / (1.0 + rs)), 4))

    return result


def classify_rsi(value: float, overbought: float = 70.0, oversold: float = 30.0) -> str:
    """Classify RSI value into signal category.

    Args:
        value: RSI value (0-100).
        overbought: Overbought threshold (default 70).
        oversold: Oversold threshold (default 30).

    Returns:
        "overbought", "oversold", or "neutral".
    """
    if value >= overbought:
        return "overbought"
    elif value <= oversold:
        return "oversold"
    return "neutral"
```

---

### `src/qitp_mcp_technical/indicators/macd.py`

```python
"""MACD (Moving Average Convergence Divergence) calculation.

Standard parameters: fast=12, slow=26, signal=9.

MACD Line = EMA(fast) - EMA(slow)
Signal Line = EMA(signal) of MACD Line
Histogram = MACD Line - Signal Line
"""

from __future__ import annotations

import numpy as np

from qitp_mcp_technical.schemas import Bar


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Compute EMA using the standard multiplier 2/(period+1).

    Returns an array the same length as input. First `period-1` values
    are computed with progressive EMA (not NaN) for usability.
    """
    multiplier = 2.0 / (period + 1)
    ema = np.empty_like(values)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = values[i] * multiplier + ema[i - 1] * (1 - multiplier)
    return ema


def compute_macd_values(
    bars: list[Bar],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Compute MACD line, signal line, and histogram.

    Args:
        bars: OHLCV bars sorted by date ascending.
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal EMA period (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram) lists aligned with bars.
        Values are None where insufficient data exists.
    """
    min_required = slow_period + signal_period
    if len(bars) < min_required:
        n = len(bars)
        return [None] * n, [None] * n, [None] * n

    closes = np.array([b.close for b in bars], dtype=np.float64)

    ema_fast = _ema(closes, fast_period)
    ema_slow = _ema(closes, slow_period)
    macd_raw = ema_fast - ema_slow

    signal_raw = _ema(macd_raw, signal_period)
    histogram_raw = macd_raw - signal_raw

    # Mark first slow_period-1 values as None (unreliable)
    macd_list: list[float | None] = []
    signal_list: list[float | None] = []
    hist_list: list[float | None] = []

    for i in range(len(bars)):
        if i < slow_period - 1:
            macd_list.append(None)
            signal_list.append(None)
            hist_list.append(None)
        elif i < slow_period - 1 + signal_period - 1:
            macd_list.append(round(float(macd_raw[i]), 4))
            signal_list.append(None)
            hist_list.append(None)
        else:
            macd_list.append(round(float(macd_raw[i]), 4))
            signal_list.append(round(float(signal_raw[i]), 4))
            hist_list.append(round(float(histogram_raw[i]), 4))

    return macd_list, signal_list, hist_list


def detect_crossover(
    macd_values: list[float | None],
    signal_values: list[float | None],
) -> str:
    """Detect MACD crossover at the most recent point.

    Returns:
        "bullish" if MACD crossed above signal, "bearish" if below, "none" otherwise.
    """
    # Need at least 2 valid points
    valid = [
        (m, s) for m, s in zip(macd_values[-2:], signal_values[-2:])
        if m is not None and s is not None
    ]
    if len(valid) < 2:
        return "none"

    prev_m, prev_s = valid[-2]
    curr_m, curr_s = valid[-1]

    if prev_m <= prev_s and curr_m > curr_s:
        return "bullish"
    elif prev_m >= prev_s and curr_m < curr_s:
        return "bearish"
    return "none"


def detect_histogram_direction(hist_values: list[float | None]) -> str:
    """Determine if histogram is expanding or contracting.

    Returns "expanding" if absolute histogram is growing, "contracting" otherwise.
    """
    valid = [h for h in hist_values[-3:] if h is not None]
    if len(valid) < 2:
        return "contracting"

    return "expanding" if abs(valid[-1]) > abs(valid[-2]) else "contracting"
```

---

### `src/qitp_mcp_technical/indicators/bollinger.py`

```python
"""Bollinger Bands calculation.

Upper Band = SMA(period) + (std_dev_multiplier * StdDev)
Lower Band = SMA(period) - (std_dev_multiplier * StdDev)
%B = (Close - Lower) / (Upper - Lower)
Bandwidth = (Upper - Lower) / Middle

Default: period=20, std_dev=2.0
"""

from __future__ import annotations

import numpy as np

from qitp_mcp_technical.schemas import Bar


def compute_bollinger_values(
    bars: list[Bar],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[
    list[float | None],  # upper
    list[float | None],  # middle (SMA)
    list[float | None],  # lower
    list[float | None],  # %B
    list[float | None],  # bandwidth
]:
    """Compute Bollinger Bands for a series of bars.

    Args:
        bars: OHLCV bars sorted by date ascending.
        period: SMA lookback period (default 20).
        std_dev: Standard deviation multiplier (default 2.0).

    Returns:
        Tuple of (upper, middle, lower, percent_b, bandwidth) lists.
        First `period-1` values are None.
    """
    if len(bars) < period:
        n = len(bars)
        return [None] * n, [None] * n, [None] * n, [None] * n, [None] * n

    closes = np.array([b.close for b in bars], dtype=np.float64)

    upper: list[float | None] = [None] * (period - 1)
    middle: list[float | None] = [None] * (period - 1)
    lower: list[float | None] = [None] * (period - 1)
    pct_b: list[float | None] = [None] * (period - 1)
    bw: list[float | None] = [None] * (period - 1)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        sma = float(np.mean(window))
        sd = float(np.std(window, ddof=0))  # Population std dev (standard for Bollinger)

        u = round(sma + std_dev * sd, 4)
        m = round(sma, 4)
        lo = round(sma - std_dev * sd, 4)

        upper.append(u)
        middle.append(m)
        lower.append(lo)

        band_range = u - lo
        if band_range > 0:
            pct_b.append(round((closes[i] - lo) / band_range, 4))
        else:
            pct_b.append(0.5)

        if m > 0:
            bw.append(round(band_range / m, 4))
        else:
            bw.append(0.0)

    return upper, middle, lower, pct_b, bw


def detect_squeeze(
    bandwidth_values: list[float | None],
    lookback: int = 120,
    threshold_percentile: float = 20.0,
) -> bool:
    """Detect Bollinger Band squeeze.

    A squeeze occurs when bandwidth is in the lowest percentile of recent history.

    Args:
        bandwidth_values: List of bandwidth values.
        lookback: How many periods of history to compare (default 120 = ~6 months).
        threshold_percentile: Percentile threshold for squeeze (default 20).

    Returns:
        True if current bandwidth is below the threshold percentile.
    """
    valid = [v for v in bandwidth_values[-lookback:] if v is not None]
    if len(valid) < 20:
        return False

    current = valid[-1]
    threshold = float(np.percentile(valid, threshold_percentile))
    return current <= threshold
```

---

### `src/qitp_mcp_technical/indicators/atr.py`

```python
"""Average True Range (ATR) calculation.

True Range = max(H-L, abs(H-Cprev), abs(L-Cprev))
ATR = Wilder's smoothed average of True Range over `period` bars.

Default period: 14.
"""

from __future__ import annotations

import numpy as np

from qitp_mcp_technical.schemas import Bar


def compute_true_range(bars: list[Bar]) -> list[float | None]:
    """Compute True Range for each bar.

    First bar returns None (no previous close available).

    Args:
        bars: OHLCV bars sorted by date ascending.

    Returns:
        List of True Range values aligned with bars.
    """
    if len(bars) < 2:
        return [None] * len(bars)

    result: list[float | None] = [None]

    for i in range(1, len(bars)):
        h = bars[i].high
        lo = bars[i].low
        c_prev = bars[i - 1].close

        tr = max(h - lo, abs(h - c_prev), abs(lo - c_prev))
        result.append(round(tr, 4))

    return result


def compute_atr_values(bars: list[Bar], period: int = 14) -> list[float | None]:
    """Compute ATR using Wilder's smoothing.

    Args:
        bars: OHLCV bars sorted by date ascending.
        period: ATR lookback period (default 14).

    Returns:
        List of ATR values aligned with bars. First `period` values are None.
    """
    tr_values = compute_true_range(bars)

    if len(bars) < period + 1:
        return [None] * len(bars)

    # Filter out the first None from TR
    valid_tr = [v for v in tr_values[1 : period + 1] if v is not None]
    if len(valid_tr) < period:
        return [None] * len(bars)

    result: list[float | None] = [None] * (period)

    # Initial ATR = simple average of first `period` true ranges
    atr = float(np.mean(valid_tr))
    result.append(round(atr, 4))

    # Wilder's smoothing for subsequent values
    for i in range(period + 1, len(bars)):
        tr = tr_values[i]
        if tr is None:
            result.append(result[-1])  # Carry forward
        else:
            atr = (atr * (period - 1) + tr) / period
            result.append(round(atr, 4))

    return result


def classify_volatility(atr_pct: float) -> str:
    """Classify ATR as percentage of price into volatility level.

    Args:
        atr_pct: ATR / close_price * 100.

    Returns:
        "low" (<1.5%), "moderate" (1.5-3%), "high" (>3%).
    """
    if atr_pct < 1.5:
        return "low"
    elif atr_pct < 3.0:
        return "moderate"
    return "high"
```

---

### `src/qitp_mcp_technical/indicators/moving_avg.py`

```python
"""Moving Average calculations — SMA, EMA, WMA.

Golden Cross: short-term MA crosses above long-term MA (bullish).
Death Cross: short-term MA crosses below long-term MA (bearish).
"""

from __future__ import annotations

import numpy as np

from qitp_mcp_technical.schemas import Bar


def compute_sma(closes: np.ndarray, period: int) -> list[float | None]:
    """Compute Simple Moving Average.

    Args:
        closes: Array of closing prices.
        period: SMA period.

    Returns:
        List of SMA values. First `period-1` values are None.
    """
    if len(closes) < period:
        return [None] * len(closes)

    result: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        result.append(round(float(np.mean(window)), 4))
    return result


def compute_ema(closes: np.ndarray, period: int) -> list[float | None]:
    """Compute Exponential Moving Average.

    Uses multiplier = 2 / (period + 1). Initial value = SMA of first `period` closes.

    Args:
        closes: Array of closing prices.
        period: EMA period.

    Returns:
        List of EMA values. First `period-1` values are None.
    """
    if len(closes) < period:
        return [None] * len(closes)

    multiplier = 2.0 / (period + 1)
    result: list[float | None] = [None] * (period - 1)

    # Seed with SMA of first `period` values
    sma_seed = float(np.mean(closes[:period]))
    result.append(round(sma_seed, 4))

    for i in range(period, len(closes)):
        prev = result[-1]
        ema_val = closes[i] * multiplier + prev * (1 - multiplier)
        result.append(round(float(ema_val), 4))

    return result


def compute_wma(closes: np.ndarray, period: int) -> list[float | None]:
    """Compute Weighted Moving Average.

    Weight = position (1 for oldest, `period` for newest).

    Args:
        closes: Array of closing prices.
        period: WMA period.

    Returns:
        List of WMA values. First `period-1` values are None.
    """
    if len(closes) < period:
        return [None] * len(closes)

    weights = np.arange(1, period + 1, dtype=np.float64)
    weight_sum = weights.sum()

    result: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        wma_val = float(np.dot(window, weights) / weight_sum)
        result.append(round(wma_val, 4))
    return result


def detect_cross(
    short_ma: list[float | None],
    long_ma: list[float | None],
) -> tuple[bool, bool]:
    """Detect golden cross and death cross at the most recent point.

    Args:
        short_ma: Short-term MA values.
        long_ma: Long-term MA values.

    Returns:
        Tuple of (golden_cross, death_cross) booleans.
    """
    valid = [
        (s, lo) for s, lo in zip(short_ma[-2:], long_ma[-2:])
        if s is not None and lo is not None
    ]
    if len(valid) < 2:
        return False, False

    prev_s, prev_l = valid[-2]
    curr_s, curr_l = valid[-1]

    golden = prev_s <= prev_l and curr_s > curr_l
    death = prev_s >= prev_l and curr_s < curr_l

    return golden, death
```

---

### `src/qitp_mcp_technical/indicators/trend.py`

```python
"""Multi-timeframe trend alignment.

Determines trend direction for daily, weekly, and monthly timeframes
using EMA crossovers (short EMA vs long EMA).

Daily:   EMA(10) vs EMA(50)
Weekly:  EMA(10) vs EMA(30)  (using weekly bars synthesized from daily)
Monthly: EMA(5) vs EMA(12)   (using monthly bars synthesized from daily)

Alignment score:
- All bullish = 1.0
- All bearish = 1.0 (direction captured separately)
- Mixed = 0.0 to 0.67 depending on agreement
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import numpy as np

from qitp_mcp_technical.schemas import Bar


def _determine_trend(short_ema: float, long_ema: float) -> Literal["bullish", "bearish", "neutral"]:
    """Determine trend from EMA comparison.

    Neutral band: within 0.1% of each other.
    """
    pct_diff = (short_ema - long_ema) / long_ema * 100 if long_ema != 0 else 0
    if pct_diff > 0.1:
        return "bullish"
    elif pct_diff < -0.1:
        return "bearish"
    return "neutral"


def _ema_last(values: np.ndarray, period: int) -> float:
    """Compute EMA and return only the last value."""
    if len(values) < period:
        return float(np.mean(values)) if len(values) > 0 else 0.0

    multiplier = 2.0 / (period + 1)
    ema = float(np.mean(values[:period]))
    for i in range(period, len(values)):
        ema = values[i] * multiplier + ema * (1 - multiplier)
    return ema


def synthesize_weekly_bars(daily_bars: list[Bar]) -> list[Bar]:
    """Convert daily bars to weekly bars (Monday-Friday grouping).

    Each weekly bar: open=Monday open, high=max(highs), low=min(lows),
    close=Friday close, volume=sum(volumes).
    """
    if not daily_bars:
        return []

    weeks: dict[str, list[Bar]] = {}
    for bar in daily_bars:
        # ISO week key: year-week
        iso = bar.date.isocalendar()
        key = f"{iso[0]}-{iso[1]:02d}"
        weeks.setdefault(key, []).append(bar)

    result: list[Bar] = []
    for key in sorted(weeks.keys()):
        week_bars = sorted(weeks[key], key=lambda b: b.date)
        result.append(Bar(
            date=week_bars[-1].date,  # Use last day as the week date
            open=week_bars[0].open,
            high=max(b.high for b in week_bars),
            low=min(b.low for b in week_bars),
            close=week_bars[-1].close,
            volume=sum(b.volume for b in week_bars),
        ))
    return result


def synthesize_monthly_bars(daily_bars: list[Bar]) -> list[Bar]:
    """Convert daily bars to monthly bars.

    Each monthly bar: open=first day open, high=max(highs), low=min(lows),
    close=last day close, volume=sum(volumes).
    """
    if not daily_bars:
        return []

    months: dict[str, list[Bar]] = {}
    for bar in daily_bars:
        key = f"{bar.date.year}-{bar.date.month:02d}"
        months.setdefault(key, []).append(bar)

    result: list[Bar] = []
    for key in sorted(months.keys()):
        month_bars = sorted(months[key], key=lambda b: b.date)
        result.append(Bar(
            date=month_bars[-1].date,
            open=month_bars[0].open,
            high=max(b.high for b in month_bars),
            low=min(b.low for b in month_bars),
            close=month_bars[-1].close,
            volume=sum(b.volume for b in month_bars),
        ))
    return result


def compute_trend_alignment(
    daily_bars: list[Bar],
) -> tuple[str, str, str, float]:
    """Compute multi-timeframe trend alignment.

    Requires at least 60 daily bars for meaningful results (weekly/monthly).

    Args:
        daily_bars: Daily OHLCV bars sorted by date ascending. At least 60 bars recommended.

    Returns:
        Tuple of (daily_trend, weekly_trend, monthly_trend, alignment_score).
    """
    if len(daily_bars) < 10:
        return "neutral", "neutral", "neutral", 0.5

    # Daily: EMA(10) vs EMA(50)
    daily_closes = np.array([b.close for b in daily_bars], dtype=np.float64)
    daily_short = _ema_last(daily_closes, 10)
    daily_long = _ema_last(daily_closes, min(50, len(daily_closes)))
    daily_trend = _determine_trend(daily_short, daily_long)

    # Weekly: EMA(10) vs EMA(30)
    weekly_bars = synthesize_weekly_bars(daily_bars)
    if len(weekly_bars) >= 5:
        weekly_closes = np.array([b.close for b in weekly_bars], dtype=np.float64)
        weekly_short = _ema_last(weekly_closes, min(10, len(weekly_closes)))
        weekly_long = _ema_last(weekly_closes, min(30, len(weekly_closes)))
        weekly_trend = _determine_trend(weekly_short, weekly_long)
    else:
        weekly_trend = "neutral"

    # Monthly: EMA(5) vs EMA(12)
    monthly_bars = synthesize_monthly_bars(daily_bars)
    if len(monthly_bars) >= 3:
        monthly_closes = np.array([b.close for b in monthly_bars], dtype=np.float64)
        monthly_short = _ema_last(monthly_closes, min(5, len(monthly_closes)))
        monthly_long = _ema_last(monthly_closes, min(12, len(monthly_closes)))
        monthly_trend = _determine_trend(monthly_short, monthly_long)
    else:
        monthly_trend = "neutral"

    # Alignment score
    trends = [daily_trend, weekly_trend, monthly_trend]
    bullish_count = trends.count("bullish")
    bearish_count = trends.count("bearish")

    if bullish_count == 3 or bearish_count == 3:
        alignment_score = 1.0
    elif bullish_count == 2 or bearish_count == 2:
        alignment_score = 0.67
    elif bullish_count == 1 and bearish_count == 1:
        alignment_score = 0.33
    else:
        alignment_score = 0.5  # All neutral

    return daily_trend, weekly_trend, monthly_trend, round(alignment_score, 2)
```

---

### `src/qitp_mcp_technical/indicators/support_resistance.py`

```python
"""Support and Resistance level detection.

Methods:
1. Pivot Points: Classic floor pivot (H+L+C)/3
2. Local Extrema: Detect local minima/maxima over rolling windows
3. Moving Average levels: Key MAs as dynamic S/R

Output: Sorted list of support and resistance levels with strength ratings.
"""

from __future__ import annotations

import numpy as np

from qitp_mcp_technical.schemas import Bar, SupportResistanceLevel


def compute_pivot_levels(bar: Bar) -> list[SupportResistanceLevel]:
    """Compute classic floor pivot points from a single bar (typically previous day).

    Pivot = (H + L + C) / 3
    R1 = 2*P - L,  S1 = 2*P - H
    R2 = P + (H-L), S2 = P - (H-L)
    R3 = H + 2*(P-L), S3 = L - 2*(H-P)

    Args:
        bar: Previous day's OHLCV bar.

    Returns:
        List of SupportResistanceLevel objects.
    """
    p = (bar.high + bar.low + bar.close) / 3
    r1 = 2 * p - bar.low
    s1 = 2 * p - bar.high
    r2 = p + (bar.high - bar.low)
    s2 = p - (bar.high - bar.low)
    r3 = bar.high + 2 * (p - bar.low)
    s3 = bar.low - 2 * (bar.high - p)

    levels = [
        SupportResistanceLevel(price=round(r3, 4), level_type="resistance", strength="weak", source="pivot"),
        SupportResistanceLevel(price=round(r2, 4), level_type="resistance", strength="moderate", source="pivot"),
        SupportResistanceLevel(price=round(r1, 4), level_type="resistance", strength="strong", source="pivot"),
        SupportResistanceLevel(price=round(s1, 4), level_type="support", strength="strong", source="pivot"),
        SupportResistanceLevel(price=round(s2, 4), level_type="support", strength="moderate", source="pivot"),
        SupportResistanceLevel(price=round(s3, 4), level_type="support", strength="weak", source="pivot"),
    ]
    return levels


def detect_local_extrema(
    bars: list[Bar],
    window: int = 5,
    tolerance_pct: float = 0.5,
) -> list[SupportResistanceLevel]:
    """Detect local minima and maxima from price history.

    A local maximum at index i: high[i] >= high[i-window:i] and high[i] >= high[i+1:i+window+1]
    A local minimum at index i: low[i] <= low[i-window:i] and low[i] <= low[i+1:i+window+1]

    Levels that are touched multiple times (within tolerance) get higher strength.

    Args:
        bars: OHLCV bars sorted by date ascending.
        window: Rolling window for extrema detection (default 5).
        tolerance_pct: Percentage tolerance for grouping similar levels.

    Returns:
        List of SupportResistanceLevel objects.
    """
    if len(bars) < 2 * window + 1:
        return []

    highs = np.array([b.high for b in bars], dtype=np.float64)
    lows = np.array([b.low for b in bars], dtype=np.float64)

    raw_levels: list[tuple[float, str]] = []

    for i in range(window, len(bars) - window):
        left_highs = highs[i - window : i]
        right_highs = highs[i + 1 : i + window + 1]
        if highs[i] >= max(left_highs) and highs[i] >= max(right_highs):
            raw_levels.append((float(highs[i]), "resistance"))

        left_lows = lows[i - window : i]
        right_lows = lows[i + 1 : i + window + 1]
        if lows[i] <= min(left_lows) and lows[i] <= min(right_lows):
            raw_levels.append((float(lows[i]), "support"))

    # Group nearby levels
    if not raw_levels:
        return []

    raw_levels.sort(key=lambda x: x[0])
    grouped: list[SupportResistanceLevel] = []

    current_price = raw_levels[0][0]
    current_type = raw_levels[0][1]
    touches = 1

    for price, level_type in raw_levels[1:]:
        if abs(price - current_price) / current_price * 100 <= tolerance_pct:
            # Merge: average price, increment touches
            current_price = (current_price * touches + price) / (touches + 1)
            touches += 1
            # Use the type of the latest touch
            current_type = level_type
        else:
            strength = "strong" if touches >= 3 else "moderate" if touches >= 2 else "weak"
            grouped.append(SupportResistanceLevel(
                price=round(current_price, 4),
                level_type=current_type,
                strength=strength,
                source="local_extrema",
                touches=touches,
            ))
            current_price = price
            current_type = level_type
            touches = 1

    # Don't forget the last group
    strength = "strong" if touches >= 3 else "moderate" if touches >= 2 else "weak"
    grouped.append(SupportResistanceLevel(
        price=round(current_price, 4),
        level_type=current_type,
        strength=strength,
        source="local_extrema",
        touches=touches,
    ))

    return grouped


def find_nearest_levels(
    current_price: float,
    levels: list[SupportResistanceLevel],
) -> tuple[float | None, float | None]:
    """Find nearest support below and resistance above current price.

    Args:
        current_price: Current closing price.
        levels: All S/R levels.

    Returns:
        Tuple of (nearest_support, nearest_resistance). Either can be None.
    """
    supports = sorted(
        [l for l in levels if l.price < current_price],
        key=lambda l: l.price,
        reverse=True,
    )
    resistances = sorted(
        [l for l in levels if l.price > current_price],
        key=lambda l: l.price,
    )

    nearest_support = supports[0].price if supports else None
    nearest_resistance = resistances[0].price if resistances else None

    return nearest_support, nearest_resistance
```

---

### `src/qitp_mcp_technical/scoring.py`

```python
"""Technical score computation logic.

Sub-weights:
- RSI: 20% — oversold=bullish(high score), overbought=bearish(low score), neutral=50
- MACD: 20% — bullish crossover=100, bearish=0, histogram direction modulates
- Bollinger: 15% — near lower band=bullish(high), near upper=bearish(low), squeeze=high
- Trend alignment: 25% — all aligned bullish=100, mixed=50, all bearish=0
- Support/Resistance proximity: 20% — near support=bullish(high), near resistance=bearish(low)

Final: composite = weighted sum, scaled to 0-100.
"""

from __future__ import annotations

from typing import Literal


# Sub-weights (must sum to 1.0)
WEIGHTS = {
    "rsi": 0.20,
    "macd": 0.20,
    "bollinger": 0.15,
    "trend": 0.25,
    "sr": 0.20,
}


def score_rsi(rsi_value: float) -> float:
    """Convert RSI to a 0-100 bullish score.

    RSI 0   -> score 100 (extremely oversold = very bullish)
    RSI 30  -> score 75
    RSI 50  -> score 50  (neutral)
    RSI 70  -> score 25
    RSI 100 -> score 0   (extremely overbought = very bearish)

    Linear interpolation: score = 100 - rsi_value
    """
    return round(max(0.0, min(100.0, 100.0 - rsi_value)), 2)


def score_macd(
    crossover: str,
    histogram_direction: str,
    histogram_value: float,
) -> float:
    """Convert MACD signals to a 0-100 bullish score.

    Base:
    - bullish crossover: 85
    - bearish crossover: 15
    - no crossover, positive histogram: 60
    - no crossover, negative histogram: 40

    Modulation: expanding histogram adds/subtracts 10.
    """
    if crossover == "bullish":
        base = 85.0
    elif crossover == "bearish":
        base = 15.0
    elif histogram_value > 0:
        base = 60.0
    else:
        base = 40.0

    # Histogram direction modulation
    if histogram_direction == "expanding":
        if histogram_value > 0:
            base = min(100.0, base + 10.0)
        else:
            base = max(0.0, base - 10.0)

    return round(base, 2)


def score_bollinger(
    percent_b: float,
    squeeze: bool,
) -> float:
    """Convert Bollinger Band position to a 0-100 bullish score.

    %B < 0.2 (near lower band): bullish -> score 80
    %B 0.2-0.4: mildly bullish -> score 65
    %B 0.4-0.6: neutral -> score 50
    %B 0.6-0.8: mildly bearish -> score 35
    %B > 0.8 (near upper band): bearish -> score 20

    Squeeze bonus: +10 (high volatility expected, often breakout follows)
    """
    if percent_b < 0.2:
        base = 80.0
    elif percent_b < 0.4:
        base = 65.0
    elif percent_b < 0.6:
        base = 50.0
    elif percent_b < 0.8:
        base = 35.0
    else:
        base = 20.0

    if squeeze:
        base = min(100.0, base + 10.0)

    return round(base, 2)


def score_trend(alignment_score: float, dominant_direction: str) -> float:
    """Convert trend alignment to a 0-100 bullish score.

    All bullish aligned (1.0) -> 100
    All bearish aligned (1.0) -> 0
    Mixed -> scale between based on alignment and direction
    """
    if dominant_direction == "bullish":
        return round(50.0 + alignment_score * 50.0, 2)
    elif dominant_direction == "bearish":
        return round(50.0 - alignment_score * 50.0, 2)
    return 50.0


def score_support_resistance(
    support_distance_pct: float | None,
    resistance_distance_pct: float | None,
) -> float:
    """Convert S/R proximity to a 0-100 bullish score.

    Near support (< 2%): bullish -> 80
    Near resistance (< 2%): bearish -> 20
    Neither: neutral -> 50

    Gradual scaling within the 2% zone.
    """
    sr_near_threshold = 2.0

    support_score = 50.0
    resistance_score = 50.0

    if support_distance_pct is not None and support_distance_pct < sr_near_threshold:
        # Closer to support = more bullish
        proximity_ratio = 1.0 - (support_distance_pct / sr_near_threshold)
        support_score = 50.0 + proximity_ratio * 30.0

    if resistance_distance_pct is not None and resistance_distance_pct < sr_near_threshold:
        # Closer to resistance = more bearish
        proximity_ratio = 1.0 - (resistance_distance_pct / sr_near_threshold)
        resistance_score = 50.0 - proximity_ratio * 30.0

    # Use whichever signal is stronger (closer level dominates)
    if support_distance_pct is not None and resistance_distance_pct is not None:
        if support_distance_pct < resistance_distance_pct:
            return round(support_score, 2)
        else:
            return round(resistance_score, 2)
    elif support_distance_pct is not None:
        return round(support_score, 2)
    elif resistance_distance_pct is not None:
        return round(resistance_score, 2)

    return 50.0


def compute_composite_score(
    rsi_score: float,
    macd_score: float,
    bollinger_score: float,
    trend_score: float,
    sr_score: float,
) -> tuple[float, str, float]:
    """Compute weighted composite technical score.

    Args:
        rsi_score: RSI component (0-100).
        macd_score: MACD component (0-100).
        bollinger_score: Bollinger component (0-100).
        trend_score: Trend alignment component (0-100).
        sr_score: Support/resistance component (0-100).

    Returns:
        Tuple of (composite_score, signal, confidence).
        - composite_score: 0-100
        - signal: strong_buy/buy/neutral/sell/strong_sell
        - confidence: 0.0-1.0 (how consistent the sub-scores are)
    """
    composite = (
        rsi_score * WEIGHTS["rsi"]
        + macd_score * WEIGHTS["macd"]
        + bollinger_score * WEIGHTS["bollinger"]
        + trend_score * WEIGHTS["trend"]
        + sr_score * WEIGHTS["sr"]
    )
    composite = round(composite, 2)

    # Signal classification
    if composite >= 80:
        signal = "strong_buy"
    elif composite >= 60:
        signal = "buy"
    elif composite >= 40:
        signal = "neutral"
    elif composite >= 20:
        signal = "sell"
    else:
        signal = "strong_sell"

    # Confidence = 1.0 - normalized standard deviation of sub-scores
    # If all sub-scores agree, confidence is high. If scattered, confidence is low.
    scores = [rsi_score, macd_score, bollinger_score, trend_score, sr_score]
    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    std_dev = variance ** 0.5
    # Normalize: max possible std_dev with 0-100 scores is ~50
    confidence = round(max(0.0, min(1.0, 1.0 - std_dev / 50.0)), 2)

    return composite, signal, confidence


def classify_signal(composite_score: float) -> Literal["strong_buy", "buy", "neutral", "sell", "strong_sell"]:
    """Classify composite score into trading signal."""
    if composite_score >= 80:
        return "strong_buy"
    elif composite_score >= 60:
        return "buy"
    elif composite_score >= 40:
        return "neutral"
    elif composite_score >= 20:
        return "sell"
    return "strong_sell"
```

---

### `src/qitp_mcp_technical/tools/__init__.py`

```python
"""MCP tool implementations for technical analysis server."""
```

---

### `src/qitp_mcp_technical/tools/momentum.py`

```python
"""Momentum tools: compute_rsi and compute_macd."""

from __future__ import annotations

import logging
from datetime import date

from qitp_mcp_technical.indicators.macd import (
    compute_macd_values,
    detect_crossover,
    detect_histogram_direction,
)
from qitp_mcp_technical.indicators.rsi import classify_rsi, compute_rsi_values
from qitp_mcp_technical.schemas import Bar, MACDResult, RSIResult

logger = logging.getLogger(__name__)


async def compute_rsi(
    symbol: str,
    bars: list[dict],
    period: int = 14,
) -> dict:
    """Compute RSI for a symbol given OHLCV bars.

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts with date, open, high, low, close, volume.
        period: RSI period (default 14).

    Returns:
        RSIResult as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]

    if len(parsed_bars) < period + 1:
        raise ValueError(
            f"Insufficient data for RSI({period}): need {period + 1} bars, got {len(parsed_bars)}"
        )

    rsi_values = compute_rsi_values(parsed_bars, period)
    current_rsi = rsi_values[-1]

    if current_rsi is None:
        raise ValueError("RSI computation returned None — insufficient data")

    signal = classify_rsi(current_rsi)

    result = RSIResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        period=period,
        value=current_rsi,
        signal=signal,
        description=f"RSI({period}) = {current_rsi:.1f} — {signal}",
    )
    return result.model_dump(mode="json")


async def compute_macd(
    symbol: str,
    bars: list[dict],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict:
    """Compute MACD for a symbol given OHLCV bars.

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts.
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal EMA period (default 9).

    Returns:
        MACDResult as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]
    min_required = slow_period + signal_period

    if len(parsed_bars) < min_required:
        raise ValueError(
            f"Insufficient data for MACD({fast_period},{slow_period},{signal_period}): "
            f"need {min_required} bars, got {len(parsed_bars)}"
        )

    macd_line, signal_line, histogram = compute_macd_values(
        parsed_bars, fast_period, slow_period, signal_period
    )

    crossover = detect_crossover(macd_line, signal_line)
    hist_direction = detect_histogram_direction(histogram)

    last_macd = macd_line[-1] if macd_line[-1] is not None else 0.0
    last_signal = signal_line[-1] if signal_line[-1] is not None else 0.0
    last_hist = histogram[-1] if histogram[-1] is not None else 0.0

    result = MACDResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        fast_period=fast_period,
        slow_period=slow_period,
        signal_period=signal_period,
        macd_line=last_macd,
        signal_line=last_signal,
        histogram=last_hist,
        crossover=crossover,
        histogram_direction=hist_direction,
        description=(
            f"MACD({fast_period},{slow_period},{signal_period}): "
            f"line={last_macd:.4f}, signal={last_signal:.4f}, "
            f"hist={last_hist:.4f}, crossover={crossover}, {hist_direction}"
        ),
    )
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_technical/tools/volatility.py`

```python
"""Volatility tools: compute_bollinger_bands and compute_atr."""

from __future__ import annotations

import logging

from qitp_mcp_technical.indicators.atr import classify_volatility, compute_atr_values
from qitp_mcp_technical.indicators.bollinger import (
    compute_bollinger_values,
    detect_squeeze,
)
from qitp_mcp_technical.schemas import ATRResult, Bar, BollingerResult

logger = logging.getLogger(__name__)


async def compute_bollinger_bands(
    symbol: str,
    bars: list[dict],
    period: int = 20,
    std_dev: float = 2.0,
) -> dict:
    """Compute Bollinger Bands for a symbol.

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts.
        period: SMA period (default 20).
        std_dev: Standard deviation multiplier (default 2.0).

    Returns:
        BollingerResult as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]

    if len(parsed_bars) < period:
        raise ValueError(
            f"Insufficient data for Bollinger({period},{std_dev}): "
            f"need {period} bars, got {len(parsed_bars)}"
        )

    upper, middle, lower, pct_b, bandwidth = compute_bollinger_values(
        parsed_bars, period, std_dev
    )

    last_upper = upper[-1]
    last_middle = middle[-1]
    last_lower = lower[-1]
    last_pct_b = pct_b[-1]
    last_bw = bandwidth[-1]

    if any(v is None for v in [last_upper, last_middle, last_lower, last_pct_b, last_bw]):
        raise ValueError("Bollinger computation returned None — insufficient data")

    squeeze = detect_squeeze(bandwidth)

    # Classify signal
    if squeeze:
        signal = "squeeze"
    elif last_pct_b < 0.2:
        signal = "near_lower"
    elif last_pct_b > 0.8:
        signal = "near_upper"
    else:
        signal = "mid_range"

    result = BollingerResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        period=period,
        std_dev=std_dev,
        upper_band=last_upper,
        middle_band=last_middle,
        lower_band=last_lower,
        percent_b=last_pct_b,
        bandwidth=last_bw,
        squeeze=squeeze,
        signal=signal,
        description=(
            f"BB({period},{std_dev}): upper={last_upper:.2f}, "
            f"mid={last_middle:.2f}, lower={last_lower:.2f}, "
            f"%B={last_pct_b:.2f}, BW={last_bw:.4f}, {signal}"
        ),
    )
    return result.model_dump(mode="json")


async def compute_atr(
    symbol: str,
    bars: list[dict],
    period: int = 14,
) -> dict:
    """Compute Average True Range for a symbol.

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts.
        period: ATR period (default 14).

    Returns:
        ATRResult as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]

    if len(parsed_bars) < period + 1:
        raise ValueError(
            f"Insufficient data for ATR({period}): "
            f"need {period + 1} bars, got {len(parsed_bars)}"
        )

    atr_values = compute_atr_values(parsed_bars, period)
    last_atr = atr_values[-1]

    if last_atr is None:
        raise ValueError("ATR computation returned None — insufficient data")

    close = parsed_bars[-1].close
    atr_pct = round(last_atr / close * 100, 4) if close > 0 else 0.0
    vol_level = classify_volatility(atr_pct)

    result = ATRResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        period=period,
        value=last_atr,
        atr_pct=atr_pct,
        volatility_level=vol_level,
        description=f"ATR({period}) = {last_atr:.2f} ({atr_pct:.2f}% of price) — {vol_level} volatility",
    )
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_technical/tools/trend.py`

```python
"""Trend tools: compute_moving_averages and compute_trend_alignment."""

from __future__ import annotations

import logging

import numpy as np

from qitp_mcp_technical.indicators.moving_avg import (
    compute_ema,
    compute_sma,
    compute_wma,
    detect_cross,
)
from qitp_mcp_technical.indicators.trend import compute_trend_alignment
from qitp_mcp_technical.schemas import (
    Bar,
    MovingAverageResult,
    MovingAveragesResult,
    TrendAlignmentResult,
)

logger = logging.getLogger(__name__)


async def compute_moving_averages(
    symbol: str,
    bars: list[dict],
    periods: list[int] | None = None,
    ma_type: str = "EMA",
) -> dict:
    """Compute moving averages for a symbol.

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts.
        periods: MA periods to compute (default [10, 20, 50, 200]).
        ma_type: Type of MA — "SMA", "EMA", or "WMA" (default "EMA").

    Returns:
        MovingAveragesResult as dictionary.
    """
    if periods is None:
        periods = [10, 20, 50, 200]

    parsed_bars = [Bar(**b) for b in bars]
    closes = np.array([b.close for b in parsed_bars], dtype=np.float64)
    current_price = parsed_bars[-1].close

    compute_fn = {
        "SMA": compute_sma,
        "EMA": compute_ema,
        "WMA": compute_wma,
    }.get(ma_type.upper())

    if compute_fn is None:
        raise ValueError(f"Unsupported MA type: {ma_type}. Use SMA, EMA, or WMA.")

    averages: list[MovingAverageResult] = []
    for period in periods:
        values = compute_fn(closes, period)
        last = values[-1] if values else None
        if last is not None:
            averages.append(MovingAverageResult(
                ma_type=ma_type.upper(),
                period=period,
                value=last,
            ))

    # Detect golden/death cross using shortest and longest available MAs
    golden_cross = False
    death_cross = False
    if len(averages) >= 2:
        short_period = min(a.period for a in averages)
        long_period = max(a.period for a in averages)
        short_values = compute_fn(closes, short_period)
        long_values = compute_fn(closes, long_period)
        golden_cross, death_cross = detect_cross(short_values, long_values)

    # Price vs MA200
    ma200_values = compute_fn(closes, 200) if len(closes) >= 200 else [None]
    ma200_last = ma200_values[-1]
    if ma200_last is not None:
        if current_price > ma200_last * 1.001:
            price_vs_ma200 = "above"
        elif current_price < ma200_last * 0.999:
            price_vs_ma200 = "below"
        else:
            price_vs_ma200 = "at"
    else:
        price_vs_ma200 = "above"  # Default if insufficient data

    result = MovingAveragesResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        current_price=current_price,
        averages=averages,
        golden_cross=golden_cross,
        death_cross=death_cross,
        price_vs_ma200=price_vs_ma200,
        description=(
            f"MAs({ma_type}): {', '.join(f'{a.period}={a.value:.2f}' for a in averages)}. "
            f"{'Golden cross!' if golden_cross else 'Death cross!' if death_cross else 'No cross.'} "
            f"Price vs MA200: {price_vs_ma200}"
        ),
    )
    return result.model_dump(mode="json")


async def compute_trend_alignment_tool(
    symbol: str,
    bars: list[dict],
) -> dict:
    """Compute multi-timeframe trend alignment for a symbol.

    Requires at least 60 daily bars for meaningful results.

    Args:
        symbol: Ticker symbol.
        bars: List of daily OHLCV bar dicts (at least 60 recommended).

    Returns:
        TrendAlignmentResult as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]

    daily_trend, weekly_trend, monthly_trend, alignment_score = compute_trend_alignment(parsed_bars)

    trends = [daily_trend, weekly_trend, monthly_trend]
    bullish_count = trends.count("bullish")
    bearish_count = trends.count("bearish")

    if bullish_count > bearish_count:
        dominant = "bullish"
    elif bearish_count > bullish_count:
        dominant = "bearish"
    else:
        dominant = "mixed"

    aligned = (bullish_count == 3 or bearish_count == 3)

    result = TrendAlignmentResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        daily_trend=daily_trend,
        weekly_trend=weekly_trend,
        monthly_trend=monthly_trend,
        alignment_score=alignment_score,
        aligned=aligned,
        dominant_direction=dominant,
        description=(
            f"Trend alignment: D={daily_trend}, W={weekly_trend}, M={monthly_trend}. "
            f"Score={alignment_score:.2f}, {dominant}"
        ),
    )
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_technical/tools/levels.py`

```python
"""Levels tool: compute_support_resistance."""

from __future__ import annotations

import logging

from qitp_mcp_technical.indicators.support_resistance import (
    compute_pivot_levels,
    detect_local_extrema,
    find_nearest_levels,
)
from qitp_mcp_technical.schemas import Bar, SupportResistanceResult

logger = logging.getLogger(__name__)


async def compute_support_resistance(
    symbol: str,
    bars: list[dict],
) -> dict:
    """Compute support and resistance levels for a symbol.

    Combines pivot points from the previous day with local extrema
    from recent price history.

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts (at least 20 bars recommended).

    Returns:
        SupportResistanceResult as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]

    if len(parsed_bars) < 2:
        raise ValueError("Insufficient data for S/R: need at least 2 bars")

    current_price = parsed_bars[-1].close

    # Pivot levels from previous day
    prev_bar = parsed_bars[-2]
    pivot_levels = compute_pivot_levels(prev_bar)

    # Local extrema from history
    extrema_levels = detect_local_extrema(parsed_bars)

    # Combine all levels
    all_levels = pivot_levels + extrema_levels

    # Find nearest S/R
    nearest_support, nearest_resistance = find_nearest_levels(current_price, all_levels)

    support_distance_pct = None
    resistance_distance_pct = None

    if nearest_support is not None and current_price > 0:
        support_distance_pct = round((current_price - nearest_support) / current_price * 100, 4)
    if nearest_resistance is not None and current_price > 0:
        resistance_distance_pct = round((nearest_resistance - current_price) / current_price * 100, 4)

    # Classify signal
    sr_threshold = 2.0  # Percentage
    if support_distance_pct is not None and support_distance_pct < sr_threshold:
        signal = "near_support"
    elif resistance_distance_pct is not None and resistance_distance_pct < sr_threshold:
        signal = "near_resistance"
    else:
        signal = "mid_range"

    result = SupportResistanceResult(
        symbol=symbol,
        date=parsed_bars[-1].date,
        current_price=current_price,
        levels=all_levels,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        support_distance_pct=support_distance_pct,
        resistance_distance_pct=resistance_distance_pct,
        signal=signal,
        description=(
            f"S/R for {symbol}: support={nearest_support}, resistance={nearest_resistance}. "
            f"Support dist={support_distance_pct}%, Resistance dist={resistance_distance_pct}%. "
            f"Signal: {signal}"
        ),
    )
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_technical/tools/composite.py`

```python
"""Composite tool: compute_technical_score.

Orchestrates all indicators and produces a single 0-100 score.
"""

from __future__ import annotations

import logging

from qitp_mcp_technical.indicators.atr import classify_volatility, compute_atr_values
from qitp_mcp_technical.indicators.bollinger import (
    compute_bollinger_values,
    detect_squeeze,
)
from qitp_mcp_technical.indicators.macd import (
    compute_macd_values,
    detect_crossover,
    detect_histogram_direction,
)
from qitp_mcp_technical.indicators.rsi import classify_rsi, compute_rsi_values
from qitp_mcp_technical.indicators.support_resistance import (
    compute_pivot_levels,
    detect_local_extrema,
    find_nearest_levels,
)
from qitp_mcp_technical.indicators.trend import compute_trend_alignment
from qitp_mcp_technical.schemas import Bar, TechnicalScore
from qitp_mcp_technical.scoring import (
    WEIGHTS,
    compute_composite_score,
    score_bollinger,
    score_macd,
    score_rsi,
    score_support_resistance,
    score_trend,
)

logger = logging.getLogger(__name__)


async def compute_technical_score(
    symbol: str,
    bars: list[dict],
) -> dict:
    """Compute composite technical score (0-100) for a symbol.

    Requires at least 35 bars (slow_period + signal_period for MACD).
    Ideally 200+ bars for full MA coverage.

    Sub-weights:
    - RSI(14): 20%
    - MACD(12,26,9): 20%
    - Bollinger(20,2): 15%
    - Trend alignment: 25%
    - S/R proximity: 20%

    Args:
        symbol: Ticker symbol.
        bars: List of OHLCV bar dicts. At least 35 bars required.

    Returns:
        TechnicalScore as dictionary.
    """
    parsed_bars = [Bar(**b) for b in bars]

    if len(parsed_bars) < 35:
        raise ValueError(
            f"Insufficient data for composite score: need at least 35 bars, got {len(parsed_bars)}"
        )

    current_price = parsed_bars[-1].close
    target_date = parsed_bars[-1].date

    # --- RSI ---
    rsi_values = compute_rsi_values(parsed_bars, 14)
    rsi_val = rsi_values[-1] if rsi_values[-1] is not None else 50.0
    rsi_component = score_rsi(rsi_val)

    # --- MACD ---
    macd_line, signal_line, histogram = compute_macd_values(parsed_bars, 12, 26, 9)
    crossover = detect_crossover(macd_line, signal_line)
    hist_direction = detect_histogram_direction(histogram)
    last_hist = histogram[-1] if histogram[-1] is not None else 0.0
    macd_component = score_macd(crossover, hist_direction, last_hist)

    # --- Bollinger ---
    upper, middle, lower, pct_b, bandwidth = compute_bollinger_values(parsed_bars, 20, 2.0)
    last_pct_b = pct_b[-1] if pct_b[-1] is not None else 0.5
    squeeze = detect_squeeze(bandwidth)
    bollinger_component = score_bollinger(last_pct_b, squeeze)

    # --- Trend alignment ---
    daily_trend, weekly_trend, monthly_trend, alignment_score = compute_trend_alignment(parsed_bars)
    trends = [daily_trend, weekly_trend, monthly_trend]
    bullish_count = trends.count("bullish")
    bearish_count = trends.count("bearish")
    if bullish_count > bearish_count:
        dominant = "bullish"
    elif bearish_count > bullish_count:
        dominant = "bearish"
    else:
        dominant = "mixed"
    trend_component = score_trend(alignment_score, dominant)

    # --- Support/Resistance ---
    if len(parsed_bars) >= 2:
        pivot_levels = compute_pivot_levels(parsed_bars[-2])
        extrema_levels = detect_local_extrema(parsed_bars)
        all_levels = pivot_levels + extrema_levels
        nearest_support, nearest_resistance = find_nearest_levels(current_price, all_levels)

        support_dist = None
        resistance_dist = None
        if nearest_support is not None and current_price > 0:
            support_dist = round((current_price - nearest_support) / current_price * 100, 4)
        if nearest_resistance is not None and current_price > 0:
            resistance_dist = round((nearest_resistance - current_price) / current_price * 100, 4)

        sr_component = score_support_resistance(support_dist, resistance_dist)
    else:
        sr_component = 50.0

    # --- Composite ---
    composite, signal, confidence = compute_composite_score(
        rsi_component, macd_component, bollinger_component, trend_component, sr_component
    )

    result = TechnicalScore(
        symbol=symbol,
        date=target_date,
        composite_score=composite,
        rsi_component=rsi_component,
        macd_component=macd_component,
        bollinger_component=bollinger_component,
        trend_component=trend_component,
        sr_component=sr_component,
        signal=signal,
        confidence=confidence,
        description=(
            f"Technical score for {symbol}: {composite:.1f}/100 ({signal}). "
            f"RSI={rsi_component:.0f}, MACD={macd_component:.0f}, BB={bollinger_component:.0f}, "
            f"Trend={trend_component:.0f}, S/R={sr_component:.0f}. "
            f"Confidence={confidence:.2f}"
        ),
    )
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_technical/server.py`

```python
"""MCP server entrypoint — registers all 8 tools and runs the server."""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("qitp_mcp_technical")

# ---------------------------------------------------------------------------
# Build the MCP server
# ---------------------------------------------------------------------------

server = Server("technical-mcp")

# ---------------------------------------------------------------------------
# Tool definitions (list_tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="compute_rsi",
        description=(
            "Compute RSI (Relative Strength Index) for a symbol. "
            "Returns value (0-100), overbought/oversold signal, and description. "
            "Default period: 14."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL)"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array [{date, open, high, low, close, volume}, ...]",
                    "items": {"type": "object"},
                },
                "period": {
                    "type": "integer",
                    "default": 14,
                    "description": "RSI lookback period (default 14)",
                },
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_macd",
        description=(
            "Compute MACD (Moving Average Convergence Divergence). "
            "Returns MACD line, signal line, histogram, crossover detection. "
            "Default parameters: fast=12, slow=26, signal=9."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array",
                    "items": {"type": "object"},
                },
                "fast_period": {"type": "integer", "default": 12},
                "slow_period": {"type": "integer", "default": 26},
                "signal_period": {"type": "integer", "default": 9},
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_bollinger_bands",
        description=(
            "Compute Bollinger Bands. Returns upper/lower bands, %%B, bandwidth, "
            "and squeeze detection. Default: period=20, std_dev=2.0."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array",
                    "items": {"type": "object"},
                },
                "period": {"type": "integer", "default": 20},
                "std_dev": {"type": "number", "default": 2.0},
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_atr",
        description=(
            "Compute Average True Range for volatility measurement. "
            "Returns ATR value, ATR as %% of price, and volatility level. "
            "Default period: 14."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array",
                    "items": {"type": "object"},
                },
                "period": {"type": "integer", "default": 14},
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_moving_averages",
        description=(
            "Compute moving averages (SMA/EMA/WMA) for multiple periods. "
            "Detects golden cross and death cross. "
            "Default periods: [10, 20, 50, 200], type: EMA."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array",
                    "items": {"type": "object"},
                },
                "periods": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "default": [10, 20, 50, 200],
                    "description": "MA periods to compute",
                },
                "ma_type": {
                    "type": "string",
                    "enum": ["SMA", "EMA", "WMA"],
                    "default": "EMA",
                    "description": "Moving average type",
                },
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_trend_alignment",
        description=(
            "Compute multi-timeframe trend alignment (daily/weekly/monthly). "
            "Returns alignment score (0-1) and dominant direction. "
            "Requires at least 60 daily bars for meaningful results."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "Daily OHLCV bar array (60+ bars recommended)",
                    "items": {"type": "object"},
                },
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_support_resistance",
        description=(
            "Compute support and resistance levels from pivot points and local extrema. "
            "Returns nearest S/R levels, distance percentages, and proximity signal."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array (20+ bars recommended)",
                    "items": {"type": "object"},
                },
            },
            "required": ["symbol", "bars"],
        },
    ),
    Tool(
        name="compute_technical_score",
        description=(
            "Compute composite technical score (0-100) combining RSI(20%%), MACD(20%%), "
            "Bollinger(15%%), Trend(25%%), S/R(20%%). Returns score, signal "
            "(strong_buy/buy/neutral/sell/strong_sell), and confidence. "
            "Requires at least 35 bars."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "bars": {
                    "type": "array",
                    "description": "OHLCV bar array (35+ bars required, 200+ recommended)",
                    "items": {"type": "object"},
                },
            },
            "required": ["symbol", "bars"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# Tool dispatch (call_tool)
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to implementations."""
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        error_detail = {
            "error": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
        return [TextContent(type="text", text=json.dumps(error_detail))]


async def _dispatch(name: str, arguments: dict):
    """Dispatch a tool call to its implementation."""
    if name == "compute_rsi":
        from qitp_mcp_technical.tools.momentum import compute_rsi

        return await compute_rsi(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
            period=arguments.get("period", 14),
        )

    elif name == "compute_macd":
        from qitp_mcp_technical.tools.momentum import compute_macd

        return await compute_macd(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
            fast_period=arguments.get("fast_period", 12),
            slow_period=arguments.get("slow_period", 26),
            signal_period=arguments.get("signal_period", 9),
        )

    elif name == "compute_bollinger_bands":
        from qitp_mcp_technical.tools.volatility import compute_bollinger_bands

        return await compute_bollinger_bands(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
            period=arguments.get("period", 20),
            std_dev=arguments.get("std_dev", 2.0),
        )

    elif name == "compute_atr":
        from qitp_mcp_technical.tools.volatility import compute_atr

        return await compute_atr(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
            period=arguments.get("period", 14),
        )

    elif name == "compute_moving_averages":
        from qitp_mcp_technical.tools.trend import compute_moving_averages

        return await compute_moving_averages(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
            periods=arguments.get("periods", [10, 20, 50, 200]),
            ma_type=arguments.get("ma_type", "EMA"),
        )

    elif name == "compute_trend_alignment":
        from qitp_mcp_technical.tools.trend import compute_trend_alignment_tool

        return await compute_trend_alignment_tool(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
        )

    elif name == "compute_support_resistance":
        from qitp_mcp_technical.tools.levels import compute_support_resistance

        return await compute_support_resistance(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
        )

    elif name == "compute_technical_score":
        from qitp_mcp_technical.tools.composite import compute_technical_score

        return await compute_technical_score(
            symbol=arguments["symbol"],
            bars=arguments["bars"],
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def run_stdio():
    """Run MCP server over stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Main entrypoint — select transport based on env."""
    import asyncio

    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        asyncio.run(run_stdio())
    elif transport == "http":
        from mcp.server.streamable_http import StreamableHTTPServer

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))
        logger.info("Starting HTTP transport on %s:%d", host, port)
        http_server = StreamableHTTPServer(server, host=host, port=port)
        asyncio.run(http_server.run())
    else:
        logger.error("Unknown MCP_TRANSPORT=%s. Use 'stdio' or 'http'.", transport)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

### `Dockerfile`

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install package
RUN pip install --no-cache-dir .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default: HTTP transport for production
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080

EXPOSE 8080

ENTRYPOINT ["technical-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  technical-mcp:
    build: .
    container_name: qitp-technical-mcp
    ports:
      - "8009:8080"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8080
    restart: unless-stopped
    networks:
      - qitp

networks:
  qitp:
    driver: bridge
```

---

### `tests/fixtures/sample_ohlcv.json`

```json
[
    {"date": "2025-01-02", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0, "volume": 1000000},
    {"date": "2025-01-03", "open": 151.0, "high": 153.0, "low": 150.0, "close": 152.5, "volume": 1100000},
    {"date": "2025-01-06", "open": 152.0, "high": 154.0, "low": 151.0, "close": 153.0, "volume": 950000},
    {"date": "2025-01-07", "open": 153.0, "high": 155.0, "low": 152.0, "close": 154.5, "volume": 1050000},
    {"date": "2025-01-08", "open": 154.0, "high": 156.0, "low": 153.0, "close": 155.0, "volume": 1200000},
    {"date": "2025-01-09", "open": 155.0, "high": 157.0, "low": 154.0, "close": 156.5, "volume": 1150000},
    {"date": "2025-01-10", "open": 156.0, "high": 158.0, "low": 155.0, "close": 157.0, "volume": 1300000},
    {"date": "2025-01-13", "open": 159.0, "high": 161.0, "low": 158.0, "close": 160.0, "volume": 1500000},
    {"date": "2025-01-14", "open": 160.0, "high": 161.5, "low": 159.0, "close": 159.5, "volume": 1250000},
    {"date": "2025-01-15", "open": 159.0, "high": 160.0, "low": 158.0, "close": 158.5, "volume": 1100000},
    {"date": "2025-01-16", "open": 158.5, "high": 160.5, "low": 157.5, "close": 160.0, "volume": 1050000},
    {"date": "2025-01-17", "open": 160.0, "high": 162.0, "low": 159.0, "close": 161.5, "volume": 1400000},
    {"date": "2025-01-20", "open": 158.0, "high": 159.0, "low": 156.0, "close": 157.0, "volume": 1600000},
    {"date": "2025-01-21", "open": 157.0, "high": 158.5, "low": 155.5, "close": 156.0, "volume": 1350000},
    {"date": "2025-01-22", "open": 156.0, "high": 158.0, "low": 155.0, "close": 157.5, "volume": 1200000},
    {"date": "2025-01-23", "open": 157.5, "high": 159.0, "low": 156.5, "close": 158.0, "volume": 1100000},
    {"date": "2025-01-24", "open": 158.0, "high": 160.0, "low": 157.0, "close": 159.5, "volume": 1250000},
    {"date": "2025-01-27", "open": 160.0, "high": 162.0, "low": 159.0, "close": 161.0, "volume": 1300000},
    {"date": "2025-01-28", "open": 161.0, "high": 163.0, "low": 160.0, "close": 162.5, "volume": 1400000},
    {"date": "2025-01-29", "open": 162.5, "high": 164.0, "low": 161.5, "close": 163.0, "volume": 1350000},
    {"date": "2025-01-30", "open": 163.0, "high": 165.0, "low": 162.0, "close": 164.5, "volume": 1500000},
    {"date": "2025-01-31", "open": 164.5, "high": 166.0, "low": 163.5, "close": 165.0, "volume": 1450000},
    {"date": "2025-02-03", "open": 164.0, "high": 165.5, "low": 163.0, "close": 163.5, "volume": 1200000},
    {"date": "2025-02-04", "open": 163.5, "high": 165.0, "low": 162.5, "close": 164.0, "volume": 1150000},
    {"date": "2025-02-05", "open": 164.0, "high": 166.0, "low": 163.0, "close": 165.5, "volume": 1300000},
    {"date": "2025-02-06", "open": 165.5, "high": 167.0, "low": 164.5, "close": 166.0, "volume": 1250000},
    {"date": "2025-02-07", "open": 166.0, "high": 168.0, "low": 165.0, "close": 167.5, "volume": 1400000},
    {"date": "2025-02-10", "open": 167.0, "high": 169.0, "low": 166.0, "close": 168.0, "volume": 1350000},
    {"date": "2025-02-11", "open": 168.0, "high": 170.0, "low": 167.0, "close": 169.5, "volume": 1500000},
    {"date": "2025-02-12", "open": 169.5, "high": 171.0, "low": 168.5, "close": 170.0, "volume": 1450000},
    {"date": "2025-02-13", "open": 170.0, "high": 171.5, "low": 169.0, "close": 169.0, "volume": 1200000},
    {"date": "2025-02-14", "open": 169.0, "high": 170.0, "low": 167.5, "close": 168.0, "volume": 1300000},
    {"date": "2025-02-18", "open": 167.0, "high": 168.5, "low": 166.0, "close": 166.5, "volume": 1400000},
    {"date": "2025-02-19", "open": 166.5, "high": 168.0, "low": 165.5, "close": 167.0, "volume": 1250000},
    {"date": "2025-02-20", "open": 167.0, "high": 169.0, "low": 166.0, "close": 168.5, "volume": 1350000},
    {"date": "2025-02-21", "open": 168.5, "high": 170.0, "low": 167.5, "close": 169.0, "volume": 1300000},
    {"date": "2025-02-24", "open": 169.0, "high": 171.0, "low": 168.0, "close": 170.5, "volume": 1450000},
    {"date": "2025-02-25", "open": 170.5, "high": 172.0, "low": 169.5, "close": 171.0, "volume": 1400000},
    {"date": "2025-02-26", "open": 171.0, "high": 172.5, "low": 170.0, "close": 171.5, "volume": 1350000},
    {"date": "2025-02-27", "open": 171.5, "high": 173.0, "low": 170.5, "close": 172.0, "volume": 1500000},
    {"date": "2025-02-28", "open": 172.0, "high": 174.0, "low": 171.0, "close": 173.5, "volume": 1550000}
]
```

---

### `tests/conftest.py`

```python
"""Shared test fixtures for technical analysis MCP server tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from qitp_mcp_technical.schemas import Bar


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_ohlcv_dicts() -> list[dict]:
    """Load sample OHLCV data from JSON fixture."""
    fixture_path = FIXTURES_DIR / "sample_ohlcv.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def sample_bars(sample_ohlcv_dicts) -> list[Bar]:
    """Parsed Bar objects from fixture data."""
    return [Bar(**d) for d in sample_ohlcv_dicts]


@pytest.fixture
def uptrend_bars() -> list[Bar]:
    """Generate 50 bars in a clear uptrend for testing."""
    bars = []
    base_price = 100.0
    for i in range(50):
        price = base_price + i * 0.5  # Steady uptrend
        bars.append(Bar(
            date=f"2025-01-{(i % 28) + 1:02d}" if i < 28 else f"2025-02-{(i - 28) + 1:02d}",
            open=price,
            high=price + 1.0,
            low=price - 0.5,
            close=price + 0.3,
            volume=1000000 + i * 10000,
        ))
    return bars


@pytest.fixture
def downtrend_bars() -> list[Bar]:
    """Generate 50 bars in a clear downtrend for testing."""
    bars = []
    base_price = 200.0
    for i in range(50):
        price = base_price - i * 0.5  # Steady downtrend
        bars.append(Bar(
            date=f"2025-01-{(i % 28) + 1:02d}" if i < 28 else f"2025-02-{(i - 28) + 1:02d}",
            open=price,
            high=price + 0.5,
            low=price - 1.0,
            close=price - 0.3,
            volume=1000000 + i * 10000,
        ))
    return bars


@pytest.fixture
def sideways_bars() -> list[Bar]:
    """Generate 50 bars in a sideways/range-bound market."""
    import math
    bars = []
    base_price = 150.0
    for i in range(50):
        # Oscillate around base price
        offset = 3.0 * math.sin(i * 0.3)
        price = base_price + offset
        bars.append(Bar(
            date=f"2025-01-{(i % 28) + 1:02d}" if i < 28 else f"2025-02-{(i - 28) + 1:02d}",
            open=price,
            high=price + 1.5,
            low=price - 1.5,
            close=price + 0.2 * math.cos(i * 0.3),
            volume=1000000,
        ))
    return bars
```

---

### `tests/test_rsi.py`

```python
"""Tests for RSI calculation."""

from __future__ import annotations

import pytest

from qitp_mcp_technical.indicators.rsi import classify_rsi, compute_rsi_values
from qitp_mcp_technical.schemas import Bar
from qitp_mcp_technical.tools.momentum import compute_rsi


class TestRSICalculation:
    def test_rsi_values_length(self, sample_bars):
        """RSI output length matches input length."""
        values = compute_rsi_values(sample_bars, period=14)
        assert len(values) == len(sample_bars)

    def test_rsi_first_period_is_none(self, sample_bars):
        """First `period` values should be None."""
        period = 14
        values = compute_rsi_values(sample_bars, period)
        for i in range(period):
            assert values[i] is None

    def test_rsi_values_in_range(self, sample_bars):
        """All non-None RSI values should be 0-100."""
        values = compute_rsi_values(sample_bars, period=14)
        for v in values:
            if v is not None:
                assert 0.0 <= v <= 100.0

    def test_rsi_uptrend_high(self, uptrend_bars):
        """Strong uptrend should produce high RSI."""
        values = compute_rsi_values(uptrend_bars, period=14)
        # Last RSI should be above 60 in a strong uptrend
        last_rsi = values[-1]
        assert last_rsi is not None
        assert last_rsi > 60.0

    def test_rsi_downtrend_low(self, downtrend_bars):
        """Strong downtrend should produce low RSI."""
        values = compute_rsi_values(downtrend_bars, period=14)
        last_rsi = values[-1]
        assert last_rsi is not None
        assert last_rsi < 40.0

    def test_rsi_insufficient_data(self):
        """RSI with fewer bars than period returns all None."""
        bars = [
            Bar(date="2025-01-01", open=100, high=102, low=99, close=101, volume=1000)
            for _ in range(5)
        ]
        values = compute_rsi_values(bars, period=14)
        assert all(v is None for v in values)

    def test_rsi_custom_period(self, sample_bars):
        """RSI with custom period works."""
        values = compute_rsi_values(sample_bars, period=7)
        assert len(values) == len(sample_bars)
        # With period=7, we should have non-None values earlier
        assert values[7] is not None


class TestRSIClassification:
    def test_overbought(self):
        assert classify_rsi(75.0) == "overbought"
        assert classify_rsi(70.0) == "overbought"
        assert classify_rsi(100.0) == "overbought"

    def test_oversold(self):
        assert classify_rsi(25.0) == "oversold"
        assert classify_rsi(30.0) == "oversold"
        assert classify_rsi(0.0) == "oversold"

    def test_neutral(self):
        assert classify_rsi(50.0) == "neutral"
        assert classify_rsi(31.0) == "neutral"
        assert classify_rsi(69.0) == "neutral"


class TestRSITool:
    @pytest.mark.asyncio
    async def test_compute_rsi_tool(self, sample_ohlcv_dicts):
        """Tool function returns valid RSIResult dict."""
        result = await compute_rsi("AAPL", sample_ohlcv_dicts, period=14)
        assert result["symbol"] == "AAPL"
        assert 0 <= result["value"] <= 100
        assert result["signal"] in ("overbought", "oversold", "neutral")
        assert result["period"] == 14

    @pytest.mark.asyncio
    async def test_compute_rsi_insufficient_data(self):
        """Tool raises ValueError with insufficient bars."""
        bars = [
            {"date": "2025-01-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}
            for _ in range(5)
        ]
        with pytest.raises(ValueError, match="Insufficient data"):
            await compute_rsi("AAPL", bars, period=14)
```

---

### `tests/test_macd.py`

```python
"""Tests for MACD calculation."""

from __future__ import annotations

import pytest

from qitp_mcp_technical.indicators.macd import (
    compute_macd_values,
    detect_crossover,
    detect_histogram_direction,
)
from qitp_mcp_technical.tools.momentum import compute_macd


class TestMACDCalculation:
    def test_macd_values_length(self, sample_bars):
        """MACD output length matches input length."""
        macd, signal, hist = compute_macd_values(sample_bars)
        assert len(macd) == len(sample_bars)
        assert len(signal) == len(sample_bars)
        assert len(hist) == len(sample_bars)

    def test_macd_first_values_none(self, sample_bars):
        """First slow_period-1 values should be None for MACD line."""
        macd, signal, hist = compute_macd_values(sample_bars, slow_period=26)
        for i in range(25):
            assert macd[i] is None

    def test_macd_signal_delayed(self, sample_bars):
        """Signal line should be None for first slow_period+signal_period-2 values."""
        macd, signal, hist = compute_macd_values(sample_bars, slow_period=26, signal_period=9)
        # Signal should be None for at least first 33 bars (26-1 + 9-1)
        for i in range(33):
            assert signal[i] is None

    def test_histogram_is_difference(self, sample_bars):
        """Histogram = MACD line - signal line."""
        macd, signal, hist = compute_macd_values(sample_bars)
        for m, s, h in zip(macd, signal, hist):
            if m is not None and s is not None and h is not None:
                assert abs(h - (m - s)) < 0.001

    def test_macd_uptrend_positive(self, uptrend_bars):
        """Uptrend should produce positive MACD line."""
        macd, signal, hist = compute_macd_values(uptrend_bars)
        valid_macd = [m for m in macd if m is not None]
        if valid_macd:
            assert valid_macd[-1] > 0

    def test_macd_insufficient_data(self):
        """Insufficient data returns all None."""
        from qitp_mcp_technical.schemas import Bar
        bars = [
            Bar(date="2025-01-01", open=100, high=102, low=99, close=101, volume=1000)
            for _ in range(10)
        ]
        macd, signal, hist = compute_macd_values(bars)
        assert all(v is None for v in macd)


class TestCrossoverDetection:
    def test_bullish_crossover(self):
        """MACD crossing above signal = bullish."""
        macd = [None, None, -0.5, 0.5]
        signal = [None, None, 0.0, 0.0]
        assert detect_crossover(macd, signal) == "bullish"

    def test_bearish_crossover(self):
        """MACD crossing below signal = bearish."""
        macd = [None, None, 0.5, -0.5]
        signal = [None, None, 0.0, 0.0]
        assert detect_crossover(macd, signal) == "bearish"

    def test_no_crossover(self):
        """No crossing = none."""
        macd = [None, None, 0.5, 0.8]
        signal = [None, None, 0.0, 0.0]
        assert detect_crossover(macd, signal) == "none"

    def test_insufficient_data(self):
        """Insufficient valid points returns none."""
        assert detect_crossover([None], [None]) == "none"


class TestHistogramDirection:
    def test_expanding(self):
        assert detect_histogram_direction([0.1, 0.3, 0.5]) == "expanding"

    def test_contracting(self):
        assert detect_histogram_direction([0.5, 0.3, 0.1]) == "contracting"

    def test_negative_expanding(self):
        """Negative histogram getting more negative = expanding."""
        assert detect_histogram_direction([-0.1, -0.3, -0.5]) == "expanding"

    def test_insufficient(self):
        assert detect_histogram_direction([None, 0.5]) == "contracting"


class TestMACDTool:
    @pytest.mark.asyncio
    async def test_compute_macd_tool(self, sample_ohlcv_dicts):
        """Tool function returns valid MACDResult dict."""
        result = await compute_macd("AAPL", sample_ohlcv_dicts)
        assert result["symbol"] == "AAPL"
        assert result["fast_period"] == 12
        assert result["slow_period"] == 26
        assert result["signal_period"] == 9
        assert result["crossover"] in ("bullish", "bearish", "none")
        assert result["histogram_direction"] in ("expanding", "contracting")

    @pytest.mark.asyncio
    async def test_compute_macd_insufficient_data(self):
        """Tool raises ValueError with insufficient bars."""
        bars = [
            {"date": "2025-01-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}
            for _ in range(10)
        ]
        with pytest.raises(ValueError, match="Insufficient data"):
            await compute_macd("AAPL", bars)
```

---

### `tests/test_bollinger.py`

```python
"""Tests for Bollinger Bands calculation."""

from __future__ import annotations

import math

import pytest

from qitp_mcp_technical.indicators.bollinger import (
    compute_bollinger_values,
    detect_squeeze,
)
from qitp_mcp_technical.schemas import Bar
from qitp_mcp_technical.tools.volatility import compute_bollinger_bands


class TestBollingerCalculation:
    def test_values_length(self, sample_bars):
        """Output length matches input."""
        upper, mid, lower, pct_b, bw = compute_bollinger_values(sample_bars, period=20)
        assert len(upper) == len(sample_bars)
        assert len(mid) == len(sample_bars)

    def test_first_values_none(self, sample_bars):
        """First period-1 values should be None."""
        upper, mid, lower, pct_b, bw = compute_bollinger_values(sample_bars, period=20)
        for i in range(19):
            assert upper[i] is None

    def test_upper_above_lower(self, sample_bars):
        """Upper band should always be above lower band."""
        upper, mid, lower, pct_b, bw = compute_bollinger_values(sample_bars, period=20)
        for u, lo in zip(upper, lower):
            if u is not None and lo is not None:
                assert u >= lo

    def test_middle_between_bands(self, sample_bars):
        """Middle band should be between upper and lower."""
        upper, mid, lower, pct_b, bw = compute_bollinger_values(sample_bars, period=20)
        for u, m, lo in zip(upper, mid, lower):
            if all(v is not None for v in [u, m, lo]):
                assert lo <= m <= u

    def test_percent_b_range(self, sample_bars):
        """Percent B should generally be between 0 and 1 in normal conditions."""
        upper, mid, lower, pct_b, bw = compute_bollinger_values(sample_bars, period=20)
        valid_pct_b = [v for v in pct_b if v is not None]
        # Note: %B can exceed [0,1] if price is outside bands
        assert len(valid_pct_b) > 0

    def test_bandwidth_positive(self, sample_bars):
        """Bandwidth should be positive."""
        upper, mid, lower, pct_b, bw = compute_bollinger_values(sample_bars, period=20)
        for v in bw:
            if v is not None:
                assert v >= 0

    def test_insufficient_data(self):
        """Fewer bars than period returns all None."""
        bars = [
            Bar(date="2025-01-01", open=100, high=102, low=99, close=101, volume=1000)
            for _ in range(10)
        ]
        upper, mid, lower, pct_b, bw = compute_bollinger_values(bars, period=20)
        assert all(v is None for v in upper)


class TestSqueezeDetection:
    def test_squeeze_detected(self):
        """Low bandwidth at the end should detect squeeze."""
        # Simulate decreasing bandwidth
        bw_values = [0.05, 0.04, 0.03, 0.02, 0.01] * 25  # 125 values, last is very low
        assert detect_squeeze(bw_values) is True

    def test_no_squeeze(self):
        """Normal bandwidth should not detect squeeze."""
        bw_values = [0.05] * 125
        assert detect_squeeze(bw_values) is False

    def test_insufficient_history(self):
        """Too few values returns False."""
        assert detect_squeeze([0.01, 0.02]) is False


class TestBollingerTool:
    @pytest.mark.asyncio
    async def test_compute_bollinger_tool(self, sample_ohlcv_dicts):
        """Tool function returns valid BollingerResult dict."""
        result = await compute_bollinger_bands("AAPL", sample_ohlcv_dicts)
        assert result["symbol"] == "AAPL"
        assert result["period"] == 20
        assert result["std_dev"] == 2.0
        assert result["upper_band"] > result["lower_band"]
        assert result["signal"] in ("near_upper", "near_lower", "mid_range", "squeeze")

    @pytest.mark.asyncio
    async def test_compute_bollinger_insufficient(self):
        """Tool raises ValueError with insufficient bars."""
        bars = [
            {"date": "2025-01-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}
            for _ in range(10)
        ]
        with pytest.raises(ValueError, match="Insufficient data"):
            await compute_bollinger_bands("AAPL", bars, period=20)
```

---

### `tests/test_trend.py`

```python
"""Tests for trend analysis — moving averages and multi-timeframe alignment."""

from __future__ import annotations

import numpy as np
import pytest

from qitp_mcp_technical.indicators.moving_avg import (
    compute_ema,
    compute_sma,
    compute_wma,
    detect_cross,
)
from qitp_mcp_technical.indicators.trend import (
    compute_trend_alignment,
    synthesize_monthly_bars,
    synthesize_weekly_bars,
)
from qitp_mcp_technical.tools.trend import compute_moving_averages, compute_trend_alignment_tool


class TestSMA:
    def test_sma_basic(self):
        closes = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        result = compute_sma(closes, period=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == pytest.approx(11.0, abs=0.01)  # (10+11+12)/3
        assert result[3] == pytest.approx(12.0, abs=0.01)
        assert result[4] == pytest.approx(13.0, abs=0.01)

    def test_sma_insufficient(self):
        closes = np.array([10.0, 11.0])
        result = compute_sma(closes, period=5)
        assert all(v is None for v in result)


class TestEMA:
    def test_ema_basic(self):
        closes = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        result = compute_ema(closes, period=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None  # SMA seed
        # EMA should be responsive to recent prices
        assert result[-1] > result[-2]  # Uptrend: EMA increases

    def test_ema_length(self):
        closes = np.array([100.0] * 20)
        result = compute_ema(closes, period=5)
        assert len(result) == 20


class TestWMA:
    def test_wma_basic(self):
        closes = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        result = compute_wma(closes, period=3)
        # WMA(3) at index 2: (10*1 + 11*2 + 12*3) / 6 = 68/6 = 11.333
        assert result[2] == pytest.approx(11.3333, abs=0.01)


class TestCrossDetection:
    def test_golden_cross(self):
        short = [None, None, 50.0, 51.0]
        long = [None, None, 51.0, 50.5]
        golden, death = detect_cross(short, long)
        assert golden is True
        assert death is False

    def test_death_cross(self):
        short = [None, None, 51.0, 49.0]
        long = [None, None, 50.0, 50.0]
        golden, death = detect_cross(short, long)
        assert golden is False
        assert death is True

    def test_no_cross(self):
        short = [None, None, 52.0, 53.0]
        long = [None, None, 50.0, 50.0]
        golden, death = detect_cross(short, long)
        assert golden is False
        assert death is False


class TestWeeklyBarSynthesis:
    def test_basic_synthesis(self, sample_bars):
        weekly = synthesize_weekly_bars(sample_bars)
        assert len(weekly) > 0
        # Each weekly bar should have volume >= any daily volume
        for wb in weekly:
            assert wb.volume > 0

    def test_empty_input(self):
        assert synthesize_weekly_bars([]) == []


class TestMonthlyBarSynthesis:
    def test_basic_synthesis(self, sample_bars):
        monthly = synthesize_monthly_bars(sample_bars)
        assert len(monthly) > 0
        # Should have 2 months: Jan and Feb
        assert len(monthly) == 2


class TestTrendAlignment:
    def test_uptrend_alignment(self, uptrend_bars):
        daily, weekly, monthly, score = compute_trend_alignment(uptrend_bars)
        assert daily == "bullish"
        assert score >= 0.5

    def test_downtrend_alignment(self, downtrend_bars):
        daily, weekly, monthly, score = compute_trend_alignment(downtrend_bars)
        assert daily == "bearish"
        assert score >= 0.5

    def test_insufficient_data(self):
        from qitp_mcp_technical.schemas import Bar
        bars = [
            Bar(date="2025-01-01", open=100, high=102, low=99, close=101, volume=1000)
            for _ in range(5)
        ]
        daily, weekly, monthly, score = compute_trend_alignment(bars)
        assert daily == "neutral"
        assert score == 0.5


class TestMovingAveragesTool:
    @pytest.mark.asyncio
    async def test_compute_ma_tool(self, sample_ohlcv_dicts):
        result = await compute_moving_averages("AAPL", sample_ohlcv_dicts, periods=[10, 20])
        assert result["symbol"] == "AAPL"
        assert len(result["averages"]) >= 1
        assert isinstance(result["golden_cross"], bool)
        assert isinstance(result["death_cross"], bool)

    @pytest.mark.asyncio
    async def test_unsupported_ma_type(self, sample_ohlcv_dicts):
        with pytest.raises(ValueError, match="Unsupported MA type"):
            await compute_moving_averages("AAPL", sample_ohlcv_dicts, ma_type="INVALID")


class TestTrendAlignmentTool:
    @pytest.mark.asyncio
    async def test_compute_trend_tool(self, sample_ohlcv_dicts):
        result = await compute_trend_alignment_tool("AAPL", sample_ohlcv_dicts)
        assert result["symbol"] == "AAPL"
        assert result["daily_trend"] in ("bullish", "bearish", "neutral")
        assert result["weekly_trend"] in ("bullish", "bearish", "neutral")
        assert result["monthly_trend"] in ("bullish", "bearish", "neutral")
        assert 0.0 <= result["alignment_score"] <= 1.0
```

---

### `tests/test_scoring.py`

```python
"""Tests for scoring logic and composite technical score."""

from __future__ import annotations

import pytest

from qitp_mcp_technical.scoring import (
    compute_composite_score,
    score_bollinger,
    score_macd,
    score_rsi,
    score_support_resistance,
    score_trend,
)
from qitp_mcp_technical.tools.composite import compute_technical_score


class TestRSIScoring:
    def test_oversold_high_score(self):
        """RSI=20 (oversold) should give high bullish score."""
        assert score_rsi(20.0) == 80.0

    def test_overbought_low_score(self):
        """RSI=80 (overbought) should give low bullish score."""
        assert score_rsi(80.0) == 20.0

    def test_neutral(self):
        """RSI=50 should give neutral score."""
        assert score_rsi(50.0) == 50.0

    def test_extreme_low(self):
        """RSI=0 should give max score."""
        assert score_rsi(0.0) == 100.0

    def test_extreme_high(self):
        """RSI=100 should give min score."""
        assert score_rsi(100.0) == 0.0


class TestMACDScoring:
    def test_bullish_crossover(self):
        score = score_macd("bullish", "expanding", 0.5)
        assert score == 95.0  # 85 + 10

    def test_bearish_crossover(self):
        score = score_macd("bearish", "expanding", -0.5)
        assert score == 5.0  # 15 - 10

    def test_no_crossover_positive(self):
        score = score_macd("none", "contracting", 0.5)
        assert score == 60.0

    def test_no_crossover_negative(self):
        score = score_macd("none", "contracting", -0.5)
        assert score == 40.0


class TestBollingerScoring:
    def test_near_lower_band(self):
        score = score_bollinger(0.1, squeeze=False)
        assert score == 80.0

    def test_near_upper_band(self):
        score = score_bollinger(0.9, squeeze=False)
        assert score == 20.0

    def test_mid_range(self):
        score = score_bollinger(0.5, squeeze=False)
        assert score == 50.0

    def test_squeeze_bonus(self):
        score = score_bollinger(0.5, squeeze=True)
        assert score == 60.0  # 50 + 10


class TestTrendScoring:
    def test_all_bullish(self):
        score = score_trend(1.0, "bullish")
        assert score == 100.0

    def test_all_bearish(self):
        score = score_trend(1.0, "bearish")
        assert score == 0.0

    def test_mixed(self):
        score = score_trend(0.5, "mixed")
        assert score == 50.0

    def test_partial_bullish(self):
        score = score_trend(0.67, "bullish")
        assert score == pytest.approx(83.5, abs=0.1)


class TestSRScoring:
    def test_near_support(self):
        score = score_support_resistance(0.5, 5.0)
        assert score > 50.0  # Bullish near support

    def test_near_resistance(self):
        score = score_support_resistance(5.0, 0.5)
        assert score < 50.0  # Bearish near resistance

    def test_no_nearby_levels(self):
        score = score_support_resistance(5.0, 5.0)
        assert score == 50.0

    def test_no_levels_at_all(self):
        score = score_support_resistance(None, None)
        assert score == 50.0


class TestCompositeScore:
    def test_all_bullish_scores(self):
        """All high scores should produce strong_buy."""
        composite, signal, confidence = compute_composite_score(90, 90, 90, 90, 90)
        assert composite == 90.0
        assert signal == "strong_buy"
        assert confidence > 0.9

    def test_all_bearish_scores(self):
        """All low scores should produce strong_sell."""
        composite, signal, confidence = compute_composite_score(10, 10, 10, 10, 10)
        assert composite == 10.0
        assert signal == "strong_sell"

    def test_mixed_scores_moderate_confidence(self):
        """Mixed scores should produce lower confidence."""
        composite, signal, confidence = compute_composite_score(90, 10, 50, 80, 20)
        assert 20 <= composite <= 80
        assert confidence < 0.7

    def test_neutral_scores(self):
        """All 50s should produce neutral."""
        composite, signal, confidence = compute_composite_score(50, 50, 50, 50, 50)
        assert composite == 50.0
        assert signal == "neutral"
        assert confidence == 1.0

    def test_weights_sum_to_one(self):
        """Verify the weights are correct."""
        from qitp_mcp_technical.scoring import WEIGHTS
        assert abs(sum(WEIGHTS.values()) - 1.0) < 0.001

    def test_signal_boundaries(self):
        """Test all signal boundary values."""
        _, signal, _ = compute_composite_score(80, 80, 80, 80, 80)
        assert signal == "strong_buy"
        _, signal, _ = compute_composite_score(60, 60, 60, 60, 60)
        assert signal == "buy"
        _, signal, _ = compute_composite_score(50, 50, 50, 50, 50)
        assert signal == "neutral"
        _, signal, _ = compute_composite_score(20, 20, 20, 20, 20)
        assert signal == "sell"
        _, signal, _ = compute_composite_score(10, 10, 10, 10, 10)
        assert signal == "strong_sell"


class TestCompositeScoreTool:
    @pytest.mark.asyncio
    async def test_compute_technical_score_tool(self, sample_ohlcv_dicts):
        """Tool function returns valid TechnicalScore dict."""
        result = await compute_technical_score("AAPL", sample_ohlcv_dicts)
        assert result["symbol"] == "AAPL"
        assert 0 <= result["composite_score"] <= 100
        assert result["signal"] in ("strong_buy", "buy", "neutral", "sell", "strong_sell")
        assert 0 <= result["confidence"] <= 1
        assert "weights" in result
        assert result["weights"]["rsi"] == 0.20
        assert result["weights"]["macd"] == 0.20
        assert result["weights"]["bollinger"] == 0.15
        assert result["weights"]["trend"] == 0.25
        assert result["weights"]["sr"] == 0.20

    @pytest.mark.asyncio
    async def test_composite_insufficient_data(self):
        """Tool raises ValueError with too few bars."""
        bars = [
            {"date": "2025-01-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}
            for _ in range(10)
        ]
        with pytest.raises(ValueError, match="Insufficient data"):
            await compute_technical_score("AAPL", bars)

    @pytest.mark.asyncio
    async def test_uptrend_produces_bullish(self):
        """50 bars in uptrend should produce buy or strong_buy."""
        bars = []
        base = 100.0
        for i in range(50):
            p = base + i * 0.5
            bars.append({
                "date": f"2025-01-{(i % 28) + 1:02d}" if i < 28 else f"2025-02-{(i - 28) + 1:02d}",
                "open": p,
                "high": p + 1.0,
                "low": p - 0.5,
                "close": p + 0.3,
                "volume": 1000000,
            })
        result = await compute_technical_score("TEST", bars)
        # In a clear uptrend, score should be above neutral
        assert result["composite_score"] >= 40.0

    @pytest.mark.asyncio
    async def test_downtrend_produces_bearish(self):
        """50 bars in downtrend should produce sell or strong_sell."""
        bars = []
        base = 200.0
        for i in range(50):
            p = base - i * 0.5
            bars.append({
                "date": f"2025-01-{(i % 28) + 1:02d}" if i < 28 else f"2025-02-{(i - 28) + 1:02d}",
                "open": p,
                "high": p + 0.5,
                "low": p - 1.0,
                "close": p - 0.3,
                "volume": 1000000,
            })
        result = await compute_technical_score("TEST", bars)
        # In a clear downtrend, score should be below neutral
        assert result["composite_score"] <= 60.0
```

---

## Agent Handler (tccw-qitp-agents)

---

### `blueprints/agents/technical_analyzer.yaml`

```yaml
agent_id: technical-analyzer
name: Technical Analysis Agent
version: "1.0.0"
description: >
  Computes technical analysis indicators for a list of symbols and produces
  a TechnicalAnalysisReport artifact. Uses market-data-mcp for OHLCV and
  technical-mcp for indicator computation. Fills the 20% technical_score
  weight in the composite scoring formula.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 4096
  temperature: 0.1

system_prompt_id: technical-analyzer-system-v1

tools:
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_ohlcv
  - name: technical-mcp
    type: mcp
    uri: "${TECHNICAL_MCP_URI}"
    operations:
      - compute_rsi
      - compute_macd
      - compute_bollinger_bands
      - compute_atr
      - compute_moving_averages
      - compute_trend_alignment
      - compute_support_resistance
      - compute_technical_score
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact

execution:
  timeout_seconds: 90
  max_tool_calls: 100
  retry_policy:
    max_retries: 2
    backoff_base: 1.0

output_schema: TechnicalAnalysisReport

tags:
  - technical-analysis
  - indicators
  - phase-2
```

---

### `src/qitp_agents/technical_analyzer/__init__.py`

```python
"""Technical Analysis Agent — computes indicators and technical scores for symbols."""
```

---

### `src/qitp_agents/technical_analyzer/handler.py`

```python
"""Technical Analysis Agent Lambda handler.

Input:  {"symbols": ["AAPL", "TSLA", ...], "date": "2026-03-15", "lookback_days": 200}
Output: TechnicalAnalysisReport JSON artifact with per-symbol technical scores.

Architecture:
- Single Strands agent (no multi-agent pattern)
- Tools: market-data-mcp (get_ohlcv for bar data)
- Tools: technical-mcp (all indicator computations)
- Tools: artifacts-mcp (create_artifact for report storage)

The agent fetches OHLCV bars from market-data-mcp, passes them to
technical-mcp for indicator computation, then assembles the report.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "lambda"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "technical-analyzer"
MAX_OUTPUT_BYTES = 256 * 1024  # 256KB claim-check threshold


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Technical Analysis Agent.

    Args:
        event: Input payload with symbols, date, and optional lookback_days.
        context: Lambda context (optional).

    Returns:
        JSON response with technical analysis report or claim-check reference.
    """
    logger.info(
        "Technical analyzer invoked",
        extra={"symbol_count": len(event.get("symbols", []))},
    )

    symbols = event.get("symbols", [])
    date = event.get("date")
    lookback_days = event.get("lookback_days", 200)

    if not symbols:
        return _error_response("Missing required field: symbols")
    if not date:
        return _error_response("Missing required field: date")

    try:
        mcp_clients = _create_mcp_clients()

        # Build agent from blueprint
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Construct the agent prompt
        symbols_str = ", ".join(symbols)
        prompt = (
            f"Compute technical analysis for the following symbols on {date}: {symbols_str}\n"
            f"Use a lookback period of {lookback_days} days for indicator computation.\n\n"
            f"For each symbol:\n"
            f"1. Call get_ohlcv(symbol, start=date-{lookback_days}d, end=date) to fetch bars.\n"
            f"2. Call compute_technical_score(symbol, bars) to get the composite 0-100 score.\n"
            f"3. If the composite score is >= 60 or <= 40 (non-neutral), also fetch:\n"
            f"   - compute_rsi for detailed RSI analysis\n"
            f"   - compute_macd for crossover details\n"
            f"   - compute_bollinger_bands for band positioning\n"
            f"   - compute_support_resistance for key levels\n"
            f"4. Record: symbol, composite_score, signal, confidence, and any notable indicators.\n\n"
            f"After all symbols are processed:\n"
            f"5. Create a TechnicalAnalysisReport artifact with all per-symbol results.\n"
            f"6. Include overall_market_technical_score (average of all composites).\n"
            f"7. Flag symbols with score >= 70 as 'strong_technical' and <= 30 as 'weak_technical'.\n"
            f"8. Return the artifact ID and the technical_scores array."
        )

        result = agent(prompt)
        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Technical analyzer failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    market_data_uri = os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8001")
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=market_data_uri,
    )

    technical_uri = os.environ.get("TECHNICAL_MCP_URI", "http://localhost:8009")
    clients["technical-mcp"] = create_mcp_client(
        name="technical-mcp",
        uri=technical_uri,
    )

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8002")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check for large outputs."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        logger.warning("Output exceeds 256KB, storing claim-check reference")
        output = {
            "claim_check": True,
            "message": "Output exceeded 256KB. Full result stored as artifact.",
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(data)}


def _error_response(message: str) -> dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": message})}
```

---

### `tests/unit/test_technical_analyzer.py`

```python
"""Unit tests for Technical Analysis Agent handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_technical_data():
    """Sample technical analysis output."""
    return {
        "technical_scores": [
            {
                "symbol": "AAPL",
                "composite_score": 72.5,
                "signal": "buy",
                "confidence": 0.78,
                "rsi": {"value": 42.0, "signal": "neutral"},
                "macd": {"crossover": "bullish", "histogram_direction": "expanding"},
                "bollinger": {"percent_b": 0.35, "signal": "mid_range"},
                "trend": {"alignment_score": 0.67, "dominant_direction": "bullish"},
                "sr": {"nearest_support": 148.0, "nearest_resistance": 162.0},
            },
            {
                "symbol": "TSLA",
                "composite_score": 35.2,
                "signal": "sell",
                "confidence": 0.65,
                "rsi": {"value": 68.0, "signal": "neutral"},
                "macd": {"crossover": "bearish", "histogram_direction": "expanding"},
            },
        ],
        "overall_market_technical_score": 53.85,
        "strong_technical": ["AAPL"],
        "weak_technical": ["TSLA"],
        "artifact_id": "tech-report-2026-03-15",
    }


class TestTechnicalAnalyzerHandler:
    """Tests for technical_analyzer.handler.handler()."""

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_success(self, mock_loader, mock_mcp, sample_technical_data):
        """Handler returns technical report on valid input."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_technical_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.technical_analyzer.handler import handler

        result = handler({
            "symbols": ["AAPL", "TSLA"],
            "date": "2026-03-15",
        })

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "technical_scores" in body
        assert "overall_market_technical_score" in body

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_missing_symbols(self, mock_loader, mock_mcp):
        """Handler returns error when symbols list is missing."""
        from qitp_agents.technical_analyzer.handler import handler

        result = handler({"date": "2026-03-15"})
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "symbols" in body["error"]

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_missing_date(self, mock_loader, mock_mcp):
        """Handler returns error when date is missing."""
        from qitp_agents.technical_analyzer.handler import handler

        result = handler({"symbols": ["AAPL"]})
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "date" in body["error"]

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_custom_lookback(self, mock_loader, mock_mcp, sample_technical_data):
        """Handler accepts custom lookback_days parameter."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_technical_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.technical_analyzer.handler import handler

        result = handler({
            "symbols": ["AAPL"],
            "date": "2026-03-15",
            "lookback_days": 60,
        })

        assert result["statusCode"] == 200
        # Verify agent was called (prompt should include 60 days)
        mock_agent.assert_called_once()
        prompt = mock_agent.call_args[0][0]
        assert "60" in prompt

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_agent_exception(self, mock_loader, mock_mcp):
        """Handler returns error when agent throws exception."""
        mock_agent = MagicMock()
        mock_agent.side_effect = RuntimeError("MCP connection failed")
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.technical_analyzer.handler import handler

        result = handler({"symbols": ["AAPL"], "date": "2026-03-15"})
        assert result["statusCode"] == 500

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_claim_check_large_output(self, mock_loader, mock_mcp):
        """Handler returns claim-check when output exceeds 256KB."""
        large_data = {
            "technical_scores": [{"symbol": f"SYM{i}", "data": "x" * 1000} for i in range(300)],
            "artifact_id": "large-report-123",
        }
        mock_agent = MagicMock()
        mock_agent.return_value = large_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.technical_analyzer.handler import handler

        result = handler({"symbols": ["AAPL"], "date": "2026-03-15"})
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body.get("claim_check") is True

    @patch("qitp_agents.technical_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.technical_analyzer.handler.LOADER")
    def test_handler_builds_correct_agent(self, mock_loader, mock_mcp, sample_technical_data):
        """Verify the loader is asked to build the technical-analyzer agent."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_technical_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.technical_analyzer.handler import handler

        handler({"symbols": ["AAPL"], "date": "2026-03-15"})

        mock_loader.build_strands_agent.assert_called_once()
        call_args = mock_loader.build_strands_agent.call_args
        assert call_args[0][0] == "technical-analyzer"
```

---

## Acceptance Criteria

- [ ] MCP server starts and lists 8 tools via `list_tools()`
- [ ] `compute_rsi` returns correct RSI with overbought/oversold classification
- [ ] `compute_macd` detects bullish/bearish crossovers correctly
- [ ] `compute_bollinger_bands` detects squeeze conditions
- [ ] `compute_atr` classifies volatility levels correctly
- [ ] `compute_moving_averages` detects golden/death cross
- [ ] `compute_trend_alignment` aligns multi-timeframe trends
- [ ] `compute_support_resistance` finds nearest S/R levels
- [ ] `compute_technical_score` produces composite 0-100 score with correct sub-weights: RSI(20%) + MACD(20%) + Bollinger(15%) + Trend(25%) + S/R(20%)
- [ ] Uptrend data produces bullish signals; downtrend produces bearish signals
- [ ] Agent handler instantiates correctly from blueprint YAML
- [ ] Agent handler returns structured JSON with `statusCode`
- [ ] Claim-check triggers for outputs exceeding 256KB
- [ ] Docker build succeeds
- [ ] All tests pass

## Test Plan

```bash
# MCP server tests
cd ~/dev/tccw-qitp-mcp-technical
pip install -e ".[dev]"
pytest -v

# Agent handler tests
cd ~/dev/tccw-qitp-agents
pip install -e ".[dev]"
pytest tests/unit/test_technical_analyzer.py -v

# Docker build
cd ~/dev/tccw-qitp-mcp-technical
docker build -t qitp-mcp-technical .
```

## Agent Instructions

This MCP server is pure computation — no external API calls, no S3, no Redis. It receives OHLCV bars as input and returns indicator results. This makes it the simplest MCP to build and test since all calculations are deterministic and self-contained.

Key implementation notes:
1. **No external dependencies at runtime**: All indicator calculations use numpy/pandas on data passed in via tool arguments. The MCP never fetches data itself — the agent (or another MCP) provides the bars.
2. **Indicator formulas must be exact**: RSI uses Wilder's smoothing, MACD uses standard EMA, Bollinger uses population std dev. These are industry-standard formulas — deviations will produce wrong trading signals.
3. **Sub-weights are non-negotiable**: RSI(20%) + MACD(20%) + Bollinger(15%) + Trend(25%) + S/R(20%) = 100%. These are defined in `scoring.py` and exposed in the `TechnicalScore.weights` field for transparency.
4. **Composite fills the 20% technical slot**: The composite 0-100 score maps to the `technical_score` field consumed by the Portfolio Recommender. Score 50 = neutral, >50 = bullish, <50 = bearish.
5. **Bars are passed as dicts, not fetched**: Each tool receives `bars: list[dict]` as input. The agent handler coordinates: it calls market-data-mcp for OHLCV, then passes those bars to technical-mcp tools.
6. **Port 8009 in docker-compose**: Maps to internal 8080. This is the 9th MCP server (after the 8 defined in Phase 1/2).
