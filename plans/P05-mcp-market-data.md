# P05 — Market Data MCP Server

## Objective
Build `market-data-mcp`: an MCP server providing unified market data access. Routes to S3 parquet (backtest) or live providers (paper/live). 8 tools covering OHLCV, gaps, volume, and watchlist operations.

## Plane Tickets
ROOT-52

## Target Repo
`~/dev/tccw-qitp-mcp-market-data`

## Dependencies
P02 (core schemas — stub if needed)

## Repo Structure
```
tccw-qitp-mcp-market-data/
├── src/
│   └── qitp_mcp_market_data/
│       ├── __init__.py
│       ├── server.py           # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── ohlcv.py        # get_ohlcv tool
│       │   ├── gaps.py         # get_gap, get_watchlist_gaps, get_friday_close, get_monday_open
│       │   ├── price.py        # get_current_price
│       │   ├── volume.py       # get_volume_profile
│       │   └── watchlist.py    # get_watchlist
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract DataProvider
│       │   ├── s3_parquet.py   # S3ParquetProvider (backtest mode)
│       │   ├── polygon.py      # PolygonProvider (live mode)
│       │   └── yahoo.py        # YahooProvider (fallback)
│       ├── cache.py            # Redis caching layer
│       └── schemas.py          # GapResult, Bar, WatchlistItem, VolumeProfile
├── tests/
│   ├── conftest.py
│   ├── test_gaps.py
│   ├── test_ohlcv.py
│   ├── test_providers.py
│   └── fixtures/
│       └── sample_data.parquet
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
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
name = "qitp-mcp-market-data"
version = "0.1.0"
description = "QITP Market Data MCP Server — unified market data access for backtest and live modes"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0",
    "pyarrow>=14.0",
    "pandas>=2.1",
    "boto3>=1.34",
    "redis>=5.0",
    "httpx>=0.27",
    "yfinance>=0.2.36",
    "uvicorn>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "moto[s3]>=5.0",
    "fakeredis>=2.21",
]

[project.scripts]
market-data-mcp = "qitp_mcp_market_data.server:main"
```

---

### `src/qitp_mcp_market_data/__init__.py`

```python
"""QITP Market Data MCP Server."""

__version__ = "0.1.0"
```

---

### `src/qitp_mcp_market_data/schemas.py`

```python
"""Shared data schemas for market data MCP server."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Bar(BaseModel):
    """Single OHLCV bar."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None


class GapResult(BaseModel):
    """Weekend gap calculation result."""

    symbol: str
    date: date  # Monday date
    friday_close: float
    monday_open: float
    gap_pct: float  # Signed: positive=up, negative=down
    gap_abs_pct: float  # abs(gap_pct)
    direction: Literal["up", "down"]
    volume_ratio: float  # Monday volume / 20-day avg volume
    significant: bool  # True if abs(gap_pct) >= threshold
    gap_type: str | None = None  # breakaway|runaway|exhaustion|common


class WatchlistItem(BaseModel):
    """A symbol on the watchlist."""

    symbol: str
    name: str
    asset_type: Literal["stock", "etf", "fund"]
    market: Literal["us", "es", "eu"]
    sector: str
    currency: Literal["USD", "EUR"]
    gap_threshold_pct: float = 2.0
    active: bool = True
    tags: list[str] = Field(default_factory=list)


class VolumeProfile(BaseModel):
    """Volume profile for a symbol on a given date."""

    symbol: str
    date: date
    total_volume: int
    avg_volume_20d: int
    volume_ratio: float  # total_volume / avg_volume_20d
    vwap: float
    high_volume_nodes: list[float] = Field(default_factory=list)  # Price levels with high volume
    low_volume_nodes: list[float] = Field(default_factory=list)   # Price levels with low volume


class BacktestModeError(Exception):
    """Raised when a live-only operation is attempted in backtest mode."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"Operation '{operation}' is not available in backtest mode. "
            "There is no concept of 'current' price in backtest."
        )
        self.operation = operation
```

---

### `src/qitp_mcp_market_data/cache.py`

```python
"""Redis caching layer for market data."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    """Lazy-init Redis client. Returns None if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis cache connected at %s", redis_url)
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable at %s — caching disabled", redis_url)
        _redis_client = None
        return None


def _override_redis(client):
    """Override the Redis client (for testing with fakeredis)."""
    global _redis_client
    _redis_client = client


def _cache_key(namespace: str, **kwargs) -> str:
    """Build a deterministic cache key."""
    raw = json.dumps(kwargs, sort_keys=True, default=str)
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"mktdata:{namespace}:{h}"


def cache_get(namespace: str, **kwargs) -> Any | None:
    """Get a value from cache. Returns None on miss or if Redis unavailable."""
    r = _get_redis()
    if r is None:
        return None
    key = _cache_key(namespace, **kwargs)
    try:
        val = r.get(key)
        if val is not None:
            return json.loads(val)
    except Exception:
        logger.debug("Cache get failed for %s", key)
    return None


def cache_set(namespace: str, value: Any, ttl_seconds: int = 300, **kwargs) -> None:
    """Set a value in cache with TTL."""
    r = _get_redis()
    if r is None:
        return
    key = _cache_key(namespace, **kwargs)
    try:
        r.setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception:
        logger.debug("Cache set failed for %s", key)
```

---

### `src/qitp_mcp_market_data/providers/__init__.py`

```python
"""Data provider implementations."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import DataProvider


def get_provider() -> DataProvider:
    """Return the appropriate DataProvider based on EXECUTION_MODE env var.

    - backtest  -> S3ParquetProvider
    - paper     -> PolygonProvider (Yahoo fallback handled internally)
    - live      -> PolygonProvider (Yahoo fallback handled internally)
    """
    mode = os.environ.get("EXECUTION_MODE", "backtest").lower()

    if mode == "backtest":
        from .s3_parquet import S3ParquetProvider

        return S3ParquetProvider()
    elif mode in ("paper", "live"):
        from .polygon import PolygonProvider

        return PolygonProvider()
    else:
        raise ValueError(
            f"Unknown EXECUTION_MODE={mode!r}. Expected: backtest, paper, live"
        )
```

---

### `src/qitp_mcp_market_data/providers/base.py`

```python
"""Abstract base class for data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from qitp_mcp_market_data.schemas import Bar, VolumeProfile, WatchlistItem


class DataProvider(ABC):
    """Abstract data provider — all providers implement this interface."""

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> list[Bar]:
        """Fetch OHLCV bars for a symbol in a date range."""
        ...

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get the latest price for a symbol. Not available in backtest mode."""
        ...

    @abstractmethod
    async def get_bar(self, symbol: str, target_date: date) -> Bar | None:
        """Get a single bar for a specific date. Returns None if no data."""
        ...

    @abstractmethod
    async def get_volume_profile(self, symbol: str, target_date: date) -> VolumeProfile:
        """Get volume profile data for a symbol on a date."""
        ...

    @abstractmethod
    async def get_watchlist(self) -> list[WatchlistItem]:
        """Get all active watchlist items."""
        ...
```

---

### `src/qitp_mcp_market_data/providers/s3_parquet.py`

```python
"""S3 Parquet data provider for backtest mode."""

from __future__ import annotations

import io
import logging
import os
from datetime import date, timedelta

import boto3
import pandas as pd
import pyarrow.parquet as pq

from qitp_mcp_market_data.schemas import (
    BacktestModeError,
    Bar,
    VolumeProfile,
    WatchlistItem,
)

from .base import DataProvider

logger = logging.getLogger(__name__)


class S3ParquetProvider(DataProvider):
    """Reads market data from S3 parquet files.

    Bucket layout:
        s3://{bucket}/{symbol}/{year}/{month:02d}.parquet

    Each parquet file contains daily bars for a month with columns:
        date, open, high, low, close, volume, adjusted_close
    """

    def __init__(
        self,
        bucket: str | None = None,
        s3_client=None,
    ) -> None:
        self.bucket = bucket or os.environ.get(
            "S3_MARKET_DATA_BUCKET", "qitp-historical-data"
        )
        self._s3 = s3_client or boto3.client("s3")
        self._watchlist_key = os.environ.get(
            "WATCHLIST_S3_KEY", "config/watchlist.json"
        )

    def _parquet_key(self, symbol: str, year: int, month: int) -> str:
        return f"{symbol}/{year}/{month:02d}.parquet"

    def _read_parquet(self, key: str) -> pd.DataFrame:
        """Download and read a parquet file from S3."""
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=key)
            buf = io.BytesIO(resp["Body"].read())
            table = pq.read_table(buf)
            return table.to_pandas()
        except self._s3.exceptions.NoSuchKey:
            logger.warning("Parquet not found: s3://%s/%s", self.bucket, key)
            return pd.DataFrame()
        except Exception:
            logger.exception("Error reading s3://%s/%s", self.bucket, key)
            return pd.DataFrame()

    def _load_range(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Load and concatenate all monthly parquet files spanning [start, end]."""
        frames: list[pd.DataFrame] = []
        current = date(start.year, start.month, 1)
        end_month = date(end.year, end.month, 1)

        while current <= end_month:
            key = self._parquet_key(symbol, current.year, current.month)
            df = self._read_parquet(key)
            if not df.empty:
                frames.append(df)
            # Advance to next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined["date"] = pd.to_datetime(combined["date"]).dt.date
        mask = (combined["date"] >= start) & (combined["date"] <= end)
        return combined[mask].sort_values("date").reset_index(drop=True)

    async def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> list[Bar]:
        if interval != "1d":
            raise NotImplementedError(
                f"S3ParquetProvider only supports '1d' interval, got '{interval}'"
            )
        df = self._load_range(symbol, start, end)
        bars: list[Bar] = []
        for _, row in df.iterrows():
            bars.append(
                Bar(
                    date=row["date"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    adjusted_close=float(row["adjusted_close"])
                    if "adjusted_close" in row and pd.notna(row.get("adjusted_close"))
                    else None,
                )
            )
        return bars

    async def get_current_price(self, symbol: str) -> float:
        raise BacktestModeError("get_current_price")

    async def get_bar(self, symbol: str, target_date: date) -> Bar | None:
        bars = await self.get_ohlcv(symbol, target_date, target_date)
        return bars[0] if bars else None

    async def get_volume_profile(self, symbol: str, target_date: date) -> VolumeProfile:
        bar = await self.get_bar(symbol, target_date)
        if bar is None:
            raise ValueError(
                f"No data for {symbol} on {target_date}"
            )

        # 20-day lookback for average volume
        lookback_start = target_date - timedelta(days=40)  # Extra days for weekends/holidays
        history = await self.get_ohlcv(symbol, lookback_start, target_date - timedelta(days=1))
        recent_bars = history[-20:] if len(history) >= 20 else history
        avg_vol = int(sum(b.volume for b in recent_bars) / len(recent_bars)) if recent_bars else bar.volume

        volume_ratio = bar.volume / avg_vol if avg_vol > 0 else 1.0
        vwap = (bar.high + bar.low + bar.close) / 3  # Simplified VWAP for daily bars

        return VolumeProfile(
            symbol=symbol,
            date=target_date,
            total_volume=bar.volume,
            avg_volume_20d=avg_vol,
            volume_ratio=round(volume_ratio, 4),
            vwap=round(vwap, 4),
            high_volume_nodes=[],
            low_volume_nodes=[],
        )

    async def get_watchlist(self) -> list[WatchlistItem]:
        """Load watchlist from S3 JSON file."""
        import json

        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=self._watchlist_key)
            data = json.loads(resp["Body"].read().decode("utf-8"))
            return [WatchlistItem(**item) for item in data if item.get("active", True)]
        except Exception:
            logger.exception("Failed to load watchlist from S3")
            return []
```

---

### `src/qitp_mcp_market_data/providers/polygon.py`

```python
"""Polygon.io data provider for live/paper modes with Yahoo Finance fallback."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import httpx

from qitp_mcp_market_data.schemas import Bar, VolumeProfile, WatchlistItem

from .base import DataProvider

logger = logging.getLogger(__name__)

_POLYGON_BASE = "https://api.polygon.io"


class PolygonProvider(DataProvider):
    """Polygon.io REST API provider with Yahoo Finance fallback.

    Uses $POLYGON_API_KEY environment variable for authentication.
    Falls back to YahooProvider if Polygon requests fail.
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get("POLYGON_API_KEY", "")
        if not self._api_key:
            logger.warning(
                "POLYGON_API_KEY not set — all requests will fall back to Yahoo Finance"
            )
        self._client = httpx.AsyncClient(timeout=30.0)
        self._fallback: DataProvider | None = None

    def _get_fallback(self) -> DataProvider:
        if self._fallback is None:
            from .yahoo import YahooProvider

            self._fallback = YahooProvider()
        return self._fallback

    async def _polygon_get(self, path: str, params: dict | None = None) -> dict:
        """Make a GET request to Polygon.io."""
        params = params or {}
        params["apiKey"] = self._api_key
        url = f"{_POLYGON_BASE}{path}"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> list[Bar]:
        multiplier, timespan = _parse_interval(interval)

        try:
            data = await self._polygon_get(
                f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}",
                params={"adjusted": "true", "sort": "asc", "limit": "50000"},
            )
            results = data.get("results", [])
            bars: list[Bar] = []
            for r in results:
                ts_ms = r["t"]
                bar_date = date.fromtimestamp(ts_ms / 1000)
                bars.append(
                    Bar(
                        date=bar_date,
                        open=r["o"],
                        high=r["h"],
                        low=r["l"],
                        close=r["c"],
                        volume=int(r["v"]),
                        adjusted_close=r.get("vw"),
                    )
                )
            return bars
        except Exception:
            logger.warning("Polygon OHLCV failed for %s, falling back to Yahoo", symbol)
            return await self._get_fallback().get_ohlcv(symbol, start, end, interval)

    async def get_current_price(self, symbol: str) -> float:
        try:
            data = await self._polygon_get(f"/v2/last/trade/{symbol}")
            return float(data["results"]["p"])
        except Exception:
            logger.warning("Polygon current price failed for %s, falling back to Yahoo", symbol)
            return await self._get_fallback().get_current_price(symbol)

    async def get_bar(self, symbol: str, target_date: date) -> Bar | None:
        bars = await self.get_ohlcv(symbol, target_date, target_date)
        return bars[0] if bars else None

    async def get_volume_profile(self, symbol: str, target_date: date) -> VolumeProfile:
        bar = await self.get_bar(symbol, target_date)
        if bar is None:
            raise ValueError(f"No data for {symbol} on {target_date}")

        lookback_start = target_date - timedelta(days=40)
        history = await self.get_ohlcv(symbol, lookback_start, target_date - timedelta(days=1))
        recent_bars = history[-20:] if len(history) >= 20 else history
        avg_vol = int(sum(b.volume for b in recent_bars) / len(recent_bars)) if recent_bars else bar.volume
        volume_ratio = bar.volume / avg_vol if avg_vol > 0 else 1.0
        vwap = (bar.high + bar.low + bar.close) / 3

        return VolumeProfile(
            symbol=symbol,
            date=target_date,
            total_volume=bar.volume,
            avg_volume_20d=avg_vol,
            volume_ratio=round(volume_ratio, 4),
            vwap=round(vwap, 4),
        )

    async def get_watchlist(self) -> list[WatchlistItem]:
        """Load watchlist from a JSON config file.

        In live/paper mode the watchlist lives in a local or S3 config.
        For simplicity, we read from WATCHLIST_PATH env var (a local JSON file).
        """
        import json

        path = os.environ.get("WATCHLIST_PATH", "config/watchlist.json")
        try:
            with open(path) as f:
                data = json.load(f)
            return [WatchlistItem(**item) for item in data if item.get("active", True)]
        except FileNotFoundError:
            logger.warning("Watchlist file not found at %s", path)
            return []


def _parse_interval(interval: str) -> tuple[int, str]:
    """Convert interval string to Polygon multiplier + timespan."""
    mapping = {
        "1d": (1, "day"),
        "1h": (1, "hour"),
        "5m": (5, "minute"),
    }
    if interval not in mapping:
        raise ValueError(f"Unsupported interval: {interval!r}. Supported: {list(mapping)}")
    return mapping[interval]
```

---

### `src/qitp_mcp_market_data/providers/yahoo.py`

```python
"""Yahoo Finance data provider (free fallback, no API key needed)."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from qitp_mcp_market_data.schemas import Bar, VolumeProfile, WatchlistItem

from .base import DataProvider

logger = logging.getLogger(__name__)


class YahooProvider(DataProvider):
    """Yahoo Finance provider using yfinance. Free, no API key required."""

    async def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> list[Bar]:
        import yfinance as yf

        interval_map = {"1d": "1d", "1h": "1h", "5m": "5m"}
        yf_interval = interval_map.get(interval)
        if yf_interval is None:
            raise ValueError(f"Unsupported interval: {interval}")

        ticker = yf.Ticker(symbol)
        # yfinance end date is exclusive; add 1 day
        df = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval=yf_interval,
        )

        bars: list[Bar] = []
        for idx, row in df.iterrows():
            bar_date = idx.date() if hasattr(idx, "date") else idx
            bars.append(
                Bar(
                    date=bar_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                    adjusted_close=None,
                )
            )
        return bars

    async def get_current_price(self, symbol: str) -> float:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if price is None:
            raise ValueError(f"Cannot get current price for {symbol} from Yahoo Finance")
        return float(price)

    async def get_bar(self, symbol: str, target_date: date) -> Bar | None:
        bars = await self.get_ohlcv(symbol, target_date, target_date)
        return bars[0] if bars else None

    async def get_volume_profile(self, symbol: str, target_date: date) -> VolumeProfile:
        bar = await self.get_bar(symbol, target_date)
        if bar is None:
            raise ValueError(f"No data for {symbol} on {target_date}")

        lookback_start = target_date - timedelta(days=40)
        history = await self.get_ohlcv(symbol, lookback_start, target_date - timedelta(days=1))
        recent_bars = history[-20:] if len(history) >= 20 else history
        avg_vol = int(sum(b.volume for b in recent_bars) / len(recent_bars)) if recent_bars else bar.volume
        volume_ratio = bar.volume / avg_vol if avg_vol > 0 else 1.0
        vwap = (bar.high + bar.low + bar.close) / 3

        return VolumeProfile(
            symbol=symbol,
            date=target_date,
            total_volume=bar.volume,
            avg_volume_20d=avg_vol,
            volume_ratio=round(volume_ratio, 4),
            vwap=round(vwap, 4),
        )

    async def get_watchlist(self) -> list[WatchlistItem]:
        """Yahoo provider does not manage a watchlist."""
        logger.warning("YahooProvider.get_watchlist() called — not supported, returning empty list")
        return []
```

---

### `src/qitp_mcp_market_data/tools/__init__.py`

```python
"""MCP tool implementations for market data server."""
```

---

### `src/qitp_mcp_market_data/tools/ohlcv.py`

```python
"""get_ohlcv tool — fetch OHLCV bars for a symbol."""

from __future__ import annotations

from datetime import date

from qitp_mcp_market_data.cache import cache_get, cache_set
from qitp_mcp_market_data.providers import get_provider
from qitp_mcp_market_data.schemas import Bar


async def get_ohlcv(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
) -> list[dict]:
    """Fetch OHLCV bars for a symbol in a date range.

    Args:
        symbol: Ticker symbol (e.g. "AAPL", "SPY").
        start: Start date in ISO format (YYYY-MM-DD).
        end: End date in ISO format (YYYY-MM-DD).
        interval: Bar interval — "1d", "1h", or "5m".

    Returns:
        List of bar dictionaries with date, open, high, low, close, volume.
    """
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    # Check cache
    cached = cache_get("ohlcv", symbol=symbol, start=start, end=end, interval=interval)
    if cached is not None:
        return cached

    provider = get_provider()
    bars: list[Bar] = await provider.get_ohlcv(symbol, start_date, end_date, interval)
    result = [bar.model_dump(mode="json") for bar in bars]

    # Cache for 5 minutes
    cache_set("ohlcv", result, ttl_seconds=300, symbol=symbol, start=start, end=end, interval=interval)

    return result
```

---

### `src/qitp_mcp_market_data/tools/gaps.py`

```python
"""Gap calculation tools — the core business logic of the market data server.

Gap formula: gap_pct = ((monday_open - friday_close) / friday_close) * 100
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from qitp_mcp_market_data.cache import cache_get, cache_set
from qitp_mcp_market_data.providers import get_provider
from qitp_mcp_market_data.schemas import Bar, GapResult

logger = logging.getLogger(__name__)


def _previous_friday(monday: date) -> date:
    """Given a Monday date, return the preceding Friday."""
    if monday.weekday() != 0:
        raise ValueError(f"Expected a Monday, got {monday} (weekday={monday.weekday()})")
    return monday - timedelta(days=3)


def _classify_gap(gap_abs_pct: float) -> str:
    """Classify gap type based on magnitude.

    Simplified classification:
    - common: < 1%
    - breakaway: 1-3%
    - runaway: 3-5%
    - exhaustion: > 5%
    """
    if gap_abs_pct < 1.0:
        return "common"
    elif gap_abs_pct < 3.0:
        return "breakaway"
    elif gap_abs_pct < 5.0:
        return "runaway"
    else:
        return "exhaustion"


def _compute_gap(
    symbol: str,
    monday_date: date,
    friday_close: float,
    monday_open: float,
    monday_volume: int,
    avg_volume_20d: int,
    threshold_pct: float = 2.0,
) -> GapResult:
    """Core gap calculation."""
    gap_pct = ((monday_open - friday_close) / friday_close) * 100
    gap_abs_pct = abs(gap_pct)
    direction = "up" if gap_pct >= 0 else "down"
    volume_ratio = monday_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0

    return GapResult(
        symbol=symbol,
        date=monday_date,
        friday_close=round(friday_close, 4),
        monday_open=round(monday_open, 4),
        gap_pct=round(gap_pct, 4),
        gap_abs_pct=round(gap_abs_pct, 4),
        direction=direction,
        volume_ratio=round(volume_ratio, 4),
        significant=gap_abs_pct >= threshold_pct,
        gap_type=_classify_gap(gap_abs_pct),
    )


async def _get_avg_volume_20d(symbol: str, before_date: date) -> int:
    """Get the 20-day average volume for a symbol before a given date."""
    provider = get_provider()
    lookback_start = before_date - timedelta(days=40)
    bars = await provider.get_ohlcv(symbol, lookback_start, before_date - timedelta(days=1))
    recent = bars[-20:] if len(bars) >= 20 else bars
    if not recent:
        return 0
    return int(sum(b.volume for b in recent) / len(recent))


async def get_friday_close(symbol: str, date_str: str) -> float:
    """Get the Friday closing price preceding the given Monday.

    Args:
        symbol: Ticker symbol.
        date_str: A Monday date in ISO format (YYYY-MM-DD).

    Returns:
        Friday closing price as float.
    """
    monday = date.fromisoformat(date_str)
    friday = _previous_friday(monday)

    provider = get_provider()
    bar = await provider.get_bar(symbol, friday)
    if bar is None:
        raise ValueError(f"No data for {symbol} on Friday {friday}")
    return bar.close


async def get_monday_open(symbol: str, date_str: str) -> float:
    """Get the Monday opening price.

    Args:
        symbol: Ticker symbol.
        date_str: A Monday date in ISO format (YYYY-MM-DD).

    Returns:
        Monday opening price as float.
    """
    monday = date.fromisoformat(date_str)
    if monday.weekday() != 0:
        raise ValueError(f"Expected a Monday, got {monday} (weekday={monday.weekday()})")

    provider = get_provider()
    bar = await provider.get_bar(symbol, monday)
    if bar is None:
        raise ValueError(f"No data for {symbol} on Monday {monday}")
    return bar.open


async def get_gap(symbol: str, date_str: str, threshold_pct: float = 2.0) -> dict:
    """Calculate the weekend gap for a symbol on a given Monday.

    Args:
        symbol: Ticker symbol.
        date_str: A Monday date in ISO format (YYYY-MM-DD).
        threshold_pct: Threshold for marking gap as significant (default 2.0%).

    Returns:
        GapResult as dictionary.
    """
    monday = date.fromisoformat(date_str)
    friday = _previous_friday(monday)

    # Check cache
    cached = cache_get("gap", symbol=symbol, date=date_str, threshold=threshold_pct)
    if cached is not None:
        return cached

    provider = get_provider()

    friday_bar = await provider.get_bar(symbol, friday)
    monday_bar = await provider.get_bar(symbol, monday)

    if friday_bar is None:
        raise ValueError(f"No Friday data for {symbol} on {friday}")
    if monday_bar is None:
        raise ValueError(f"No Monday data for {symbol} on {monday}")

    avg_vol = await _get_avg_volume_20d(symbol, monday)

    result = _compute_gap(
        symbol=symbol,
        monday_date=monday,
        friday_close=friday_bar.close,
        monday_open=monday_bar.open,
        monday_volume=monday_bar.volume,
        avg_volume_20d=avg_vol,
        threshold_pct=threshold_pct,
    )

    result_dict = result.model_dump(mode="json")
    cache_set("gap", result_dict, ttl_seconds=600, symbol=symbol, date=date_str, threshold=threshold_pct)
    return result_dict


async def get_watchlist_gaps(date_str: str, threshold_pct: float = 2.0) -> list[dict]:
    """Calculate weekend gaps for all active watchlist symbols.

    Args:
        date_str: A Monday date in ISO format (YYYY-MM-DD).
        threshold_pct: Minimum abs(gap_pct) to include in results (default 2.0%).

    Returns:
        List of GapResult dicts, filtered by threshold, sorted by abs(gap_pct) descending.
    """
    monday = date.fromisoformat(date_str)
    if monday.weekday() != 0:
        raise ValueError(f"Expected a Monday, got {monday} (weekday={monday.weekday()})")

    provider = get_provider()
    watchlist = await provider.get_watchlist()

    if not watchlist:
        logger.warning("Empty watchlist — no gaps to calculate")
        return []

    results: list[GapResult] = []
    for item in watchlist:
        try:
            gap_dict = await get_gap(item.symbol, date_str, threshold_pct=threshold_pct)
            gap = GapResult(**gap_dict)
            if gap.gap_abs_pct >= threshold_pct:
                results.append(gap)
        except Exception:
            logger.warning("Failed to calculate gap for %s on %s", item.symbol, date_str)
            continue

    # Sort by abs(gap_pct) descending
    results.sort(key=lambda g: g.gap_abs_pct, reverse=True)

    return [r.model_dump(mode="json") for r in results]
```

---

### `src/qitp_mcp_market_data/tools/price.py`

```python
"""get_current_price tool."""

from __future__ import annotations

from qitp_mcp_market_data.cache import cache_get, cache_set
from qitp_mcp_market_data.providers import get_provider


async def get_current_price(symbol: str) -> float:
    """Get the current/latest price for a symbol.

    Not available in backtest mode (raises BacktestModeError).

    Args:
        symbol: Ticker symbol (e.g. "AAPL").

    Returns:
        Current price as float.
    """
    cached = cache_get("current_price", symbol=symbol)
    if cached is not None:
        return cached

    provider = get_provider()
    price = await provider.get_current_price(symbol)

    # Short TTL — price changes frequently
    cache_set("current_price", price, ttl_seconds=15, symbol=symbol)

    return price
```

---

### `src/qitp_mcp_market_data/tools/volume.py`

```python
"""get_volume_profile tool."""

from __future__ import annotations

from qitp_mcp_market_data.cache import cache_get, cache_set
from qitp_mcp_market_data.providers import get_provider

from datetime import date


async def get_volume_profile(symbol: str, date_str: str) -> dict:
    """Get the volume profile for a symbol on a specific date.

    Args:
        symbol: Ticker symbol.
        date_str: Date in ISO format (YYYY-MM-DD).

    Returns:
        VolumeProfile as dictionary.
    """
    cached = cache_get("volume_profile", symbol=symbol, date=date_str)
    if cached is not None:
        return cached

    target_date = date.fromisoformat(date_str)
    provider = get_provider()
    profile = await provider.get_volume_profile(symbol, target_date)

    result = profile.model_dump(mode="json")
    cache_set("volume_profile", result, ttl_seconds=300, symbol=symbol, date=date_str)
    return result
```

---

### `src/qitp_mcp_market_data/tools/watchlist.py`

```python
"""get_watchlist tool."""

from __future__ import annotations

from qitp_mcp_market_data.cache import cache_get, cache_set
from qitp_mcp_market_data.providers import get_provider


async def get_watchlist() -> list[dict]:
    """Get all active symbols on the watchlist.

    Returns:
        List of WatchlistItem dictionaries.
    """
    cached = cache_get("watchlist")
    if cached is not None:
        return cached

    provider = get_provider()
    items = await provider.get_watchlist()

    result = [item.model_dump(mode="json") for item in items]
    cache_set("watchlist", result, ttl_seconds=60)
    return result
```

---

### `src/qitp_mcp_market_data/server.py`

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
logger = logging.getLogger("qitp_mcp_market_data")

# ---------------------------------------------------------------------------
# Build the MCP server
# ---------------------------------------------------------------------------

server = Server("market-data-mcp")


# ---------------------------------------------------------------------------
# Tool definitions (list_tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="get_ohlcv",
        description=(
            "Fetch OHLCV bars for a symbol in a date range. "
            "Interval: '1d', '1h', or '5m'. "
            "In backtest mode only '1d' is supported."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL, SPY)"},
                "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                "interval": {
                    "type": "string",
                    "enum": ["1d", "1h", "5m"],
                    "default": "1d",
                    "description": "Bar interval",
                },
            },
            "required": ["symbol", "start", "end"],
        },
    ),
    Tool(
        name="get_current_price",
        description=(
            "Get the latest/current price for a symbol. "
            "NOT available in backtest mode — will raise BacktestModeError."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_friday_close",
        description="Get the Friday closing price preceding a given Monday.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "date": {"type": "string", "description": "A Monday date YYYY-MM-DD"},
            },
            "required": ["symbol", "date"],
        },
    ),
    Tool(
        name="get_monday_open",
        description="Get the Monday opening price for a given Monday.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "date": {"type": "string", "description": "A Monday date YYYY-MM-DD"},
            },
            "required": ["symbol", "date"],
        },
    ),
    Tool(
        name="get_gap",
        description=(
            "Calculate the weekend gap for a symbol on a given Monday. "
            "gap_pct = ((monday_open - friday_close) / friday_close) * 100"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "date": {"type": "string", "description": "A Monday date YYYY-MM-DD"},
                "threshold_pct": {
                    "type": "number",
                    "default": 2.0,
                    "description": "Threshold for marking gap as significant (%)",
                },
            },
            "required": ["symbol", "date"],
        },
    ),
    Tool(
        name="get_watchlist_gaps",
        description=(
            "Calculate weekend gaps for all active watchlist symbols. "
            "Returns results filtered by threshold and sorted by abs(gap_pct) descending."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "A Monday date YYYY-MM-DD"},
                "threshold_pct": {
                    "type": "number",
                    "default": 2.0,
                    "description": "Minimum abs(gap_pct) to include (%)",
                },
            },
            "required": ["date"],
        },
    ),
    Tool(
        name="get_volume_profile",
        description="Get volume profile data for a symbol on a specific date.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "date": {"type": "string", "description": "Date YYYY-MM-DD"},
            },
            "required": ["symbol", "date"],
        },
    ),
    Tool(
        name="get_watchlist",
        description="Get all active symbols on the watchlist.",
        inputSchema={
            "type": "object",
            "properties": {},
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
    if name == "get_ohlcv":
        from qitp_mcp_market_data.tools.ohlcv import get_ohlcv

        return await get_ohlcv(
            symbol=arguments["symbol"],
            start=arguments["start"],
            end=arguments["end"],
            interval=arguments.get("interval", "1d"),
        )

    elif name == "get_current_price":
        from qitp_mcp_market_data.tools.price import get_current_price

        return await get_current_price(symbol=arguments["symbol"])

    elif name == "get_friday_close":
        from qitp_mcp_market_data.tools.gaps import get_friday_close

        return await get_friday_close(
            symbol=arguments["symbol"],
            date_str=arguments["date"],
        )

    elif name == "get_monday_open":
        from qitp_mcp_market_data.tools.gaps import get_monday_open

        return await get_monday_open(
            symbol=arguments["symbol"],
            date_str=arguments["date"],
        )

    elif name == "get_gap":
        from qitp_mcp_market_data.tools.gaps import get_gap

        return await get_gap(
            symbol=arguments["symbol"],
            date_str=arguments["date"],
            threshold_pct=arguments.get("threshold_pct", 2.0),
        )

    elif name == "get_watchlist_gaps":
        from qitp_mcp_market_data.tools.gaps import get_watchlist_gaps

        return await get_watchlist_gaps(
            date_str=arguments["date"],
            threshold_pct=arguments.get("threshold_pct", 2.0),
        )

    elif name == "get_volume_profile":
        from qitp_mcp_market_data.tools.volume import get_volume_profile

        return await get_volume_profile(
            symbol=arguments["symbol"],
            date_str=arguments["date"],
        )

    elif name == "get_watchlist":
        from qitp_mcp_market_data.tools.watchlist import get_watchlist

        return await get_watchlist()

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
        # Streamable HTTP transport for production
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

### `tests/conftest.py`

```python
"""Shared test fixtures for market data MCP server tests."""

from __future__ import annotations

import io
import json
import os
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


@pytest.fixture(autouse=True)
def _set_backtest_mode(monkeypatch):
    """Default all tests to backtest mode."""
    monkeypatch.setenv("EXECUTION_MODE", "backtest")


@pytest.fixture
def sample_bars_df() -> pd.DataFrame:
    """DataFrame with sample daily bars spanning two weeks including a Monday gap."""
    data = {
        "date": [
            date(2025, 1, 6),   # Monday
            date(2025, 1, 7),   # Tuesday
            date(2025, 1, 8),   # Wednesday
            date(2025, 1, 9),   # Thursday
            date(2025, 1, 10),  # Friday
            date(2025, 1, 13),  # Monday (gap day)
            date(2025, 1, 14),  # Tuesday
            date(2025, 1, 15),  # Wednesday
            date(2025, 1, 16),  # Thursday
            date(2025, 1, 17),  # Friday
            date(2025, 1, 20),  # Monday (gap day 2) — MLK holiday but pretend it traded
        ],
        "open":  [150.0, 151.0, 152.0, 151.5, 153.0, 157.0, 156.5, 157.0, 158.0, 159.0, 155.0],
        "high":  [152.0, 153.0, 153.5, 153.0, 154.0, 158.0, 158.0, 158.5, 159.0, 160.0, 157.0],
        "low":   [149.0, 150.0, 151.0, 150.5, 152.0, 155.0, 155.5, 156.0, 157.0, 158.0, 153.0],
        "close": [151.0, 152.0, 151.5, 153.0, 153.5, 156.5, 157.0, 158.0, 159.0, 159.5, 155.5],
        "volume": [1000000, 1100000, 950000, 1050000, 1200000, 1500000, 1300000, 1250000, 1100000, 1400000, 1600000],
        "adjusted_close": [151.0, 152.0, 151.5, 153.0, 153.5, 156.5, 157.0, 158.0, 159.0, 159.5, 155.5],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_parquet_bytes(sample_bars_df) -> bytes:
    """Sample bars as parquet bytes."""
    table = pa.Table.from_pandas(sample_bars_df)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


@pytest.fixture
def mock_s3_client(sample_parquet_bytes):
    """Mock boto3 S3 client that serves sample parquet data."""
    client = MagicMock()

    class NoSuchKey(Exception):
        pass

    client.exceptions = MagicMock()
    client.exceptions.NoSuchKey = NoSuchKey

    def get_object(Bucket, Key):
        # Serve data for AAPL in January 2025
        if "AAPL" in Key and "2025" in Key and "01" in Key:
            body = MagicMock()
            body.read.return_value = sample_parquet_bytes
            return {"Body": body}
        raise NoSuchKey(f"Not found: {Key}")

    client.get_object = MagicMock(side_effect=get_object)
    return client


@pytest.fixture
def watchlist_items() -> list[dict]:
    """Sample watchlist for testing."""
    return [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "asset_type": "stock",
            "market": "us",
            "sector": "Technology",
            "currency": "USD",
            "gap_threshold_pct": 2.0,
            "active": True,
            "tags": ["tech", "mega-cap"],
        },
        {
            "symbol": "SPY",
            "name": "SPDR S&P 500 ETF",
            "asset_type": "etf",
            "market": "us",
            "sector": "Index",
            "currency": "USD",
            "gap_threshold_pct": 1.0,
            "active": True,
            "tags": ["index", "benchmark"],
        },
    ]


@pytest.fixture
def mock_s3_client_with_watchlist(mock_s3_client, watchlist_items, sample_parquet_bytes):
    """Mock S3 client that also serves a watchlist JSON."""
    original_get = mock_s3_client.get_object.side_effect

    def get_object(Bucket, Key):
        if Key == "config/watchlist.json":
            body = MagicMock()
            body.read.return_value = json.dumps(watchlist_items).encode("utf-8")
            return {"Body": body}
        return original_get(Bucket=Bucket, Key=Key)

    mock_s3_client.get_object = MagicMock(side_effect=get_object)
    return mock_s3_client
```

---

### `tests/test_ohlcv.py`

```python
"""Tests for the get_ohlcv tool and S3 parquet reading."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from qitp_mcp_market_data.providers.s3_parquet import S3ParquetProvider
from qitp_mcp_market_data.tools.ohlcv import get_ohlcv


@pytest.mark.asyncio
async def test_s3_parquet_provider_reads_bars(mock_s3_client):
    """S3ParquetProvider should read bars from mock parquet files."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)
    bars = await provider.get_ohlcv("AAPL", date(2025, 1, 6), date(2025, 1, 10))

    assert len(bars) == 5
    assert bars[0].date == date(2025, 1, 6)
    assert bars[0].open == 150.0
    assert bars[-1].date == date(2025, 1, 10)
    assert bars[-1].close == 153.5


@pytest.mark.asyncio
async def test_s3_parquet_provider_filters_date_range(mock_s3_client):
    """Bars outside the requested range should be excluded."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)
    bars = await provider.get_ohlcv("AAPL", date(2025, 1, 8), date(2025, 1, 9))

    assert len(bars) == 2
    assert bars[0].date == date(2025, 1, 8)
    assert bars[1].date == date(2025, 1, 9)


@pytest.mark.asyncio
async def test_s3_parquet_provider_empty_for_unknown_symbol(mock_s3_client):
    """Unknown symbols should return empty list."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)
    bars = await provider.get_ohlcv("ZZZZ", date(2025, 1, 6), date(2025, 1, 10))

    assert bars == []


@pytest.mark.asyncio
async def test_s3_parquet_provider_rejects_non_daily_interval(mock_s3_client):
    """S3 provider only supports '1d' interval."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with pytest.raises(NotImplementedError, match="1d"):
        await provider.get_ohlcv("AAPL", date(2025, 1, 6), date(2025, 1, 10), interval="5m")


@pytest.mark.asyncio
async def test_get_ohlcv_tool(mock_s3_client):
    """The get_ohlcv tool function should return serialized bars."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with patch("qitp_mcp_market_data.tools.ohlcv.get_provider", return_value=provider):
        result = await get_ohlcv("AAPL", "2025-01-06", "2025-01-10")

    assert len(result) == 5
    assert result[0]["open"] == 150.0
    assert result[0]["date"] == "2025-01-06"
```

---

### `tests/test_gaps.py`

```python
"""Tests for gap calculation — the core business logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from qitp_mcp_market_data.providers.s3_parquet import S3ParquetProvider
from qitp_mcp_market_data.schemas import GapResult
from qitp_mcp_market_data.tools.gaps import (
    _classify_gap,
    _compute_gap,
    _previous_friday,
    get_friday_close,
    get_gap,
    get_monday_open,
    get_watchlist_gaps,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestPreviousFriday:
    def test_normal_monday(self):
        assert _previous_friday(date(2025, 1, 13)) == date(2025, 1, 10)

    def test_raises_on_non_monday(self):
        with pytest.raises(ValueError, match="Expected a Monday"):
            _previous_friday(date(2025, 1, 14))  # Tuesday


class TestClassifyGap:
    def test_common(self):
        assert _classify_gap(0.5) == "common"

    def test_breakaway(self):
        assert _classify_gap(2.0) == "breakaway"

    def test_runaway(self):
        assert _classify_gap(4.0) == "runaway"

    def test_exhaustion(self):
        assert _classify_gap(7.0) == "exhaustion"


class TestComputeGap:
    def test_positive_gap(self):
        """Monday opens higher than Friday close -> positive gap."""
        result = _compute_gap(
            symbol="TEST",
            monday_date=date(2025, 1, 13),
            friday_close=100.0,
            monday_open=103.0,
            monday_volume=1500000,
            avg_volume_20d=1000000,
            threshold_pct=2.0,
        )
        assert result.gap_pct == 3.0
        assert result.gap_abs_pct == 3.0
        assert result.direction == "up"
        assert result.significant is True
        assert result.volume_ratio == 1.5
        assert result.gap_type == "breakaway"

    def test_negative_gap(self):
        """Monday opens lower than Friday close -> negative gap."""
        result = _compute_gap(
            symbol="TEST",
            monday_date=date(2025, 1, 13),
            friday_close=100.0,
            monday_open=95.0,
            monday_volume=800000,
            avg_volume_20d=1000000,
            threshold_pct=2.0,
        )
        assert result.gap_pct == -5.0
        assert result.gap_abs_pct == 5.0
        assert result.direction == "down"
        assert result.significant is True

    def test_below_threshold(self):
        """Small gap should not be marked as significant."""
        result = _compute_gap(
            symbol="TEST",
            monday_date=date(2025, 1, 13),
            friday_close=100.0,
            monday_open=100.5,
            monday_volume=1000000,
            avg_volume_20d=1000000,
            threshold_pct=2.0,
        )
        assert result.gap_pct == 0.5
        assert result.significant is False

    def test_gap_formula_precision(self):
        """Verify the exact gap formula: ((monday_open - friday_close) / friday_close) * 100."""
        friday_close = 153.5
        monday_open = 157.0
        expected = ((157.0 - 153.5) / 153.5) * 100  # ~2.2801...

        result = _compute_gap(
            symbol="AAPL",
            monday_date=date(2025, 1, 13),
            friday_close=friday_close,
            monday_open=monday_open,
            monday_volume=1500000,
            avg_volume_20d=1100000,
            threshold_pct=2.0,
        )
        assert abs(result.gap_pct - round(expected, 4)) < 0.001


# ---------------------------------------------------------------------------
# Integration tests with mock S3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_friday_close(mock_s3_client):
    """get_friday_close should return the Friday closing price."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with patch("qitp_mcp_market_data.tools.gaps.get_provider", return_value=provider):
        price = await get_friday_close("AAPL", "2025-01-13")

    assert price == 153.5  # Friday Jan 10 close


@pytest.mark.asyncio
async def test_get_monday_open(mock_s3_client):
    """get_monday_open should return the Monday opening price."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with patch("qitp_mcp_market_data.tools.gaps.get_provider", return_value=provider):
        price = await get_monday_open("AAPL", "2025-01-13")

    assert price == 157.0  # Monday Jan 13 open


@pytest.mark.asyncio
async def test_get_monday_open_rejects_non_monday(mock_s3_client):
    """get_monday_open should raise if date is not a Monday."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with patch("qitp_mcp_market_data.tools.gaps.get_provider", return_value=provider):
        with pytest.raises(ValueError, match="Expected a Monday"):
            await get_monday_open("AAPL", "2025-01-14")


@pytest.mark.asyncio
async def test_get_gap(mock_s3_client):
    """get_gap should return a correct GapResult."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with patch("qitp_mcp_market_data.tools.gaps.get_provider", return_value=provider):
        result = await get_gap("AAPL", "2025-01-13")

    assert result["symbol"] == "AAPL"
    assert result["friday_close"] == 153.5
    assert result["monday_open"] == 157.0

    expected_gap = ((157.0 - 153.5) / 153.5) * 100
    assert abs(result["gap_pct"] - round(expected_gap, 4)) < 0.01
    assert result["direction"] == "up"
    assert result["significant"] is True


@pytest.mark.asyncio
async def test_get_gap_negative(mock_s3_client):
    """Test a Monday that opens lower (Jan 20 in our fixture data)."""
    provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

    with patch("qitp_mcp_market_data.tools.gaps.get_provider", return_value=provider):
        result = await get_gap("AAPL", "2025-01-20")

    # Friday Jan 17 close = 159.5, Monday Jan 20 open = 155.0
    assert result["friday_close"] == 159.5
    assert result["monday_open"] == 155.0
    expected_gap = ((155.0 - 159.5) / 159.5) * 100  # ~-2.82
    assert result["gap_pct"] < 0
    assert result["direction"] == "down"
    assert abs(result["gap_pct"] - round(expected_gap, 4)) < 0.01


@pytest.mark.asyncio
async def test_get_watchlist_gaps(mock_s3_client_with_watchlist):
    """get_watchlist_gaps should return sorted gaps for all watchlist symbols."""
    provider = S3ParquetProvider(
        bucket="test-bucket", s3_client=mock_s3_client_with_watchlist
    )

    with patch("qitp_mcp_market_data.tools.gaps.get_provider", return_value=provider):
        results = await get_watchlist_gaps("2025-01-13", threshold_pct=2.0)

    # AAPL should have a ~2.28% gap which passes threshold.
    # SPY is not in our parquet data, so it should be skipped.
    assert len(results) >= 1
    # Verify sorted by abs(gap_pct) descending
    for i in range(len(results) - 1):
        assert results[i]["gap_abs_pct"] >= results[i + 1]["gap_abs_pct"]
```

---

### `tests/test_providers.py`

```python
"""Tests for provider routing and the abstract base."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from qitp_mcp_market_data.providers import get_provider
from qitp_mcp_market_data.providers.base import DataProvider
from qitp_mcp_market_data.providers.s3_parquet import S3ParquetProvider
from qitp_mcp_market_data.schemas import BacktestModeError


class TestProviderRouting:
    def test_backtest_returns_s3(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "backtest")
        provider = get_provider()
        assert isinstance(provider, S3ParquetProvider)

    def test_paper_returns_polygon(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "paper")
        provider = get_provider()
        # Can't import PolygonProvider at top level without polygon key,
        # so just check it's not S3
        assert not isinstance(provider, S3ParquetProvider)

    def test_live_returns_polygon(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "live")
        provider = get_provider()
        assert not isinstance(provider, S3ParquetProvider)

    def test_unknown_mode_raises(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_MODE", "invalid")
        with pytest.raises(ValueError, match="Unknown EXECUTION_MODE"):
            get_provider()


class TestBacktestModeError:
    @pytest.mark.asyncio
    async def test_current_price_raises_in_backtest(self, mock_s3_client):
        provider = S3ParquetProvider(bucket="test-bucket", s3_client=mock_s3_client)

        with pytest.raises(BacktestModeError, match="get_current_price"):
            await provider.get_current_price("AAPL")
```

---

### `tests/fixtures/sample_data.parquet`

This file should be generated by the test setup. The `conftest.py` creates parquet data dynamically via `sample_parquet_bytes` fixture. A static fixture can be generated with:

```python
# Run once to generate: python -c "
import io, pandas as pd, pyarrow as pa, pyarrow.parquet as pq
from datetime import date
data = {
    'date': [date(2025,1,6), date(2025,1,7), date(2025,1,8), date(2025,1,9), date(2025,1,10),
             date(2025,1,13), date(2025,1,14), date(2025,1,15), date(2025,1,16), date(2025,1,17),
             date(2025,1,20)],
    'open':  [150.0, 151.0, 152.0, 151.5, 153.0, 157.0, 156.5, 157.0, 158.0, 159.0, 155.0],
    'high':  [152.0, 153.0, 153.5, 153.0, 154.0, 158.0, 158.0, 158.5, 159.0, 160.0, 157.0],
    'low':   [149.0, 150.0, 151.0, 150.5, 152.0, 155.0, 155.5, 156.0, 157.0, 158.0, 153.0],
    'close': [151.0, 152.0, 151.5, 153.0, 153.5, 156.5, 157.0, 158.0, 159.0, 159.5, 155.5],
    'volume': [1000000, 1100000, 950000, 1050000, 1200000, 1500000, 1300000, 1250000, 1100000, 1400000, 1600000],
    'adjusted_close': [151.0, 152.0, 151.5, 153.0, 153.5, 156.5, 157.0, 158.0, 159.0, 159.5, 155.5],
}
table = pa.Table.from_pandas(pd.DataFrame(data))
pq.write_table(table, 'tests/fixtures/sample_data.parquet')
# "
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
ENV EXECUTION_MODE=backtest

EXPOSE 8080

ENTRYPOINT ["market-data-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  market-data-mcp:
    build: .
    container_name: qitp-market-data-mcp
    ports:
      - "8080:8080"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8080
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - S3_MARKET_DATA_BUCKET=${S3_MARKET_DATA_BUCKET:-qitp-historical-data}
      - POLYGON_API_KEY=${POLYGON_API_KEY:-}
      - REDIS_URL=redis://redis:6379/0
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - qitp

  redis:
    image: redis:7-alpine
    container_name: qitp-market-data-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    volumes:
      - redis-data:/data
    networks:
      - qitp

volumes:
  redis-data:

networks:
  qitp:
    driver: bridge
```

---

## Acceptance Criteria

- [ ] MCP server starts and lists 8 tools
- [ ] `get_watchlist_gaps` returns correctly sorted `GapResult` items
- [ ] Gap calculation formula matches: `gap_pct = ((monday_open - friday_close) / friday_close) * 100`
- [ ] `S3ParquetProvider` reads parquet files correctly
- [ ] `EXECUTION_MODE` routing works (backtest -> S3, live -> Polygon)
- [ ] Docker build succeeds
- [ ] All tests pass

## Test Plan

```bash
cd ~/dev/tccw-qitp-mcp-market-data
pip install -e ".[dev]"
pytest -v
docker build -t qitp-mcp-market-data .
```

## Agent Instructions

This MCP server is the most-used data source in the platform. Every agent depends on it. The gap calculation is the core business logic -- get it right and test it thoroughly. Use the `mcp` Python SDK for the server. Keep providers truly pluggable via the abstract base class.

Key implementation notes:
1. **Gap formula is sacred**: `gap_pct = ((monday_open - friday_close) / friday_close) * 100`. Test edge cases (zero close, tiny gaps, large gaps).
2. **Provider routing**: `EXECUTION_MODE` env var controls which provider is used. Never call live APIs in backtest mode.
3. **S3 parquet layout**: `s3://{bucket}/{symbol}/{year}/{month:02d}.parquet`. The provider must load and concatenate multiple months when the date range spans months.
4. **Watchlist gaps sorting**: Always sort by `abs(gap_pct)` descending. Filter by threshold before returning.
5. **Error handling**: Return structured error JSON from tool calls, never crash the server.
6. **Credentials**: `POLYGON_API_KEY`, AWS credentials, and `REDIS_URL` are all via environment variables. Never hardcode.
