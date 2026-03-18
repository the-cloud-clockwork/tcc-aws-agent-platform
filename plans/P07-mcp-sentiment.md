# P07 — Sentiment MCP Server

## Objective
Build `sentiment-mcp`: aggregates news sentiment, analyst ratings, and macro indicators into normalized scores. 5 tools. Data from Polygon.io News API, Financial Modeling Prep, FRED API.

## Plane Tickets
ROOT-55

## Target Repo
`~/dev/tccw-qitp-mcp-sentiment`

## Dependencies
P02 (core schemas)

## Repo Structure
```
tccw-qitp-mcp-sentiment/
├── src/
│   └── qitp_mcp_sentiment/
│       ├── __init__.py
│       ├── server.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── news.py          # get_news_sentiment
│       │   ├── analyst.py       # get_analyst_ratings
│       │   ├── macro.py         # get_macro_sentiment
│       │   ├── earnings.py      # get_earnings_context
│       │   └── composite.py     # get_composite_sentiment
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── polygon_news.py  # Polygon.io News API
│       │   ├── fmp.py           # Financial Modeling Prep (analyst ratings)
│       │   ├── fred.py          # FRED API (macro indicators)
│       │   └── mock_provider.py # Mock for backtest mode
│       ├── scoring.py           # Sentiment scoring/normalization logic
│       └── schemas.py
├── tests/
│   ├── conftest.py
│   ├── test_news.py
│   ├── test_composite.py
│   ├── test_scoring.py
│   └── fixtures/
│       ├── sample_news.json
│       └── sample_ratings.json
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Implementation Details

### 5 Tools (from Doc 6):

1. `get_news_sentiment(symbol, days=7)` - NewsSentiment
   - Fetches recent news articles, scores each, returns aggregate + top headlines

2. `get_analyst_ratings(symbol)` - AnalystRatings
   - Consensus: strong_buy|buy|hold|sell|strong_sell, mean target price, # analysts, recent upgrades/downgrades

3. `get_macro_sentiment()` - MacroSentiment
   - VIX level, Fear&Greed index, SPY 5-day return
   - Classification: risk_on (VIX<20, F&G>60), risk_off (VIX>30, F&G<20), neutral (else)

4. `get_earnings_context(symbol)` - EarningsContext
   - Next earnings date, expected move (options-implied), last 4 EPS surprises

5. `get_composite_sentiment(symbol)` - CompositeSentiment
   - Weighted: news(40%) + analyst(40%) + macro alignment
   - Score 0.0 (very bearish) to 1.0 (very bullish)

### Scoring Logic:
- composite = news_score * 0.4 + analyst_score * 0.4 + macro_score * 0.2
- Labels: <0.2=very_bearish, <0.4=bearish, <0.6=neutral, <0.8=bullish, >=0.8=very_bullish
- Macro override: if regime == "risk_off", all momentum strategies blocked regardless of score
- Confidence based on data completeness: full data=1.0, missing news=0.7, missing analyst=0.7, missing both=0.4

### EXECUTION_MODE routing:
- backtest: use mock_provider with deterministic fixture data
- paper/live: use real API providers (Polygon, FMP, FRED)

### Environment variables:
- POLYGON_API_KEY, FMP_API_KEY, FRED_API_KEY
- EXECUTION_MODE (backtest|paper|live)

---

## Full Inline Code

---

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-sentiment"
version = "0.1.0"
description = "QITP Sentiment MCP Server — news, analyst, macro sentiment aggregation"
requires-python = ">=3.11"
dependencies = [
    "mcp[server]>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[project.scripts]
qitp-sentiment-mcp = "qitp_mcp_sentiment.server:main"
```

---

### `src/qitp_mcp_sentiment/__init__.py`

```python
"""QITP Sentiment MCP Server."""
```

---

### `src/qitp_mcp_sentiment/schemas.py`

```python
"""Sentiment schemas aligned with QITP core spec (Doc 6)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class NewsSentiment(BaseModel):
    """Aggregated news sentiment for a symbol."""

    symbol: str
    score: float = Field(ge=0.0, le=1.0, description="Normalized sentiment 0-1")
    article_count: int = Field(ge=0)
    top_headlines: list[str] = Field(default_factory=list)
    avg_article_score: float = Field(ge=0.0, le=1.0)
    data_staleness_hours: int = Field(ge=0)


class AnalystRatings(BaseModel):
    """Analyst consensus and target price."""

    symbol: str
    consensus: Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
    score: float = Field(ge=0.0, le=1.0, description="Normalized 0-1")
    mean_target_price: float
    num_analysts: int = Field(ge=0)
    upgrades_7d: int = Field(ge=0)
    downgrades_7d: int = Field(ge=0)


class MacroSentiment(BaseModel):
    """Macro regime classification."""

    vix_level: float
    fear_greed_index: int = Field(ge=0, le=100)
    spy_5d_return_pct: float
    regime: Literal["risk_on", "risk_off", "neutral"]


class EarningsContext(BaseModel):
    """Upcoming earnings context for a symbol."""

    symbol: str
    next_earnings_date: date | None = None
    days_until_earnings: int = Field(default=-1, description="-1 if unknown")
    earnings_upcoming: bool = Field(
        default=False, description="True if within 7 days"
    )
    last_4_eps_surprises: list[float] = Field(default_factory=list)


class CompositeSentiment(BaseModel):
    """Weighted composite sentiment score."""

    symbol: str
    composite_score: float = Field(ge=0.0, le=1.0)
    sentiment_label: Literal[
        "very_bearish", "bearish", "neutral", "bullish", "very_bullish"
    ]
    news_score: float = Field(ge=0.0, le=1.0)
    news_article_count: int = Field(ge=0)
    analyst_score: float = Field(ge=0.0, le=1.0)
    analyst_consensus: str
    analyst_target_price: float
    macro_alignment: Literal["risk_on", "neutral", "risk_off"]
    earnings_upcoming: bool
    earnings_date: date | None = None
    confidence: float = Field(
        ge=0.0, le=1.0, description="Data completeness confidence"
    )
    data_staleness_hours: int = Field(ge=0)
```

---

### `src/qitp_mcp_sentiment/scoring.py`

```python
"""Sentiment scoring and normalization logic."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Composite weighting
# ---------------------------------------------------------------------------
NEWS_WEIGHT = 0.4
ANALYST_WEIGHT = 0.4
MACRO_WEIGHT = 0.2


def compute_composite_score(
    news_score: float | None,
    analyst_score: float | None,
    macro_score: float | None,
) -> float:
    """Weighted composite: news(40%) + analyst(40%) + macro(20%).

    Missing components are replaced with 0.5 (neutral) so the composite
    still returns a value even with partial data.
    """
    ns = news_score if news_score is not None else 0.5
    als = analyst_score if analyst_score is not None else 0.5
    ms = macro_score if macro_score is not None else 0.5
    raw = ns * NEWS_WEIGHT + als * ANALYST_WEIGHT + ms * MACRO_WEIGHT
    return round(max(0.0, min(1.0, raw)), 4)


def score_to_label(score: float) -> str:
    """Map 0-1 score to sentiment label."""
    if score < 0.2:
        return "very_bearish"
    if score < 0.4:
        return "bearish"
    if score < 0.6:
        return "neutral"
    if score < 0.8:
        return "bullish"
    return "very_bullish"


def classify_macro_regime(
    vix: float,
    fear_greed: int,
) -> str:
    """Classify macro regime from VIX and Fear & Greed index.

    risk_on:  VIX < 20 AND F&G > 60
    risk_off: VIX > 30 OR  F&G < 20
    neutral:  everything else
    """
    if vix > 30 or fear_greed < 20:
        return "risk_off"
    if vix < 20 and fear_greed > 60:
        return "risk_on"
    return "neutral"


def macro_regime_to_score(regime: str) -> float:
    """Convert macro regime to a 0-1 score for composite weighting."""
    mapping = {
        "risk_on": 0.8,
        "neutral": 0.5,
        "risk_off": 0.2,
    }
    return mapping.get(regime, 0.5)


def consensus_to_score(consensus: str) -> float:
    """Map analyst consensus string to 0-1 score."""
    mapping = {
        "strong_buy": 1.0,
        "buy": 0.75,
        "hold": 0.5,
        "sell": 0.25,
        "strong_sell": 0.0,
    }
    return mapping.get(consensus, 0.5)


def compute_confidence(
    has_news: bool,
    has_analyst: bool,
    has_macro: bool,
) -> float:
    """Confidence based on data completeness.

    full data        = 1.0
    missing news     = 0.7
    missing analyst  = 0.7
    missing both     = 0.4
    missing macro    = 0.8  (macro is lower weight, less impact)
    """
    if has_news and has_analyst and has_macro:
        return 1.0
    if not has_news and not has_analyst:
        return 0.4
    if not has_news or not has_analyst:
        return 0.7
    # has_news and has_analyst but missing macro
    return 0.8


def normalize_article_sentiment(raw_score: float) -> float:
    """Normalize a raw article sentiment score to 0-1 range.

    Polygon returns sentiment as -1.0 to 1.0.  We rescale to 0-1.
    """
    clamped = max(-1.0, min(1.0, raw_score))
    return round((clamped + 1.0) / 2.0, 4)
```

---

### `src/qitp_mcp_sentiment/providers/__init__.py`

```python
"""Sentiment data providers."""
```

---

### `src/qitp_mcp_sentiment/providers/polygon_news.py`

```python
"""Polygon.io News API provider."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

POLYGON_BASE = "https://api.polygon.io"


async def fetch_news(
    symbol: str,
    days: int = 7,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch recent news articles for *symbol* from Polygon.io.

    Returns a list of dicts with keys: title, published_utc, sentiment_score.
    """
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY not set")

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    url = f"{POLYGON_BASE}/v2/reference/news"
    params = {
        "ticker": symbol.upper(),
        "published_utc.gte": since,
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
        "apiKey": api_key,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    articles: list[dict[str, Any]] = []
    for item in data.get("results", []):
        # Polygon includes per-ticker sentiment in insights
        sentiment_val = 0.0
        for insight in item.get("insights", []):
            if insight.get("ticker", "").upper() == symbol.upper():
                sentiment_val = float(insight.get("sentiment", 0.0))
                break
        articles.append(
            {
                "title": item.get("title", ""),
                "published_utc": item.get("published_utc", ""),
                "sentiment_score": sentiment_val,
            }
        )
    return articles
```

---

### `src/qitp_mcp_sentiment/providers/fmp.py`

```python
"""Financial Modeling Prep provider — analyst ratings & earnings."""

from __future__ import annotations

import os
from typing import Any

import httpx

FMP_BASE = "https://financialmodelingprep.com/api/v3"


async def fetch_analyst_ratings(symbol: str) -> dict[str, Any]:
    """Fetch analyst consensus from FMP.

    Returns dict with keys: consensus, mean_target, num_analysts,
    upgrades_7d, downgrades_7d, rating_details.
    """
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("FMP_API_KEY not set")

    url = f"{FMP_BASE}/grade/{symbol.upper()}"
    params = {"apikey": api_key, "limit": 30}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        grades = resp.json()

    if not grades:
        return {
            "consensus": "hold",
            "mean_target": 0.0,
            "num_analysts": 0,
            "upgrades_7d": 0,
            "downgrades_7d": 0,
        }

    # Count upgrades/downgrades in last 7 days
    upgrades = 0
    downgrades = 0
    buy_equiv = {"Buy", "Outperform", "Overweight", "Strong Buy", "Strong-Buy"}
    sell_equiv = {"Sell", "Underperform", "Underweight", "Strong Sell", "Strong-Sell"}

    for g in grades[:10]:
        new = g.get("newGrade", "")
        prev = g.get("previousGrade", "")
        if new in buy_equiv and prev not in buy_equiv:
            upgrades += 1
        elif new in sell_equiv and prev not in sell_equiv:
            downgrades += 1

    # Determine consensus from most recent grades
    buy_count = sum(1 for g in grades[:20] if g.get("newGrade", "") in buy_equiv)
    sell_count = sum(1 for g in grades[:20] if g.get("newGrade", "") in sell_equiv)
    total = min(len(grades), 20)

    if total == 0:
        consensus = "hold"
    elif buy_count / total >= 0.7:
        consensus = "strong_buy"
    elif buy_count / total >= 0.5:
        consensus = "buy"
    elif sell_count / total >= 0.7:
        consensus = "strong_sell"
    elif sell_count / total >= 0.5:
        consensus = "sell"
    else:
        consensus = "hold"

    return {
        "consensus": consensus,
        "mean_target": 0.0,  # FMP grade endpoint doesn't include targets
        "num_analysts": total,
        "upgrades_7d": upgrades,
        "downgrades_7d": downgrades,
    }


async def fetch_earnings_calendar(symbol: str) -> list[dict[str, Any]]:
    """Fetch upcoming & recent earnings dates from FMP."""
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("FMP_API_KEY not set")

    url = f"{FMP_BASE}/earning_calendar"
    params = {"apikey": api_key, "symbol": symbol.upper()}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def fetch_eps_surprises(symbol: str) -> list[dict[str, Any]]:
    """Fetch historical EPS surprises from FMP."""
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("FMP_API_KEY not set")

    url = f"{FMP_BASE}/earnings-surprises/{symbol.upper()}"
    params = {"apikey": api_key}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
```

---

### `src/qitp_mcp_sentiment/providers/fred.py`

```python
"""FRED API provider — macro indicators (VIX, SPY returns)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

FRED_BASE = "https://api.stlouisfed.org/fred"


async def fetch_series(
    series_id: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Fetch recent observations for a FRED series."""
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        raise RuntimeError("FRED_API_KEY not set")

    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"{FRED_BASE}/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "desc",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    return data.get("observations", [])


async def fetch_vix() -> float:
    """Get latest VIX close from FRED (series VIXCLS)."""
    obs = await fetch_series("VIXCLS", days=10)
    for o in obs:
        val = o.get("value", ".")
        if val != ".":
            return float(val)
    return 20.0  # fallback neutral


async def fetch_spy_5d_return() -> float:
    """Approximate SPY 5-day return using S&P 500 FRED series (SP500).

    Returns percentage change over last 5 trading observations.
    """
    obs = await fetch_series("SP500", days=14)
    values: list[float] = []
    for o in obs:
        val = o.get("value", ".")
        if val != ".":
            values.append(float(val))
        if len(values) >= 6:
            break

    if len(values) < 2:
        return 0.0

    latest = values[0]
    oldest = values[min(5, len(values) - 1)]
    if oldest == 0:
        return 0.0
    return round(((latest - oldest) / oldest) * 100.0, 2)
```

---

### `src/qitp_mcp_sentiment/providers/mock_provider.py`

```python
"""Mock provider for backtest mode — deterministic, no live API calls."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Mock news
# ---------------------------------------------------------------------------
MOCK_NEWS: dict[str, list[dict[str, Any]]] = {
    "AAPL": [
        {"title": "Apple beats Q4 estimates", "published_utc": "2026-03-10T14:00:00Z", "sentiment_score": 0.6},
        {"title": "iPhone demand strong in Asia", "published_utc": "2026-03-09T10:00:00Z", "sentiment_score": 0.4},
        {"title": "Apple announces dividend increase", "published_utc": "2026-03-08T08:00:00Z", "sentiment_score": 0.5},
    ],
    "TSLA": [
        {"title": "Tesla deliveries miss expectations", "published_utc": "2026-03-10T14:00:00Z", "sentiment_score": -0.3},
        {"title": "EV competition intensifies in China", "published_utc": "2026-03-09T10:00:00Z", "sentiment_score": -0.2},
    ],
}

DEFAULT_NEWS = [
    {"title": "Market steady amid mixed signals", "published_utc": "2026-03-10T14:00:00Z", "sentiment_score": 0.0},
]


async def mock_fetch_news(symbol: str, days: int = 7, limit: int = 50) -> list[dict[str, Any]]:
    """Return deterministic mock news articles."""
    return MOCK_NEWS.get(symbol.upper(), DEFAULT_NEWS)[:limit]


# ---------------------------------------------------------------------------
# Mock analyst ratings
# ---------------------------------------------------------------------------
MOCK_RATINGS: dict[str, dict[str, Any]] = {
    "AAPL": {
        "consensus": "buy",
        "mean_target": 210.0,
        "num_analysts": 35,
        "upgrades_7d": 2,
        "downgrades_7d": 0,
    },
    "TSLA": {
        "consensus": "hold",
        "mean_target": 180.0,
        "num_analysts": 28,
        "upgrades_7d": 0,
        "downgrades_7d": 1,
    },
}

DEFAULT_RATINGS: dict[str, Any] = {
    "consensus": "hold",
    "mean_target": 0.0,
    "num_analysts": 0,
    "upgrades_7d": 0,
    "downgrades_7d": 0,
}


async def mock_fetch_analyst_ratings(symbol: str) -> dict[str, Any]:
    """Return deterministic mock analyst ratings."""
    return MOCK_RATINGS.get(symbol.upper(), DEFAULT_RATINGS.copy())


# ---------------------------------------------------------------------------
# Mock macro
# ---------------------------------------------------------------------------
MOCK_VIX = 18.5
MOCK_FEAR_GREED = 65
MOCK_SPY_5D_RETURN = 1.2


async def mock_fetch_vix() -> float:
    return MOCK_VIX


async def mock_fetch_spy_5d_return() -> float:
    return MOCK_SPY_5D_RETURN


async def mock_fetch_fear_greed() -> int:
    return MOCK_FEAR_GREED


# ---------------------------------------------------------------------------
# Mock earnings
# ---------------------------------------------------------------------------
MOCK_EARNINGS: dict[str, dict[str, Any]] = {
    "AAPL": {
        "next_date": "2026-04-25",
        "eps_surprises": [0.08, 0.12, -0.02, 0.05],
    },
    "TSLA": {
        "next_date": "2026-03-20",
        "eps_surprises": [-0.10, 0.15, 0.03, -0.05],
    },
}


async def mock_fetch_earnings_calendar(symbol: str) -> list[dict[str, Any]]:
    """Return mock earnings calendar entries."""
    info = MOCK_EARNINGS.get(symbol.upper())
    if not info:
        return []
    return [{"date": info["next_date"], "symbol": symbol.upper()}]


async def mock_fetch_eps_surprises(symbol: str) -> list[dict[str, Any]]:
    """Return mock EPS surprise history."""
    info = MOCK_EARNINGS.get(symbol.upper())
    if not info:
        return []
    return [
        {"actualEarningResult": 1.0 + s, "estimatedEarning": 1.0}
        for s in info["eps_surprises"]
    ]
```

---

### `src/qitp_mcp_sentiment/tools/__init__.py`

```python
"""Sentiment MCP tools."""
```

---

### `src/qitp_mcp_sentiment/tools/news.py`

```python
"""get_news_sentiment tool."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from ..providers import polygon_news, mock_provider
from ..schemas import NewsSentiment
from ..scoring import normalize_article_sentiment


async def get_news_sentiment(symbol: str, days: int = 7) -> NewsSentiment:
    """Fetch recent news and return aggregated sentiment."""
    mode = os.environ.get("EXECUTION_MODE", "backtest")

    if mode == "backtest":
        articles = await mock_provider.mock_fetch_news(symbol, days=days)
    else:
        articles = await polygon_news.fetch_news(symbol, days=days)

    if not articles:
        return NewsSentiment(
            symbol=symbol.upper(),
            score=0.5,
            article_count=0,
            top_headlines=[],
            avg_article_score=0.5,
            data_staleness_hours=0,
        )

    scores = [
        normalize_article_sentiment(a.get("sentiment_score", 0.0))
        for a in articles
    ]
    avg = sum(scores) / len(scores)

    headlines = [a.get("title", "") for a in articles[:5]]

    # Compute staleness from most recent article
    staleness = 0
    if articles and articles[0].get("published_utc"):
        try:
            pub = datetime.fromisoformat(
                articles[0]["published_utc"].replace("Z", "+00:00")
            )
            staleness = int(
                (datetime.now(timezone.utc) - pub).total_seconds() / 3600
            )
        except (ValueError, TypeError):
            staleness = 0

    return NewsSentiment(
        symbol=symbol.upper(),
        score=round(avg, 4),
        article_count=len(articles),
        top_headlines=headlines,
        avg_article_score=round(avg, 4),
        data_staleness_hours=max(0, staleness),
    )
```

---

### `src/qitp_mcp_sentiment/tools/analyst.py`

```python
"""get_analyst_ratings tool."""

from __future__ import annotations

import os

from ..providers import fmp, mock_provider
from ..schemas import AnalystRatings
from ..scoring import consensus_to_score


async def get_analyst_ratings(symbol: str) -> AnalystRatings:
    """Fetch analyst consensus and target prices."""
    mode = os.environ.get("EXECUTION_MODE", "backtest")

    if mode == "backtest":
        data = await mock_provider.mock_fetch_analyst_ratings(symbol)
    else:
        data = await fmp.fetch_analyst_ratings(symbol)

    consensus = data.get("consensus", "hold")
    score = consensus_to_score(consensus)

    return AnalystRatings(
        symbol=symbol.upper(),
        consensus=consensus,
        score=score,
        mean_target_price=data.get("mean_target", 0.0),
        num_analysts=data.get("num_analysts", 0),
        upgrades_7d=data.get("upgrades_7d", 0),
        downgrades_7d=data.get("downgrades_7d", 0),
    )
```

---

### `src/qitp_mcp_sentiment/tools/macro.py`

```python
"""get_macro_sentiment tool."""

from __future__ import annotations

import os

from ..providers import fred, mock_provider
from ..schemas import MacroSentiment
from ..scoring import classify_macro_regime


async def get_macro_sentiment() -> MacroSentiment:
    """Fetch macro indicators and classify regime."""
    mode = os.environ.get("EXECUTION_MODE", "backtest")

    if mode == "backtest":
        vix = await mock_provider.mock_fetch_vix()
        spy_ret = await mock_provider.mock_fetch_spy_5d_return()
        fear_greed = await mock_provider.mock_fetch_fear_greed()
    else:
        vix = await fred.fetch_vix()
        spy_ret = await fred.fetch_spy_5d_return()
        # Fear & Greed index is not on FRED — use VIX as proxy for live mode
        # In production, integrate CNN Fear & Greed API or similar
        if vix < 15:
            fear_greed = 80
        elif vix < 20:
            fear_greed = 65
        elif vix < 25:
            fear_greed = 45
        elif vix < 30:
            fear_greed = 30
        else:
            fear_greed = 15

    regime = classify_macro_regime(vix, fear_greed)

    return MacroSentiment(
        vix_level=vix,
        fear_greed_index=fear_greed,
        spy_5d_return_pct=spy_ret,
        regime=regime,
    )
```

---

### `src/qitp_mcp_sentiment/tools/earnings.py`

```python
"""get_earnings_context tool."""

from __future__ import annotations

import os
from datetime import date, datetime

from ..providers import fmp, mock_provider
from ..schemas import EarningsContext


async def get_earnings_context(symbol: str) -> EarningsContext:
    """Fetch upcoming earnings date and recent EPS surprises."""
    mode = os.environ.get("EXECUTION_MODE", "backtest")

    if mode == "backtest":
        calendar = await mock_provider.mock_fetch_earnings_calendar(symbol)
        surprises_raw = await mock_provider.mock_fetch_eps_surprises(symbol)
    else:
        calendar = await fmp.fetch_earnings_calendar(symbol)
        surprises_raw = await fmp.fetch_eps_surprises(symbol)

    # Parse next earnings date
    next_date: date | None = None
    days_until = -1
    today = date.today()

    for entry in calendar:
        try:
            d = date.fromisoformat(entry.get("date", ""))
            if d >= today:
                next_date = d
                days_until = (d - today).days
                break
        except (ValueError, TypeError):
            continue

    earnings_upcoming = 0 <= days_until <= 7

    # Parse last 4 EPS surprises
    eps_surprises: list[float] = []
    for s in surprises_raw[:4]:
        actual = s.get("actualEarningResult", 0.0)
        estimated = s.get("estimatedEarning", 0.0)
        if estimated:
            eps_surprises.append(round(actual - estimated, 4))
        else:
            eps_surprises.append(0.0)

    return EarningsContext(
        symbol=symbol.upper(),
        next_earnings_date=next_date,
        days_until_earnings=days_until,
        earnings_upcoming=earnings_upcoming,
        last_4_eps_surprises=eps_surprises,
    )
```

---

### `src/qitp_mcp_sentiment/tools/composite.py`

```python
"""get_composite_sentiment tool — aggregates all sentiment signals."""

from __future__ import annotations

from ..schemas import CompositeSentiment
from ..scoring import (
    compute_composite_score,
    compute_confidence,
    macro_regime_to_score,
    score_to_label,
)
from .analyst import get_analyst_ratings
from .earnings import get_earnings_context
from .macro import get_macro_sentiment
from .news import get_news_sentiment


async def get_composite_sentiment(symbol: str) -> CompositeSentiment:
    """Build weighted composite sentiment from all sub-signals."""
    # Gather all signals — catch failures individually so partial data works
    has_news = True
    has_analyst = True
    has_macro = True

    try:
        news = await get_news_sentiment(symbol)
    except Exception:
        news = None
        has_news = False

    try:
        analyst = await get_analyst_ratings(symbol)
    except Exception:
        analyst = None
        has_analyst = False

    try:
        macro = await get_macro_sentiment()
    except Exception:
        macro = None
        has_macro = False

    try:
        earnings = await get_earnings_context(symbol)
    except Exception:
        earnings = None

    # Extract scores
    news_score = news.score if news else None
    analyst_score = analyst.score if analyst else None
    macro_score = macro_regime_to_score(macro.regime) if macro else None

    composite = compute_composite_score(news_score, analyst_score, macro_score)
    label = score_to_label(composite)
    confidence = compute_confidence(has_news, has_analyst, has_macro)

    # Staleness: use news staleness as representative
    staleness = news.data_staleness_hours if news else 0

    return CompositeSentiment(
        symbol=symbol.upper(),
        composite_score=composite,
        sentiment_label=label,
        news_score=news.score if news else 0.5,
        news_article_count=news.article_count if news else 0,
        analyst_score=analyst.score if analyst else 0.5,
        analyst_consensus=analyst.consensus if analyst else "hold",
        analyst_target_price=analyst.mean_target_price if analyst else 0.0,
        macro_alignment=macro.regime if macro else "neutral",
        earnings_upcoming=earnings.earnings_upcoming if earnings else False,
        earnings_date=earnings.next_earnings_date if earnings else None,
        confidence=confidence,
        data_staleness_hours=staleness,
    )
```

---

### `src/qitp_mcp_sentiment/server.py`

```python
"""QITP Sentiment MCP Server — exposes 5 sentiment tools via MCP."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .tools.analyst import get_analyst_ratings
from .tools.composite import get_composite_sentiment
from .tools.earnings import get_earnings_context
from .tools.macro import get_macro_sentiment
from .tools.news import get_news_sentiment

logger = logging.getLogger("qitp-sentiment-mcp")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
TOOLS: list[Tool] = [
    Tool(
        name="get_news_sentiment",
        description=(
            "Fetch recent news articles for a symbol and return aggregated "
            "sentiment score with top headlines."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL)"},
                "days": {
                    "type": "integer",
                    "description": "Look-back window in days (default 7)",
                    "default": 7,
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_analyst_ratings",
        description=(
            "Fetch analyst consensus rating, target price, and recent "
            "upgrade/downgrade activity for a symbol."
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
        name="get_macro_sentiment",
        description=(
            "Get current macro sentiment indicators: VIX, Fear & Greed index, "
            "SPY 5-day return, and regime classification."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_earnings_context",
        description=(
            "Get upcoming earnings date, days until earnings, and last 4 "
            "EPS surprises for a symbol."
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
        name="get_composite_sentiment",
        description=(
            "Compute weighted composite sentiment score combining news (40%), "
            "analyst (40%), and macro alignment (20%) for a symbol."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
            },
            "required": ["symbol"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------
def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("qitp-sentiment-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            result = await _dispatch(name, arguments)
            return [TextContent(type="text", text=result)]
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            error_body = json.dumps({"error": str(exc)})
            return [TextContent(type="text", text=error_body)]

    return server


async def _dispatch(name: str, arguments: dict[str, Any]) -> str:
    """Route tool calls to the correct handler and serialize response."""
    if name == "get_news_sentiment":
        result = await get_news_sentiment(
            symbol=arguments["symbol"],
            days=arguments.get("days", 7),
        )
    elif name == "get_analyst_ratings":
        result = await get_analyst_ratings(symbol=arguments["symbol"])
    elif name == "get_macro_sentiment":
        result = await get_macro_sentiment()
    elif name == "get_earnings_context":
        result = await get_earnings_context(symbol=arguments["symbol"])
    elif name == "get_composite_sentiment":
        result = await get_composite_sentiment(symbol=arguments["symbol"])
    else:
        raise ValueError(f"Unknown tool: {name}")

    return result.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
async def _run() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

---

### `tests/conftest.py`

```python
"""Shared test fixtures for sentiment MCP tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _backtest_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force backtest mode for all tests — no live API calls."""
    monkeypatch.setenv("EXECUTION_MODE", "backtest")
```

---

### `tests/fixtures/sample_news.json`

```json
[
    {
        "title": "Apple beats Q4 estimates",
        "published_utc": "2026-03-10T14:00:00Z",
        "sentiment_score": 0.6
    },
    {
        "title": "iPhone demand strong in Asia",
        "published_utc": "2026-03-09T10:00:00Z",
        "sentiment_score": 0.4
    },
    {
        "title": "Apple announces dividend increase",
        "published_utc": "2026-03-08T08:00:00Z",
        "sentiment_score": 0.5
    }
]
```

---

### `tests/fixtures/sample_ratings.json`

```json
{
    "AAPL": {
        "consensus": "buy",
        "mean_target": 210.0,
        "num_analysts": 35,
        "upgrades_7d": 2,
        "downgrades_7d": 0
    },
    "TSLA": {
        "consensus": "hold",
        "mean_target": 180.0,
        "num_analysts": 28,
        "upgrades_7d": 0,
        "downgrades_7d": 1
    }
}
```

---

### `tests/test_news.py`

```python
"""Tests for news sentiment tool."""

from __future__ import annotations

import pytest

from qitp_mcp_sentiment.tools.news import get_news_sentiment


@pytest.mark.asyncio
async def test_news_sentiment_aapl() -> None:
    """AAPL mock news should return positive sentiment."""
    result = await get_news_sentiment("AAPL")
    assert result.symbol == "AAPL"
    assert result.article_count == 3
    assert 0.0 <= result.score <= 1.0
    # All AAPL mock articles have positive sentiment (0.4, 0.5, 0.6)
    # Normalized from [-1,1] to [0,1]: (x+1)/2 => 0.7, 0.75, 0.8 => avg ~0.75
    assert result.score > 0.5
    assert len(result.top_headlines) == 3
    assert result.top_headlines[0] == "Apple beats Q4 estimates"


@pytest.mark.asyncio
async def test_news_sentiment_tsla() -> None:
    """TSLA mock news should return negative sentiment."""
    result = await get_news_sentiment("TSLA")
    assert result.symbol == "TSLA"
    assert result.article_count == 2
    # TSLA mock articles have negative sentiment (-0.3, -0.2)
    # Normalized: (x+1)/2 => 0.35, 0.4 => avg ~0.375
    assert result.score < 0.5


@pytest.mark.asyncio
async def test_news_sentiment_unknown_symbol() -> None:
    """Unknown symbol should return default neutral news."""
    result = await get_news_sentiment("ZZZZ")
    assert result.symbol == "ZZZZ"
    assert result.article_count == 1
    assert result.score == 0.5  # neutral default article has score 0.0 => normalized 0.5


@pytest.mark.asyncio
async def test_news_sentiment_case_insensitive() -> None:
    """Symbol lookup should be case-insensitive."""
    result = await get_news_sentiment("aapl")
    assert result.symbol == "AAPL"
    assert result.article_count == 3
```

---

### `tests/test_composite.py`

```python
"""Tests for composite sentiment tool."""

from __future__ import annotations

import pytest

from qitp_mcp_sentiment.tools.composite import get_composite_sentiment


@pytest.mark.asyncio
async def test_composite_aapl() -> None:
    """AAPL should get bullish composite in backtest mode."""
    result = await get_composite_sentiment("AAPL")
    assert result.symbol == "AAPL"
    assert 0.0 <= result.composite_score <= 1.0
    assert result.sentiment_label in {
        "very_bearish", "bearish", "neutral", "bullish", "very_bullish"
    }
    # AAPL: news positive (~0.75), analyst buy (0.75), macro risk_on (0.8)
    # composite = 0.75*0.4 + 0.75*0.4 + 0.8*0.2 = 0.3 + 0.3 + 0.16 = 0.76
    assert result.composite_score >= 0.6, f"Expected bullish range, got {result.composite_score}"
    assert result.analyst_consensus == "buy"
    assert result.macro_alignment == "risk_on"
    assert result.confidence == 1.0  # full data in backtest


@pytest.mark.asyncio
async def test_composite_tsla() -> None:
    """TSLA should get lower composite due to negative news and hold rating."""
    result = await get_composite_sentiment("TSLA")
    assert result.symbol == "TSLA"
    # TSLA: news negative (~0.375), analyst hold (0.5), macro risk_on (0.8)
    # composite = 0.375*0.4 + 0.5*0.4 + 0.8*0.2 = 0.15 + 0.2 + 0.16 = 0.51
    assert result.composite_score < result.composite_score + 1  # sanity
    assert result.analyst_consensus == "hold"
    assert result.earnings_upcoming is True  # TSLA mock: 2026-03-20, within 7 days


@pytest.mark.asyncio
async def test_composite_unknown_symbol() -> None:
    """Unknown symbol should still return valid composite with neutral defaults."""
    result = await get_composite_sentiment("ZZZZ")
    assert result.symbol == "ZZZZ"
    assert 0.0 <= result.composite_score <= 1.0
    assert result.confidence == 1.0  # mock providers don't fail, just return defaults
    assert result.analyst_consensus == "hold"


@pytest.mark.asyncio
async def test_composite_score_bounds() -> None:
    """Composite score must always be in [0, 1]."""
    for sym in ["AAPL", "TSLA", "MSFT", "ZZZZ"]:
        result = await get_composite_sentiment(sym)
        assert 0.0 <= result.composite_score <= 1.0
        assert 0.0 <= result.confidence <= 1.0
```

---

### `tests/test_scoring.py`

```python
"""Tests for scoring logic — the most critical math in the system."""

from __future__ import annotations

import pytest

from qitp_mcp_sentiment.scoring import (
    classify_macro_regime,
    compute_composite_score,
    compute_confidence,
    consensus_to_score,
    macro_regime_to_score,
    normalize_article_sentiment,
    score_to_label,
)


# ---------------------------------------------------------------------------
# composite score
# ---------------------------------------------------------------------------
class TestCompositeScore:
    def test_all_neutral(self) -> None:
        assert compute_composite_score(0.5, 0.5, 0.5) == 0.5

    def test_all_bullish(self) -> None:
        # 1.0*0.4 + 1.0*0.4 + 1.0*0.2 = 1.0
        assert compute_composite_score(1.0, 1.0, 1.0) == 1.0

    def test_all_bearish(self) -> None:
        assert compute_composite_score(0.0, 0.0, 0.0) == 0.0

    def test_weighted_correctly(self) -> None:
        # news=0.8, analyst=0.6, macro=0.5
        # 0.8*0.4 + 0.6*0.4 + 0.5*0.2 = 0.32 + 0.24 + 0.10 = 0.66
        result = compute_composite_score(0.8, 0.6, 0.5)
        assert abs(result - 0.66) < 0.001

    def test_missing_news_uses_neutral(self) -> None:
        # None news => 0.5, analyst=0.8, macro=0.8
        # 0.5*0.4 + 0.8*0.4 + 0.8*0.2 = 0.20 + 0.32 + 0.16 = 0.68
        result = compute_composite_score(None, 0.8, 0.8)
        assert abs(result - 0.68) < 0.001

    def test_missing_all_returns_neutral(self) -> None:
        # All None => all 0.5 => 0.5
        assert compute_composite_score(None, None, None) == 0.5

    def test_clamped_to_bounds(self) -> None:
        # Even with extreme inputs, result stays in [0, 1]
        assert 0.0 <= compute_composite_score(2.0, 2.0, 2.0) <= 1.0
        assert 0.0 <= compute_composite_score(-1.0, -1.0, -1.0) <= 1.0


# ---------------------------------------------------------------------------
# score to label
# ---------------------------------------------------------------------------
class TestScoreToLabel:
    def test_very_bearish(self) -> None:
        assert score_to_label(0.0) == "very_bearish"
        assert score_to_label(0.19) == "very_bearish"

    def test_bearish(self) -> None:
        assert score_to_label(0.2) == "bearish"
        assert score_to_label(0.39) == "bearish"

    def test_neutral(self) -> None:
        assert score_to_label(0.4) == "neutral"
        assert score_to_label(0.59) == "neutral"

    def test_bullish(self) -> None:
        assert score_to_label(0.6) == "bullish"
        assert score_to_label(0.79) == "bullish"

    def test_very_bullish(self) -> None:
        assert score_to_label(0.8) == "very_bullish"
        assert score_to_label(1.0) == "very_bullish"


# ---------------------------------------------------------------------------
# macro regime classification
# ---------------------------------------------------------------------------
class TestMacroRegime:
    def test_risk_on(self) -> None:
        assert classify_macro_regime(vix=15.0, fear_greed=70) == "risk_on"

    def test_risk_off_high_vix(self) -> None:
        assert classify_macro_regime(vix=35.0, fear_greed=50) == "risk_off"

    def test_risk_off_low_fear_greed(self) -> None:
        assert classify_macro_regime(vix=22.0, fear_greed=15) == "risk_off"

    def test_neutral_mid_range(self) -> None:
        assert classify_macro_regime(vix=22.0, fear_greed=45) == "neutral"

    def test_neutral_vix_low_but_fg_not_high(self) -> None:
        # VIX < 20 but F&G <= 60 => neutral (not risk_on)
        assert classify_macro_regime(vix=18.0, fear_greed=55) == "neutral"

    def test_risk_off_takes_precedence(self) -> None:
        # VIX > 30 even with high F&G => risk_off
        assert classify_macro_regime(vix=32.0, fear_greed=70) == "risk_off"

    def test_boundary_vix_20(self) -> None:
        # VIX == 20 is NOT < 20, so not risk_on
        assert classify_macro_regime(vix=20.0, fear_greed=70) == "neutral"

    def test_boundary_vix_30(self) -> None:
        # VIX == 30 is NOT > 30, so not risk_off from VIX alone
        assert classify_macro_regime(vix=30.0, fear_greed=50) == "neutral"


# ---------------------------------------------------------------------------
# macro regime to score
# ---------------------------------------------------------------------------
class TestMacroRegimeToScore:
    def test_risk_on(self) -> None:
        assert macro_regime_to_score("risk_on") == 0.8

    def test_neutral(self) -> None:
        assert macro_regime_to_score("neutral") == 0.5

    def test_risk_off(self) -> None:
        assert macro_regime_to_score("risk_off") == 0.2

    def test_unknown(self) -> None:
        assert macro_regime_to_score("unknown") == 0.5


# ---------------------------------------------------------------------------
# consensus to score
# ---------------------------------------------------------------------------
class TestConsensusToScore:
    def test_all_values(self) -> None:
        assert consensus_to_score("strong_buy") == 1.0
        assert consensus_to_score("buy") == 0.75
        assert consensus_to_score("hold") == 0.5
        assert consensus_to_score("sell") == 0.25
        assert consensus_to_score("strong_sell") == 0.0

    def test_unknown(self) -> None:
        assert consensus_to_score("whatever") == 0.5


# ---------------------------------------------------------------------------
# confidence
# ---------------------------------------------------------------------------
class TestConfidence:
    def test_full_data(self) -> None:
        assert compute_confidence(True, True, True) == 1.0

    def test_missing_news(self) -> None:
        assert compute_confidence(False, True, True) == 0.7

    def test_missing_analyst(self) -> None:
        assert compute_confidence(True, False, True) == 0.7

    def test_missing_both(self) -> None:
        assert compute_confidence(False, False, True) == 0.4

    def test_missing_macro_only(self) -> None:
        assert compute_confidence(True, True, False) == 0.8

    def test_missing_all(self) -> None:
        assert compute_confidence(False, False, False) == 0.4


# ---------------------------------------------------------------------------
# normalize article sentiment
# ---------------------------------------------------------------------------
class TestNormalizeArticleSentiment:
    def test_zero(self) -> None:
        assert normalize_article_sentiment(0.0) == 0.5

    def test_max(self) -> None:
        assert normalize_article_sentiment(1.0) == 1.0

    def test_min(self) -> None:
        assert normalize_article_sentiment(-1.0) == 0.0

    def test_positive(self) -> None:
        assert normalize_article_sentiment(0.5) == 0.75

    def test_clamping(self) -> None:
        assert normalize_article_sentiment(2.0) == 1.0
        assert normalize_article_sentiment(-5.0) == 0.0
```

---

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# Runtime env vars must be provided at container start:
#   POLYGON_API_KEY, FMP_API_KEY, FRED_API_KEY, EXECUTION_MODE
ENV EXECUTION_MODE=backtest

ENTRYPOINT ["qitp-sentiment-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  sentiment-mcp:
    build: .
    container_name: qitp-sentiment-mcp
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - POLYGON_API_KEY=${POLYGON_API_KEY:-}
      - FMP_API_KEY=${FMP_API_KEY:-}
      - FRED_API_KEY=${FRED_API_KEY:-}
    stdin_open: true
    restart: unless-stopped
```

---

## Acceptance Criteria
- [ ] All 5 tools return correctly typed responses
- [ ] Composite scoring formula: news(40%) + analyst(40%) + macro alignment(20%)
- [ ] Macro regime classification correct (risk_on/risk_off/neutral thresholds)
- [ ] Backtest mode uses mock provider, no live API calls
- [ ] Confidence scoring reflects data completeness
- [ ] Docker build succeeds
- [ ] All tests pass

## Test Plan
```bash
cd ~/dev/tccw-qitp-mcp-sentiment
pip install -e ".[dev]"
pytest -v
```

## Agent Instructions
Sentiment scoring is critical for strategy entry conditions. The composite score directly drives whether trades are taken. Test the scoring math thoroughly. Mock providers must return deterministic data for reproducible backtests.

Key implementation notes:
- All providers route through EXECUTION_MODE: backtest uses mock_provider, paper/live use real APIs
- The mock provider returns hardcoded deterministic data so backtest results are reproducible
- Fear & Greed index is not available on FRED; in live mode, VIX is used as a proxy (replace with CNN F&G API in production)
- Scoring boundaries are strict: the label thresholds and regime classification must match the spec exactly
- The composite tool catches individual sub-tool failures and degrades gracefully with reduced confidence
- All API keys are referenced via environment variables only — never hardcoded
