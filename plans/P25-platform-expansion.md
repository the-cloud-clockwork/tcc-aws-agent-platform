# P25 — Platform Expansion

## Objective
Expand QITP with six cross-cutting capabilities: (1) dynamic AI screener agent for automated watchlist expansion, (2) multi-market support for Asia and crypto, (3) Google A2A protocol interoperability so QITP agents are discoverable/invokable by external agent systems, (4) advanced AgentCore features (memory branching, streaming, multi-tenant), (5) Spanish IRPF tax report auto-generation, and (6) CFD/leveraged product risk rules with ESMA compliance.

## Plane Tickets
ROOT-71 (Platform Expansion epic), ROOT-72 (Watchlist Screener), ROOT-73 (Multi-Market), ROOT-74 (A2A Protocol), ROOT-75 (Tax Reporter), ROOT-76 (AgentCore Advanced), ROOT-77 (CFD Risk Rules)

## Target Repos
- `~/dev/tccw-qitp-agents` — watchlist screener agent, tax reporter agent, A2A server
- `~/dev/tccw-qitp-mcp-market-data` — multi-market providers (Tokyo, HKEX, crypto)
- `~/dev/tccw-agent-core` — market calendar, timezone, sessions, currency, AgentCore advanced, multi-tenant
- `~/dev/tccw-agent-infra` — CDK constructs for new resources (not covered in this plan)

## Dependencies
P14 (ibkr-mcp), P15 (2FA), P16 (risk engine), P17 (infra), P18 (observability), P19 (AgentCore integration), P20 (charting-mcp)

---

## Repo Structure (New Files Only)

```
tccw-qitp-agents/
├── blueprints/agents/
│   ├── watchlist_screener.yaml
│   └── tax_reporter.yaml
├── src/qitp_agents/
│   ├── watchlist_screener/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── universe.py
│   │   ├── filters.py
│   │   └── ranking.py
│   ├── tax_reporter/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── irpf.py
│   │   ├── models.py
│   │   └── formatter.py
│   └── a2a/
│       ├── __init__.py
│       ├── server.py
│       ├── agent_card.py
│       ├── task_handler.py
│       └── discovery.py
├── tests/
│   ├── unit/
│   │   ├── test_watchlist_screener.py
│   │   ├── test_tax_reporter.py
│   │   └── test_a2a.py
│   └── integration/
│       └── test_a2a_server.py

tccw-qitp-mcp-market-data/
├── src/qitp_mcp_market_data/
│   └── providers/
│       ├── tokyo.py
│       ├── hkex.py
│       └── crypto.py
├── tests/
│   ├── test_tokyo_provider.py
│   ├── test_hkex_provider.py
│   └── test_crypto_provider.py

tccw-agent-core/
├── src/agent_core/
│   ├── markets/
│   │   ├── __init__.py
│   │   ├── calendar.py
│   │   ├── timezone.py
│   │   ├── sessions.py
│   │   └── currency.py
│   ├── agentcore/
│   │   ├── __init__.py
│   │   ├── memory_branching.py
│   │   ├── streaming.py
│   │   └── multi_tenant.py
│   └── risk/
│       ├── cfd_leverage.py
│       ├── margin_call.py
│       └── product_classifier.py
├── tests/
│   ├── test_markets.py
│   ├── test_agentcore_advanced.py
│   └── test_cfd_risk.py
```

---

## Full Inline Code

---

# Component 1: Dynamic Watchlist Screener Agent

---

### blueprints/agents/watchlist_screener.yaml

```yaml
agent_id: watchlist-screener
name: Watchlist Screener Agent
version: "1.0.0"
description: >
  AI-powered screener that scans stock universes (S&P 500, STOXX 600,
  Nikkei 225, crypto top 100) and identifies candidates with high gap
  potential based on liquidity, volatility, sector rotation signals,
  and historical gap frequency. Outputs a ranked candidate list for
  watchlist expansion.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.2

system_prompt_id: watchlist-screener-system-v1

tools:
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_ohlcv
      - get_volume_profile
      - get_watchlist
      - get_watchlist_gaps
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact
      - get_artifact

execution:
  timeout_seconds: 180
  max_tool_calls: 200
  retry_policy:
    max_retries: 2
    backoff_base: 2.0

output_schema: ScreenerOutput

tags:
  - screener
  - watchlist
  - phase-3
```

---

### src/qitp_agents/watchlist_screener/__init__.py

```python
"""Watchlist Screener Agent — AI-powered stock universe scanning for gap candidates."""
```

---

### src/qitp_agents/watchlist_screener/universe.py

```python
"""Stock universe providers for the watchlist screener.

Each universe provider returns a list of symbols with basic metadata
that the screener agent can then filter and rank.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UniverseSymbol(BaseModel):
    """A symbol from a stock universe with screening metadata."""

    symbol: str
    name: str
    market: str  # "us", "eu", "jp", "hk", "crypto"
    sector: str
    industry: str
    market_cap_usd: float
    avg_daily_volume: int
    currency: str
    exchange: str
    asset_type: str  # "stock", "etf", "crypto"
    tags: list[str] = Field(default_factory=list)


class UniverseProvider(ABC):
    """Abstract base class for stock universe providers."""

    @abstractmethod
    async def get_symbols(self) -> list[UniverseSymbol]:
        """Return all symbols in this universe."""
        ...

    @abstractmethod
    def universe_id(self) -> str:
        """Unique identifier for this universe."""
        ...


class SP500Provider(UniverseProvider):
    """S&P 500 universe provider.

    Loads constituents from S3 reference data or falls back to
    a static list for backtest mode.
    """

    def __init__(self, s3_client: Any = None, bucket: str = "qitp-historical-data") -> None:
        self._s3_client = s3_client
        self._bucket = bucket

    def universe_id(self) -> str:
        return "sp500"

    async def get_symbols(self) -> list[UniverseSymbol]:
        """Load S&P 500 constituents from S3 reference data."""
        try:
            if self._s3_client:
                return await self._load_from_s3()
        except Exception:
            logger.warning("Failed to load S&P 500 from S3, using static fallback")

        return self._static_fallback()

    async def _load_from_s3(self) -> list[UniverseSymbol]:
        """Load universe from S3 parquet reference file."""
        import pandas as pd
        import io

        response = self._s3_client.get_object(
            Bucket=self._bucket,
            Key="reference/sp500_constituents.parquet",
        )
        df = pd.read_parquet(io.BytesIO(response["Body"].read()))
        return [
            UniverseSymbol(
                symbol=row["symbol"],
                name=row["name"],
                market="us",
                sector=row["sector"],
                industry=row.get("industry", "Unknown"),
                market_cap_usd=row["market_cap"],
                avg_daily_volume=int(row["avg_volume"]),
                currency="USD",
                exchange="NYSE" if row.get("exchange") == "NYSE" else "NASDAQ",
                asset_type="stock",
            )
            for _, row in df.iterrows()
        ]

    def _static_fallback(self) -> list[UniverseSymbol]:
        """Minimal static fallback for testing."""
        # In production, this would be a full 500-symbol list from S3
        symbols = [
            ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics", 3_000_000_000_000, 50_000_000, "NASDAQ"),
            ("MSFT", "Microsoft Corp.", "Technology", "Software", 2_800_000_000_000, 25_000_000, "NASDAQ"),
            ("AMZN", "Amazon.com Inc.", "Consumer Discretionary", "E-Commerce", 1_800_000_000_000, 40_000_000, "NASDAQ"),
            ("NVDA", "NVIDIA Corp.", "Technology", "Semiconductors", 2_500_000_000_000, 35_000_000, "NASDAQ"),
            ("GOOGL", "Alphabet Inc.", "Communication Services", "Internet", 2_000_000_000_000, 20_000_000, "NASDAQ"),
            ("META", "Meta Platforms", "Communication Services", "Social Media", 1_200_000_000_000, 15_000_000, "NASDAQ"),
            ("JPM", "JPMorgan Chase", "Financials", "Banks", 500_000_000_000, 10_000_000, "NYSE"),
            ("V", "Visa Inc.", "Financials", "Payments", 550_000_000_000, 7_000_000, "NYSE"),
            ("JNJ", "Johnson & Johnson", "Healthcare", "Pharmaceuticals", 400_000_000_000, 6_000_000, "NYSE"),
            ("XOM", "Exxon Mobil", "Energy", "Oil & Gas", 450_000_000_000, 12_000_000, "NYSE"),
        ]
        return [
            UniverseSymbol(
                symbol=s[0], name=s[1], market="us", sector=s[2],
                industry=s[3], market_cap_usd=s[4], avg_daily_volume=s[5],
                currency="USD", exchange=s[6], asset_type="stock",
            )
            for s in symbols
        ]


class STOXX600Provider(UniverseProvider):
    """STOXX Europe 600 universe provider."""

    def __init__(self, s3_client: Any = None, bucket: str = "qitp-historical-data") -> None:
        self._s3_client = s3_client
        self._bucket = bucket

    def universe_id(self) -> str:
        return "stoxx600"

    async def get_symbols(self) -> list[UniverseSymbol]:
        """Load STOXX 600 constituents."""
        try:
            if self._s3_client:
                return await self._load_from_s3()
        except Exception:
            logger.warning("Failed to load STOXX 600 from S3, using static fallback")

        return self._static_fallback()

    async def _load_from_s3(self) -> list[UniverseSymbol]:
        """Load from S3 reference data."""
        import pandas as pd
        import io

        response = self._s3_client.get_object(
            Bucket=self._bucket,
            Key="reference/stoxx600_constituents.parquet",
        )
        df = pd.read_parquet(io.BytesIO(response["Body"].read()))
        return [
            UniverseSymbol(
                symbol=row["symbol"],
                name=row["name"],
                market="eu",
                sector=row["sector"],
                industry=row.get("industry", "Unknown"),
                market_cap_usd=row["market_cap_usd"],
                avg_daily_volume=int(row["avg_volume"]),
                currency=row.get("currency", "EUR"),
                exchange=row.get("exchange", "XETRA"),
                asset_type="stock",
            )
            for _, row in df.iterrows()
        ]

    def _static_fallback(self) -> list[UniverseSymbol]:
        """Minimal static fallback."""
        symbols = [
            ("SAN.MC", "Banco Santander", "Financials", "Banks", 70_000_000_000, 30_000_000, "BME", "EUR"),
            ("ITX.MC", "Inditex", "Consumer Discretionary", "Apparel", 110_000_000_000, 5_000_000, "BME", "EUR"),
            ("SAP.DE", "SAP SE", "Technology", "Software", 250_000_000_000, 3_000_000, "XETRA", "EUR"),
            ("ASML.AS", "ASML Holding", "Technology", "Semiconductors", 350_000_000_000, 2_000_000, "AMS", "EUR"),
            ("NESN.SW", "Nestle SA", "Consumer Staples", "Food", 250_000_000_000, 4_000_000, "SIX", "CHF"),
        ]
        return [
            UniverseSymbol(
                symbol=s[0], name=s[1], market="eu", sector=s[2],
                industry=s[3], market_cap_usd=s[4], avg_daily_volume=s[5],
                currency=s[7], exchange=s[6], asset_type="stock",
            )
            for s in symbols
        ]


class Nikkei225Provider(UniverseProvider):
    """Nikkei 225 universe provider (Japan market)."""

    def __init__(self, s3_client: Any = None, bucket: str = "qitp-historical-data") -> None:
        self._s3_client = s3_client
        self._bucket = bucket

    def universe_id(self) -> str:
        return "nikkei225"

    async def get_symbols(self) -> list[UniverseSymbol]:
        """Load Nikkei 225 constituents."""
        # Always static fallback for now — S3 loading same pattern as SP500
        return self._static_fallback()

    def _static_fallback(self) -> list[UniverseSymbol]:
        symbols = [
            ("7203.T", "Toyota Motor", "Consumer Discretionary", "Automobiles", 300_000_000_000, 8_000_000, "TSE", "JPY"),
            ("6758.T", "Sony Group", "Technology", "Electronics", 120_000_000_000, 5_000_000, "TSE", "JPY"),
            ("9984.T", "SoftBank Group", "Communication Services", "Telecom", 80_000_000_000, 10_000_000, "TSE", "JPY"),
            ("6861.T", "Keyence Corp", "Technology", "Instruments", 130_000_000_000, 1_000_000, "TSE", "JPY"),
            ("8306.T", "MUFG", "Financials", "Banks", 100_000_000_000, 15_000_000, "TSE", "JPY"),
        ]
        return [
            UniverseSymbol(
                symbol=s[0], name=s[1], market="jp", sector=s[2],
                industry=s[3], market_cap_usd=s[4], avg_daily_volume=s[5],
                currency=s[7], exchange=s[6], asset_type="stock",
            )
            for s in symbols
        ]


class CryptoTop100Provider(UniverseProvider):
    """Top 100 cryptocurrency universe provider."""

    def __init__(self, s3_client: Any = None, bucket: str = "qitp-historical-data") -> None:
        self._s3_client = s3_client
        self._bucket = bucket

    def universe_id(self) -> str:
        return "crypto_top100"

    async def get_symbols(self) -> list[UniverseSymbol]:
        """Load top 100 crypto assets."""
        return self._static_fallback()

    def _static_fallback(self) -> list[UniverseSymbol]:
        symbols = [
            ("BTC-USD", "Bitcoin", "Cryptocurrency", "Layer 1", 1_200_000_000_000, 30_000_000_000),
            ("ETH-USD", "Ethereum", "Cryptocurrency", "Layer 1", 400_000_000_000, 15_000_000_000),
            ("SOL-USD", "Solana", "Cryptocurrency", "Layer 1", 80_000_000_000, 3_000_000_000),
            ("BNB-USD", "Binance Coin", "Cryptocurrency", "Exchange", 60_000_000_000, 1_000_000_000),
            ("XRP-USD", "Ripple", "Cryptocurrency", "Payments", 30_000_000_000, 2_000_000_000),
        ]
        return [
            UniverseSymbol(
                symbol=s[0], name=s[1], market="crypto", sector=s[2],
                industry=s[3], market_cap_usd=s[4], avg_daily_volume=s[5],
                currency="USD", exchange="MULTI", asset_type="crypto",
            )
            for s in symbols
        ]


# --- Registry ---

UNIVERSE_REGISTRY: dict[str, type[UniverseProvider]] = {
    "sp500": SP500Provider,
    "stoxx600": STOXX600Provider,
    "nikkei225": Nikkei225Provider,
    "crypto_top100": CryptoTop100Provider,
}


def get_universe_provider(universe_id: str, **kwargs: Any) -> UniverseProvider:
    """Get a universe provider by ID.

    Args:
        universe_id: One of "sp500", "stoxx600", "nikkei225", "crypto_top100".
        **kwargs: Passed to the provider constructor (e.g., s3_client, bucket).

    Returns:
        UniverseProvider instance.

    Raises:
        ValueError: If universe_id is not recognized.
    """
    provider_cls = UNIVERSE_REGISTRY.get(universe_id)
    if not provider_cls:
        raise ValueError(
            f"Unknown universe '{universe_id}'. "
            f"Available: {list(UNIVERSE_REGISTRY.keys())}"
        )
    return provider_cls(**kwargs)
```

---

### src/qitp_agents/watchlist_screener/filters.py

```python
"""Screening filters for watchlist candidate selection.

Each filter is a callable that takes a list of UniverseSymbol and returns
a filtered subset. Filters are composable and order-independent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from qitp_agents.watchlist_screener.universe import UniverseSymbol

logger = logging.getLogger(__name__)


@dataclass
class FilterConfig:
    """Configuration for screening filters."""

    min_market_cap_usd: float = 1_000_000_000  # $1B minimum
    max_market_cap_usd: float | None = None
    min_avg_daily_volume: int = 1_000_000  # 1M shares/day minimum
    allowed_markets: list[str] = field(default_factory=lambda: ["us", "eu", "jp", "hk", "crypto"])
    allowed_sectors: list[str] | None = None  # None = all sectors
    excluded_sectors: list[str] = field(default_factory=list)
    allowed_asset_types: list[str] = field(default_factory=lambda: ["stock", "etf", "crypto"])
    exclude_symbols: list[str] = field(default_factory=list)  # Already on watchlist
    max_candidates: int = 200


def apply_liquidity_filter(
    symbols: list[UniverseSymbol],
    config: FilterConfig,
) -> list[UniverseSymbol]:
    """Filter by minimum average daily volume.

    Illiquid stocks produce unreliable gap signals due to wide spreads
    and low fill probability.
    """
    filtered = [
        s for s in symbols
        if s.avg_daily_volume >= config.min_avg_daily_volume
    ]
    logger.info(
        "Liquidity filter: %d -> %d (min_volume=%d)",
        len(symbols), len(filtered), config.min_avg_daily_volume,
    )
    return filtered


def apply_market_cap_filter(
    symbols: list[UniverseSymbol],
    config: FilterConfig,
) -> list[UniverseSymbol]:
    """Filter by market capitalization range.

    Micro/small caps excluded by default — too volatile, unreliable gaps.
    """
    filtered = []
    for s in symbols:
        if s.market_cap_usd < config.min_market_cap_usd:
            continue
        if config.max_market_cap_usd and s.market_cap_usd > config.max_market_cap_usd:
            continue
        filtered.append(s)

    logger.info(
        "Market cap filter: %d -> %d (min=$%.0fB)",
        len(symbols), len(filtered), config.min_market_cap_usd / 1e9,
    )
    return filtered


def apply_sector_filter(
    symbols: list[UniverseSymbol],
    config: FilterConfig,
) -> list[UniverseSymbol]:
    """Filter by allowed/excluded sectors.

    Supports both allowlist and blocklist modes.
    """
    filtered = symbols

    if config.allowed_sectors:
        filtered = [s for s in filtered if s.sector in config.allowed_sectors]

    if config.excluded_sectors:
        filtered = [s for s in filtered if s.sector not in config.excluded_sectors]

    logger.info("Sector filter: %d -> %d", len(symbols), len(filtered))
    return filtered


def apply_market_filter(
    symbols: list[UniverseSymbol],
    config: FilterConfig,
) -> list[UniverseSymbol]:
    """Filter by allowed markets."""
    filtered = [s for s in symbols if s.market in config.allowed_markets]
    logger.info("Market filter: %d -> %d", len(symbols), len(filtered))
    return filtered


def apply_exclusion_filter(
    symbols: list[UniverseSymbol],
    config: FilterConfig,
) -> list[UniverseSymbol]:
    """Exclude symbols already on the active watchlist."""
    if not config.exclude_symbols:
        return symbols
    excluded = set(config.exclude_symbols)
    filtered = [s for s in symbols if s.symbol not in excluded]
    logger.info(
        "Exclusion filter: %d -> %d (excluded %d existing)",
        len(symbols), len(filtered), len(excluded),
    )
    return filtered


def apply_all_filters(
    symbols: list[UniverseSymbol],
    config: FilterConfig,
) -> list[UniverseSymbol]:
    """Apply all filters in sequence and cap at max_candidates.

    Filter order: market -> sector -> market_cap -> liquidity -> exclusion -> cap.
    """
    result = symbols
    result = apply_market_filter(result, config)
    result = apply_sector_filter(result, config)
    result = apply_market_cap_filter(result, config)
    result = apply_liquidity_filter(result, config)
    result = apply_exclusion_filter(result, config)

    if len(result) > config.max_candidates:
        # Sort by market cap descending, take top N
        result.sort(key=lambda s: s.market_cap_usd, reverse=True)
        result = result[: config.max_candidates]
        logger.info("Capped candidates to %d", config.max_candidates)

    logger.info("Final candidate count: %d", len(result))
    return result
```

---

### src/qitp_agents/watchlist_screener/ranking.py

```python
"""Ranking engine for watchlist screener candidates.

Ranks filtered candidates by gap potential using a weighted scoring model.
Factors: historical gap frequency, average gap magnitude, volume stability,
sector momentum, and volatility characteristics.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from qitp_agents.watchlist_screener.universe import UniverseSymbol

logger = logging.getLogger(__name__)


class GapHistoryStats(BaseModel):
    """Historical gap statistics for a symbol."""

    symbol: str
    total_gaps: int  # Number of gaps > threshold in lookback period
    avg_gap_pct: float  # Average gap magnitude
    max_gap_pct: float  # Maximum gap magnitude
    gap_up_ratio: float  # Proportion of gaps that were up
    avg_volume_ratio_on_gap: float  # Avg volume ratio on gap days
    gap_frequency_per_month: float  # Average gaps per month


class RankingWeights(BaseModel):
    """Weights for the gap potential scoring model."""

    gap_frequency: float = 0.30
    gap_magnitude: float = 0.25
    volume_stability: float = 0.20
    market_cap_score: float = 0.15
    sector_diversity: float = 0.10


class RankedCandidate(BaseModel):
    """A ranked candidate with scoring breakdown."""

    symbol: str
    name: str
    market: str
    sector: str
    overall_score: float = Field(ge=0.0, le=1.0)
    gap_frequency_score: float = Field(ge=0.0, le=1.0)
    gap_magnitude_score: float = Field(ge=0.0, le=1.0)
    volume_stability_score: float = Field(ge=0.0, le=1.0)
    market_cap_score: float = Field(ge=0.0, le=1.0)
    sector_diversity_score: float = Field(ge=0.0, le=1.0)
    gap_stats: GapHistoryStats | None = None
    recommendation: str  # "strong_add", "add", "monitor", "skip"


def compute_gap_frequency_score(stats: GapHistoryStats) -> float:
    """Score based on how often gaps occur.

    2+ gaps/month = 1.0, 0 gaps/month = 0.0. Log-scaled.
    """
    if stats.gap_frequency_per_month <= 0:
        return 0.0
    # Log scale: ln(1 + freq) / ln(3) capped at 1.0
    return min(1.0, math.log(1 + stats.gap_frequency_per_month) / math.log(3))


def compute_gap_magnitude_score(stats: GapHistoryStats) -> float:
    """Score based on average gap magnitude.

    5%+ avg = 1.0, 0% = 0.0. Linear.
    """
    return min(1.0, stats.avg_gap_pct / 5.0)


def compute_volume_stability_score(stats: GapHistoryStats) -> float:
    """Score based on volume consistency on gap days.

    High volume ratio on gap days = high conviction gaps.
    Ratio 3.0+ = 1.0, ratio 1.0 = 0.0.
    """
    if stats.avg_volume_ratio_on_gap <= 1.0:
        return 0.0
    return min(1.0, (stats.avg_volume_ratio_on_gap - 1.0) / 2.0)


def compute_market_cap_score(symbol: UniverseSymbol) -> float:
    """Score based on market cap — mid-cap sweet spot.

    Mid-cap ($10B-$100B) scores highest. Large and mega-cap score lower
    because gaps tend to be smaller. Small-cap excluded by filters.
    """
    cap_b = symbol.market_cap_usd / 1e9  # Convert to billions
    if cap_b < 5:
        return 0.3
    elif cap_b < 10:
        return 0.6
    elif cap_b < 50:
        return 1.0  # Sweet spot
    elif cap_b < 200:
        return 0.8
    elif cap_b < 1000:
        return 0.5
    else:
        return 0.3  # Mega-cap — gaps are rare


def compute_sector_diversity_score(
    symbol: UniverseSymbol,
    existing_sectors: dict[str, int],
    max_sector_count: int = 10,
) -> float:
    """Score based on sector diversification benefit.

    Under-represented sectors score higher to encourage portfolio diversity.
    """
    sector_count = existing_sectors.get(symbol.sector, 0)
    if sector_count == 0:
        return 1.0  # New sector — maximum diversity benefit
    return max(0.0, 1.0 - (sector_count / max_sector_count))


def rank_candidates(
    candidates: list[UniverseSymbol],
    gap_stats_map: dict[str, GapHistoryStats],
    existing_sectors: dict[str, int],
    weights: RankingWeights | None = None,
    top_n: int = 20,
) -> list[RankedCandidate]:
    """Rank candidates by gap potential score.

    Args:
        candidates: Filtered universe symbols.
        gap_stats_map: Historical gap stats keyed by symbol.
        existing_sectors: Current watchlist sector counts for diversity scoring.
        weights: Custom scoring weights (defaults used if None).
        top_n: Number of top candidates to return.

    Returns:
        Sorted list of RankedCandidate, highest score first.
    """
    if weights is None:
        weights = RankingWeights()

    ranked: list[RankedCandidate] = []

    for candidate in candidates:
        stats = gap_stats_map.get(candidate.symbol)

        if stats is None:
            # No gap history — assign minimum scores
            freq_score = 0.1
            mag_score = 0.1
            vol_score = 0.1
        else:
            freq_score = compute_gap_frequency_score(stats)
            mag_score = compute_gap_magnitude_score(stats)
            vol_score = compute_volume_stability_score(stats)

        cap_score = compute_market_cap_score(candidate)
        div_score = compute_sector_diversity_score(candidate, existing_sectors)

        overall = (
            weights.gap_frequency * freq_score
            + weights.gap_magnitude * mag_score
            + weights.volume_stability * vol_score
            + weights.market_cap_score * cap_score
            + weights.sector_diversity * div_score
        )

        # Recommendation thresholds
        if overall >= 0.7:
            recommendation = "strong_add"
        elif overall >= 0.5:
            recommendation = "add"
        elif overall >= 0.3:
            recommendation = "monitor"
        else:
            recommendation = "skip"

        ranked.append(
            RankedCandidate(
                symbol=candidate.symbol,
                name=candidate.name,
                market=candidate.market,
                sector=candidate.sector,
                overall_score=round(overall, 4),
                gap_frequency_score=round(freq_score, 4),
                gap_magnitude_score=round(mag_score, 4),
                volume_stability_score=round(vol_score, 4),
                market_cap_score=round(cap_score, 4),
                sector_diversity_score=round(div_score, 4),
                gap_stats=stats,
                recommendation=recommendation,
            )
        )

    ranked.sort(key=lambda r: r.overall_score, reverse=True)
    return ranked[:top_n]
```

---

### src/qitp_agents/watchlist_screener/handler.py

```python
"""Watchlist Screener Agent Lambda handler.

Input:
    {
        "universes": ["sp500", "stoxx600"],
        "lookback_months": 6,
        "top_n": 20,
        "filter_config": { ... optional overrides ... },
        "date": "2026-03-15"
    }

Output: ScreenerOutput JSON artifact with ranked candidate list.

Architecture:
- Single Strands agent with extended context
- Tools: market-data-mcp (get_ohlcv, get_volume_profile, get_watchlist)
- Tools: artifacts-mcp (create_artifact)
- The agent scans universes, applies filters, computes gap stats, and ranks.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

from qitp_agents.watchlist_screener.filters import FilterConfig, apply_all_filters
from qitp_agents.watchlist_screener.ranking import RankingWeights
from qitp_agents.watchlist_screener.universe import get_universe_provider

logger = logging.getLogger(__name__)

# --- Warm-start initialization ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "backtest"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "watchlist-screener"
MAX_OUTPUT_BYTES = 256 * 1024


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Watchlist Screener Agent.

    Args:
        event: Input with universes list, lookback config, filter overrides.
        context: Lambda context (optional).

    Returns:
        JSON response with screener results or claim-check reference.
    """
    logger.info(
        "Watchlist screener invoked",
        extra={"universes": event.get("universes", [])},
    )

    universes = event.get("universes", ["sp500"])
    lookback_months = event.get("lookback_months", 6)
    top_n = event.get("top_n", 20)
    date = event.get("date")
    filter_overrides = event.get("filter_config", {})

    if not date:
        return _error_response("Missing required field: date")

    try:
        mcp_clients = _create_mcp_clients()

        # Build agent from blueprint
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Build filter config with overrides
        filter_config = FilterConfig(**filter_overrides) if filter_overrides else FilterConfig()

        # Construct the agent prompt
        universes_str = ", ".join(universes)
        prompt = (
            f"Screen stock universes for gap trading candidates.\n\n"
            f"Parameters:\n"
            f"- Universes: {universes_str}\n"
            f"- Lookback period: {lookback_months} months from {date}\n"
            f"- Target candidates: top {top_n}\n"
            f"- Min market cap: ${filter_config.min_market_cap_usd / 1e9:.1f}B\n"
            f"- Min avg daily volume: {filter_config.min_avg_daily_volume:,}\n\n"
            f"Steps:\n"
            f"1. Get the current watchlist to identify existing symbols.\n"
            f"2. For a representative sample from each universe, call get_ohlcv\n"
            f"   with {lookback_months} months of data to compute gap statistics.\n"
            f"3. Calculate for each symbol: gap frequency per month, avg gap magnitude,\n"
            f"   max gap, avg volume ratio on gap days, gap up/down ratio.\n"
            f"4. Rank candidates using weighted scoring:\n"
            f"   - Gap frequency (30%)\n"
            f"   - Gap magnitude (25%)\n"
            f"   - Volume stability (20%)\n"
            f"   - Market cap sweet spot (15%)\n"
            f"   - Sector diversity benefit (10%)\n"
            f"5. Create a ScreenerOutput artifact with the top {top_n} candidates,\n"
            f"   each including: symbol, name, market, sector, overall_score,\n"
            f"   score breakdown, gap stats, and recommendation.\n"
            f"6. Return the artifact ID and summary statistics.\n"
        )

        result = agent(prompt)

        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Watchlist screener failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    market_data_uri = os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8002")
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=market_data_uri,
    )

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result, with claim-check for large outputs."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        logger.warning("Output exceeds 256KB, returning claim-check")
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

# Component 2: Multi-Market Expansion

---

### src/agent_core/markets/__init__.py

```python
"""Multi-market support for QITP — trading calendars, timezones, sessions, and currency."""

from agent_core.markets.calendar import MarketCalendar, get_calendar
from agent_core.markets.timezone import MarketTimezone, to_market_time, to_utc
from agent_core.markets.sessions import MarketSession, get_current_session
from agent_core.markets.currency import convert_currency, CurrencyPair

__all__ = [
    "MarketCalendar",
    "get_calendar",
    "MarketTimezone",
    "to_market_time",
    "to_utc",
    "MarketSession",
    "get_current_session",
    "convert_currency",
    "CurrencyPair",
]
```

---

### src/agent_core/markets/calendar.py

```python
"""Multi-market trading calendar.

Supports EU, US, Japan, Hong Kong, and crypto (24/7) markets.
Provides holiday detection, trading day validation, and next/previous
trading day computation.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MarketCode(str, Enum):
    """Supported market codes."""

    US = "us"           # NYSE/NASDAQ
    EU = "eu"           # European exchanges (BME, XETRA, Euronext, LSE)
    ES = "es"           # BME (Madrid) — subset of EU but with specific holidays
    JP = "jp"           # TSE (Tokyo)
    HK = "hk"           # HKEX (Hong Kong)
    CRYPTO = "crypto"   # 24/7 — no holidays


class MarketHoliday(BaseModel):
    """A market holiday."""

    date: date
    name: str
    market: MarketCode
    half_day: bool = False  # True for early close days


class MarketCalendar:
    """Trading calendar for a specific market.

    Determines whether a given date is a trading day, and provides
    next/previous trading day lookups.
    """

    def __init__(self, market: MarketCode, holidays: list[MarketHoliday] | None = None) -> None:
        self._market = market
        self._holidays: dict[date, MarketHoliday] = {}

        if holidays:
            for h in holidays:
                self._holidays[h.date] = h

    @property
    def market(self) -> MarketCode:
        return self._market

    def is_trading_day(self, d: date) -> bool:
        """Check if date is a trading day (not weekend, not holiday).

        Crypto markets trade 24/7 — always returns True.
        """
        if self._market == MarketCode.CRYPTO:
            return True

        # Weekends are not trading days
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Check holidays
        if d in self._holidays:
            return False

        return True

    def is_half_day(self, d: date) -> bool:
        """Check if date is a half-day (early close)."""
        holiday = self._holidays.get(d)
        return holiday is not None and holiday.half_day

    def next_trading_day(self, d: date) -> date:
        """Return the next trading day after d."""
        candidate = d + timedelta(days=1)
        max_lookahead = 10  # Safety: no market closes for >10 days
        for _ in range(max_lookahead):
            if self.is_trading_day(candidate):
                return candidate
            candidate += timedelta(days=1)
        raise ValueError(f"No trading day found within {max_lookahead} days of {d}")

    def previous_trading_day(self, d: date) -> date:
        """Return the previous trading day before d."""
        candidate = d - timedelta(days=1)
        max_lookback = 10
        for _ in range(max_lookback):
            if self.is_trading_day(candidate):
                return candidate
            candidate -= timedelta(days=1)
        raise ValueError(f"No trading day found within {max_lookback} days before {d}")

    def trading_days_between(self, start: date, end: date) -> list[date]:
        """Return all trading days in [start, end] inclusive."""
        days = []
        current = start
        while current <= end:
            if self.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    def gap_window(self, monday: date) -> tuple[date, date] | None:
        """Return (friday_close_date, monday_open_date) for a weekend gap.

        For crypto: returns None (no weekend gaps — market is 24/7).
        For Asia markets: adjusts for local holidays/closures.
        """
        if self._market == MarketCode.CRYPTO:
            return None  # No weekend gaps for crypto

        if monday.weekday() != 0:  # Not a Monday
            return None

        friday = self.previous_trading_day(monday)
        if not self.is_trading_day(monday):
            return None

        return (friday, monday)


# --- Static holiday data (2026) ---

_US_HOLIDAYS_2026 = [
    MarketHoliday(date=date(2026, 1, 1), name="New Year's Day", market=MarketCode.US),
    MarketHoliday(date=date(2026, 1, 19), name="MLK Day", market=MarketCode.US),
    MarketHoliday(date=date(2026, 2, 16), name="Presidents' Day", market=MarketCode.US),
    MarketHoliday(date=date(2026, 4, 3), name="Good Friday", market=MarketCode.US),
    MarketHoliday(date=date(2026, 5, 25), name="Memorial Day", market=MarketCode.US),
    MarketHoliday(date=date(2026, 6, 19), name="Juneteenth", market=MarketCode.US),
    MarketHoliday(date=date(2026, 7, 3), name="Independence Day (observed)", market=MarketCode.US),
    MarketHoliday(date=date(2026, 9, 7), name="Labor Day", market=MarketCode.US),
    MarketHoliday(date=date(2026, 11, 26), name="Thanksgiving", market=MarketCode.US),
    MarketHoliday(date=date(2026, 11, 27), name="Day after Thanksgiving", market=MarketCode.US, half_day=True),
    MarketHoliday(date=date(2026, 12, 25), name="Christmas", market=MarketCode.US),
]

_JP_HOLIDAYS_2026 = [
    MarketHoliday(date=date(2026, 1, 1), name="New Year", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 1, 2), name="Bank Holiday", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 1, 3), name="Bank Holiday", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 1, 12), name="Coming of Age Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 2, 11), name="National Foundation Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 2, 23), name="Emperor's Birthday", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 3, 20), name="Vernal Equinox", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 4, 29), name="Showa Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 5, 3), name="Constitution Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 5, 4), name="Greenery Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 5, 5), name="Children's Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 7, 20), name="Marine Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 9, 21), name="Respect for the Aged Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 9, 23), name="Autumnal Equinox", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 11, 3), name="Culture Day", market=MarketCode.JP),
    MarketHoliday(date=date(2026, 11, 23), name="Labor Thanksgiving", market=MarketCode.JP),
]

_HK_HOLIDAYS_2026 = [
    MarketHoliday(date=date(2026, 1, 1), name="New Year", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 2, 17), name="Lunar New Year", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 2, 18), name="Lunar New Year", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 2, 19), name="Lunar New Year", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 4, 3), name="Good Friday", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 4, 6), name="Easter Monday", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 5, 1), name="Labour Day", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 7, 1), name="SAR Establishment Day", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 10, 1), name="National Day", market=MarketCode.HK),
    MarketHoliday(date=date(2026, 12, 25), name="Christmas", market=MarketCode.HK),
]

_CALENDAR_REGISTRY: dict[MarketCode, list[MarketHoliday]] = {
    MarketCode.US: _US_HOLIDAYS_2026,
    MarketCode.JP: _JP_HOLIDAYS_2026,
    MarketCode.HK: _HK_HOLIDAYS_2026,
    MarketCode.CRYPTO: [],
}


def get_calendar(market: MarketCode | str) -> MarketCalendar:
    """Get a MarketCalendar for the given market code.

    Args:
        market: Market code string or enum (e.g., "us", "jp", "crypto").

    Returns:
        MarketCalendar instance with holidays loaded.
    """
    if isinstance(market, str):
        market = MarketCode(market)

    holidays = _CALENDAR_REGISTRY.get(market, [])
    return MarketCalendar(market=market, holidays=holidays)
```

---

### src/agent_core/markets/timezone.py

```python
"""Market timezone conversions.

Each market operates in a specific timezone. This module provides
conversion utilities for aligning data across markets.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

from agent_core.markets.calendar import MarketCode

logger = logging.getLogger(__name__)


# Market timezone mapping
MARKET_TIMEZONES: dict[MarketCode, str] = {
    MarketCode.US: "America/New_York",
    MarketCode.EU: "Europe/Berlin",
    MarketCode.ES: "Europe/Madrid",
    MarketCode.JP: "Asia/Tokyo",
    MarketCode.HK: "Asia/Hong_Kong",
    MarketCode.CRYPTO: "UTC",
}


class MarketTimezone:
    """Timezone wrapper for a specific market."""

    def __init__(self, market: MarketCode) -> None:
        self._market = market
        tz_name = MARKET_TIMEZONES.get(market, "UTC")
        self._tz = ZoneInfo(tz_name)

    @property
    def market(self) -> MarketCode:
        return self._market

    @property
    def tzinfo(self) -> ZoneInfo:
        return self._tz

    @property
    def tz_name(self) -> str:
        return str(self._tz)

    def now(self) -> datetime:
        """Current time in market timezone."""
        return datetime.now(tz=self._tz)

    def localize(self, dt: datetime) -> datetime:
        """Convert naive datetime to market timezone."""
        if dt.tzinfo is not None:
            return dt.astimezone(self._tz)
        return dt.replace(tzinfo=self._tz)


def to_market_time(dt: datetime, market: MarketCode) -> datetime:
    """Convert a datetime to market local time.

    Args:
        dt: Datetime (may be naive UTC or timezone-aware).
        market: Target market code.

    Returns:
        Datetime in market timezone.
    """
    tz_name = MARKET_TIMEZONES.get(market, "UTC")
    target_tz = ZoneInfo(tz_name)

    if dt.tzinfo is None:
        # Assume naive = UTC
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    return dt.astimezone(target_tz)


def to_utc(dt: datetime, source_market: MarketCode | None = None) -> datetime:
    """Convert a datetime to UTC.

    Args:
        dt: Datetime to convert. If naive and source_market provided,
            assumes market local time. If naive and no source_market,
            assumes UTC.
        source_market: Market whose timezone the naive datetime is in.

    Returns:
        Datetime in UTC.
    """
    utc = ZoneInfo("UTC")

    if dt.tzinfo is not None:
        return dt.astimezone(utc)

    if source_market:
        tz_name = MARKET_TIMEZONES.get(source_market, "UTC")
        source_tz = ZoneInfo(tz_name)
        dt = dt.replace(tzinfo=source_tz)
        return dt.astimezone(utc)

    return dt.replace(tzinfo=utc)
```

---

### src/agent_core/markets/sessions.py

```python
"""Market session detection — pre-market, regular, after-hours, closed.

Provides session-aware logic for determining which market phase is active
at any given time, critical for multi-market gap trading.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, date
from enum import Enum
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from agent_core.markets.calendar import MarketCode, MarketCalendar, get_calendar
from agent_core.markets.timezone import MARKET_TIMEZONES

logger = logging.getLogger(__name__)


class SessionType(str, Enum):
    """Market session types."""

    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"
    CLOSED = "closed"


class MarketSession(BaseModel):
    """Current session state for a market."""

    market: MarketCode
    session: SessionType
    local_time: datetime
    regular_open: time
    regular_close: time
    is_trading_day: bool
    is_half_day: bool = False
    next_open: datetime | None = None


# Market hours (local time)
MARKET_HOURS: dict[MarketCode, dict[str, time]] = {
    MarketCode.US: {
        "pre_open": time(4, 0),
        "regular_open": time(9, 30),
        "regular_close": time(16, 0),
        "after_close": time(20, 0),
        "half_day_close": time(13, 0),
    },
    MarketCode.EU: {
        "pre_open": time(7, 0),
        "regular_open": time(9, 0),
        "regular_close": time(17, 30),
        "after_close": time(17, 30),  # No extended hours in Europe
    },
    MarketCode.ES: {
        "pre_open": time(7, 0),
        "regular_open": time(9, 0),
        "regular_close": time(17, 30),
        "after_close": time(17, 30),
    },
    MarketCode.JP: {
        "pre_open": time(8, 0),
        "regular_open": time(9, 0),
        "regular_close": time(15, 0),  # Lunch break 11:30-12:30 ignored for simplicity
        "after_close": time(15, 0),
    },
    MarketCode.HK: {
        "pre_open": time(9, 0),
        "regular_open": time(9, 30),
        "regular_close": time(16, 0),  # Lunch break 12:00-13:00 ignored for simplicity
        "after_close": time(16, 10),
    },
    MarketCode.CRYPTO: {
        "pre_open": time(0, 0),
        "regular_open": time(0, 0),
        "regular_close": time(23, 59, 59),
        "after_close": time(23, 59, 59),
    },
}


def get_current_session(
    market: MarketCode,
    at_time: datetime | None = None,
) -> MarketSession:
    """Determine the current market session.

    Args:
        market: Market code.
        at_time: Specific datetime to check (default: now).

    Returns:
        MarketSession with session type and metadata.
    """
    tz_name = MARKET_TIMEZONES.get(market, "UTC")
    tz = ZoneInfo(tz_name)

    if at_time is None:
        local_now = datetime.now(tz=tz)
    elif at_time.tzinfo is None:
        local_now = at_time.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        local_now = at_time.astimezone(tz)

    hours = MARKET_HOURS.get(market)
    if not hours:
        return MarketSession(
            market=market,
            session=SessionType.CLOSED,
            local_time=local_now,
            regular_open=time(0, 0),
            regular_close=time(0, 0),
            is_trading_day=False,
        )

    calendar = get_calendar(market)
    today = local_now.date()
    is_trading = calendar.is_trading_day(today)
    is_half = calendar.is_half_day(today)

    # Crypto is always open
    if market == MarketCode.CRYPTO:
        return MarketSession(
            market=market,
            session=SessionType.REGULAR,
            local_time=local_now,
            regular_open=hours["regular_open"],
            regular_close=hours["regular_close"],
            is_trading_day=True,
        )

    if not is_trading:
        return MarketSession(
            market=market,
            session=SessionType.CLOSED,
            local_time=local_now,
            regular_open=hours["regular_open"],
            regular_close=hours["regular_close"],
            is_trading_day=False,
        )

    current_time = local_now.time()
    close_time = hours.get("half_day_close", hours["regular_close"]) if is_half else hours["regular_close"]

    if current_time < hours["pre_open"]:
        session = SessionType.CLOSED
    elif current_time < hours["regular_open"]:
        session = SessionType.PRE_MARKET
    elif current_time < close_time:
        session = SessionType.REGULAR
    elif current_time < hours["after_close"]:
        session = SessionType.AFTER_HOURS
    else:
        session = SessionType.CLOSED

    return MarketSession(
        market=market,
        session=session,
        local_time=local_now,
        regular_open=hours["regular_open"],
        regular_close=close_time,
        is_trading_day=is_trading,
        is_half_day=is_half,
    )
```

---

### src/agent_core/markets/currency.py

```python
"""FX conversion for multi-currency positions.

Provides currency pair conversion using ECB reference rates (cached)
or live rates from market-data-mcp.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CurrencyPair(BaseModel):
    """A currency conversion rate."""

    base: str  # e.g., "EUR"
    quote: str  # e.g., "USD"
    rate: float  # 1 base = rate quote
    timestamp: datetime
    source: str = "ecb"  # "ecb", "polygon", "ibkr"


class CurrencyConverter:
    """Currency converter with caching and fallback logic.

    Primary source: ECB daily reference rates (free, reliable).
    Fallback: Static rates (for backtest mode without network).
    """

    # Static fallback rates (approximate, updated periodically)
    _STATIC_RATES: dict[str, float] = {
        "EUR/USD": 1.08,
        "USD/EUR": 0.926,
        "EUR/GBP": 0.86,
        "GBP/EUR": 1.163,
        "EUR/JPY": 162.0,
        "JPY/EUR": 0.00617,
        "EUR/CHF": 0.96,
        "CHF/EUR": 1.042,
        "USD/JPY": 150.0,
        "JPY/USD": 0.00667,
        "USD/HKD": 7.82,
        "HKD/USD": 0.128,
        "EUR/HKD": 8.45,
        "HKD/EUR": 0.118,
        # Crypto — always USD denominated in QITP
        "BTC/USD": 65000.0,
        "ETH/USD": 3500.0,
    }

    def __init__(self, rate_provider: Any = None) -> None:
        """Initialize converter.

        Args:
            rate_provider: Optional async callable(base, quote) -> float.
                           If None, uses static rates.
        """
        self._rate_provider = rate_provider
        self._cache: dict[str, CurrencyPair] = {}

    async def get_rate(self, base: str, quote: str) -> CurrencyPair:
        """Get conversion rate from base to quote currency.

        Args:
            base: Base currency (e.g., "EUR").
            quote: Quote currency (e.g., "USD").

        Returns:
            CurrencyPair with the rate.
        """
        if base == quote:
            return CurrencyPair(
                base=base, quote=quote, rate=1.0,
                timestamp=datetime.utcnow(), source="identity",
            )

        pair_key = f"{base}/{quote}"

        # Check cache (valid for 1 hour)
        cached = self._cache.get(pair_key)
        if cached and (datetime.utcnow() - cached.timestamp).seconds < 3600:
            return cached

        # Try live provider
        if self._rate_provider:
            try:
                rate = await self._rate_provider(base, quote)
                pair = CurrencyPair(
                    base=base, quote=quote, rate=rate,
                    timestamp=datetime.utcnow(), source="live",
                )
                self._cache[pair_key] = pair
                return pair
            except Exception:
                logger.warning("Live rate fetch failed for %s, using static", pair_key)

        # Static fallback
        static_rate = self._STATIC_RATES.get(pair_key)
        if static_rate:
            return CurrencyPair(
                base=base, quote=quote, rate=static_rate,
                timestamp=datetime.utcnow(), source="static",
            )

        # Try inverse
        inverse_key = f"{quote}/{base}"
        inverse_rate = self._STATIC_RATES.get(inverse_key)
        if inverse_rate and inverse_rate != 0:
            return CurrencyPair(
                base=base, quote=quote, rate=1.0 / inverse_rate,
                timestamp=datetime.utcnow(), source="static_inverse",
            )

        raise ValueError(f"No rate available for {pair_key}")


# Module-level singleton
_converter: CurrencyConverter | None = None


async def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    converter: CurrencyConverter | None = None,
) -> float:
    """Convert an amount from one currency to another.

    Args:
        amount: Amount in from_currency.
        from_currency: Source currency code (e.g., "JPY").
        to_currency: Target currency code (e.g., "EUR").
        converter: Optional converter instance (uses module singleton if None).

    Returns:
        Converted amount in to_currency.
    """
    global _converter
    if converter is None:
        if _converter is None:
            _converter = CurrencyConverter()
        converter = _converter

    pair = await converter.get_rate(from_currency, to_currency)
    return amount * pair.rate
```

---

### src/qitp_mcp_market_data/providers/tokyo.py

```python
"""Tokyo Stock Exchange (TSE) market data provider.

Supports Nikkei 225 and TOPIX constituents. Uses J-Quants API
for live data and S3 parquet for historical/backtest mode.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

from qitp_mcp_market_data.providers.base import DataProvider
from qitp_mcp_market_data.schemas import Bar, GapResult, VolumeProfile

logger = logging.getLogger(__name__)


class TokyoProvider(DataProvider):
    """TSE data provider.

    Backtest mode: reads from S3 parquet files at
        s3://qitp-historical-data/jp/{symbol}/{year}.parquet

    Live/paper mode: uses J-Quants API (requires JQUANTS_API_KEY env var).
    """

    def __init__(
        self,
        s3_client: Any = None,
        bucket: str = "qitp-historical-data",
        execution_mode: str = "backtest",
    ) -> None:
        self._s3_client = s3_client
        self._bucket = bucket
        self._execution_mode = execution_mode
        self._api_key = os.environ.get("JQUANTS_API_KEY")

    @property
    def provider_id(self) -> str:
        return "tokyo"

    @property
    def supported_markets(self) -> list[str]:
        return ["jp"]

    async def get_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Get OHLCV bars for a TSE symbol.

        TSE symbols use format: {code}.T (e.g., 7203.T for Toyota).
        """
        if self._execution_mode == "backtest":
            return await self._load_from_s3(symbol, start_date, end_date)
        else:
            return await self._fetch_from_jquants(symbol, start_date, end_date)

    async def _load_from_s3(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Load historical data from S3 parquet."""
        import pandas as pd
        import io

        bars: list[Bar] = []
        years = range(start_date.year, end_date.year + 1)

        for year in years:
            key = f"jp/{symbol}/{year}.parquet"
            try:
                response = self._s3_client.get_object(
                    Bucket=self._bucket, Key=key,
                )
                df = pd.read_parquet(io.BytesIO(response["Body"].read()))
                df["date"] = pd.to_datetime(df["date"]).dt.date

                mask = (df["date"] >= start_date) & (df["date"] <= end_date)
                for _, row in df[mask].iterrows():
                    bars.append(
                        Bar(
                            date=row["date"],
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"]),
                            adjusted_close=float(row.get("adjusted_close", row["close"])),
                        )
                    )
            except Exception as e:
                logger.warning("Failed to load %s: %s", key, e)

        return sorted(bars, key=lambda b: b.date)

    async def _fetch_from_jquants(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Fetch data from J-Quants API."""
        import httpx

        if not self._api_key:
            raise RuntimeError("JQUANTS_API_KEY env var required for live TSE data")

        # Strip .T suffix for J-Quants API
        code = symbol.replace(".T", "")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.jquants.com/v1/prices/daily_quotes",
                params={
                    "code": code,
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        bars = []
        for quote in data.get("daily_quotes", []):
            bars.append(
                Bar(
                    date=date.fromisoformat(quote["Date"]),
                    open=float(quote["Open"]),
                    high=float(quote["High"]),
                    low=float(quote["Low"]),
                    close=float(quote["Close"]),
                    volume=int(quote["Volume"]),
                    adjusted_close=float(quote.get("AdjustmentClose", quote["Close"])),
                )
            )

        return sorted(bars, key=lambda b: b.date)

    async def get_gap(
        self,
        symbol: str,
        monday: date,
        threshold_pct: float = 2.0,
    ) -> GapResult | None:
        """Calculate weekend gap for a TSE symbol.

        TSE opens Monday 9:00 JST. Friday close is 15:00 JST.
        """
        from agent_core.markets.calendar import get_calendar, MarketCode

        calendar = get_calendar(MarketCode.JP)
        gap_window = calendar.gap_window(monday)
        if not gap_window:
            return None

        friday, mon = gap_window
        bars = await self.get_ohlcv(symbol, friday, mon)

        friday_bar = next((b for b in bars if b.date == friday), None)
        monday_bar = next((b for b in bars if b.date == mon), None)

        if not friday_bar or not monday_bar:
            return None

        gap_pct = ((monday_bar.open - friday_bar.close) / friday_bar.close) * 100

        return GapResult(
            symbol=symbol,
            date=mon,
            friday_close=friday_bar.close,
            monday_open=monday_bar.open,
            gap_pct=round(gap_pct, 4),
            gap_abs_pct=round(abs(gap_pct), 4),
            direction="up" if gap_pct > 0 else "down",
            volume_ratio=1.0,  # Volume ratio requires 20-day avg computation
            significant=abs(gap_pct) >= threshold_pct,
        )
```

---

### src/qitp_mcp_market_data/providers/hkex.py

```python
"""HKEX (Hong Kong Stock Exchange) market data provider.

Supports Hang Seng Index constituents. Uses HKEX public API or
Yahoo Finance as fallback. S3 parquet for backtest mode.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

from qitp_mcp_market_data.providers.base import DataProvider
from qitp_mcp_market_data.schemas import Bar, GapResult

logger = logging.getLogger(__name__)


class HKEXProvider(DataProvider):
    """HKEX data provider.

    Backtest mode: S3 at s3://qitp-historical-data/hk/{symbol}/{year}.parquet
    Live/paper mode: Yahoo Finance (yfinance) with .HK suffix.
    """

    def __init__(
        self,
        s3_client: Any = None,
        bucket: str = "qitp-historical-data",
        execution_mode: str = "backtest",
    ) -> None:
        self._s3_client = s3_client
        self._bucket = bucket
        self._execution_mode = execution_mode

    @property
    def provider_id(self) -> str:
        return "hkex"

    @property
    def supported_markets(self) -> list[str]:
        return ["hk"]

    async def get_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Get OHLCV bars for an HKEX symbol.

        HKEX symbols use format: {code}.HK (e.g., 0700.HK for Tencent).
        """
        if self._execution_mode == "backtest":
            return await self._load_from_s3(symbol, start_date, end_date)
        else:
            return await self._fetch_from_yahoo(symbol, start_date, end_date)

    async def _load_from_s3(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Load historical data from S3 parquet."""
        import pandas as pd
        import io

        bars: list[Bar] = []
        years = range(start_date.year, end_date.year + 1)

        for year in years:
            key = f"hk/{symbol}/{year}.parquet"
            try:
                response = self._s3_client.get_object(
                    Bucket=self._bucket, Key=key,
                )
                df = pd.read_parquet(io.BytesIO(response["Body"].read()))
                df["date"] = pd.to_datetime(df["date"]).dt.date

                mask = (df["date"] >= start_date) & (df["date"] <= end_date)
                for _, row in df[mask].iterrows():
                    bars.append(
                        Bar(
                            date=row["date"],
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"]),
                        )
                    )
            except Exception as e:
                logger.warning("Failed to load %s: %s", key, e)

        return sorted(bars, key=lambda b: b.date)

    async def _fetch_from_yahoo(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Fetch data from Yahoo Finance."""
        import yfinance as yf

        # Ensure .HK suffix
        yf_symbol = symbol if symbol.endswith(".HK") else f"{symbol}.HK"

        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date.isoformat(), end=end_date.isoformat())

        bars = []
        for idx, row in df.iterrows():
            bars.append(
                Bar(
                    date=idx.date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )

        return sorted(bars, key=lambda b: b.date)

    async def get_gap(
        self,
        symbol: str,
        monday: date,
        threshold_pct: float = 2.0,
    ) -> GapResult | None:
        """Calculate weekend gap for an HKEX symbol."""
        from agent_core.markets.calendar import get_calendar, MarketCode

        calendar = get_calendar(MarketCode.HK)
        gap_window = calendar.gap_window(monday)
        if not gap_window:
            return None

        friday, mon = gap_window
        bars = await self.get_ohlcv(symbol, friday, mon)

        friday_bar = next((b for b in bars if b.date == friday), None)
        monday_bar = next((b for b in bars if b.date == mon), None)

        if not friday_bar or not monday_bar:
            return None

        gap_pct = ((monday_bar.open - friday_bar.close) / friday_bar.close) * 100

        return GapResult(
            symbol=symbol,
            date=mon,
            friday_close=friday_bar.close,
            monday_open=monday_bar.open,
            gap_pct=round(gap_pct, 4),
            gap_abs_pct=round(abs(gap_pct), 4),
            direction="up" if gap_pct > 0 else "down",
            volume_ratio=1.0,
            significant=abs(gap_pct) >= threshold_pct,
        )
```

---

### src/qitp_mcp_market_data/providers/crypto.py

```python
"""Cryptocurrency market data provider.

Supports major crypto assets via Binance and Coinbase APIs.
Crypto trades 24/7 — gap detection uses weekly candle boundaries
(Sunday 00:00 UTC to Monday 00:00 UTC) instead of traditional
Friday close / Monday open.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

from qitp_mcp_market_data.providers.base import DataProvider
from qitp_mcp_market_data.schemas import Bar, GapResult

logger = logging.getLogger(__name__)


class CryptoProvider(DataProvider):
    """Crypto data provider using Binance or Coinbase.

    Backtest: S3 at s3://qitp-historical-data/crypto/{symbol}/{year}.parquet
    Live/paper: Binance public API (no auth for market data) or Coinbase.

    Symbol format: BTC-USD, ETH-USD, SOL-USD.
    """

    def __init__(
        self,
        s3_client: Any = None,
        bucket: str = "qitp-historical-data",
        execution_mode: str = "backtest",
        provider: str = "binance",  # "binance" or "coinbase"
    ) -> None:
        self._s3_client = s3_client
        self._bucket = bucket
        self._execution_mode = execution_mode
        self._provider = provider

    @property
    def provider_id(self) -> str:
        return "crypto"

    @property
    def supported_markets(self) -> list[str]:
        return ["crypto"]

    def _to_binance_symbol(self, symbol: str) -> str:
        """Convert QITP symbol (BTC-USD) to Binance format (BTCUSDT)."""
        base = symbol.split("-")[0]
        return f"{base}USDT"

    async def get_ohlcv(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Get daily OHLCV bars for a crypto asset."""
        if self._execution_mode == "backtest":
            return await self._load_from_s3(symbol, start_date, end_date)
        else:
            return await self._fetch_from_binance(symbol, start_date, end_date)

    async def _load_from_s3(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Load historical data from S3 parquet."""
        import pandas as pd
        import io

        bars: list[Bar] = []
        years = range(start_date.year, end_date.year + 1)

        for year in years:
            key = f"crypto/{symbol}/{year}.parquet"
            try:
                response = self._s3_client.get_object(
                    Bucket=self._bucket, Key=key,
                )
                df = pd.read_parquet(io.BytesIO(response["Body"].read()))
                df["date"] = pd.to_datetime(df["date"]).dt.date

                mask = (df["date"] >= start_date) & (df["date"] <= end_date)
                for _, row in df[mask].iterrows():
                    bars.append(
                        Bar(
                            date=row["date"],
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"]),
                        )
                    )
            except Exception as e:
                logger.warning("Failed to load %s: %s", key, e)

        return sorted(bars, key=lambda b: b.date)

    async def _fetch_from_binance(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Fetch data from Binance public klines API.

        No API key required for market data endpoints.
        """
        import httpx

        binance_symbol = self._to_binance_symbol(symbol)
        start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(end_date, datetime.min.time()).timestamp() * 1000)

        bars: list[Bar] = []

        async with httpx.AsyncClient() as client:
            # Binance returns max 1000 candles per request
            current_start = start_ms
            while current_start < end_ms:
                response = await client.get(
                    "https://api.binance.com/api/v3/klines",
                    params={
                        "symbol": binance_symbol,
                        "interval": "1d",
                        "startTime": current_start,
                        "endTime": end_ms,
                        "limit": 1000,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                klines = response.json()

                if not klines:
                    break

                for k in klines:
                    bar_date = datetime.fromtimestamp(k[0] / 1000).date()
                    bars.append(
                        Bar(
                            date=bar_date,
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=int(float(k[5])),
                        )
                    )

                # Move to next batch
                current_start = klines[-1][0] + 1

        return sorted(bars, key=lambda b: b.date)

    async def get_gap(
        self,
        symbol: str,
        monday: date,
        threshold_pct: float = 2.0,
    ) -> GapResult | None:
        """Calculate 'weekend gap' for crypto.

        Since crypto trades 24/7, there is no true gap. Instead,
        we measure the difference between Sunday 23:59 UTC close
        and Monday 00:00 UTC open — which captures weekend momentum shifts.

        This is a weaker signal than equity gaps but still useful
        for detecting weekend news-driven moves.
        """
        sunday = monday - timedelta(days=1)
        bars = await self.get_ohlcv(symbol, sunday, monday)

        sunday_bar = next((b for b in bars if b.date == sunday), None)
        monday_bar = next((b for b in bars if b.date == monday), None)

        if not sunday_bar or not monday_bar:
            return None

        gap_pct = ((monday_bar.open - sunday_bar.close) / sunday_bar.close) * 100

        return GapResult(
            symbol=symbol,
            date=monday,
            friday_close=sunday_bar.close,  # Using sunday close for crypto
            monday_open=monday_bar.open,
            gap_pct=round(gap_pct, 4),
            gap_abs_pct=round(abs(gap_pct), 4),
            direction="up" if gap_pct > 0 else "down",
            volume_ratio=1.0,
            significant=abs(gap_pct) >= threshold_pct,
            gap_type="crypto_weekend",
        )
```

---

# Component 3: A2A Protocol Integration

---

### src/qitp_agents/a2a/__init__.py

```python
"""A2A Protocol integration — expose QITP agents as discoverable A2A services."""
```

---

### src/qitp_agents/a2a/agent_card.py

```python
"""A2A Agent Card generation.

Agent Cards are the discovery mechanism in the A2A protocol. Each QITP
agent publishes a card at /.well-known/agent.json describing its
capabilities, input/output schemas, and authentication requirements.

Ref: https://google.github.io/A2A/specification/
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentSkill(BaseModel):
    """A skill (capability) exposed by the agent."""

    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class AgentAuthentication(BaseModel):
    """Authentication requirements for the agent."""

    schemes: list[str] = Field(default_factory=lambda: ["bearer"])
    credentials: str | None = None  # URL to get credentials


class AgentCapabilities(BaseModel):
    """Agent capability declarations."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = True


class AgentCard(BaseModel):
    """A2A Agent Card — the discovery document for an agent.

    Published at /.well-known/agent.json per the A2A specification.
    """

    name: str
    description: str
    url: str  # Agent endpoint URL
    version: str = "1.0.0"
    protocol_version: str = "0.2.1"  # A2A protocol version
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    authentication: AgentAuthentication = Field(default_factory=AgentAuthentication)
    default_input_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    default_output_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    skills: list[AgentSkill] = Field(default_factory=list)
    provider: dict[str, str] = Field(
        default_factory=lambda: {
            "organization": "QITP",
            "url": "https://qitp.internal",
        }
    )


# --- Card generators for each QITP agent ---

def build_gap_detector_card(base_url: str) -> AgentCard:
    """Build A2A Agent Card for the Gap Detection Agent."""
    return AgentCard(
        name="QITP Gap Detection Agent",
        description=(
            "Identifies and ranks weekend price gaps across a configurable "
            "watchlist of equity symbols. Returns ranked gap list with "
            "magnitude, direction, volume confirmation, and confidence scores."
        ),
        url=f"{base_url}/agents/gap-detector",
        skills=[
            AgentSkill(
                id="detect_gaps",
                name="Detect Weekend Gaps",
                description="Scan watchlist for weekend price gaps on a given date.",
                tags=["market-data", "gap-detection", "trading"],
                examples=[
                    "Find all price gaps greater than 2% for the default watchlist on 2026-03-09",
                    "Scan for gaps in US equities on Monday 2026-01-05",
                ],
            ),
        ],
    )


def build_sentiment_analyzer_card(base_url: str) -> AgentCard:
    """Build A2A Agent Card for the Sentiment Analysis Agent."""
    return AgentCard(
        name="QITP Sentiment Analysis Agent",
        description=(
            "Multi-source sentiment scoring for financial instruments. "
            "Aggregates news, social media, and analyst sentiment into "
            "a composite score per symbol."
        ),
        url=f"{base_url}/agents/sentiment-analyzer",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="analyze_sentiment",
                name="Analyze Sentiment",
                description="Get composite sentiment score for one or more symbols.",
                tags=["sentiment", "nlp", "trading"],
                examples=[
                    "What is the sentiment for AAPL and TSLA on 2026-03-15?",
                    "Analyze news sentiment for NVDA",
                ],
            ),
        ],
    )


def build_portfolio_recommender_card(base_url: str) -> AgentCard:
    """Build A2A Agent Card for the Portfolio Recommender Agent."""
    return AgentCard(
        name="QITP Portfolio Recommender Agent",
        description=(
            "Synthesizes gap detection, sentiment analysis, and strategy "
            "evaluation results into actionable portfolio recommendations "
            "with position sizing and risk parameters."
        ),
        url=f"{base_url}/agents/portfolio-recommender",
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="recommend_portfolio",
                name="Generate Portfolio Recommendation",
                description=(
                    "Given gap and sentiment analysis results, generate "
                    "a portfolio recommendation with position sizes."
                ),
                tags=["portfolio", "recommendation", "trading"],
                examples=[
                    "Generate portfolio recommendation from gap analysis artifact abc123",
                ],
            ),
        ],
    )


def build_watchlist_screener_card(base_url: str) -> AgentCard:
    """Build A2A Agent Card for the Watchlist Screener Agent."""
    return AgentCard(
        name="QITP Watchlist Screener Agent",
        description=(
            "AI-powered stock universe scanner that identifies candidates "
            "with high gap trading potential based on liquidity, volatility, "
            "historical gap frequency, and sector diversification."
        ),
        url=f"{base_url}/agents/watchlist-screener",
        skills=[
            AgentSkill(
                id="screen_universe",
                name="Screen Stock Universe",
                description="Scan universes for gap trading candidates.",
                tags=["screener", "watchlist", "universe"],
                examples=[
                    "Screen S&P 500 and STOXX 600 for gap candidates",
                    "Find top 20 crypto assets with gap potential",
                ],
            ),
        ],
    )


def build_tax_reporter_card(base_url: str) -> AgentCard:
    """Build A2A Agent Card for the Tax Reporter Agent."""
    return AgentCard(
        name="QITP Tax Reporter Agent",
        description=(
            "Generates Spanish IRPF tax reports from trading history. "
            "Calculates capital gains/losses using FIFO, handles multi-currency "
            "positions, and produces AEAT-compatible output."
        ),
        url=f"{base_url}/agents/tax-reporter",
        skills=[
            AgentSkill(
                id="generate_tax_report",
                name="Generate IRPF Tax Report",
                description="Generate Spanish tax report for a given fiscal year.",
                tags=["tax", "irpf", "compliance", "spain"],
                examples=[
                    "Generate 2025 IRPF tax report",
                    "Calculate capital gains for fiscal year 2025",
                ],
            ),
        ],
    )


# --- Registry ---

AGENT_CARD_BUILDERS: dict[str, Any] = {
    "gap-detector": build_gap_detector_card,
    "sentiment-analyzer": build_sentiment_analyzer_card,
    "portfolio-recommender": build_portfolio_recommender_card,
    "watchlist-screener": build_watchlist_screener_card,
    "tax-reporter": build_tax_reporter_card,
}


def build_all_cards(base_url: str) -> dict[str, AgentCard]:
    """Build Agent Cards for all registered QITP agents."""
    return {
        agent_id: builder(base_url)
        for agent_id, builder in AGENT_CARD_BUILDERS.items()
    }
```

---

### src/qitp_agents/a2a/task_handler.py

```python
"""A2A Task handler — receive, execute, and respond to A2A tasks.

Implements the A2A task lifecycle:
  1. tasks/send — receive task, invoke appropriate QITP agent
  2. tasks/get — return task status/result
  3. tasks/cancel — cancel a running task

Ref: https://google.github.io/A2A/specification/
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """A2A task states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskMessage(BaseModel):
    """A message in the A2A task conversation."""

    role: str  # "user" or "agent"
    parts: list[dict[str, Any]]  # Content parts (text, data, file, etc.)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TaskStatus(BaseModel):
    """Current status of an A2A task."""

    state: TaskState
    message: TaskMessage | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Task(BaseModel):
    """An A2A task representing a single request-response cycle."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    status: TaskStatus
    messages: list[TaskMessage] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2ATaskHandler:
    """Handles A2A task lifecycle by routing to QITP agent handlers.

    Maps A2A task messages to QITP agent invocations and converts
    agent outputs back to A2A response format.
    """

    def __init__(self, agent_handlers: dict[str, Any]) -> None:
        """Initialize with a map of agent_id -> handler function.

        Each handler function has signature: handler(event, context) -> dict
        """
        self._handlers = agent_handlers
        self._tasks: dict[str, Task] = {}  # In-memory store (DynamoDB in production)

    async def send_task(self, agent_id: str, request: dict[str, Any]) -> Task:
        """Handle tasks/send — create and execute a task.

        Args:
            agent_id: Target QITP agent ID.
            request: A2A task send request body.

        Returns:
            Task with result or error status.
        """
        task_id = request.get("id", str(uuid.uuid4()))
        session_id = request.get("sessionId")

        # Extract user message
        message_data = request.get("message", {})
        user_message = TaskMessage(
            role="user",
            parts=message_data.get("parts", []),
        )

        task = Task(
            id=task_id,
            session_id=session_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            messages=[user_message],
        )
        self._tasks[task_id] = task

        # Route to QITP agent handler
        handler_fn = self._handlers.get(agent_id)
        if not handler_fn:
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message=TaskMessage(
                    role="agent",
                    parts=[{"type": "text", "text": f"Unknown agent: {agent_id}"}],
                ),
            )
            return task

        # Convert A2A message parts to QITP agent event
        event = self._a2a_to_agent_event(user_message, agent_id)

        task.status = TaskStatus(state=TaskState.WORKING)

        try:
            result = handler_fn(event)

            # Convert agent response to A2A format
            response_parts = self._agent_result_to_parts(result)

            agent_message = TaskMessage(role="agent", parts=response_parts)
            task.messages.append(agent_message)

            # Store artifacts if present
            body = result.get("body")
            if body:
                import json
                body_data = json.loads(body) if isinstance(body, str) else body
                if "artifact_id" in body_data:
                    task.artifacts.append({
                        "name": f"{agent_id}_output",
                        "parts": [{"type": "data", "data": body_data}],
                    })

            task.status = TaskStatus(
                state=TaskState.COMPLETED,
                message=agent_message,
            )

        except Exception as e:
            logger.exception("A2A task execution failed: %s", task_id)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message=TaskMessage(
                    role="agent",
                    parts=[{"type": "text", "text": f"Execution failed: {e}"}],
                ),
            )

        return task

    async def get_task(self, task_id: str) -> Task | None:
        """Handle tasks/get — retrieve task status."""
        return self._tasks.get(task_id)

    async def cancel_task(self, task_id: str) -> Task | None:
        """Handle tasks/cancel — cancel a running task."""
        task = self._tasks.get(task_id)
        if task and task.status.state in (TaskState.SUBMITTED, TaskState.WORKING):
            task.status = TaskStatus(state=TaskState.CANCELED)
        return task

    def _a2a_to_agent_event(self, message: TaskMessage, agent_id: str) -> dict[str, Any]:
        """Convert A2A message parts to QITP Lambda event format."""
        event: dict[str, Any] = {"agent_id": agent_id}

        for part in message.parts:
            if part.get("type") == "data":
                # Structured data — merge into event
                event.update(part.get("data", {}))
            elif part.get("type") == "text":
                # Free text — add as query
                event["query"] = part.get("text", "")

        return event

    def _agent_result_to_parts(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert QITP agent result to A2A message parts."""
        import json

        parts: list[dict[str, Any]] = []
        status_code = result.get("statusCode", 500)
        body = result.get("body", "{}")

        if isinstance(body, str):
            body_data = json.loads(body)
        else:
            body_data = body

        if status_code == 200:
            parts.append({"type": "data", "data": body_data})
            # Add human-readable summary
            summary = body_data.get("summary", body_data.get("message", "Task completed."))
            parts.append({"type": "text", "text": str(summary)})
        else:
            error_msg = body_data.get("error", "Unknown error")
            parts.append({"type": "text", "text": f"Error: {error_msg}"})

        return parts
```

---

### src/qitp_agents/a2a/discovery.py

```python
"""A2A Agent discovery — find and connect to external A2A agents.

Provides client-side discovery of external agents that QITP can
delegate tasks to (e.g., external research agents, data providers).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from qitp_agents.a2a.agent_card import AgentCard

logger = logging.getLogger(__name__)


class DiscoveredAgent(BaseModel):
    """An externally discovered A2A agent."""

    card: AgentCard
    health_status: str = "unknown"  # "healthy", "degraded", "unhealthy", "unknown"
    last_checked: str | None = None


class AgentDiscovery:
    """Discover and cache external A2A agents.

    Discovery process:
    1. Fetch /.well-known/agent.json from known agent URLs
    2. Parse Agent Card
    3. Cache for reuse (TTL-based)
    4. Health check via ping
    """

    def __init__(self) -> None:
        self._cache: dict[str, DiscoveredAgent] = {}

    async def discover(self, agent_url: str) -> DiscoveredAgent | None:
        """Discover an agent by fetching its Agent Card.

        Args:
            agent_url: Base URL of the agent (e.g., https://agent.example.com).

        Returns:
            DiscoveredAgent if card found, None otherwise.
        """
        import httpx
        from datetime import datetime

        well_known_url = f"{agent_url.rstrip('/')}/.well-known/agent.json"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(well_known_url, timeout=10.0)
                response.raise_for_status()
                card_data = response.json()

            card = AgentCard(**card_data)

            discovered = DiscoveredAgent(
                card=card,
                health_status="healthy",
                last_checked=datetime.utcnow().isoformat(),
            )
            self._cache[agent_url] = discovered

            logger.info("Discovered A2A agent: %s at %s", card.name, agent_url)
            return discovered

        except Exception as e:
            logger.warning("Failed to discover agent at %s: %s", agent_url, e)
            return None

    async def discover_many(self, urls: list[str]) -> list[DiscoveredAgent]:
        """Discover multiple agents in parallel."""
        import asyncio

        results = await asyncio.gather(
            *[self.discover(url) for url in urls],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, DiscoveredAgent)]

    def get_cached(self, agent_url: str) -> DiscoveredAgent | None:
        """Get a cached agent discovery result."""
        return self._cache.get(agent_url)

    def list_cached(self) -> list[DiscoveredAgent]:
        """List all cached discovered agents."""
        return list(self._cache.values())

    def find_by_skill(self, skill_tag: str) -> list[DiscoveredAgent]:
        """Find cached agents that have a skill matching the given tag."""
        matches = []
        for agent in self._cache.values():
            for skill in agent.card.skills:
                if skill_tag in skill.tags:
                    matches.append(agent)
                    break
        return matches
```

---

### src/qitp_agents/a2a/server.py

```python
"""A2A HTTP server — expose QITP agents via the A2A protocol.

Runs as a FastAPI service that implements the A2A endpoints:
  GET  /.well-known/agent.json    — Agent Card discovery
  POST /agents/{agent_id}/tasks/send    — Send a task
  GET  /agents/{agent_id}/tasks/{id}    — Get task status
  POST /agents/{agent_id}/tasks/{id}/cancel — Cancel a task

Deployed as ECS Fargate service or Lambda + API Gateway.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from qitp_agents.a2a.agent_card import build_all_cards, AGENT_CARD_BUILDERS
from qitp_agents.a2a.task_handler import A2ATaskHandler

logger = logging.getLogger(__name__)

app = FastAPI(
    title="QITP A2A Server",
    description="A2A protocol server exposing QITP trading agents",
    version="1.0.0",
)

# Lazy-initialized handler (populated on first request or at startup)
_task_handler: A2ATaskHandler | None = None
_base_url: str = os.environ.get("A2A_BASE_URL", "http://localhost:8080")


def _get_task_handler() -> A2ATaskHandler:
    """Lazy-initialize the task handler with QITP agent handlers."""
    global _task_handler
    if _task_handler is None:
        # Import agent handlers
        handlers: dict[str, Any] = {}

        try:
            from qitp_agents.gap_detector.handler import handler as gap_handler
            handlers["gap-detector"] = gap_handler
        except ImportError:
            logger.warning("Gap detector handler not available")

        try:
            from qitp_agents.sentiment_analyzer.handler import handler as sentiment_handler
            handlers["sentiment-analyzer"] = sentiment_handler
        except ImportError:
            logger.warning("Sentiment analyzer handler not available")

        try:
            from qitp_agents.watchlist_screener.handler import handler as screener_handler
            handlers["watchlist-screener"] = screener_handler
        except ImportError:
            logger.warning("Watchlist screener handler not available")

        try:
            from qitp_agents.tax_reporter.handler import handler as tax_handler
            handlers["tax-reporter"] = tax_handler
        except ImportError:
            logger.warning("Tax reporter handler not available")

        _task_handler = A2ATaskHandler(agent_handlers=handlers)

    return _task_handler


# --- Discovery endpoint ---

@app.get("/.well-known/agent.json")
async def get_agent_card(request: Request):
    """Return the multi-agent Agent Card for QITP.

    Returns a composite card listing all available agents as skills.
    Individual agent cards are available at /agents/{agent_id}/.well-known/agent.json.
    """
    cards = build_all_cards(_base_url)
    # Return first card as the "root" agent — in production this would be
    # a composite card that references sub-agents
    all_skills = []
    for card in cards.values():
        all_skills.extend(card.skills)

    root_card = {
        "name": "QITP Trading Platform",
        "description": "AI-native quantitative trading platform with gap detection, sentiment analysis, portfolio recommendation, and tax reporting.",
        "url": _base_url,
        "version": "1.0.0",
        "protocolVersion": "0.2.1",
        "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": True},
        "authentication": {"schemes": ["bearer"]},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [s.model_dump() for s in all_skills],
        "provider": {"organization": "QITP", "url": "https://qitp.internal"},
    }
    return JSONResponse(content=root_card)


@app.get("/agents/{agent_id}/.well-known/agent.json")
async def get_individual_agent_card(agent_id: str):
    """Return Agent Card for a specific QITP agent."""
    builder = AGENT_CARD_BUILDERS.get(agent_id)
    if not builder:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    card = builder(_base_url)
    return JSONResponse(content=card.model_dump())


# --- Task endpoints ---

@app.post("/agents/{agent_id}/tasks/send")
async def send_task(agent_id: str, request: Request):
    """Send a task to a QITP agent."""
    handler = _get_task_handler()
    body = await request.json()

    task = await handler.send_task(agent_id, body)
    return JSONResponse(content=task.model_dump(mode="json"))


@app.get("/agents/{agent_id}/tasks/{task_id}")
async def get_task(agent_id: str, task_id: str):
    """Get task status and result."""
    handler = _get_task_handler()
    task = await handler.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return JSONResponse(content=task.model_dump(mode="json"))


@app.post("/agents/{agent_id}/tasks/{task_id}/cancel")
async def cancel_task(agent_id: str, task_id: str):
    """Cancel a running task."""
    handler = _get_task_handler()
    task = await handler.cancel_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return JSONResponse(content=task.model_dump(mode="json"))


# --- Health endpoint ---

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "qitp-a2a-server"}


def main() -> None:
    """Run the A2A server."""
    import uvicorn

    host = os.environ.get("A2A_HOST", "0.0.0.0")
    port = int(os.environ.get("A2A_PORT", "8080"))

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
```

---

# Component 4: Tax Report Generator

---

### blueprints/agents/tax_reporter.yaml

```yaml
agent_id: tax-reporter
name: Tax Reporter Agent
version: "1.0.0"
description: >
  Generates Spanish IRPF (Impuesto sobre la Renta de las Personas Fisicas)
  tax reports from QITP trading history. Calculates capital gains/losses
  using FIFO method, handles multi-currency conversion to EUR, and produces
  output compatible with AEAT Modelo 100 declarations.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.0

system_prompt_id: tax-reporter-system-v1

tools:
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact
      - get_artifact
      - list_artifacts
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_ohlcv

execution:
  timeout_seconds: 300
  max_tool_calls: 100
  retry_policy:
    max_retries: 2
    backoff_base: 2.0

output_schema: TaxReport

tags:
  - tax
  - irpf
  - compliance
  - phase-3
```

---

### src/qitp_agents/tax_reporter/__init__.py

```python
"""Tax Reporter Agent — Spanish IRPF tax report generation from trading history."""
```

---

### src/qitp_agents/tax_reporter/models.py

```python
"""Tax report data models.

Implements Spanish IRPF tax structures for capital gains from
financial instrument trading. Follows AEAT Modelo 100 requirements.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AssetType(str, Enum):
    """Financial asset types for tax classification."""

    EQUITY = "equity"
    ETF = "etf"
    CFD = "cfd"
    CRYPTO = "crypto"
    FUND = "fund"


class TransactionType(str, Enum):
    """Transaction types."""

    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FX_CONVERSION = "fx_conversion"


class TaxLot(BaseModel):
    """A tax lot representing a specific acquisition of shares/units.

    FIFO (First In First Out) is mandatory in Spain for capital gains calculation.
    Each buy creates a new lot; each sell consumes lots in FIFO order.
    """

    lot_id: str
    symbol: str
    asset_type: AssetType
    acquisition_date: date
    acquisition_price_local: float  # Price in instrument currency
    acquisition_price_eur: float  # Price converted to EUR at acquisition date rate
    acquisition_fx_rate: float  # FX rate on acquisition date (1 local = X EUR)
    quantity: float
    remaining_quantity: float  # Quantity not yet disposed
    currency: str  # Instrument currency (USD, EUR, JPY, etc.)
    exchange: str
    isin: str | None = None  # ISIN for MiFID II compliance
    commission_eur: float = 0.0  # Acquisition commission in EUR


class CapitalGain(BaseModel):
    """A single capital gain/loss from disposing of a tax lot.

    Spanish IRPF distinguishes:
    - Short-term: acquisition to disposal < 1 year (taxed as savings income)
    - Long-term: >= 1 year (also savings income, same rates in Spain)

    Tax rates for savings income (rentas del ahorro) 2025:
    - First EUR 6,000: 19%
    - EUR 6,001 - 50,000: 21%
    - EUR 50,001 - 200,000: 23%
    - EUR 200,001 - 300,000: 27%
    - Over EUR 300,000: 28%
    """

    symbol: str
    asset_type: AssetType
    isin: str | None = None
    acquisition_date: date
    disposal_date: date
    holding_period_days: int
    quantity: float
    acquisition_price_eur: float  # Total cost basis in EUR (price * qty + commission)
    disposal_price_eur: float  # Total proceeds in EUR (price * qty - commission)
    gain_loss_eur: float  # disposal_price_eur - acquisition_price_eur
    is_gain: bool  # True if gain_loss_eur > 0
    acquisition_commission_eur: float = 0.0
    disposal_commission_eur: float = 0.0
    acquisition_fx_rate: float = 1.0
    disposal_fx_rate: float = 1.0
    lot_id: str | None = None

    # Anti-avoidance: Spanish law prohibits claiming a loss if you
    # repurchase the same asset within 2 months (homogeneous securities rule)
    loss_disallowed: bool = False
    loss_disallowed_reason: str | None = None


class DividendIncome(BaseModel):
    """Dividend income record for tax reporting."""

    symbol: str
    payment_date: date
    gross_amount_local: float
    gross_amount_eur: float
    withholding_tax_local: float  # Tax withheld at source
    withholding_tax_eur: float
    net_amount_eur: float
    country_of_source: str  # For double taxation treaty claims
    fx_rate: float = 1.0


class TaxSummary(BaseModel):
    """Aggregated tax summary for the fiscal year."""

    fiscal_year: int
    total_gains_eur: float
    total_losses_eur: float
    net_gain_loss_eur: float
    disallowed_losses_eur: float  # Losses blocked by homogeneous securities rule
    total_commissions_eur: float
    dividend_income_gross_eur: float
    dividend_withholding_eur: float
    estimated_tax_eur: float  # Estimated tax liability
    tax_bracket_breakdown: list[dict[str, float]]  # Per-bracket amounts
    num_transactions: int
    num_capital_gains: int
    num_capital_losses: int


class TaxReport(BaseModel):
    """Complete IRPF tax report for a fiscal year.

    Contains all the data needed to complete Modelo 100 sections:
    - Box 0328-0339: Capital gains from financial instruments
    - Box 0029: Dividend income
    - Box 0588: Foreign tax credits
    """

    fiscal_year: int
    generated_at: datetime
    taxpayer_id: str | None = None  # NIF/NIE — NOT stored, passed at generation time
    summary: TaxSummary
    capital_gains: list[CapitalGain]
    dividends: list[DividendIncome] = Field(default_factory=list)
    tax_lots_open: list[TaxLot] = Field(default_factory=list)  # Lots still held at year end
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

### src/qitp_agents/tax_reporter/irpf.py

```python
"""Spanish IRPF capital gains calculation engine.

Implements FIFO lot matching, multi-currency conversion,
homogeneous securities anti-avoidance rules, and tax bracket computation.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Any

from qitp_agents.tax_reporter.models import (
    AssetType,
    CapitalGain,
    DividendIncome,
    TaxLot,
    TaxReport,
    TaxSummary,
)

logger = logging.getLogger(__name__)

# Spanish savings income tax brackets (2025/2026)
SAVINGS_TAX_BRACKETS: list[tuple[float, float]] = [
    (6_000.0, 0.19),       # First EUR 6,000 at 19%
    (50_000.0, 0.21),      # EUR 6,001 - 50,000 at 21%
    (200_000.0, 0.23),     # EUR 50,001 - 200,000 at 23%
    (300_000.0, 0.27),     # EUR 200,001 - 300,000 at 27%
    (float("inf"), 0.28),  # Over EUR 300,000 at 28%
]

# Homogeneous securities rule: 2 months for listed, 1 year for unlisted
HOMOGENEOUS_SECURITIES_WINDOW_DAYS = 60  # 2 months for listed securities


class IRPFCalculator:
    """IRPF capital gains calculator using FIFO lot matching.

    Usage:
        calc = IRPFCalculator(fiscal_year=2025)
        calc.add_buy(...)   # Add all buys
        calc.add_sell(...)  # Add all sells — triggers FIFO matching
        report = calc.generate_report()
    """

    def __init__(self, fiscal_year: int) -> None:
        self._fiscal_year = fiscal_year
        # FIFO queues per symbol
        self._lots: dict[str, deque[TaxLot]] = defaultdict(deque)
        self._capital_gains: list[CapitalGain] = []
        self._dividends: list[DividendIncome] = []
        self._lot_counter = 0
        self._total_commissions = 0.0
        # Track sells for homogeneous securities rule
        self._recent_sells: dict[str, list[date]] = defaultdict(list)
        self._recent_buys: dict[str, list[date]] = defaultdict(list)
        self._warnings: list[str] = []

    def add_buy(
        self,
        symbol: str,
        buy_date: date,
        quantity: float,
        price_local: float,
        price_eur: float,
        fx_rate: float,
        currency: str,
        asset_type: AssetType = AssetType.EQUITY,
        exchange: str = "",
        isin: str | None = None,
        commission_eur: float = 0.0,
    ) -> TaxLot:
        """Record a buy transaction — creates a new FIFO lot."""
        self._lot_counter += 1
        lot = TaxLot(
            lot_id=f"LOT-{self._lot_counter:06d}",
            symbol=symbol,
            asset_type=asset_type,
            acquisition_date=buy_date,
            acquisition_price_local=price_local,
            acquisition_price_eur=price_eur,
            acquisition_fx_rate=fx_rate,
            quantity=quantity,
            remaining_quantity=quantity,
            currency=currency,
            exchange=exchange,
            isin=isin,
            commission_eur=commission_eur,
        )

        self._lots[symbol].append(lot)
        self._total_commissions += commission_eur
        self._recent_buys[symbol].append(buy_date)

        return lot

    def add_sell(
        self,
        symbol: str,
        sell_date: date,
        quantity: float,
        price_local: float,
        price_eur: float,
        fx_rate: float,
        commission_eur: float = 0.0,
    ) -> list[CapitalGain]:
        """Record a sell transaction — matches against FIFO lots.

        Args:
            symbol: Symbol sold.
            sell_date: Date of sale.
            quantity: Number of shares/units sold.
            price_local: Sell price per unit in local currency.
            price_eur: Sell price per unit in EUR.
            fx_rate: FX rate on sell date.
            commission_eur: Sell commission in EUR.

        Returns:
            List of CapitalGain records (one per matched lot).
        """
        self._total_commissions += commission_eur
        self._recent_sells[symbol].append(sell_date)

        gains: list[CapitalGain] = []
        remaining_qty = quantity
        lots = self._lots.get(symbol, deque())

        # Distribute commission proportionally across matched lots
        commission_per_unit = commission_eur / quantity if quantity > 0 else 0.0

        while remaining_qty > 0 and lots:
            lot = lots[0]

            if lot.remaining_quantity <= 0:
                lots.popleft()
                continue

            match_qty = min(remaining_qty, lot.remaining_quantity)
            lot.remaining_quantity -= match_qty
            remaining_qty -= match_qty

            # Calculate capital gain for this lot match
            acquisition_total_eur = (
                lot.acquisition_price_eur * match_qty
                + (lot.commission_eur * match_qty / lot.quantity)  # Pro-rata acquisition commission
            )
            disposal_total_eur = (
                price_eur * match_qty
                - commission_per_unit * match_qty  # Pro-rata disposal commission
            )
            gain_loss = disposal_total_eur - acquisition_total_eur

            holding_days = (sell_date - lot.acquisition_date).days

            # Check homogeneous securities rule
            loss_disallowed = False
            loss_disallowed_reason = None
            if gain_loss < 0:
                loss_disallowed, loss_disallowed_reason = self._check_homogeneous_rule(
                    symbol, sell_date,
                )

            gain = CapitalGain(
                symbol=symbol,
                asset_type=lot.asset_type,
                isin=lot.isin,
                acquisition_date=lot.acquisition_date,
                disposal_date=sell_date,
                holding_period_days=holding_days,
                quantity=match_qty,
                acquisition_price_eur=round(acquisition_total_eur, 2),
                disposal_price_eur=round(disposal_total_eur, 2),
                gain_loss_eur=round(gain_loss, 2),
                is_gain=gain_loss > 0,
                acquisition_commission_eur=round(lot.commission_eur * match_qty / lot.quantity, 2),
                disposal_commission_eur=round(commission_per_unit * match_qty, 2),
                acquisition_fx_rate=lot.acquisition_fx_rate,
                disposal_fx_rate=fx_rate,
                lot_id=lot.lot_id,
                loss_disallowed=loss_disallowed,
                loss_disallowed_reason=loss_disallowed_reason,
            )

            self._capital_gains.append(gain)
            gains.append(gain)

            if lot.remaining_quantity <= 0:
                lots.popleft()

        if remaining_qty > 0:
            self._warnings.append(
                f"Sold {quantity} of {symbol} on {sell_date} but only matched "
                f"{quantity - remaining_qty}. Possible short sale or missing buy data."
            )

        return gains

    def add_dividend(self, dividend: DividendIncome) -> None:
        """Record a dividend payment."""
        self._dividends.append(dividend)

    def _check_homogeneous_rule(self, symbol: str, sell_date: date) -> tuple[bool, str | None]:
        """Check the homogeneous securities anti-avoidance rule.

        If the investor sells at a loss and repurchases the same security
        within 2 months before or after the sale, the loss is disallowed
        and added to the cost basis of the new acquisition.

        Returns:
            (is_disallowed, reason_string)
        """
        window_start = sell_date - timedelta(days=HOMOGENEOUS_SECURITIES_WINDOW_DAYS)
        window_end = sell_date + timedelta(days=HOMOGENEOUS_SECURITIES_WINDOW_DAYS)

        recent_buys = self._recent_buys.get(symbol, [])
        for buy_date in recent_buys:
            if window_start <= buy_date <= window_end and buy_date != sell_date:
                return (
                    True,
                    f"Repurchase of {symbol} on {buy_date} within 2-month window "
                    f"of loss sale on {sell_date} (Art. 33.5.f LIRPF)",
                )

        return (False, None)

    def compute_tax(self, net_gain: float) -> tuple[float, list[dict[str, float]]]:
        """Compute estimated tax on net capital gains using savings brackets.

        Args:
            net_gain: Net capital gain in EUR (after offsetting losses).

        Returns:
            (total_tax, bracket_breakdown)
        """
        if net_gain <= 0:
            return (0.0, [])

        remaining = net_gain
        total_tax = 0.0
        breakdown: list[dict[str, float]] = []
        prev_threshold = 0.0

        for threshold, rate in SAVINGS_TAX_BRACKETS:
            bracket_size = threshold - prev_threshold
            taxable_in_bracket = min(remaining, bracket_size)

            if taxable_in_bracket <= 0:
                break

            tax = taxable_in_bracket * rate
            total_tax += tax
            breakdown.append({
                "bracket_from": prev_threshold,
                "bracket_to": prev_threshold + taxable_in_bracket,
                "rate": rate,
                "taxable_amount": round(taxable_in_bracket, 2),
                "tax": round(tax, 2),
            })

            remaining -= taxable_in_bracket
            prev_threshold = threshold

        return (round(total_tax, 2), breakdown)

    def generate_report(self) -> TaxReport:
        """Generate the complete IRPF tax report.

        Returns:
            TaxReport with all capital gains, dividends, summary, and estimates.
        """
        from datetime import datetime

        # Filter capital gains for this fiscal year
        year_gains = [
            g for g in self._capital_gains
            if g.disposal_date.year == self._fiscal_year
        ]

        total_gains = sum(g.gain_loss_eur for g in year_gains if g.is_gain)
        total_losses = sum(g.gain_loss_eur for g in year_gains if not g.is_gain)
        disallowed = sum(
            abs(g.gain_loss_eur) for g in year_gains
            if g.loss_disallowed
        )
        # Disallowed losses are not deductible
        effective_losses = total_losses + disallowed  # losses are negative, disallowed makes them less negative

        net = total_gains + total_losses + disallowed

        # Spanish law allows offsetting up to 25% of gains with excess losses
        # from prior years (not implemented here — would need multi-year state)

        dividend_gross = sum(d.gross_amount_eur for d in self._dividends)
        dividend_withholding = sum(d.withholding_tax_eur for d in self._dividends)

        # Total savings base includes capital gains + dividends
        total_savings_base = max(0, net) + dividend_gross
        estimated_tax, bracket_breakdown = self.compute_tax(total_savings_base)
        # Credit for withholding tax already paid
        estimated_tax = max(0, estimated_tax - dividend_withholding)

        # Open lots at year end
        open_lots = []
        for symbol, lots in self._lots.items():
            for lot in lots:
                if lot.remaining_quantity > 0:
                    open_lots.append(lot)

        summary = TaxSummary(
            fiscal_year=self._fiscal_year,
            total_gains_eur=round(total_gains, 2),
            total_losses_eur=round(total_losses, 2),
            net_gain_loss_eur=round(net, 2),
            disallowed_losses_eur=round(disallowed, 2),
            total_commissions_eur=round(self._total_commissions, 2),
            dividend_income_gross_eur=round(dividend_gross, 2),
            dividend_withholding_eur=round(dividend_withholding, 2),
            estimated_tax_eur=round(estimated_tax, 2),
            tax_bracket_breakdown=bracket_breakdown,
            num_transactions=len(year_gains),
            num_capital_gains=sum(1 for g in year_gains if g.is_gain),
            num_capital_losses=sum(1 for g in year_gains if not g.is_gain),
        )

        return TaxReport(
            fiscal_year=self._fiscal_year,
            generated_at=datetime.utcnow(),
            summary=summary,
            capital_gains=year_gains,
            dividends=self._dividends,
            tax_lots_open=open_lots,
            warnings=self._warnings,
        )
```

---

### src/qitp_agents/tax_reporter/formatter.py

```python
"""Tax report formatters — CSV and structured JSON output.

Produces output suitable for:
- Manual review in spreadsheet (CSV)
- Import into tax software (structured JSON)
- Artifact storage via artifacts-mcp
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from qitp_agents.tax_reporter.models import TaxReport

logger = logging.getLogger(__name__)


def format_as_csv(report: TaxReport) -> str:
    """Format capital gains as CSV for spreadsheet review.

    Columns follow AEAT Modelo 100 structure:
    Symbol, ISIN, Acquisition Date, Disposal Date, Days Held,
    Quantity, Acquisition EUR, Disposal EUR, Gain/Loss EUR,
    Loss Disallowed, Notes
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Symbol", "ISIN", "Asset Type",
        "Acquisition Date", "Disposal Date", "Holding Period (days)",
        "Quantity",
        "Acquisition Price EUR", "Disposal Price EUR",
        "Gain/Loss EUR", "Is Gain",
        "Acq Commission EUR", "Disp Commission EUR",
        "Acq FX Rate", "Disp FX Rate",
        "Loss Disallowed", "Disallowed Reason",
    ])

    # Capital gains rows
    for gain in report.capital_gains:
        writer.writerow([
            gain.symbol,
            gain.isin or "",
            gain.asset_type.value,
            gain.acquisition_date.isoformat(),
            gain.disposal_date.isoformat(),
            gain.holding_period_days,
            gain.quantity,
            f"{gain.acquisition_price_eur:.2f}",
            f"{gain.disposal_price_eur:.2f}",
            f"{gain.gain_loss_eur:.2f}",
            gain.is_gain,
            f"{gain.acquisition_commission_eur:.2f}",
            f"{gain.disposal_commission_eur:.2f}",
            f"{gain.acquisition_fx_rate:.6f}",
            f"{gain.disposal_fx_rate:.6f}",
            gain.loss_disallowed,
            gain.loss_disallowed_reason or "",
        ])

    # Blank row + dividends section
    if report.dividends:
        writer.writerow([])
        writer.writerow(["--- DIVIDENDS ---"])
        writer.writerow([
            "Symbol", "Payment Date", "Gross EUR",
            "Withholding EUR", "Net EUR", "Country", "FX Rate",
        ])
        for div in report.dividends:
            writer.writerow([
                div.symbol,
                div.payment_date.isoformat(),
                f"{div.gross_amount_eur:.2f}",
                f"{div.withholding_tax_eur:.2f}",
                f"{div.net_amount_eur:.2f}",
                div.country_of_source,
                f"{div.fx_rate:.6f}",
            ])

    # Summary section
    writer.writerow([])
    writer.writerow(["--- SUMMARY ---"])
    s = report.summary
    writer.writerow(["Fiscal Year", s.fiscal_year])
    writer.writerow(["Total Gains EUR", f"{s.total_gains_eur:.2f}"])
    writer.writerow(["Total Losses EUR", f"{s.total_losses_eur:.2f}"])
    writer.writerow(["Net Gain/Loss EUR", f"{s.net_gain_loss_eur:.2f}"])
    writer.writerow(["Disallowed Losses EUR", f"{s.disallowed_losses_eur:.2f}"])
    writer.writerow(["Total Commissions EUR", f"{s.total_commissions_eur:.2f}"])
    writer.writerow(["Dividend Income EUR", f"{s.dividend_income_gross_eur:.2f}"])
    writer.writerow(["Dividend Withholding EUR", f"{s.dividend_withholding_eur:.2f}"])
    writer.writerow(["Estimated Tax EUR", f"{s.estimated_tax_eur:.2f}"])
    writer.writerow(["Transactions", s.num_transactions])

    return output.getvalue()


def format_as_json(report: TaxReport) -> str:
    """Format report as structured JSON for programmatic consumption."""
    return report.model_dump_json(indent=2)


def format_summary_text(report: TaxReport) -> str:
    """Format a human-readable summary of the tax report."""
    s = report.summary
    lines = [
        f"IRPF Tax Report — Fiscal Year {s.fiscal_year}",
        "=" * 50,
        "",
        f"Capital Gains:     EUR {s.total_gains_eur:>12,.2f}",
        f"Capital Losses:    EUR {s.total_losses_eur:>12,.2f}",
        f"Net Gain/Loss:     EUR {s.net_gain_loss_eur:>12,.2f}",
        "",
    ]

    if s.disallowed_losses_eur != 0:
        lines.append(f"Disallowed Losses: EUR {s.disallowed_losses_eur:>12,.2f}")
        lines.append("  (Homogeneous securities rule — Art. 33.5.f LIRPF)")
        lines.append("")

    lines.extend([
        f"Dividend Income:   EUR {s.dividend_income_gross_eur:>12,.2f}",
        f"Withholding Tax:   EUR {s.dividend_withholding_eur:>12,.2f}",
        f"Total Commissions: EUR {s.total_commissions_eur:>12,.2f}",
        "",
        f"Estimated Tax:     EUR {s.estimated_tax_eur:>12,.2f}",
        "",
        "Tax Bracket Breakdown:",
    ])

    for bracket in s.tax_bracket_breakdown:
        lines.append(
            f"  EUR {bracket['bracket_from']:>10,.0f} - {bracket['bracket_to']:>10,.0f} "
            f"@ {bracket['rate']*100:.0f}%: EUR {bracket['tax']:>10,.2f}"
        )

    lines.extend([
        "",
        f"Transactions: {s.num_transactions} ({s.num_capital_gains} gains, {s.num_capital_losses} losses)",
    ])

    if report.warnings:
        lines.extend(["", "WARNINGS:"])
        for w in report.warnings:
            lines.append(f"  - {w}")

    return "\n".join(lines)
```

---

### src/qitp_agents/tax_reporter/handler.py

```python
"""Tax Reporter Agent Lambda handler.

Input:
    {
        "fiscal_year": 2025,
        "trading_history_artifact_id": "...",
        "output_format": "json"  # "json", "csv", "summary"
    }

Output: TaxReport artifact with capital gains, dividends, and IRPF estimates.

Architecture:
- Single Strands agent with deterministic calculation backend
- Agent uses artifacts-mcp to load trading history and store report
- IRPF calculation is pure Python (no model inference needed for math)
- Agent adds narrative commentary and warnings interpretation
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "backtest"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "tax-reporter"
MAX_OUTPUT_BYTES = 256 * 1024


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Tax Reporter Agent.

    Args:
        event: Input with fiscal_year, trading_history_artifact_id, output_format.
        context: Lambda context (optional).

    Returns:
        JSON response with tax report or claim-check reference.
    """
    logger.info("Tax reporter invoked", extra={"fiscal_year": event.get("fiscal_year")})

    fiscal_year = event.get("fiscal_year")
    history_artifact_id = event.get("trading_history_artifact_id")
    output_format = event.get("output_format", "json")

    if not fiscal_year:
        return _error_response("Missing required field: fiscal_year")
    if not history_artifact_id:
        return _error_response("Missing required field: trading_history_artifact_id")

    try:
        mcp_clients = _create_mcp_clients()

        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        prompt = (
            f"Generate the Spanish IRPF tax report for fiscal year {fiscal_year}.\n\n"
            f"Steps:\n"
            f"1. Load trading history from artifact '{history_artifact_id}'.\n"
            f"2. For each trade, identify: symbol, date, quantity, price, currency, commission.\n"
            f"3. Convert all non-EUR amounts to EUR using the FX rate on the transaction date.\n"
            f"4. Apply FIFO lot matching to compute capital gains/losses.\n"
            f"5. Check the homogeneous securities anti-avoidance rule "
            f"   (Art. 33.5.f LIRPF — 2-month repurchase window).\n"
            f"6. Compute estimated tax using 2025/2026 savings income brackets:\n"
            f"   - First EUR 6,000: 19%%\n"
            f"   - EUR 6,001-50,000: 21%%\n"
            f"   - EUR 50,001-200,000: 23%%\n"
            f"   - EUR 200,001-300,000: 27%%\n"
            f"   - Over EUR 300,000: 28%%\n"
            f"7. Create a TaxReport artifact in {output_format} format.\n"
            f"8. Include warnings for any issues found:\n"
            f"   - Missing ISIN codes\n"
            f"   - Disallowed losses\n"
            f"   - Unmatched sells (possible short sales)\n"
            f"   - Large FX movements affecting gains\n"
            f"9. Provide a narrative summary of the tax situation.\n"
        )

        result = agent(prompt)

        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Tax reporter failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    market_data_uri = os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8002")
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=market_data_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result, with claim-check for large outputs."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output, default=str)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        logger.warning("Output exceeds 256KB, returning claim-check")
        output = {
            "claim_check": True,
            "message": "Output exceeded 256KB. Full report stored as artifact.",
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(message: str) -> dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": message})}
```

---

# Component 5: Advanced AgentCore Features

---

### src/agent_core/agentcore/__init__.py

```python
"""Advanced AgentCore features — memory branching, streaming, multi-tenant."""
```

---

### src/agent_core/agentcore/memory_branching.py

```python
"""Memory branching for strategy exploration.

Allows agents to create "what-if" branches of their memory state,
explore alternative strategies, and merge or discard branches.
Useful for the Strategy Evaluation agent comparing multiple approaches.

Maps to AgentCore Memory's session branching capability.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MemoryBranch(BaseModel):
    """A branch in the memory tree."""

    branch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_branch_id: str | None = None
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    state: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"  # "active", "merged", "discarded"
    metrics: dict[str, float] = Field(default_factory=dict)


class MemoryBranchManager:
    """Manages memory branches for strategy exploration.

    In POC (Phase 1): branches stored in-memory dict.
    In Production (Phase 2): branches stored in AgentCore Memory with
    session branching API.

    Usage:
        mgr = MemoryBranchManager(session_id="sfn-exec-123")
        branch = mgr.create_branch("aggressive_strategy", base_state={...})
        mgr.update_branch(branch.branch_id, new_state={...})
        best = mgr.compare_branches(["branch-a", "branch-b"], metric="sharpe_ratio")
        mgr.merge_branch(best.branch_id)  # Promote to main
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._branches: dict[str, MemoryBranch] = {}
        self._main_state: dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    def create_branch(
        self,
        name: str,
        base_state: dict[str, Any] | None = None,
        parent_branch_id: str | None = None,
        description: str = "",
    ) -> MemoryBranch:
        """Create a new memory branch.

        Args:
            name: Human-readable branch name (e.g., "conservative_strategy").
            base_state: Initial state (deep-copied). Defaults to main state.
            parent_branch_id: Branch to fork from (None = fork from main).
            description: What this branch explores.

        Returns:
            New MemoryBranch.
        """
        if base_state is None:
            if parent_branch_id and parent_branch_id in self._branches:
                base_state = copy.deepcopy(self._branches[parent_branch_id].state)
            else:
                base_state = copy.deepcopy(self._main_state)

        branch = MemoryBranch(
            parent_branch_id=parent_branch_id,
            name=name,
            description=description,
            state=base_state,
        )

        self._branches[branch.branch_id] = branch
        logger.info(
            "Created memory branch '%s' (id=%s) for session %s",
            name, branch.branch_id, self._session_id,
        )
        return branch

    def update_branch(
        self,
        branch_id: str,
        state_updates: dict[str, Any] | None = None,
        metrics: dict[str, float] | None = None,
    ) -> MemoryBranch:
        """Update a branch's state and/or metrics."""
        branch = self._branches.get(branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")
        if branch.status != "active":
            raise ValueError(f"Branch {branch_id} is {branch.status}, cannot update")

        if state_updates:
            branch.state.update(state_updates)
        if metrics:
            branch.metrics.update(metrics)

        return branch

    def get_branch(self, branch_id: str) -> MemoryBranch | None:
        """Get a branch by ID."""
        return self._branches.get(branch_id)

    def list_branches(self, status: str | None = None) -> list[MemoryBranch]:
        """List all branches, optionally filtered by status."""
        branches = list(self._branches.values())
        if status:
            branches = [b for b in branches if b.status == status]
        return branches

    def compare_branches(
        self,
        branch_ids: list[str],
        metric: str,
        higher_is_better: bool = True,
    ) -> MemoryBranch | None:
        """Compare branches by a specific metric and return the best.

        Args:
            branch_ids: Branch IDs to compare.
            metric: Metric key to compare (e.g., "sharpe_ratio", "max_drawdown").
            higher_is_better: If True, highest metric wins.

        Returns:
            Best branch, or None if no branches have the metric.
        """
        candidates = []
        for bid in branch_ids:
            branch = self._branches.get(bid)
            if branch and metric in branch.metrics:
                candidates.append(branch)

        if not candidates:
            return None

        return max(candidates, key=lambda b: b.metrics[metric]) if higher_is_better else min(candidates, key=lambda b: b.metrics[metric])

    def merge_branch(self, branch_id: str) -> dict[str, Any]:
        """Merge a branch into main state.

        The branch state becomes the new main state.
        Branch is marked as 'merged'.
        """
        branch = self._branches.get(branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")

        self._main_state = copy.deepcopy(branch.state)
        branch.status = "merged"

        logger.info("Merged branch '%s' into main for session %s", branch.name, self._session_id)
        return self._main_state

    def discard_branch(self, branch_id: str) -> None:
        """Discard a branch without merging."""
        branch = self._branches.get(branch_id)
        if branch:
            branch.status = "discarded"
            logger.info("Discarded branch '%s' for session %s", branch.name, self._session_id)
```

---

### src/agent_core/agentcore/streaming.py

```python
"""Bi-directional streaming for real-time UI updates.

Provides server-sent events (SSE) and WebSocket adapters for
streaming agent progress to the UI layer. Used by:
- Portfolio Recommender (streaming reasoning)
- Watchlist Screener (progress updates as universes are scanned)
- Tax Reporter (progress as lots are processed)

In POC: SSE via Lambda response streaming.
In Production: AgentCore Runtime native streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StreamEventType(str, Enum):
    """Types of streaming events."""

    PROGRESS = "progress"
    PARTIAL_RESULT = "partial_result"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    COMPLETE = "complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    """A single streaming event."""

    event_type: StreamEventType
    agent_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)
    sequence: int = 0


class StreamBuffer:
    """Buffer for collecting and distributing stream events.

    Thread-safe event buffer that allows agents to push events
    and UI clients to consume them via async iteration.
    """

    def __init__(self, session_id: str, agent_id: str) -> None:
        self._session_id = session_id
        self._agent_id = agent_id
        self._events: list[StreamEvent] = []
        self._sequence = 0
        self._complete = False
        self._subscribers: list[asyncio.Queue[StreamEvent | None]] = []

    async def push(self, event_type: StreamEventType, data: dict[str, Any]) -> None:
        """Push an event to the buffer and notify subscribers."""
        self._sequence += 1
        event = StreamEvent(
            event_type=event_type,
            agent_id=self._agent_id,
            session_id=self._session_id,
            data=data,
            sequence=self._sequence,
        )
        self._events.append(event)

        for queue in self._subscribers:
            await queue.put(event)

        if event_type in (StreamEventType.COMPLETE, StreamEventType.ERROR):
            self._complete = True
            for queue in self._subscribers:
                await queue.put(None)  # Sentinel

    async def subscribe(self) -> AsyncIterator[StreamEvent]:
        """Subscribe to stream events. Yields events as they arrive."""
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        self._subscribers.append(queue)

        # Replay existing events
        for event in self._events:
            yield event

        if self._complete:
            return

        # Wait for new events
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

        self._subscribers.remove(queue)

    def get_events(self, after_sequence: int = 0) -> list[StreamEvent]:
        """Get events after a given sequence number (for polling clients)."""
        return [e for e in self._events if e.sequence > after_sequence]

    @property
    def is_complete(self) -> bool:
        return self._complete


def format_sse(event: StreamEvent) -> str:
    """Format a StreamEvent as Server-Sent Events (SSE) text.

    Returns:
        SSE-formatted string ready to write to HTTP response.
    """
    data = event.model_dump_json()
    return f"event: {event.event_type.value}\ndata: {data}\n\n"
```

---

### src/agent_core/agentcore/multi_tenant.py

```python
"""Multi-tenant isolation primitives.

Provides tenant-scoped resource access for future SaaS expansion.
In POC: single tenant (Nestor Colt). In production: tenant isolation
at DynamoDB, S3, and AgentCore session level.

Design principle: every data access path includes tenant_id, even in
single-tenant mode. This makes multi-tenant migration a config change,
not a code change.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default tenant for single-tenant POC
DEFAULT_TENANT_ID = os.environ.get("TENANT_ID", "default")


class TenantContext(BaseModel):
    """Tenant context passed through all operations."""

    tenant_id: str = DEFAULT_TENANT_ID
    display_name: str = ""
    tier: str = "standard"  # "standard", "professional", "enterprise"
    config: dict[str, Any] = Field(default_factory=dict)

    # Resource limits per tier
    max_watchlist_symbols: int = 100
    max_universes: int = 4
    max_concurrent_agents: int = 5
    max_artifacts_gb: float = 10.0

    @classmethod
    def from_env(cls) -> TenantContext:
        """Create tenant context from environment variables."""
        return cls(
            tenant_id=os.environ.get("TENANT_ID", DEFAULT_TENANT_ID),
            display_name=os.environ.get("TENANT_NAME", "Default Tenant"),
            tier=os.environ.get("TENANT_TIER", "standard"),
        )


class TenantScopedKey:
    """Generates tenant-scoped keys for DynamoDB and S3.

    All keys follow the pattern: {tenant_id}/{resource_type}/{resource_id}
    """

    @staticmethod
    def dynamodb_pk(tenant_id: str, resource_type: str, resource_id: str) -> str:
        """Generate DynamoDB partition key with tenant scope."""
        return f"TENANT#{tenant_id}#TYPE#{resource_type}#ID#{resource_id}"

    @staticmethod
    def s3_prefix(tenant_id: str, resource_type: str) -> str:
        """Generate S3 key prefix with tenant scope."""
        return f"tenants/{tenant_id}/{resource_type}/"

    @staticmethod
    def s3_key(tenant_id: str, resource_type: str, filename: str) -> str:
        """Generate full S3 key with tenant scope."""
        return f"tenants/{tenant_id}/{resource_type}/{filename}"

    @staticmethod
    def session_id(tenant_id: str, workflow_execution_id: str) -> str:
        """Generate tenant-scoped session ID for AgentCore Memory."""
        return f"{tenant_id}:{workflow_execution_id}"


class TenantResourceGuard:
    """Enforce tenant resource limits.

    Checks that operations do not exceed tenant tier limits.
    Raises TenantLimitExceeded if a limit would be breached.
    """

    def __init__(self, context: TenantContext) -> None:
        self._context = context

    def check_watchlist_limit(self, current_count: int) -> None:
        """Check if adding a symbol would exceed watchlist limit."""
        if current_count >= self._context.max_watchlist_symbols:
            raise TenantLimitExceeded(
                f"Watchlist limit reached ({self._context.max_watchlist_symbols} symbols). "
                f"Upgrade to a higher tier for more capacity."
            )

    def check_concurrent_agents(self, running_count: int) -> None:
        """Check if launching another agent would exceed concurrency limit."""
        if running_count >= self._context.max_concurrent_agents:
            raise TenantLimitExceeded(
                f"Concurrent agent limit reached ({self._context.max_concurrent_agents}). "
                f"Wait for running agents to complete or upgrade tier."
            )

    def check_artifact_storage(self, current_gb: float, additional_gb: float) -> None:
        """Check if storing more artifacts would exceed storage limit."""
        if current_gb + additional_gb > self._context.max_artifacts_gb:
            raise TenantLimitExceeded(
                f"Artifact storage limit reached ({self._context.max_artifacts_gb} GB). "
                f"Delete old artifacts or upgrade tier."
            )


class TenantLimitExceeded(Exception):
    """Raised when a tenant operation would exceed tier limits."""
    pass
```

---

# Component 6: CFD/Leveraged Products Risk Rules

---

### src/agent_core/risk/product_classifier.py

```python
"""Product classifier — determines asset type for risk rule routing.

Classifies instruments into: equity, ETF, CFD, crypto, fund.
Each type has different risk rules, leverage limits, and regulatory requirements.
"""

from __future__ import annotations

import logging
import re
from enum import Enum

logger = logging.getLogger(__name__)


class ProductType(str, Enum):
    """Financial product types."""

    EQUITY = "equity"
    ETF = "etf"
    CFD = "cfd"
    CRYPTO = "crypto"
    FUND = "fund"
    OPTION = "option"
    FUTURE = "future"
    UNKNOWN = "unknown"


# Known ETF suffixes/patterns
_ETF_SYMBOLS = {
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO",
    "EEM", "GLD", "SLV", "TLT", "IEF", "HYG", "LQD", "XLF",
    "XLE", "XLK", "XLV", "XLI", "XLU", "ARKK", "ARKG",
}

# Crypto symbol patterns
_CRYPTO_PATTERN = re.compile(r"^[A-Z]{2,10}-(USD|USDT|EUR|BTC|ETH)$")

# CFD symbol patterns (varies by broker)
_CFD_SUFFIXES = {".CFD", ".cfd", "-CFD"}


def classify_product(
    symbol: str,
    instrument_type: str | None = None,
    exchange: str | None = None,
) -> ProductType:
    """Classify a financial instrument by its product type.

    Args:
        symbol: Instrument symbol (e.g., "AAPL", "BTC-USD", "AAPL.CFD").
        instrument_type: Optional hint from broker (e.g., "STK", "CFD", "CRYPTO").
        exchange: Optional exchange code for disambiguation.

    Returns:
        ProductType classification.
    """
    # Explicit type hint takes priority
    if instrument_type:
        type_map = {
            "STK": ProductType.EQUITY,
            "ETF": ProductType.ETF,
            "CFD": ProductType.CFD,
            "CRYPTO": ProductType.CRYPTO,
            "FUND": ProductType.FUND,
            "OPT": ProductType.OPTION,
            "FUT": ProductType.FUTURE,
        }
        classified = type_map.get(instrument_type.upper())
        if classified:
            return classified

    # CFD suffix detection
    for suffix in _CFD_SUFFIXES:
        if symbol.endswith(suffix):
            return ProductType.CFD

    # Crypto pattern detection
    if _CRYPTO_PATTERN.match(symbol):
        return ProductType.CRYPTO

    # Known ETF detection
    base_symbol = symbol.split(".")[0].split("-")[0]
    if base_symbol in _ETF_SYMBOLS:
        return ProductType.ETF

    # Crypto exchange detection
    if exchange and exchange.upper() in {"BINANCE", "COINBASE", "KRAKEN", "MULTI"}:
        return ProductType.CRYPTO

    # Default to equity
    return ProductType.EQUITY
```

---

### src/agent_core/risk/cfd_leverage.py

```python
"""ESMA CFD leverage limit enforcement.

Implements the ESMA restrictions on CFD trading that apply to
retail investors in the EU (including Spain under CNMV supervision).

ESMA Leverage Limits (Retail):
- Major FX pairs: 30:1
- Non-major FX, gold, major indices: 20:1
- Non-major indices, other commodities: 10:1
- Individual equities: 5:1
- Crypto: 2:1

ESMA also requires:
- Negative balance protection (NBP)
- Margin close-out at 50% of required margin
- Standardized risk warning
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from agent_core.risk.product_classifier import ProductType

logger = logging.getLogger(__name__)


class ESMAAssetClass(str, Enum):
    """ESMA asset classes for leverage limit determination."""

    MAJOR_FX = "major_fx"           # EUR/USD, GBP/USD, USD/JPY, etc.
    NON_MAJOR_FX = "non_major_fx"   # All other FX pairs
    GOLD = "gold"
    MAJOR_INDEX = "major_index"     # S&P 500, FTSE 100, DAX, etc.
    NON_MAJOR_INDEX = "non_major_index"
    COMMODITY = "commodity"         # Oil, silver, etc.
    INDIVIDUAL_EQUITY = "individual_equity"
    CRYPTO = "crypto"


# ESMA maximum leverage by asset class (for retail investors)
ESMA_LEVERAGE_LIMITS: dict[ESMAAssetClass, int] = {
    ESMAAssetClass.MAJOR_FX: 30,
    ESMAAssetClass.NON_MAJOR_FX: 20,
    ESMAAssetClass.GOLD: 20,
    ESMAAssetClass.MAJOR_INDEX: 20,
    ESMAAssetClass.NON_MAJOR_INDEX: 10,
    ESMAAssetClass.COMMODITY: 10,
    ESMAAssetClass.INDIVIDUAL_EQUITY: 5,
    ESMAAssetClass.CRYPTO: 2,
}

# Major indices for ESMA classification
_MAJOR_INDICES = {
    "SPX", "SPY", "ES",       # S&P 500
    "NDX", "QQQ", "NQ",       # NASDAQ 100
    "DJI", "DIA", "YM",       # Dow Jones
    "FTSE", "UKX",             # FTSE 100
    "DAX", "GDAXI",           # DAX
    "CAC", "FCHI",             # CAC 40
    "IBEX", "IBEX35",         # IBEX 35
    "NKY", "N225",             # Nikkei 225
    "HSI",                     # Hang Seng
    "SX5E", "STOXX50E",       # Euro Stoxx 50
}


class CFDLeverageCheck(BaseModel):
    """Result of a CFD leverage limit check."""

    symbol: str
    asset_class: ESMAAssetClass
    max_leverage: int
    requested_leverage: float
    is_compliant: bool
    margin_required_pct: float  # 100 / max_leverage
    message: str


def classify_esma_asset_class(
    symbol: str,
    product_type: ProductType,
    sector: str | None = None,
) -> ESMAAssetClass:
    """Classify a symbol into ESMA asset class for leverage limits.

    Args:
        symbol: Instrument symbol.
        product_type: Already-classified product type.
        sector: Optional sector hint.

    Returns:
        ESMAAssetClass for leverage limit lookup.
    """
    if product_type == ProductType.CRYPTO:
        return ESMAAssetClass.CRYPTO

    # Check if it's an index
    base = symbol.split(".")[0].split("-")[0].upper()
    if base in _MAJOR_INDICES:
        return ESMAAssetClass.MAJOR_INDEX

    if product_type == ProductType.ETF:
        # ETFs tracking major indices get index leverage
        if base in _MAJOR_INDICES or any(idx in symbol.upper() for idx in ["SPX", "NDX", "DAX"]):
            return ESMAAssetClass.MAJOR_INDEX
        return ESMAAssetClass.NON_MAJOR_INDEX

    if product_type == ProductType.EQUITY:
        return ESMAAssetClass.INDIVIDUAL_EQUITY

    # Default to most conservative
    return ESMAAssetClass.INDIVIDUAL_EQUITY


def check_cfd_leverage(
    symbol: str,
    product_type: ProductType,
    requested_leverage: float,
    sector: str | None = None,
    is_professional: bool = False,
) -> CFDLeverageCheck:
    """Check if requested CFD leverage complies with ESMA limits.

    Args:
        symbol: Instrument symbol.
        product_type: Product type classification.
        requested_leverage: Desired leverage (e.g., 10.0 for 10:1).
        sector: Optional sector for classification.
        is_professional: If True, ESMA retail limits do not apply.

    Returns:
        CFDLeverageCheck with compliance result.
    """
    if is_professional:
        # Professional clients are not subject to ESMA retail limits
        return CFDLeverageCheck(
            symbol=symbol,
            asset_class=ESMAAssetClass.INDIVIDUAL_EQUITY,
            max_leverage=500,  # Broker-specific limit
            requested_leverage=requested_leverage,
            is_compliant=True,
            margin_required_pct=100 / requested_leverage if requested_leverage > 0 else 100,
            message="Professional client — ESMA retail limits do not apply.",
        )

    asset_class = classify_esma_asset_class(symbol, product_type, sector)
    max_leverage = ESMA_LEVERAGE_LIMITS[asset_class]
    margin_pct = 100 / max_leverage
    is_compliant = requested_leverage <= max_leverage

    if is_compliant:
        message = (
            f"Leverage {requested_leverage}:1 is within ESMA limit of "
            f"{max_leverage}:1 for {asset_class.value}."
        )
    else:
        message = (
            f"REJECTED: Leverage {requested_leverage}:1 exceeds ESMA limit of "
            f"{max_leverage}:1 for {asset_class.value}. "
            f"Maximum leverage for {asset_class.value} is {max_leverage}:1 "
            f"(margin requirement: {margin_pct:.1f}%)."
        )

    return CFDLeverageCheck(
        symbol=symbol,
        asset_class=asset_class,
        max_leverage=max_leverage,
        requested_leverage=requested_leverage,
        is_compliant=is_compliant,
        margin_required_pct=margin_pct,
        message=message,
    )
```

---

### src/agent_core/risk/margin_call.py

```python
"""Margin call detection and auto-close logic.

Monitors margin utilization and triggers protective actions when
margin levels approach or breach critical thresholds.

ESMA requires margin close-out at 50% of initial required margin
for CFD positions. This module implements that plus additional
safety margins.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MarginLevel(str, Enum):
    """Margin utilization levels."""

    HEALTHY = "healthy"         # > 200% margin
    WARNING = "warning"         # 100% - 200% margin
    MARGIN_CALL = "margin_call" # 50% - 100% margin (broker sends margin call)
    CLOSE_OUT = "close_out"     # <= 50% (ESMA mandatory close-out)


class PositionMargin(BaseModel):
    """Margin information for a single position."""

    symbol: str
    position_value: float  # Current market value
    initial_margin: float  # Margin required at entry
    maintenance_margin: float  # Minimum margin to hold position
    current_margin: float  # Current margin available
    margin_utilization_pct: float  # (initial_margin / equity) * 100
    unrealized_pnl: float
    leverage: float


class MarginStatus(BaseModel):
    """Overall account margin status."""

    account_equity: float
    total_margin_required: float
    free_margin: float
    margin_level_pct: float  # (equity / margin_required) * 100
    margin_level: MarginLevel
    positions: list[PositionMargin] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    close_out_positions: list[str] = Field(default_factory=list)  # Symbols to close
    message: str = ""


class MarginCallDetector:
    """Detects margin call conditions and determines close-out actions.

    Thresholds:
    - Healthy: margin_level > 200%
    - Warning: 100% < margin_level <= 200%
    - Margin Call: 50% < margin_level <= 100%
    - Close-Out: margin_level <= 50% (ESMA mandatory)
    """

    # Custom thresholds (more conservative than ESMA minimum)
    HEALTHY_THRESHOLD = 200.0
    WARNING_THRESHOLD = 100.0
    MARGIN_CALL_THRESHOLD = 75.0  # More conservative than ESMA 50%
    CLOSE_OUT_THRESHOLD = 50.0    # ESMA mandatory

    def evaluate(
        self,
        account_equity: float,
        positions: list[PositionMargin],
    ) -> MarginStatus:
        """Evaluate margin status across all positions.

        Args:
            account_equity: Total account equity (cash + unrealized P&L).
            positions: List of open positions with margin info.

        Returns:
            MarginStatus with level assessment and close-out recommendations.
        """
        total_margin = sum(p.initial_margin for p in positions)

        if total_margin == 0:
            return MarginStatus(
                account_equity=account_equity,
                total_margin_required=0.0,
                free_margin=account_equity,
                margin_level_pct=float("inf"),
                margin_level=MarginLevel.HEALTHY,
                positions=positions,
                message="No margin positions open.",
            )

        margin_level_pct = (account_equity / total_margin) * 100
        free_margin = account_equity - total_margin

        # Determine level
        if margin_level_pct > self.HEALTHY_THRESHOLD:
            level = MarginLevel.HEALTHY
            message = f"Margin level healthy at {margin_level_pct:.1f}%."
        elif margin_level_pct > self.WARNING_THRESHOLD:
            level = MarginLevel.WARNING
            message = (
                f"WARNING: Margin level at {margin_level_pct:.1f}%. "
                f"Consider reducing position sizes."
            )
        elif margin_level_pct > self.CLOSE_OUT_THRESHOLD:
            level = MarginLevel.MARGIN_CALL
            message = (
                f"MARGIN CALL: Margin level at {margin_level_pct:.1f}%. "
                f"Deposit funds or close positions immediately."
            )
        else:
            level = MarginLevel.CLOSE_OUT
            message = (
                f"CLOSE-OUT: Margin level at {margin_level_pct:.1f}% "
                f"(below ESMA 50% threshold). Initiating forced close-out."
            )

        # Determine which positions to close (largest margin first)
        close_out_symbols: list[str] = []
        if level == MarginLevel.CLOSE_OUT:
            close_out_symbols = self._determine_close_out_order(
                account_equity, positions,
            )

        return MarginStatus(
            account_equity=round(account_equity, 2),
            total_margin_required=round(total_margin, 2),
            free_margin=round(free_margin, 2),
            margin_level_pct=round(margin_level_pct, 2),
            margin_level=level,
            positions=positions,
            close_out_positions=close_out_symbols,
            message=message,
        )

    def _determine_close_out_order(
        self,
        equity: float,
        positions: list[PositionMargin],
    ) -> list[str]:
        """Determine order of positions to close to restore margin.

        Strategy: close positions with highest margin requirement first
        until margin level is restored above close-out threshold.
        """
        # Sort by margin required descending
        sorted_positions = sorted(
            positions,
            key=lambda p: p.initial_margin,
            reverse=True,
        )

        to_close: list[str] = []
        released_margin = 0.0
        total_margin = sum(p.initial_margin for p in positions)

        for pos in sorted_positions:
            to_close.append(pos.symbol)
            released_margin += pos.initial_margin
            remaining_margin = total_margin - released_margin

            if remaining_margin == 0:
                break

            new_level = (equity / remaining_margin) * 100
            if new_level > self.MARGIN_CALL_THRESHOLD:
                break

        return to_close
```

---

# Tests

---

### tests/unit/test_watchlist_screener.py

```python
"""Tests for the Watchlist Screener Agent components."""

from __future__ import annotations

import pytest

from qitp_agents.watchlist_screener.universe import (
    UniverseSymbol,
    SP500Provider,
    STOXX600Provider,
    Nikkei225Provider,
    CryptoTop100Provider,
    get_universe_provider,
)
from qitp_agents.watchlist_screener.filters import (
    FilterConfig,
    apply_liquidity_filter,
    apply_market_cap_filter,
    apply_sector_filter,
    apply_exclusion_filter,
    apply_all_filters,
)
from qitp_agents.watchlist_screener.ranking import (
    GapHistoryStats,
    RankingWeights,
    RankedCandidate,
    rank_candidates,
    compute_gap_frequency_score,
    compute_gap_magnitude_score,
    compute_volume_stability_score,
    compute_market_cap_score,
)


# --- Universe Provider Tests ---

class TestUniverseProviders:
    @pytest.mark.asyncio
    async def test_sp500_static_fallback(self):
        provider = SP500Provider()
        symbols = await provider.get_symbols()
        assert len(symbols) > 0
        assert all(s.market == "us" for s in symbols)
        assert provider.universe_id() == "sp500"

    @pytest.mark.asyncio
    async def test_stoxx600_static_fallback(self):
        provider = STOXX600Provider()
        symbols = await provider.get_symbols()
        assert len(symbols) > 0
        assert all(s.market == "eu" for s in symbols)

    @pytest.mark.asyncio
    async def test_nikkei225_static_fallback(self):
        provider = Nikkei225Provider()
        symbols = await provider.get_symbols()
        assert len(symbols) > 0
        assert all(s.market == "jp" for s in symbols)

    @pytest.mark.asyncio
    async def test_crypto_static_fallback(self):
        provider = CryptoTop100Provider()
        symbols = await provider.get_symbols()
        assert len(symbols) > 0
        assert all(s.market == "crypto" for s in symbols)
        assert all(s.asset_type == "crypto" for s in symbols)

    def test_get_universe_provider_valid(self):
        provider = get_universe_provider("sp500")
        assert provider.universe_id() == "sp500"

    def test_get_universe_provider_invalid(self):
        with pytest.raises(ValueError, match="Unknown universe"):
            get_universe_provider("nonexistent")


# --- Filter Tests ---

def _make_symbol(
    symbol: str = "TEST",
    market: str = "us",
    sector: str = "Technology",
    market_cap: float = 50e9,
    volume: int = 5_000_000,
) -> UniverseSymbol:
    return UniverseSymbol(
        symbol=symbol, name=f"Test {symbol}", market=market,
        sector=sector, industry="Test", market_cap_usd=market_cap,
        avg_daily_volume=volume, currency="USD", exchange="NYSE",
        asset_type="stock",
    )


class TestFilters:
    def test_liquidity_filter(self):
        symbols = [
            _make_symbol("A", volume=5_000_000),
            _make_symbol("B", volume=500_000),  # Below 1M threshold
            _make_symbol("C", volume=10_000_000),
        ]
        config = FilterConfig(min_avg_daily_volume=1_000_000)
        result = apply_liquidity_filter(symbols, config)
        assert len(result) == 2
        assert all(s.avg_daily_volume >= 1_000_000 for s in result)

    def test_market_cap_filter(self):
        symbols = [
            _make_symbol("A", market_cap=500e6),   # Below $1B
            _make_symbol("B", market_cap=10e9),     # OK
            _make_symbol("C", market_cap=500e9),    # OK
        ]
        config = FilterConfig(min_market_cap_usd=1e9)
        result = apply_market_cap_filter(symbols, config)
        assert len(result) == 2

    def test_sector_filter_exclude(self):
        symbols = [
            _make_symbol("A", sector="Technology"),
            _make_symbol("B", sector="Energy"),
            _make_symbol("C", sector="Technology"),
        ]
        config = FilterConfig(excluded_sectors=["Energy"])
        result = apply_sector_filter(symbols, config)
        assert len(result) == 2
        assert all(s.sector != "Energy" for s in result)

    def test_exclusion_filter(self):
        symbols = [
            _make_symbol("AAPL"),
            _make_symbol("MSFT"),
            _make_symbol("GOOGL"),
        ]
        config = FilterConfig(exclude_symbols=["AAPL", "GOOGL"])
        result = apply_exclusion_filter(symbols, config)
        assert len(result) == 1
        assert result[0].symbol == "MSFT"

    def test_apply_all_filters(self):
        symbols = [
            _make_symbol("A", market_cap=50e9, volume=5_000_000, market="us"),
            _make_symbol("B", market_cap=500e6, volume=100_000, market="us"),  # Fails both
            _make_symbol("C", market_cap=10e9, volume=2_000_000, market="jp"),
        ]
        config = FilterConfig(allowed_markets=["us", "jp"])
        result = apply_all_filters(symbols, config)
        assert len(result) == 2  # B filtered out


# --- Ranking Tests ---

class TestRanking:
    def test_gap_frequency_score(self):
        stats = GapHistoryStats(
            symbol="TEST", total_gaps=10, avg_gap_pct=3.0,
            max_gap_pct=8.0, gap_up_ratio=0.6,
            avg_volume_ratio_on_gap=2.5, gap_frequency_per_month=2.0,
        )
        score = compute_gap_frequency_score(stats)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # 2 gaps/month should score high

    def test_gap_frequency_zero(self):
        stats = GapHistoryStats(
            symbol="TEST", total_gaps=0, avg_gap_pct=0,
            max_gap_pct=0, gap_up_ratio=0,
            avg_volume_ratio_on_gap=0, gap_frequency_per_month=0,
        )
        assert compute_gap_frequency_score(stats) == 0.0

    def test_gap_magnitude_score(self):
        stats = GapHistoryStats(
            symbol="TEST", total_gaps=5, avg_gap_pct=5.0,
            max_gap_pct=10.0, gap_up_ratio=0.5,
            avg_volume_ratio_on_gap=2.0, gap_frequency_per_month=1.0,
        )
        assert compute_gap_magnitude_score(stats) == 1.0  # 5% = max score

    def test_market_cap_sweet_spot(self):
        # Mid-cap ($10B-$50B) should score highest
        midcap = _make_symbol("MID", market_cap=30e9)
        megacap = _make_symbol("MEGA", market_cap=2000e9)
        assert compute_market_cap_score(midcap) > compute_market_cap_score(megacap)

    def test_rank_candidates(self):
        candidates = [
            _make_symbol("A", market_cap=30e9),
            _make_symbol("B", market_cap=100e9),
        ]
        stats = {
            "A": GapHistoryStats(
                symbol="A", total_gaps=10, avg_gap_pct=4.0,
                max_gap_pct=8.0, gap_up_ratio=0.6,
                avg_volume_ratio_on_gap=2.5, gap_frequency_per_month=2.0,
            ),
        }
        ranked = rank_candidates(candidates, stats, {}, top_n=5)
        assert len(ranked) == 2
        assert ranked[0].overall_score >= ranked[1].overall_score
        assert ranked[0].symbol == "A"  # A has gap history, B does not
```

---

### tests/unit/test_tax_reporter.py

```python
"""Tests for the Tax Reporter Agent components."""

from __future__ import annotations

from datetime import date

import pytest

from qitp_agents.tax_reporter.models import (
    AssetType,
    CapitalGain,
    TaxLot,
    TaxReport,
    TaxSummary,
)
from qitp_agents.tax_reporter.irpf import (
    IRPFCalculator,
    SAVINGS_TAX_BRACKETS,
)
from qitp_agents.tax_reporter.formatter import (
    format_as_csv,
    format_summary_text,
)


class TestIRPFCalculator:
    def test_simple_gain(self):
        calc = IRPFCalculator(fiscal_year=2025)
        calc.add_buy(
            symbol="AAPL", buy_date=date(2025, 1, 15),
            quantity=10, price_local=150.0, price_eur=138.0,
            fx_rate=0.92, currency="USD",
        )
        gains = calc.add_sell(
            symbol="AAPL", sell_date=date(2025, 6, 15),
            quantity=10, price_local=180.0, price_eur=166.0,
            fx_rate=0.922,
        )
        assert len(gains) == 1
        assert gains[0].is_gain is True
        assert gains[0].gain_loss_eur > 0
        assert gains[0].holding_period_days == 151

    def test_simple_loss(self):
        calc = IRPFCalculator(fiscal_year=2025)
        calc.add_buy(
            symbol="TSLA", buy_date=date(2025, 3, 1),
            quantity=5, price_local=200.0, price_eur=185.0,
            fx_rate=0.925, currency="USD",
        )
        gains = calc.add_sell(
            symbol="TSLA", sell_date=date(2025, 4, 1),
            quantity=5, price_local=150.0, price_eur=139.0,
            fx_rate=0.927,
        )
        assert len(gains) == 1
        assert gains[0].is_gain is False
        assert gains[0].gain_loss_eur < 0

    def test_fifo_matching(self):
        """Two buys at different prices, single sell should match FIFO."""
        calc = IRPFCalculator(fiscal_year=2025)
        calc.add_buy(
            symbol="MSFT", buy_date=date(2025, 1, 1),
            quantity=10, price_local=300.0, price_eur=277.0,
            fx_rate=0.923, currency="USD",
        )
        calc.add_buy(
            symbol="MSFT", buy_date=date(2025, 2, 1),
            quantity=10, price_local=350.0, price_eur=323.0,
            fx_rate=0.923, currency="USD",
        )
        gains = calc.add_sell(
            symbol="MSFT", sell_date=date(2025, 6, 1),
            quantity=15, price_local=380.0, price_eur=351.0,
            fx_rate=0.924,
        )
        # Should match 10 from first lot + 5 from second lot
        assert len(gains) == 2
        assert gains[0].quantity == 10  # Full first lot
        assert gains[1].quantity == 5   # Partial second lot

    def test_homogeneous_securities_rule(self):
        """Loss should be disallowed if repurchased within 2 months."""
        calc = IRPFCalculator(fiscal_year=2025)
        # Buy
        calc.add_buy(
            symbol="NVDA", buy_date=date(2025, 3, 1),
            quantity=10, price_local=800.0, price_eur=740.0,
            fx_rate=0.925, currency="USD",
        )
        # Sell at loss
        gains = calc.add_sell(
            symbol="NVDA", sell_date=date(2025, 4, 1),
            quantity=10, price_local=700.0, price_eur=648.0,
            fx_rate=0.926,
        )
        assert gains[0].is_gain is False
        # No repurchase yet — loss should be allowed
        assert gains[0].loss_disallowed is False

        # Now buy again within 2 months of the sell
        calc2 = IRPFCalculator(fiscal_year=2025)
        calc2.add_buy(
            symbol="NVDA", buy_date=date(2025, 3, 1),
            quantity=10, price_local=800.0, price_eur=740.0,
            fx_rate=0.925, currency="USD",
        )
        # Repurchase before sell (within 2-month window)
        calc2.add_buy(
            symbol="NVDA", buy_date=date(2025, 3, 25),
            quantity=5, price_local=720.0, price_eur=666.0,
            fx_rate=0.925, currency="USD",
        )
        gains2 = calc2.add_sell(
            symbol="NVDA", sell_date=date(2025, 4, 1),
            quantity=10, price_local=700.0, price_eur=648.0,
            fx_rate=0.926,
        )
        assert gains2[0].loss_disallowed is True
        assert "Art. 33.5.f LIRPF" in (gains2[0].loss_disallowed_reason or "")

    def test_tax_computation_brackets(self):
        calc = IRPFCalculator(fiscal_year=2025)
        # Test with EUR 60,000 net gain
        tax, brackets = calc.compute_tax(60_000.0)
        assert tax > 0
        assert len(brackets) == 3  # Spans 3 brackets
        # Verify first bracket
        assert brackets[0]["rate"] == 0.19
        assert brackets[0]["taxable_amount"] == 6_000.0

    def test_tax_zero_on_loss(self):
        calc = IRPFCalculator(fiscal_year=2025)
        tax, brackets = calc.compute_tax(-5_000.0)
        assert tax == 0.0
        assert len(brackets) == 0

    def test_generate_report(self):
        calc = IRPFCalculator(fiscal_year=2025)
        calc.add_buy(
            symbol="AAPL", buy_date=date(2025, 1, 1),
            quantity=10, price_local=150.0, price_eur=138.0,
            fx_rate=0.92, currency="USD",
        )
        calc.add_sell(
            symbol="AAPL", sell_date=date(2025, 6, 1),
            quantity=10, price_local=180.0, price_eur=166.0,
            fx_rate=0.922,
        )
        report = calc.generate_report()
        assert report.fiscal_year == 2025
        assert len(report.capital_gains) == 1
        assert report.summary.num_transactions == 1
        assert report.summary.total_gains_eur > 0


class TestFormatter:
    def _make_report(self) -> TaxReport:
        calc = IRPFCalculator(fiscal_year=2025)
        calc.add_buy(
            symbol="AAPL", buy_date=date(2025, 1, 1),
            quantity=10, price_local=150.0, price_eur=138.0,
            fx_rate=0.92, currency="USD", isin="US0378331005",
        )
        calc.add_sell(
            symbol="AAPL", sell_date=date(2025, 6, 1),
            quantity=10, price_local=180.0, price_eur=166.0,
            fx_rate=0.922,
        )
        return calc.generate_report()

    def test_csv_format(self):
        report = self._make_report()
        csv_output = format_as_csv(report)
        assert "AAPL" in csv_output
        assert "US0378331005" in csv_output
        assert "SUMMARY" in csv_output

    def test_summary_text_format(self):
        report = self._make_report()
        text = format_summary_text(report)
        assert "IRPF Tax Report" in text
        assert "2025" in text
        assert "Capital Gains" in text
```

---

### tests/unit/test_a2a.py

```python
"""Tests for A2A Protocol integration."""

from __future__ import annotations

import pytest

from qitp_agents.a2a.agent_card import (
    AgentCard,
    build_gap_detector_card,
    build_all_cards,
    AGENT_CARD_BUILDERS,
)
from qitp_agents.a2a.task_handler import (
    A2ATaskHandler,
    Task,
    TaskState,
)
from qitp_agents.a2a.discovery import AgentDiscovery


class TestAgentCards:
    def test_build_gap_detector_card(self):
        card = build_gap_detector_card("http://localhost:8080")
        assert card.name == "QITP Gap Detection Agent"
        assert card.url == "http://localhost:8080/agents/gap-detector"
        assert len(card.skills) == 1
        assert card.skills[0].id == "detect_gaps"
        assert card.protocol_version == "0.2.1"

    def test_build_all_cards(self):
        cards = build_all_cards("http://localhost:8080")
        assert len(cards) == len(AGENT_CARD_BUILDERS)
        for agent_id, card in cards.items():
            assert card.url.startswith("http://localhost:8080")
            assert len(card.skills) >= 1

    def test_card_serialization(self):
        card = build_gap_detector_card("http://test.example.com")
        data = card.model_dump()
        assert "name" in data
        assert "skills" in data
        # Roundtrip
        card2 = AgentCard(**data)
        assert card2.name == card.name


class TestTaskHandler:
    @pytest.fixture
    def mock_handler(self):
        """Create a mock agent handler."""
        def handler(event):
            return {
                "statusCode": 200,
                "body": '{"result": "success", "summary": "Test completed."}',
            }
        return handler

    @pytest.fixture
    def task_handler(self, mock_handler):
        return A2ATaskHandler(agent_handlers={"test-agent": mock_handler})

    @pytest.mark.asyncio
    async def test_send_task_success(self, task_handler):
        request = {
            "id": "task-001",
            "message": {
                "parts": [{"type": "data", "data": {"date": "2026-03-15"}}],
            },
        }
        task = await task_handler.send_task("test-agent", request)
        assert task.id == "task-001"
        assert task.status.state == TaskState.COMPLETED
        assert len(task.messages) == 2  # user + agent

    @pytest.mark.asyncio
    async def test_send_task_unknown_agent(self, task_handler):
        request = {"message": {"parts": []}}
        task = await task_handler.send_task("nonexistent-agent", request)
        assert task.status.state == TaskState.FAILED

    @pytest.mark.asyncio
    async def test_get_task(self, task_handler):
        request = {"id": "task-002", "message": {"parts": []}}
        await task_handler.send_task("test-agent", request)
        task = await task_handler.get_task("task-002")
        assert task is not None
        assert task.id == "task-002"

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_handler):
        # Create a task
        request = {"id": "task-003", "message": {"parts": []}}
        await task_handler.send_task("test-agent", request)
        # Cancel it (already completed, so cancel should have no effect)
        task = await task_handler.cancel_task("task-003")
        assert task is not None
        # Task already completed, so state stays completed
        assert task.status.state == TaskState.COMPLETED


class TestDiscovery:
    def test_find_by_skill_empty(self):
        discovery = AgentDiscovery()
        results = discovery.find_by_skill("trading")
        assert len(results) == 0

    def test_list_cached_empty(self):
        discovery = AgentDiscovery()
        assert len(discovery.list_cached()) == 0
```

---

### tests/test_markets.py

```python
"""Tests for multi-market support (calendar, timezone, sessions, currency)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from agent_core.markets.calendar import (
    MarketCalendar,
    MarketCode,
    MarketHoliday,
    get_calendar,
)
from agent_core.markets.timezone import (
    MarketTimezone,
    to_market_time,
    to_utc,
    MARKET_TIMEZONES,
)
from agent_core.markets.sessions import (
    SessionType,
    get_current_session,
)
from agent_core.markets.currency import (
    CurrencyConverter,
    CurrencyPair,
    convert_currency,
)


class TestMarketCalendar:
    def test_us_trading_day(self):
        cal = get_calendar(MarketCode.US)
        # Regular Wednesday
        assert cal.is_trading_day(date(2026, 3, 18)) is True

    def test_us_weekend(self):
        cal = get_calendar(MarketCode.US)
        assert cal.is_trading_day(date(2026, 3, 14)) is False  # Saturday
        assert cal.is_trading_day(date(2026, 3, 15)) is False  # Sunday

    def test_us_holiday(self):
        cal = get_calendar(MarketCode.US)
        assert cal.is_trading_day(date(2026, 1, 1)) is False  # New Year

    def test_crypto_always_open(self):
        cal = get_calendar(MarketCode.CRYPTO)
        assert cal.is_trading_day(date(2026, 12, 25)) is True
        assert cal.is_trading_day(date(2026, 3, 14)) is True  # Saturday

    def test_japan_holiday(self):
        cal = get_calendar(MarketCode.JP)
        assert cal.is_trading_day(date(2026, 1, 1)) is False  # New Year

    def test_next_trading_day(self):
        cal = get_calendar(MarketCode.US)
        # Friday -> Monday
        assert cal.next_trading_day(date(2026, 3, 13)) == date(2026, 3, 16)

    def test_previous_trading_day(self):
        cal = get_calendar(MarketCode.US)
        # Monday -> Friday
        assert cal.previous_trading_day(date(2026, 3, 16)) == date(2026, 3, 13)

    def test_gap_window(self):
        cal = get_calendar(MarketCode.US)
        result = cal.gap_window(date(2026, 3, 16))  # Monday
        assert result is not None
        friday, monday = result
        assert friday == date(2026, 3, 13)
        assert monday == date(2026, 3, 16)

    def test_gap_window_crypto_returns_none(self):
        cal = get_calendar(MarketCode.CRYPTO)
        assert cal.gap_window(date(2026, 3, 16)) is None

    def test_gap_window_non_monday(self):
        cal = get_calendar(MarketCode.US)
        assert cal.gap_window(date(2026, 3, 17)) is None  # Tuesday

    def test_trading_days_between(self):
        cal = get_calendar(MarketCode.US)
        days = cal.trading_days_between(date(2026, 3, 16), date(2026, 3, 20))
        assert len(days) == 5  # Mon-Fri


class TestTimezone:
    def test_market_timezone(self):
        tz = MarketTimezone(MarketCode.JP)
        assert tz.tz_name == "Asia/Tokyo"

    def test_to_market_time(self):
        # 14:00 UTC -> Tokyo (UTC+9)
        utc_dt = datetime(2026, 3, 16, 14, 0, tzinfo=ZoneInfo("UTC"))
        tokyo_dt = to_market_time(utc_dt, MarketCode.JP)
        assert tokyo_dt.hour == 23

    def test_to_utc_from_market(self):
        # 9:00 Tokyo -> UTC
        tokyo_naive = datetime(2026, 3, 16, 9, 0)
        utc_dt = to_utc(tokyo_naive, source_market=MarketCode.JP)
        assert utc_dt.hour == 0


class TestSessions:
    def test_us_regular_hours(self):
        # 10:00 AM New York on a Monday
        ny_time = datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        session = get_current_session(MarketCode.US, at_time=ny_time)
        assert session.session == SessionType.REGULAR
        assert session.is_trading_day is True

    def test_us_pre_market(self):
        ny_time = datetime(2026, 3, 16, 5, 0, tzinfo=ZoneInfo("America/New_York"))
        session = get_current_session(MarketCode.US, at_time=ny_time)
        assert session.session == SessionType.PRE_MARKET

    def test_us_closed_weekend(self):
        ny_time = datetime(2026, 3, 14, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        session = get_current_session(MarketCode.US, at_time=ny_time)
        assert session.session == SessionType.CLOSED

    def test_crypto_always_regular(self):
        any_time = datetime(2026, 3, 14, 3, 30, tzinfo=ZoneInfo("UTC"))
        session = get_current_session(MarketCode.CRYPTO, at_time=any_time)
        assert session.session == SessionType.REGULAR

    def test_japan_regular_hours(self):
        tokyo_time = datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        session = get_current_session(MarketCode.JP, at_time=tokyo_time)
        assert session.session == SessionType.REGULAR


class TestCurrency:
    @pytest.mark.asyncio
    async def test_same_currency(self):
        converter = CurrencyConverter()
        pair = await converter.get_rate("EUR", "EUR")
        assert pair.rate == 1.0
        assert pair.source == "identity"

    @pytest.mark.asyncio
    async def test_static_rate(self):
        converter = CurrencyConverter()
        pair = await converter.get_rate("EUR", "USD")
        assert pair.rate == 1.08
        assert pair.source == "static"

    @pytest.mark.asyncio
    async def test_inverse_rate(self):
        converter = CurrencyConverter()
        pair = await converter.get_rate("USD", "CHF")
        # No direct rate, but EUR/CHF and EUR/USD exist
        # This tests inverse fallback for pairs that have the inverse in static rates
        # USD/EUR inverse should work
        eur_pair = await converter.get_rate("USD", "EUR")
        assert eur_pair.rate == 0.926

    @pytest.mark.asyncio
    async def test_convert_currency(self):
        result = await convert_currency(1000.0, "EUR", "USD")
        assert result == pytest.approx(1080.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_unknown_pair_raises(self):
        converter = CurrencyConverter()
        with pytest.raises(ValueError, match="No rate available"):
            await converter.get_rate("XYZ", "ABC")
```

---

### tests/test_cfd_risk.py

```python
"""Tests for CFD risk rules — leverage limits, margin, product classification."""

from __future__ import annotations

import pytest

from agent_core.risk.product_classifier import (
    ProductType,
    classify_product,
)
from agent_core.risk.cfd_leverage import (
    ESMAAssetClass,
    CFDLeverageCheck,
    check_cfd_leverage,
    classify_esma_asset_class,
    ESMA_LEVERAGE_LIMITS,
)
from agent_core.risk.margin_call import (
    MarginLevel,
    MarginCallDetector,
    PositionMargin,
)


class TestProductClassifier:
    def test_equity(self):
        assert classify_product("AAPL") == ProductType.EQUITY

    def test_etf(self):
        assert classify_product("SPY") == ProductType.ETF
        assert classify_product("QQQ") == ProductType.ETF

    def test_crypto_pattern(self):
        assert classify_product("BTC-USD") == ProductType.CRYPTO
        assert classify_product("ETH-USDT") == ProductType.CRYPTO

    def test_cfd_suffix(self):
        assert classify_product("AAPL.CFD") == ProductType.CFD

    def test_explicit_type_hint(self):
        assert classify_product("AAPL", instrument_type="CFD") == ProductType.CFD
        assert classify_product("BTC", instrument_type="CRYPTO") == ProductType.CRYPTO

    def test_crypto_exchange(self):
        assert classify_product("BTC", exchange="BINANCE") == ProductType.CRYPTO

    def test_unknown_defaults_equity(self):
        assert classify_product("UNKNOWN_SYMBOL") == ProductType.EQUITY


class TestESMALeverage:
    def test_equity_cfd_5x(self):
        result = check_cfd_leverage(
            "AAPL", ProductType.EQUITY,
            requested_leverage=5.0,
        )
        assert result.is_compliant is True
        assert result.max_leverage == 5

    def test_equity_cfd_exceeds(self):
        result = check_cfd_leverage(
            "AAPL", ProductType.EQUITY,
            requested_leverage=10.0,
        )
        assert result.is_compliant is False
        assert "REJECTED" in result.message

    def test_crypto_cfd_2x(self):
        result = check_cfd_leverage(
            "BTC-USD", ProductType.CRYPTO,
            requested_leverage=2.0,
        )
        assert result.is_compliant is True
        assert result.max_leverage == 2

    def test_crypto_cfd_exceeds(self):
        result = check_cfd_leverage(
            "BTC-USD", ProductType.CRYPTO,
            requested_leverage=5.0,
        )
        assert result.is_compliant is False

    def test_major_index_20x(self):
        result = check_cfd_leverage(
            "SPY", ProductType.ETF,
            requested_leverage=20.0,
        )
        assert result.is_compliant is True

    def test_professional_exempt(self):
        result = check_cfd_leverage(
            "AAPL", ProductType.EQUITY,
            requested_leverage=50.0,
            is_professional=True,
        )
        assert result.is_compliant is True

    def test_margin_percentage(self):
        result = check_cfd_leverage(
            "AAPL", ProductType.EQUITY,
            requested_leverage=5.0,
        )
        assert result.margin_required_pct == 20.0  # 100/5

    def test_classify_esma_crypto(self):
        assert classify_esma_asset_class("BTC-USD", ProductType.CRYPTO) == ESMAAssetClass.CRYPTO

    def test_classify_esma_equity(self):
        assert classify_esma_asset_class("AAPL", ProductType.EQUITY) == ESMAAssetClass.INDIVIDUAL_EQUITY


class TestMarginCall:
    @pytest.fixture
    def detector(self):
        return MarginCallDetector()

    def test_healthy_margin(self, detector):
        positions = [
            PositionMargin(
                symbol="AAPL", position_value=10000,
                initial_margin=2000, maintenance_margin=1000,
                current_margin=8000, margin_utilization_pct=20,
                unrealized_pnl=500, leverage=5,
            ),
        ]
        status = detector.evaluate(account_equity=10000, positions=positions)
        assert status.margin_level == MarginLevel.HEALTHY
        assert status.margin_level_pct == 500.0  # 10000/2000 * 100

    def test_warning_margin(self, detector):
        positions = [
            PositionMargin(
                symbol="AAPL", position_value=50000,
                initial_margin=8000, maintenance_margin=4000,
                current_margin=4000, margin_utilization_pct=66,
                unrealized_pnl=-2000, leverage=5,
            ),
        ]
        status = detector.evaluate(account_equity=12000, positions=positions)
        assert status.margin_level == MarginLevel.WARNING

    def test_close_out_margin(self, detector):
        positions = [
            PositionMargin(
                symbol="AAPL", position_value=50000,
                initial_margin=10000, maintenance_margin=5000,
                current_margin=1000, margin_utilization_pct=90,
                unrealized_pnl=-7000, leverage=5,
            ),
        ]
        status = detector.evaluate(account_equity=4000, positions=positions)
        assert status.margin_level == MarginLevel.CLOSE_OUT
        assert len(status.close_out_positions) > 0
        assert "AAPL" in status.close_out_positions

    def test_no_positions(self, detector):
        status = detector.evaluate(account_equity=10000, positions=[])
        assert status.margin_level == MarginLevel.HEALTHY
        assert status.free_margin == 10000

    def test_close_out_order(self, detector):
        """Largest margin position should be closed first."""
        positions = [
            PositionMargin(
                symbol="AAPL", position_value=10000,
                initial_margin=2000, maintenance_margin=1000,
                current_margin=500, margin_utilization_pct=80,
                unrealized_pnl=-1000, leverage=5,
            ),
            PositionMargin(
                symbol="TSLA", position_value=30000,
                initial_margin=6000, maintenance_margin=3000,
                current_margin=500, margin_utilization_pct=75,
                unrealized_pnl=-3000, leverage=5,
            ),
        ]
        status = detector.evaluate(account_equity=3000, positions=positions)
        assert status.margin_level == MarginLevel.CLOSE_OUT
        # TSLA has higher margin, should be closed first
        assert status.close_out_positions[0] == "TSLA"
```

---

### tests/test_agentcore_advanced.py

```python
"""Tests for advanced AgentCore features — memory branching, streaming, multi-tenant."""

from __future__ import annotations

import asyncio
import pytest

from agent_core.agentcore.memory_branching import MemoryBranchManager
from agent_core.agentcore.streaming import StreamBuffer, StreamEventType, format_sse
from agent_core.agentcore.multi_tenant import (
    TenantContext,
    TenantScopedKey,
    TenantResourceGuard,
    TenantLimitExceeded,
)


class TestMemoryBranching:
    def test_create_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("strategy_a", base_state={"symbols": ["AAPL"]})
        assert branch.name == "strategy_a"
        assert branch.state == {"symbols": ["AAPL"]}
        assert branch.status == "active"

    def test_update_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("test", base_state={"count": 0})
        mgr.update_branch(branch.branch_id, state_updates={"count": 5}, metrics={"sharpe": 1.5})
        updated = mgr.get_branch(branch.branch_id)
        assert updated.state["count"] == 5
        assert updated.metrics["sharpe"] == 1.5

    def test_compare_branches(self):
        mgr = MemoryBranchManager(session_id="test-session")
        b1 = mgr.create_branch("conservative")
        b2 = mgr.create_branch("aggressive")
        mgr.update_branch(b1.branch_id, metrics={"sharpe_ratio": 1.2})
        mgr.update_branch(b2.branch_id, metrics={"sharpe_ratio": 1.8})

        best = mgr.compare_branches(
            [b1.branch_id, b2.branch_id],
            metric="sharpe_ratio",
        )
        assert best.name == "aggressive"

    def test_merge_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("winner", base_state={"strategy": "momentum"})
        result = mgr.merge_branch(branch.branch_id)
        assert result == {"strategy": "momentum"}
        assert mgr.get_branch(branch.branch_id).status == "merged"

    def test_discard_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("loser")
        mgr.discard_branch(branch.branch_id)
        assert mgr.get_branch(branch.branch_id).status == "discarded"

    def test_list_branches(self):
        mgr = MemoryBranchManager(session_id="test-session")
        mgr.create_branch("a")
        mgr.create_branch("b")
        b3 = mgr.create_branch("c")
        mgr.discard_branch(b3.branch_id)

        active = mgr.list_branches(status="active")
        assert len(active) == 2
        all_branches = mgr.list_branches()
        assert len(all_branches) == 3


class TestStreaming:
    @pytest.mark.asyncio
    async def test_push_and_get(self):
        buffer = StreamBuffer(session_id="s1", agent_id="gap-detector")
        await buffer.push(StreamEventType.PROGRESS, {"step": 1, "total": 5})
        await buffer.push(StreamEventType.COMPLETE, {"result": "done"})

        events = buffer.get_events()
        assert len(events) == 2
        assert events[0].event_type == StreamEventType.PROGRESS
        assert events[1].event_type == StreamEventType.COMPLETE
        assert buffer.is_complete is True

    @pytest.mark.asyncio
    async def test_get_events_after_sequence(self):
        buffer = StreamBuffer(session_id="s1", agent_id="test")
        await buffer.push(StreamEventType.PROGRESS, {"step": 1})
        await buffer.push(StreamEventType.PROGRESS, {"step": 2})
        await buffer.push(StreamEventType.COMPLETE, {})

        events_after_1 = buffer.get_events(after_sequence=1)
        assert len(events_after_1) == 2

    def test_format_sse(self):
        from agent_core.agentcore.streaming import StreamEvent
        event = StreamEvent(
            event_type=StreamEventType.PROGRESS,
            agent_id="test",
            session_id="s1",
            data={"step": 1},
            sequence=1,
        )
        sse = format_sse(event)
        assert sse.startswith("event: progress\n")
        assert "data:" in sse
        assert sse.endswith("\n\n")


class TestMultiTenant:
    def test_tenant_context_defaults(self):
        ctx = TenantContext()
        assert ctx.tenant_id == "default"
        assert ctx.max_watchlist_symbols == 100

    def test_scoped_dynamodb_key(self):
        key = TenantScopedKey.dynamodb_pk("tenant-1", "artifact", "abc123")
        assert "tenant-1" in key
        assert "artifact" in key
        assert "abc123" in key

    def test_scoped_s3_key(self):
        key = TenantScopedKey.s3_key("tenant-1", "reports", "tax_2025.json")
        assert key == "tenants/tenant-1/reports/tax_2025.json"

    def test_scoped_session_id(self):
        sid = TenantScopedKey.session_id("tenant-1", "sfn-exec-abc")
        assert sid == "tenant-1:sfn-exec-abc"

    def test_resource_guard_watchlist_ok(self):
        ctx = TenantContext(max_watchlist_symbols=100)
        guard = TenantResourceGuard(ctx)
        guard.check_watchlist_limit(50)  # Should not raise

    def test_resource_guard_watchlist_exceeded(self):
        ctx = TenantContext(max_watchlist_symbols=100)
        guard = TenantResourceGuard(ctx)
        with pytest.raises(TenantLimitExceeded, match="Watchlist limit"):
            guard.check_watchlist_limit(100)

    def test_resource_guard_concurrent_agents(self):
        ctx = TenantContext(max_concurrent_agents=5)
        guard = TenantResourceGuard(ctx)
        with pytest.raises(TenantLimitExceeded, match="Concurrent agent"):
            guard.check_concurrent_agents(5)

    def test_resource_guard_storage(self):
        ctx = TenantContext(max_artifacts_gb=10.0)
        guard = TenantResourceGuard(ctx)
        with pytest.raises(TenantLimitExceeded, match="storage limit"):
            guard.check_artifact_storage(9.5, 1.0)
```

---

## Acceptance Criteria

1. **Watchlist Screener**: `pytest tests/unit/test_watchlist_screener.py` — all universe providers return symbols, filters reduce candidate counts correctly, ranking produces sorted results with score breakdowns.

2. **Tax Reporter**: `pytest tests/unit/test_tax_reporter.py` — FIFO lot matching produces correct gains/losses, homogeneous securities rule detects 2-month repurchase violations, tax bracket computation matches IRPF rates, CSV/text formatters produce valid output.

3. **A2A Protocol**: `pytest tests/unit/test_a2a.py` — Agent Cards contain valid skill definitions, task handler routes to correct agent, task lifecycle (submit/get/cancel) works correctly.

4. **Multi-Market**: `pytest tests/test_markets.py` — calendars correctly identify trading days/holidays for US/JP/HK/crypto, timezone conversions are accurate, session detection returns correct state, currency conversion uses static rates with inverse fallback.

5. **CFD Risk**: `pytest tests/test_cfd_risk.py` — product classifier correctly identifies equity/ETF/CFD/crypto, ESMA leverage limits enforced per asset class, professional client exemption works, margin call detector correctly identifies healthy/warning/close-out levels.

6. **AgentCore Advanced**: `pytest tests/test_agentcore_advanced.py` — memory branching creates/updates/compares/merges/discards branches, streaming buffer pushes and retrieves events with sequence filtering, multi-tenant key generation is correct, resource guards enforce limits.

7. **No hardcoded prompts** — all agent blueprints reference `system_prompt_id`, not inline prompt text.

8. **No hardcoded credentials** — all API keys referenced via environment variables (`JQUANTS_API_KEY`, etc.).

9. **Claim-check pattern** — all agent handlers marshal output with 256KB check and claim-check fallback.

10. **MCP clients scoped per invocation** — all handlers create MCP clients inside the handler function, not at module level.
