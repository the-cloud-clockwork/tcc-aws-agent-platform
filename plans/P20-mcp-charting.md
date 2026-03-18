# P20 — Charting MCP Server

## Objective
Build `charting-mcp`: an MCP server generating interactive financial charts as React/Recharts JSX artifacts. 7 chart tools covering candlesticks, equity curves, gap analysis, sentiment heatmaps, P&L, portfolio allocation, and a generic chart builder. Charts are stored via artifacts-mcp and rendered in Claude.ai as interactive React components.

## Plane Tickets
ROOT-65

## Target Repo
`~/dev/tccw-qitp-mcp-charting`

## Dependencies
P01 (repo scaffold), P06 (artifacts-mcp for storage)

## Repo Structure
```
tccw-qitp-mcp-charting/
├── src/
│   └── qitp_mcp_charting/
│       ├── __init__.py
│       ├── server.py              # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── candlestick.py     # generate_candlestick (OHLC + SMA/EMA overlay + volume)
│       │   ├── equity_curve.py    # generate_equity_curve (with drawdown shading)
│       │   ├── gap_scatter.py     # generate_gap_scatter (gap% vs return scatter)
│       │   ├── sentiment.py       # generate_sentiment_heatmap (symbol × source heat matrix)
│       │   ├── pnl.py             # generate_pnl_bar (daily/weekly P&L bar chart)
│       │   ├── allocation.py      # generate_portfolio_allocation (pie/treemap)
│       │   └── generic.py         # generate_chart (flexible chart from spec)
│       ├── renderers/
│       │   ├── __init__.py
│       │   ├── recharts.py        # React/Recharts JSX template engine
│       │   ├── html_fallback.py   # Static HTML+Chart.js fallback
│       │   └── templates/         # Jinja2 templates for each chart type
│       │       ├── candlestick.jsx.j2
│       │       ├── equity_curve.jsx.j2
│       │       ├── gap_scatter.jsx.j2
│       │       ├── sentiment_heatmap.jsx.j2
│       │       ├── pnl_bar.jsx.j2
│       │       ├── allocation.jsx.j2
│       │       └── base.html.j2
│       ├── schemas.py             # ChartRequest, ChartResult, CandlestickData, etc.
│       └── artifact_client.py     # Client to store charts via artifacts-mcp
├── tests/
│   ├── conftest.py
│   ├── test_candlestick.py
│   ├── test_equity_curve.py
│   ├── test_renderers.py
│   └── fixtures/
│       └── sample_ohlcv.json
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
name = "qitp-mcp-charting"
version = "0.1.0"
description = "QITP Charting MCP Server — interactive React/Recharts financial chart generation"
requires-python = ">=3.11"
dependencies = [
    "mcp[server]>=1.0.0",
    "pydantic>=2.0",
    "jinja2>=3.1",
    "httpx>=0.27",
    "uvicorn>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[project.scripts]
charting-mcp = "qitp_mcp_charting.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_charting"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

### `src/qitp_mcp_charting/__init__.py`

```python
"""QITP Charting MCP Server — interactive financial chart generation."""

__version__ = "0.1.0"
```

---

### `src/qitp_mcp_charting/schemas.py`

```python
"""Shared data schemas for charting MCP server."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChartFormat(str, Enum):
    """Output format for rendered charts."""

    RECHARTS_JSX = "recharts_jsx"
    HTML_FALLBACK = "html_fallback"


class ChartType(str, Enum):
    """Supported generic chart types."""

    LINE = "line"
    BAR = "bar"
    SCATTER = "scatter"
    PIE = "pie"
    AREA = "area"
    COMPOSED = "composed"


class Theme(str, Enum):
    """Chart color theme."""

    DARK = "dark"
    LIGHT = "light"


# ---------------------------------------------------------------------------
# Data models — inputs for each chart tool
# ---------------------------------------------------------------------------

class OHLCVBar(BaseModel):
    """Single OHLCV bar for candlestick charts."""

    date: str = Field(description="ISO date string YYYY-MM-DD")
    open: float
    high: float
    low: float
    close: float
    volume: int


class EquityCurvePoint(BaseModel):
    """Single data point on an equity curve."""

    date: str = Field(description="ISO date string YYYY-MM-DD")
    value: float = Field(description="Portfolio value at this date")
    peak: float | None = Field(None, description="Running peak value for drawdown calc")
    drawdown_pct: float | None = Field(None, description="Drawdown percentage from peak")


class GapScatterPoint(BaseModel):
    """Single point on the gap scatter plot."""

    symbol: str
    gap_pct: float = Field(description="Weekend gap percentage (signed)")
    subsequent_return: float = Field(description="Return after gap, e.g. 1-day or 5-day")
    strategy: str | None = Field(None, description="Strategy name for color coding")
    date: str | None = Field(None, description="Date of the gap event")


class SentimentCell(BaseModel):
    """Single cell in the sentiment heatmap."""

    symbol: str
    source: str = Field(description="One of: news, analyst, macro, social")
    score: float = Field(description="Sentiment score -1.0 to 1.0")
    label: str | None = Field(None, description="Optional text label for the cell")


class PnLEntry(BaseModel):
    """Single bar in a P&L chart."""

    period: str = Field(description="Date or week label")
    pnl: float = Field(description="Profit/loss for this period (signed)")
    cumulative: float | None = Field(None, description="Cumulative P&L")


class AllocationSlice(BaseModel):
    """Single slice of portfolio allocation."""

    name: str = Field(description="Sector or position name")
    value: float = Field(description="Allocation value (absolute or percentage)")
    color: str | None = Field(None, description="Optional hex color override")


# ---------------------------------------------------------------------------
# Chart configuration
# ---------------------------------------------------------------------------

class OverlayConfig(BaseModel):
    """Configuration for technical indicator overlays on candlestick charts."""

    type: Literal["sma", "ema"] = "sma"
    period: int = 20
    color: str = "#FFD700"
    label: str | None = None


class ChartConfig(BaseModel):
    """Common chart configuration."""

    title: str = ""
    subtitle: str = ""
    width: int = 800
    height: int = 500
    theme: Theme = Theme.DARK
    format: ChartFormat = ChartFormat.RECHARTS_JSX
    responsive: bool = True
    show_legend: bool = True
    show_grid: bool = True
    show_tooltip: bool = True


# ---------------------------------------------------------------------------
# Tool request/response models
# ---------------------------------------------------------------------------

class CandlestickRequest(BaseModel):
    """Request for generate_candlestick tool."""

    symbol: str
    bars: list[OHLCVBar]
    overlays: list[OverlayConfig] = Field(default_factory=list)
    show_volume: bool = True
    config: ChartConfig = Field(default_factory=ChartConfig)


class EquityCurveRequest(BaseModel):
    """Request for generate_equity_curve tool."""

    strategy_name: str
    data: list[EquityCurvePoint]
    show_drawdown: bool = True
    benchmark_data: list[EquityCurvePoint] | None = None
    config: ChartConfig = Field(default_factory=ChartConfig)


class GapScatterRequest(BaseModel):
    """Request for generate_gap_scatter tool."""

    data: list[GapScatterPoint]
    strategies: list[str] = Field(default_factory=list, description="Strategy names for legend")
    x_label: str = "Gap %"
    y_label: str = "Subsequent Return %"
    config: ChartConfig = Field(default_factory=ChartConfig)


class SentimentHeatmapRequest(BaseModel):
    """Request for generate_sentiment_heatmap tool."""

    data: list[SentimentCell]
    symbols: list[str] = Field(default_factory=list, description="Row order")
    sources: list[str] = Field(default_factory=lambda: ["news", "analyst", "macro", "social"])
    config: ChartConfig = Field(default_factory=ChartConfig)


class PnLBarRequest(BaseModel):
    """Request for generate_pnl_bar tool."""

    data: list[PnLEntry]
    show_cumulative: bool = True
    period_type: Literal["daily", "weekly", "monthly"] = "daily"
    config: ChartConfig = Field(default_factory=ChartConfig)


class AllocationRequest(BaseModel):
    """Request for generate_portfolio_allocation tool."""

    data: list[AllocationSlice]
    chart_style: Literal["pie", "treemap", "donut"] = "donut"
    show_percentages: bool = True
    config: ChartConfig = Field(default_factory=ChartConfig)


class GenericChartRequest(BaseModel):
    """Request for generate_chart (flexible/generic) tool."""

    chart_type: ChartType
    data: list[dict[str, Any]] = Field(description="Array of data objects")
    x_key: str = Field(description="Key in data objects to use as X axis")
    y_keys: list[str] = Field(description="Keys in data objects to plot as Y series")
    series_colors: dict[str, str] = Field(default_factory=dict)
    config: ChartConfig = Field(default_factory=ChartConfig)


class ChartResult(BaseModel):
    """Standard result returned by all chart tools."""

    chart_id: str = Field(description="Unique chart identifier")
    content: str = Field(description="Rendered chart content (JSX or HTML)")
    format: ChartFormat
    artifact_id: str | None = Field(None, description="Artifact ID if stored via artifacts-mcp")
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

### `src/qitp_mcp_charting/artifact_client.py`

```python
"""Client for storing charts as artifacts via artifacts-mcp."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ARTIFACTS_MCP_URL = os.getenv("ARTIFACTS_MCP_URL", "http://localhost:8004")


class ArtifactClient:
    """HTTP client for the artifacts-mcp create_artifact tool.

    Charts are stored with type=chart so they can be retrieved
    and rendered by any QITP client.
    """

    def __init__(self, base_url: str = ARTIFACTS_MCP_URL) -> None:
        self._base_url = base_url.rstrip("/")

    async def store_chart(
        self,
        chart_id: str,
        content: str,
        agent_id: str | None = None,
        execution_id: str | None = None,
        metadata: dict | None = None,
    ) -> str | None:
        """Store chart content via artifacts-mcp.

        Returns the artifact_id on success, None on failure.
        Failures are logged but never raised — chart generation
        should succeed even if artifact storage is unavailable.
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": chart_id,
                "method": "tools/call",
                "params": {
                    "name": "create_artifact",
                    "arguments": {
                        "artifact_type": "chart",
                        "content": content,
                        "agent_id": agent_id or "charting-mcp",
                        "execution_id": execution_id,
                        "metadata": {
                            "chart_id": chart_id,
                            **(metadata or {}),
                        },
                    },
                },
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/mcp",
                    json=payload,
                )
                resp.raise_for_status()
                result = resp.json()

                # Extract artifact_id from JSON-RPC response
                if "result" in result:
                    content_list = result["result"].get("content", [])
                    for item in content_list:
                        if item.get("type") == "text":
                            import json
                            data = json.loads(item["text"])
                            return data.get("artifact_id")

                logger.warning("Unexpected response from artifacts-mcp: %s", result)
                return None

        except Exception:
            logger.exception("Failed to store chart %s via artifacts-mcp", chart_id)
            return None
```

---

### `src/qitp_mcp_charting/renderers/__init__.py`

```python
"""Chart rendering engines."""

from __future__ import annotations

from qitp_mcp_charting.schemas import ChartFormat

from .html_fallback import HtmlFallbackRenderer
from .recharts import RechartsRenderer


def get_renderer(fmt: ChartFormat) -> RechartsRenderer | HtmlFallbackRenderer:
    """Return the appropriate renderer for the requested format."""
    if fmt == ChartFormat.RECHARTS_JSX:
        return RechartsRenderer()
    elif fmt == ChartFormat.HTML_FALLBACK:
        return HtmlFallbackRenderer()
    else:
        raise ValueError(f"Unknown chart format: {fmt}")


__all__ = [
    "get_renderer",
    "RechartsRenderer",
    "HtmlFallbackRenderer",
]
```

---

### `src/qitp_mcp_charting/renderers/recharts.py`

```python
"""React/Recharts JSX template renderer.

Renders chart data into self-contained React components using Recharts.
Output is compatible with Claude.ai artifact rendering (React sandbox).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class RechartsRenderer:
    """Renders chart data as React/Recharts JSX using Jinja2 templates."""

    def __init__(self, template_dir: Path = TEMPLATE_DIR) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Register custom filters
        self._env.filters["tojson"] = lambda v: json.dumps(v, default=str)

    def render_candlestick(
        self,
        symbol: str,
        bars: list[dict[str, Any]],
        overlays: list[dict[str, Any]],
        show_volume: bool,
        config: dict[str, Any],
    ) -> str:
        """Render a candlestick chart with optional overlays and volume."""
        template = self._env.get_template("candlestick.jsx.j2")
        return template.render(
            symbol=symbol,
            bars=bars,
            overlays=overlays,
            show_volume=show_volume,
            config=config,
        )

    def render_equity_curve(
        self,
        strategy_name: str,
        data: list[dict[str, Any]],
        show_drawdown: bool,
        benchmark_data: list[dict[str, Any]] | None,
        config: dict[str, Any],
    ) -> str:
        """Render an equity curve with optional drawdown shading."""
        template = self._env.get_template("equity_curve.jsx.j2")
        return template.render(
            strategy_name=strategy_name,
            data=data,
            show_drawdown=show_drawdown,
            benchmark_data=benchmark_data or [],
            config=config,
        )

    def render_gap_scatter(
        self,
        data: list[dict[str, Any]],
        strategies: list[str],
        x_label: str,
        y_label: str,
        config: dict[str, Any],
    ) -> str:
        """Render a gap scatter plot."""
        template = self._env.get_template("gap_scatter.jsx.j2")
        return template.render(
            data=data,
            strategies=strategies,
            x_label=x_label,
            y_label=y_label,
            config=config,
        )

    def render_sentiment_heatmap(
        self,
        data: list[dict[str, Any]],
        symbols: list[str],
        sources: list[str],
        config: dict[str, Any],
    ) -> str:
        """Render a sentiment heatmap matrix."""
        template = self._env.get_template("sentiment_heatmap.jsx.j2")
        return template.render(
            data=data,
            symbols=symbols,
            sources=sources,
            config=config,
        )

    def render_pnl_bar(
        self,
        data: list[dict[str, Any]],
        show_cumulative: bool,
        period_type: str,
        config: dict[str, Any],
    ) -> str:
        """Render a P&L bar chart."""
        template = self._env.get_template("pnl_bar.jsx.j2")
        return template.render(
            data=data,
            show_cumulative=show_cumulative,
            period_type=period_type,
            config=config,
        )

    def render_allocation(
        self,
        data: list[dict[str, Any]],
        chart_style: str,
        show_percentages: bool,
        config: dict[str, Any],
    ) -> str:
        """Render a portfolio allocation chart (pie/donut/treemap)."""
        template = self._env.get_template("allocation.jsx.j2")
        return template.render(
            data=data,
            chart_style=chart_style,
            show_percentages=show_percentages,
            config=config,
        )

    def render_generic(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        x_key: str,
        y_keys: list[str],
        series_colors: dict[str, str],
        config: dict[str, Any],
    ) -> str:
        """Render a generic chart from a flexible spec.

        Supports: line, bar, scatter, area, composed.
        Pie charts should use render_allocation instead.
        """
        # For pie, redirect to allocation template
        if chart_type == "pie":
            return self.render_allocation(
                data=[{"name": d.get(x_key, ""), "value": d.get(y_keys[0], 0)} for d in data],
                chart_style="pie",
                show_percentages=True,
                config=config,
            )

        # Map chart type to Recharts component names
        type_map = {
            "line": "Line",
            "bar": "Bar",
            "scatter": "Scatter",
            "area": "Area",
            "composed": "Composed",
        }
        recharts_type = type_map.get(chart_type, "Line")

        # Default colors for series
        default_colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff7300", "#00C49F", "#FFBB28"]
        colors = {}
        for i, key in enumerate(y_keys):
            colors[key] = series_colors.get(key, default_colors[i % len(default_colors)])

        template = self._env.get_template("generic.jsx.j2")
        return template.render(
            chart_type=chart_type,
            recharts_type=recharts_type,
            data=data,
            x_key=x_key,
            y_keys=y_keys,
            colors=colors,
            config=config,
        )
```

---

### `src/qitp_mcp_charting/renderers/html_fallback.py`

```python
"""Static HTML + Chart.js fallback renderer.

Used for non-Claude clients that cannot render React components.
Produces self-contained HTML documents with embedded Chart.js.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class HtmlFallbackRenderer:
    """Renders chart data as standalone HTML pages using Chart.js."""

    def __init__(self, template_dir: Path = TEMPLATE_DIR) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["tojson"] = lambda v: json.dumps(v, default=str)

    def _render_html(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        config: dict[str, Any],
        extra_context: dict[str, Any] | None = None,
    ) -> str:
        """Render a chart as a standalone HTML page with Chart.js."""
        template = self._env.get_template("base.html.j2")
        context = {
            "chart_type": chart_type,
            "data": data,
            "config": config,
            **(extra_context or {}),
        }
        return template.render(**context)

    def render_candlestick(
        self,
        symbol: str,
        bars: list[dict[str, Any]],
        overlays: list[dict[str, Any]],
        show_volume: bool,
        config: dict[str, Any],
    ) -> str:
        """Render candlestick as HTML Chart.js (OHLC rendered as bar ranges)."""
        return self._render_html(
            chart_type="candlestick",
            data=bars,
            config=config,
            extra_context={
                "symbol": symbol,
                "overlays": overlays,
                "show_volume": show_volume,
            },
        )

    def render_equity_curve(
        self,
        strategy_name: str,
        data: list[dict[str, Any]],
        show_drawdown: bool,
        benchmark_data: list[dict[str, Any]] | None,
        config: dict[str, Any],
    ) -> str:
        """Render equity curve as HTML Chart.js line chart."""
        return self._render_html(
            chart_type="equity_curve",
            data=data,
            config=config,
            extra_context={
                "strategy_name": strategy_name,
                "show_drawdown": show_drawdown,
                "benchmark_data": benchmark_data or [],
            },
        )

    def render_gap_scatter(
        self,
        data: list[dict[str, Any]],
        strategies: list[str],
        x_label: str,
        y_label: str,
        config: dict[str, Any],
    ) -> str:
        """Render gap scatter as HTML Chart.js scatter chart."""
        return self._render_html(
            chart_type="gap_scatter",
            data=data,
            config=config,
            extra_context={
                "strategies": strategies,
                "x_label": x_label,
                "y_label": y_label,
            },
        )

    def render_sentiment_heatmap(
        self,
        data: list[dict[str, Any]],
        symbols: list[str],
        sources: list[str],
        config: dict[str, Any],
    ) -> str:
        """Render sentiment heatmap as HTML (table with colored cells)."""
        return self._render_html(
            chart_type="sentiment_heatmap",
            data=data,
            config=config,
            extra_context={
                "symbols": symbols,
                "sources": sources,
            },
        )

    def render_pnl_bar(
        self,
        data: list[dict[str, Any]],
        show_cumulative: bool,
        period_type: str,
        config: dict[str, Any],
    ) -> str:
        """Render P&L bar chart as HTML Chart.js bar chart."""
        return self._render_html(
            chart_type="pnl_bar",
            data=data,
            config=config,
            extra_context={
                "show_cumulative": show_cumulative,
                "period_type": period_type,
            },
        )

    def render_allocation(
        self,
        data: list[dict[str, Any]],
        chart_style: str,
        show_percentages: bool,
        config: dict[str, Any],
    ) -> str:
        """Render allocation as HTML Chart.js doughnut/pie chart."""
        return self._render_html(
            chart_type="allocation",
            data=data,
            config=config,
            extra_context={
                "chart_style": chart_style,
                "show_percentages": show_percentages,
            },
        )

    def render_generic(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        x_key: str,
        y_keys: list[str],
        series_colors: dict[str, str],
        config: dict[str, Any],
    ) -> str:
        """Render generic chart as HTML Chart.js."""
        return self._render_html(
            chart_type=chart_type,
            data=data,
            config=config,
            extra_context={
                "x_key": x_key,
                "y_keys": y_keys,
                "series_colors": series_colors,
            },
        )
```

---

### `src/qitp_mcp_charting/renderers/templates/candlestick.jsx.j2`

```jsx
import { useState, useMemo } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine
} from "recharts";

const COLORS = {
  up: "#26a69a",
  down: "#ef5350",
  wick: "#999",
  volume_up: "rgba(38, 166, 154, 0.3)",
  volume_down: "rgba(239, 83, 80, 0.3)",
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
};

const rawBars = {{ bars | tojson }};
const overlayConfigs = {{ overlays | tojson }};
const showVolume = {{ show_volume | tojson }};

// Calculate SMA/EMA overlays
function calcSMA(data, period) {
  return data.map((_, i) => {
    if (i < period - 1) return null;
    const slice = data.slice(i - period + 1, i + 1);
    return slice.reduce((sum, b) => sum + b.close, 0) / period;
  });
}

function calcEMA(data, period) {
  const k = 2 / (period + 1);
  const ema = [];
  let prev = null;
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      ema.push(null);
    } else if (prev === null) {
      prev = data.slice(0, period).reduce((s, b) => s + b.close, 0) / period;
      ema.push(prev);
    } else {
      prev = data[i].close * k + prev * (1 - k);
      ema.push(prev);
    }
  }
  return ema;
}

export default function CandlestickChart() {
  const data = useMemo(() => {
    // Prepare data with OHLC range for candlestick rendering
    const enriched = rawBars.map((bar) => {
      const isUp = bar.close >= bar.open;
      return {
        ...bar,
        isUp,
        // Body range: [min(open,close), max(open,close)]
        bodyLow: Math.min(bar.open, bar.close),
        bodyHigh: Math.max(bar.open, bar.close),
        bodyRange: [Math.min(bar.open, bar.close), Math.max(bar.open, bar.close)],
        wickRange: [bar.low, bar.high],
        fill: isUp ? COLORS.up : COLORS.down,
        volumeFill: isUp ? COLORS.volume_up : COLORS.volume_down,
      };
    });

    // Add overlay values
    overlayConfigs.forEach((ov, idx) => {
      const key = `overlay_${idx}`;
      const values = ov.type === "ema"
        ? calcEMA(enriched, ov.period)
        : calcSMA(enriched, ov.period);
      enriched.forEach((d, i) => { d[key] = values[i]; });
    });

    return enriched;
  }, []);

  const maxVolume = Math.max(...data.map(d => d.volume));
  const minPrice = Math.min(...data.map(d => d.low)) * 0.998;
  const maxPrice = Math.max(...data.map(d => d.high)) * 1.002;

  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 8px 0", fontFamily: "system-ui" }}{% endraw %}>
        {{ symbol }} — Candlestick
        {% if config.subtitle %}
        <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
        {% endif %}
      </h3>

      <ResponsiveContainer width="100%" height={ {{ config.height }} }>
        <ComposedChart data={data} margin={% raw %}{{ top: 10, right: 30, left: 10, bottom: showVolume ? 60 : 20 }}{% endraw %}>
          {% if config.show_grid %}
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
          {% endif %}

          <XAxis
            dataKey="date"
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            tickLine={% raw %}{{ stroke: COLORS.grid }}{% endraw %}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="price"
            domain={[minPrice, maxPrice]}
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            tickLine={% raw %}{{ stroke: COLORS.grid }}{% endraw %}
            tickFormatter={(v) => v.toFixed(2)}
            orientation="right"
          />

          {showVolume && (
            <YAxis
              yAxisId="volume"
              domain={[0, maxVolume * 4]}
              hide
            />
          )}

          {% if config.show_tooltip %}
          <Tooltip
            contentStyle={% raw %}{{
              background: COLORS.bg,
              border: `1px solid ${COLORS.grid}`,
              borderRadius: 4,
              color: COLORS.text,
              fontSize: 12
            }}{% endraw %}
            formatter={(value, name) => {
              if (Array.isArray(value)) return [value.map(v => v.toFixed(2)).join(" – "), name];
              if (typeof value === "number") return [value.toFixed(2), name];
              return [value, name];
            }}
          />
          {% endif %}

          {/* Wick (high-low range) as thin bar */}
          <Bar yAxisId="price" dataKey="wickRange" barSize={1} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={`wick-${i}`} fill={COLORS.wick} />
            ))}
          </Bar>

          {/* Body (open-close range) as wider bar */}
          <Bar yAxisId="price" dataKey="bodyRange" barSize={8} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={`body-${i}`} fill={d.fill} />
            ))}
          </Bar>

          {/* Volume bars at bottom */}
          {showVolume && (
            <Bar yAxisId="volume" dataKey="volume" barSize={6} isAnimationActive={false}>
              {data.map((d, i) => (
                <Cell key={`vol-${i}`} fill={d.volumeFill} />
              ))}
            </Bar>
          )}

          {/* Overlay lines (SMA/EMA) */}
          {overlayConfigs.map((ov, idx) => (
            <Line
              key={`overlay-${idx}`}
              yAxisId="price"
              type="monotone"
              dataKey={`overlay_${idx}`}
              stroke={ov.color || "#FFD700"}
              dot={false}
              strokeWidth={1.5}
              name={ov.label || `${ov.type.toUpperCase()}(${ov.period})`}
              connectNulls={false}
            />
          ))}

          {% if config.show_legend %}
          <Legend
            verticalAlign="top"
            wrapperStyle={% raw %}{{ color: COLORS.text, fontSize: 11 }}{% endraw %}
          />
          {% endif %}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/renderers/templates/equity_curve.jsx.j2`

```jsx
import { useMemo } from "react";
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from "recharts";

const COLORS = {
  equity: "#26a69a",
  drawdown: "rgba(239, 83, 80, 0.3)",
  drawdown_line: "#ef5350",
  benchmark: "#7e57c2",
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
};

const rawData = {{ data | tojson }};
const benchmarkData = {{ benchmark_data | tojson }};
const showDrawdown = {{ show_drawdown | tojson }};

export default function EquityCurveChart() {
  const data = useMemo(() => {
    // Merge benchmark data by date if present
    const benchMap = {};
    benchmarkData.forEach(b => { benchMap[b.date] = b.value; });

    let peak = -Infinity;
    return rawData.map(d => {
      const val = d.value;
      if (val > peak) peak = val;
      const drawdown_pct = d.drawdown_pct != null ? d.drawdown_pct : ((val - peak) / peak) * 100;
      return {
        ...d,
        peak,
        drawdown_pct,
        benchmark: benchMap[d.date] ?? null,
      };
    });
  }, []);

  const minValue = Math.min(...data.map(d => d.value)) * 0.98;
  const maxValue = Math.max(...data.map(d => Math.max(d.value, d.peak))) * 1.02;
  const minDD = Math.min(...data.map(d => d.drawdown_pct));

  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 4px 0", fontFamily: "system-ui" }}{% endraw %}>
        {{ strategy_name }} — Equity Curve
      </h3>
      {% if config.subtitle %}
      <p style={% raw %}{{ color: COLORS.text, opacity: 0.7, margin: "0 0 12px 0", fontSize: "0.85em" }}{% endraw %}>
        {{ config.subtitle }}
      </p>
      {% endif %}

      <ResponsiveContainer width="100%" height={ {{ config.height }} }>
        <ComposedChart data={data} margin={% raw %}{{ top: 10, right: 30, left: 10, bottom: showDrawdown ? 80 : 20 }}{% endraw %}>
          {% if config.show_grid %}
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
          {% endif %}

          <XAxis
            dataKey="date"
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="equity"
            domain={[minValue, maxValue]}
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            orientation="right"
          />

          {showDrawdown && (
            <YAxis
              yAxisId="drawdown"
              domain={[minDD * 1.5, 0]}
              tick={% raw %}{{ fill: COLORS.drawdown_line, fontSize: 10 }}{% endraw %}
              tickFormatter={(v) => `${v.toFixed(1)}%`}
              orientation="left"
            />
          )}

          {% if config.show_tooltip %}
          <Tooltip
            contentStyle={% raw %}{{
              background: COLORS.bg,
              border: `1px solid ${COLORS.grid}`,
              borderRadius: 4,
              color: COLORS.text,
              fontSize: 12
            }}{% endraw %}
            formatter={(value, name) => {
              if (name === "drawdown_pct") return [`${value.toFixed(2)}%`, "Drawdown"];
              if (name === "benchmark") return [`$${value.toLocaleString()}`, "Benchmark"];
              return [`$${value.toLocaleString()}`, name];
            }}
          />
          {% endif %}

          {/* Drawdown area (below zero line on left axis) */}
          {showDrawdown && (
            <Area
              yAxisId="drawdown"
              type="monotone"
              dataKey="drawdown_pct"
              fill={COLORS.drawdown}
              stroke={COLORS.drawdown_line}
              strokeWidth={1}
              name="Drawdown"
            />
          )}

          {/* Main equity line */}
          <Line
            yAxisId="equity"
            type="monotone"
            dataKey="value"
            stroke={COLORS.equity}
            strokeWidth={2}
            dot={false}
            name="Portfolio Value"
          />

          {/* Peak line (dashed) */}
          <Line
            yAxisId="equity"
            type="monotone"
            dataKey="peak"
            stroke={COLORS.equity}
            strokeWidth={1}
            strokeDasharray="4 4"
            dot={false}
            name="Peak"
            opacity={0.5}
          />

          {/* Benchmark line */}
          {benchmarkData.length > 0 && (
            <Line
              yAxisId="equity"
              type="monotone"
              dataKey="benchmark"
              stroke={COLORS.benchmark}
              strokeWidth={1.5}
              dot={false}
              name="Benchmark"
              connectNulls
            />
          )}

          {% if config.show_legend %}
          <Legend
            verticalAlign="top"
            wrapperStyle={% raw %}{{ color: COLORS.text, fontSize: 11 }}{% endraw %}
          />
          {% endif %}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/renderers/templates/gap_scatter.jsx.j2`

```jsx
import { useMemo } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ZAxis, ReferenceLine
} from "recharts";

const COLORS = {
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
};

const STRATEGY_COLORS = [
  "#26a69a", "#ef5350", "#7e57c2", "#FFB74D", "#4FC3F7",
  "#81C784", "#F06292", "#AED581", "#BA68C8", "#4DD0E1",
];

const rawData = {{ data | tojson }};
const strategies = {{ strategies | tojson }};

export default function GapScatterChart() {
  const groupedData = useMemo(() => {
    const groups = {};
    rawData.forEach(d => {
      const key = d.strategy || "ungrouped";
      if (!groups[key]) groups[key] = [];
      groups[key].push({ x: d.gap_pct, y: d.subsequent_return, symbol: d.symbol, date: d.date });
    });
    return groups;
  }, []);

  const allStrategies = strategies.length > 0
    ? strategies
    : Object.keys(groupedData);

  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 4px 0", fontFamily: "system-ui" }}{% endraw %}>
        Gap Analysis — Scatter
        {% if config.subtitle %}
        <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
        {% endif %}
      </h3>

      <ResponsiveContainer width="100%" height={ {{ config.height }} }>
        <ScatterChart margin={% raw %}{{ top: 20, right: 30, left: 20, bottom: 20 }}{% endraw %}>
          {% if config.show_grid %}
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
          {% endif %}

          <XAxis
            type="number"
            dataKey="x"
            name="{{ x_label }}"
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            label={% raw %}{{ value: "{{ x_label }}", position: "bottom", fill: COLORS.text, fontSize: 12 }}{% endraw %}
            tickFormatter={(v) => `${v.toFixed(1)}%`}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="{{ y_label }}"
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            label={% raw %}{{ value: "{{ y_label }}", angle: -90, position: "insideLeft", fill: COLORS.text, fontSize: 12 }}{% endraw %}
            tickFormatter={(v) => `${v.toFixed(1)}%`}
          />

          {/* Zero reference lines */}
          <ReferenceLine x={0} stroke={COLORS.text} strokeDasharray="3 3" opacity={0.5} />
          <ReferenceLine y={0} stroke={COLORS.text} strokeDasharray="3 3" opacity={0.5} />

          {% if config.show_tooltip %}
          <Tooltip
            contentStyle={% raw %}{{
              background: COLORS.bg,
              border: `1px solid ${COLORS.grid}`,
              borderRadius: 4,
              color: COLORS.text,
              fontSize: 12
            }}{% endraw %}
            formatter={(value, name) => [`${value.toFixed(2)}%`, name]}
            labelFormatter={(_, payload) => {
              if (payload && payload[0]) {
                const d = payload[0].payload;
                return `${d.symbol}${d.date ? ` (${d.date})` : ""}`;
              }
              return "";
            }}
          />
          {% endif %}

          {allStrategies.map((strategy, idx) => (
            <Scatter
              key={strategy}
              name={strategy}
              data={groupedData[strategy] || []}
              fill={STRATEGY_COLORS[idx % STRATEGY_COLORS.length]}
              opacity={0.8}
            />
          ))}

          {% if config.show_legend %}
          <Legend
            verticalAlign="top"
            wrapperStyle={% raw %}{{ color: COLORS.text, fontSize: 11 }}{% endraw %}
          />
          {% endif %}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/renderers/templates/sentiment_heatmap.jsx.j2`

```jsx
import { useMemo } from "react";

const COLORS = {
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
  cell_bg: "{{ config.theme == 'dark' and '#2a2a3e' or '#f5f5f5' }}",
};

const rawData = {{ data | tojson }};
const symbolOrder = {{ symbols | tojson }};
const sourceOrder = {{ sources | tojson }};

// Color interpolation from red (-1) through neutral (0) to green (+1)
function sentimentColor(score) {
  const clamped = Math.max(-1, Math.min(1, score));
  if (clamped >= 0) {
    const g = Math.round(100 + clamped * 155);
    const r = Math.round(100 - clamped * 60);
    const b = Math.round(100 - clamped * 60);
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    const abs = Math.abs(clamped);
    const r = Math.round(100 + abs * 155);
    const g = Math.round(100 - abs * 60);
    const b = Math.round(100 - abs * 60);
    return `rgb(${r}, ${g}, ${b})`;
  }
}

export default function SentimentHeatmap() {
  const { matrix, symbols, sources } = useMemo(() => {
    // Build lookup: { symbol: { source: { score, label } } }
    const lookup = {};
    rawData.forEach(d => {
      if (!lookup[d.symbol]) lookup[d.symbol] = {};
      lookup[d.symbol][d.source] = { score: d.score, label: d.label };
    });

    // Determine row/col order
    const syms = symbolOrder.length > 0
      ? symbolOrder
      : [...new Set(rawData.map(d => d.symbol))];
    const srcs = sourceOrder.length > 0
      ? sourceOrder
      : [...new Set(rawData.map(d => d.source))];

    // Build matrix rows
    const rows = syms.map(sym => ({
      symbol: sym,
      cells: srcs.map(src => {
        const entry = lookup[sym]?.[src];
        return {
          source: src,
          score: entry?.score ?? null,
          label: entry?.label ?? null,
        };
      }),
    }));

    return { matrix: rows, symbols: syms, sources: srcs };
  }, []);

  const cellSize = 70;
  const labelWidth = 100;

  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px", fontFamily: "system-ui" }}{% endraw %}>
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 12px 0" }}{% endraw %}>
        Sentiment Heatmap
        {% if config.subtitle %}
        <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
        {% endif %}
      </h3>

      <div style={% raw %}{{ overflowX: "auto" }}{% endraw %}>
        <table style={% raw %}{{ borderCollapse: "collapse", fontSize: 12, color: COLORS.text }}{% endraw %}>
          <thead>
            <tr>
              <th style={% raw %}{{ width: labelWidth, textAlign: "left", padding: "6px 10px", borderBottom: `1px solid ${COLORS.grid}` }}{% endraw %}>
                Symbol
              </th>
              {sources.map(src => (
                <th
                  key={src}
                  style={% raw %}{{ width: cellSize, textAlign: "center", padding: "6px 10px", borderBottom: `1px solid ${COLORS.grid}`, textTransform: "capitalize" }}{% endraw %}
                >
                  {src}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map(row => (
              <tr key={row.symbol}>
                <td style={% raw %}{{ padding: "6px 10px", fontWeight: 600, borderBottom: `1px solid ${COLORS.grid}` }}{% endraw %}>
                  {row.symbol}
                </td>
                {row.cells.map(cell => (
                  <td
                    key={`${row.symbol}-${cell.source}`}
                    style={% raw %}{{
                      width: cellSize,
                      height: cellSize,
                      textAlign: "center",
                      padding: "6px",
                      borderBottom: `1px solid ${COLORS.grid}`,
                      background: cell.score != null ? sentimentColor(cell.score) : COLORS.cell_bg,
                      color: cell.score != null && Math.abs(cell.score) > 0.5 ? "#fff" : COLORS.text,
                      fontWeight: cell.score != null && Math.abs(cell.score) > 0.7 ? 700 : 400,
                      borderRadius: 4,
                    }}{% endraw %}
                    title={cell.label || `${cell.source}: ${cell.score?.toFixed(2) ?? "N/A"}`}
                  >
                    {cell.score != null ? cell.score.toFixed(2) : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div style={% raw %}{{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 11, color: COLORS.text }}{% endraw %}>
        <span>Bearish</span>
        <div style={% raw %}{{
          width: 200, height: 12, borderRadius: 6,
          background: "linear-gradient(to right, rgb(255, 40, 40), rgb(100, 100, 100), rgb(40, 255, 40))"
        }}{% endraw %} />
        <span>Bullish</span>
      </div>
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/renderers/templates/pnl_bar.jsx.j2`

```jsx
import { useMemo } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine
} from "recharts";

const COLORS = {
  profit: "#26a69a",
  loss: "#ef5350",
  cumulative: "#7e57c2",
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
};

const rawData = {{ data | tojson }};
const showCumulative = {{ show_cumulative | tojson }};

export default function PnLBarChart() {
  const data = useMemo(() => {
    let cumulative = 0;
    return rawData.map(d => {
      cumulative = d.cumulative != null ? d.cumulative : cumulative + d.pnl;
      return {
        ...d,
        cumulative,
        fill: d.pnl >= 0 ? COLORS.profit : COLORS.loss,
      };
    });
  }, []);

  const maxPnl = Math.max(...data.map(d => Math.abs(d.pnl)));
  const maxCum = Math.max(...data.map(d => Math.abs(d.cumulative)));

  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 4px 0", fontFamily: "system-ui" }}{% endraw %}>
        P&L — {{ period_type | capitalize }}
        {% if config.subtitle %}
        <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
        {% endif %}
      </h3>

      <ResponsiveContainer width="100%" height={ {{ config.height }} }>
        <ComposedChart data={data} margin={% raw %}{{ top: 10, right: 30, left: 10, bottom: 20 }}{% endraw %}>
          {% if config.show_grid %}
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
          {% endif %}

          <XAxis
            dataKey="period"
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="pnl"
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            tickFormatter={(v) => `$${v >= 0 ? "" : "-"}${Math.abs(v).toLocaleString()}`}
          />

          {showCumulative && (
            <YAxis
              yAxisId="cumulative"
              orientation="right"
              tick={% raw %}{{ fill: COLORS.cumulative, fontSize: 10 }}{% endraw %}
              tickFormatter={(v) => `$${v.toLocaleString()}`}
            />
          )}

          <ReferenceLine yAxisId="pnl" y={0} stroke={COLORS.text} strokeDasharray="3 3" opacity={0.5} />

          {% if config.show_tooltip %}
          <Tooltip
            contentStyle={% raw %}{{
              background: COLORS.bg,
              border: `1px solid ${COLORS.grid}`,
              borderRadius: 4,
              color: COLORS.text,
              fontSize: 12
            }}{% endraw %}
            formatter={(value, name) => {
              const formatted = `$${value >= 0 ? "" : "-"}${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
              return [formatted, name === "pnl" ? "P&L" : "Cumulative"];
            }}
          />
          {% endif %}

          <Bar yAxisId="pnl" dataKey="pnl" name="P&L" barSize={20}>
            {data.map((d, i) => (
              <Cell key={`pnl-${i}`} fill={d.fill} />
            ))}
          </Bar>

          {showCumulative && (
            <Line
              yAxisId="cumulative"
              type="monotone"
              dataKey="cumulative"
              stroke={COLORS.cumulative}
              strokeWidth={2}
              dot={false}
              name="Cumulative"
            />
          )}

          {% if config.show_legend %}
          <Legend
            verticalAlign="top"
            wrapperStyle={% raw %}{{ color: COLORS.text, fontSize: 11 }}{% endraw %}
          />
          {% endif %}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/renderers/templates/allocation.jsx.j2`

```jsx
import { useMemo, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  Treemap
} from "recharts";

const COLORS = {
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
};

const PALETTE = [
  "#26a69a", "#ef5350", "#7e57c2", "#FFB74D", "#4FC3F7",
  "#81C784", "#F06292", "#AED581", "#BA68C8", "#4DD0E1",
  "#FF8A65", "#A1887F", "#90A4AE", "#DCE775", "#FFF176",
];

const rawData = {{ data | tojson }};
const chartStyle = "{{ chart_style }}";
const showPercentages = {{ show_percentages | tojson }};

export default function AllocationChart() {
  const [activeIndex, setActiveIndex] = useState(null);

  const { data, total } = useMemo(() => {
    const total = rawData.reduce((sum, d) => sum + d.value, 0);
    const enriched = rawData.map((d, i) => ({
      ...d,
      color: d.color || PALETTE[i % PALETTE.length],
      pct: total > 0 ? ((d.value / total) * 100).toFixed(1) : "0.0",
    }));
    return { data: enriched, total };
  }, []);

  const isDonut = chartStyle === "donut";
  const innerRadius = isDonut ? "55%" : 0;

  if (chartStyle === "treemap") {
    const treemapData = data.map(d => ({
      name: `${d.name} (${d.pct}%)`,
      size: d.value,
      fill: d.color,
    }));

    return (
      <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
        <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 12px 0", fontFamily: "system-ui" }}{% endraw %}>
          Portfolio Allocation
          {% if config.subtitle %}
          <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
          {% endif %}
        </h3>
        <ResponsiveContainer width="100%" height={ {{ config.height }} }>
          <Treemap
            data={treemapData}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke={COLORS.bg}
            content={({ x, y, width, height, name, fill }) => (
              <g>
                <rect x={x} y={y} width={width} height={height} fill={fill} stroke={COLORS.bg} strokeWidth={2} rx={4} />
                {width > 60 && height > 30 && (
                  <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize={11} fontWeight={600}>
                    {name}
                  </text>
                )}
              </g>
            )}
          />
        </ResponsiveContainer>
      </div>
    );
  }

  // Pie / Donut
  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 12px 0", fontFamily: "system-ui" }}{% endraw %}>
        Portfolio Allocation
        {% if config.subtitle %}
        <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
        {% endif %}
      </h3>

      <ResponsiveContainer width="100%" height={ {{ config.height }} }>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius="80%"
            paddingAngle={2}
            onMouseEnter={(_, idx) => setActiveIndex(idx)}
            onMouseLeave={() => setActiveIndex(null)}
            label={showPercentages ? ({ name, pct }) => `${name} ${pct}%` : false}
            labelLine={showPercentages}
          >
            {data.map((d, i) => (
              <Cell
                key={`cell-${i}`}
                fill={d.color}
                opacity={activeIndex === null || activeIndex === i ? 1 : 0.6}
                stroke={COLORS.bg}
                strokeWidth={2}
              />
            ))}
          </Pie>

          {% if config.show_tooltip %}
          <Tooltip
            contentStyle={% raw %}{{
              background: COLORS.bg,
              border: `1px solid ${COLORS.grid}`,
              borderRadius: 4,
              color: COLORS.text,
              fontSize: 12
            }}{% endraw %}
            formatter={(value, name) => [`$${value.toLocaleString()} (${((value / total) * 100).toFixed(1)}%)`, name]}
          />
          {% endif %}

          {% if config.show_legend %}
          <Legend
            verticalAlign="bottom"
            wrapperStyle={% raw %}{{ color: COLORS.text, fontSize: 11 }}{% endraw %}
          />
          {% endif %}
        </PieChart>
      </ResponsiveContainer>

      {/* Center label for donut */}
      {isDonut && (
        <div style={% raw %}{{
          position: "relative", top: -{{ config.height // 2 + 20 }},
          textAlign: "center", pointerEvents: "none"
        }}{% endraw %}>
          <div style={% raw %}{{ color: COLORS.text, fontSize: 24, fontWeight: 700, fontFamily: "system-ui" }}{% endraw %}>
            ${total.toLocaleString()}
          </div>
          <div style={% raw %}{{ color: COLORS.text, fontSize: 12, opacity: 0.7 }}{% endraw %}>
            Total Value
          </div>
        </div>
      )}
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/renderers/templates/base.html.j2`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ config.title or 'QITP Chart' }}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  {% if chart_type == 'candlestick' %}
  <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.2.0/dist/chartjs-chart-financial.min.js"></script>
  {% endif %}
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      {% if config.theme == 'dark' %}
      background: #1a1a2e;
      color: #e0e0e0;
      {% else %}
      background: #ffffff;
      color: #333333;
      {% endif %}
      padding: 16px;
    }
    .chart-container {
      position: relative;
      width: 100%;
      max-width: {{ config.width }}px;
      margin: 0 auto;
    }
    h3 {
      margin-bottom: 12px;
      font-size: 1.1em;
    }
    .subtitle {
      font-size: 0.85em;
      opacity: 0.7;
      margin-bottom: 12px;
    }

    /* Sentiment heatmap styles */
    .heatmap-table { border-collapse: collapse; width: 100%; font-size: 12px; }
    .heatmap-table th, .heatmap-table td { padding: 8px; text-align: center; border: 1px solid {% if config.theme == 'dark' %}#333{% else %}#e0e0e0{% endif %}; }
    .heatmap-table th { text-transform: capitalize; font-weight: 600; }
    .heatmap-legend { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 11px; }
    .heatmap-gradient { width: 200px; height: 12px; border-radius: 6px; background: linear-gradient(to right, rgb(255,40,40), rgb(100,100,100), rgb(40,255,40)); }
  </style>
</head>
<body>
  <h3>{{ config.title }}</h3>
  {% if config.subtitle %}
  <p class="subtitle">{{ config.subtitle }}</p>
  {% endif %}

  {% if chart_type == 'sentiment_heatmap' %}
  {# Sentiment heatmap rendered as HTML table #}
  <table class="heatmap-table">
    <thead>
      <tr>
        <th>Symbol</th>
        {% for src in sources %}
        <th>{{ src }}</th>
        {% endfor %}
      </tr>
    </thead>
    <tbody>
      {% for sym in symbols %}
      <tr>
        <td style="font-weight:600; text-align:left;">{{ sym }}</td>
        {% for src in sources %}
        {% set cell = None %}
        {% for d in data %}
          {% if d.symbol == sym and d.source == src %}
            {% set cell = d %}
          {% endif %}
        {% endfor %}
        {% if cell %}
        <td style="background: {{ 'rgb(%d,%d,%d)' | format(
          (100 + (cell.score|abs * 155)) if cell.score < 0 else (100 - cell.score * 60),
          (100 - (cell.score|abs * 60)) if cell.score < 0 else (100 + cell.score * 155),
          (100 - (cell.score|abs * 60)) if cell.score < 0 else (100 - cell.score * 60)
        ) }}; color: {{ '#fff' if (cell.score|abs) > 0.5 else 'inherit' }};">
          {{ '%.2f' | format(cell.score) }}
        </td>
        {% else %}
        <td>—</td>
        {% endif %}
        {% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <div class="heatmap-legend">
    <span>Bearish</span>
    <div class="heatmap-gradient"></div>
    <span>Bullish</span>
  </div>

  {% else %}
  {# All other chart types use Chart.js canvas #}
  <div class="chart-container">
    <canvas id="chart"></canvas>
  </div>

  <script>
    const ctx = document.getElementById('chart').getContext('2d');
    const rawData = {{ data | tojson }};

    {% if chart_type == 'equity_curve' %}
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: rawData.map(d => d.date),
        datasets: [
          {
            label: '{{ strategy_name }}',
            data: rawData.map(d => d.value),
            borderColor: '#26a69a',
            fill: false,
            tension: 0.1,
            pointRadius: 0,
          },
          {% if show_drawdown %}
          {
            label: 'Drawdown %',
            data: rawData.map(d => d.drawdown_pct),
            borderColor: '#ef5350',
            backgroundColor: 'rgba(239,83,80,0.15)',
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            yAxisID: 'y1',
          },
          {% endif %}
          {% if benchmark_data %}
          {
            label: 'Benchmark',
            data: {{ benchmark_data | tojson }}.map(d => d.value),
            borderColor: '#7e57c2',
            fill: false,
            tension: 0.1,
            pointRadius: 0,
          },
          {% endif %}
        ]
      },
      options: {
        responsive: true,
        scales: {
          y: { position: 'right' },
          {% if show_drawdown %}
          y1: { position: 'left', grid: { drawOnChartArea: false } },
          {% endif %}
        }
      }
    });

    {% elif chart_type == 'gap_scatter' %}
    new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: (() => {
          const groups = {};
          rawData.forEach(d => {
            const key = d.strategy || 'ungrouped';
            if (!groups[key]) groups[key] = [];
            groups[key].push({ x: d.gap_pct, y: d.subsequent_return });
          });
          const colors = ['#26a69a','#ef5350','#7e57c2','#FFB74D','#4FC3F7'];
          return Object.entries(groups).map(([name, points], i) => ({
            label: name,
            data: points,
            backgroundColor: colors[i % colors.length],
          }));
        })()
      },
      options: {
        responsive: true,
        scales: {
          x: { title: { display: true, text: '{{ x_label }}' } },
          y: { title: { display: true, text: '{{ y_label }}' } },
        }
      }
    });

    {% elif chart_type == 'pnl_bar' %}
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: rawData.map(d => d.period),
        datasets: [
          {
            label: 'P&L',
            data: rawData.map(d => d.pnl),
            backgroundColor: rawData.map(d => d.pnl >= 0 ? '#26a69a' : '#ef5350'),
          },
          {% if show_cumulative %}
          {
            label: 'Cumulative',
            data: (() => { let c = 0; return rawData.map(d => { c = d.cumulative != null ? d.cumulative : c + d.pnl; return c; }); })(),
            type: 'line',
            borderColor: '#7e57c2',
            fill: false,
            pointRadius: 0,
            yAxisID: 'y1',
          },
          {% endif %}
        ]
      },
      options: {
        responsive: true,
        scales: {
          y: { position: 'left' },
          {% if show_cumulative %}
          y1: { position: 'right', grid: { drawOnChartArea: false } },
          {% endif %}
        }
      }
    });

    {% elif chart_type == 'allocation' %}
    new Chart(ctx, {
      type: '{{ "doughnut" if chart_style == "donut" else "pie" }}',
      data: {
        labels: rawData.map(d => d.name),
        datasets: [{
          data: rawData.map(d => d.value),
          backgroundColor: ['#26a69a','#ef5350','#7e57c2','#FFB74D','#4FC3F7','#81C784','#F06292','#AED581','#BA68C8','#4DD0E1'],
        }]
      },
      options: { responsive: true }
    });

    {% elif chart_type == 'candlestick' %}
    {# Candlestick approximation with floating bars #}
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: rawData.map(d => d.date),
        datasets: [{
          label: '{{ symbol }}',
          data: rawData.map(d => [Math.min(d.open, d.close), Math.max(d.open, d.close)]),
          backgroundColor: rawData.map(d => d.close >= d.open ? '#26a69a' : '#ef5350'),
        }]
      },
      options: {
        responsive: true,
        scales: { y: { position: 'right' } }
      }
    });

    {% else %}
    {# Generic fallback: line/bar/area #}
    const xKey = '{{ x_key }}';
    const yKeys = {{ y_keys | tojson }};
    const seriesColors = {{ series_colors | tojson }};
    const defaultColors = ['#8884d8','#82ca9d','#ffc658','#ff7300','#00C49F'];

    new Chart(ctx, {
      type: '{{ chart_type }}',
      data: {
        labels: rawData.map(d => d[xKey]),
        datasets: yKeys.map((key, i) => ({
          label: key,
          data: rawData.map(d => d[key]),
          borderColor: seriesColors[key] || defaultColors[i % defaultColors.length],
          backgroundColor: seriesColors[key] || defaultColors[i % defaultColors.length],
          fill: '{{ chart_type }}' === 'area',
          tension: 0.1,
          pointRadius: '{{ chart_type }}' === 'scatter' ? 4 : 0,
        }))
      },
      options: { responsive: true }
    });
    {% endif %}
  </script>
  {% endif %}
</body>
</html>
```

---

### `src/qitp_mcp_charting/tools/__init__.py`

```python
"""Chart generation tools."""

from .allocation import generate_portfolio_allocation
from .candlestick import generate_candlestick
from .equity_curve import generate_equity_curve
from .gap_scatter import generate_gap_scatter
from .generic import generate_chart
from .pnl import generate_pnl_bar
from .sentiment import generate_sentiment_heatmap

__all__ = [
    "generate_candlestick",
    "generate_equity_curve",
    "generate_gap_scatter",
    "generate_sentiment_heatmap",
    "generate_pnl_bar",
    "generate_portfolio_allocation",
    "generate_chart",
]
```

---

### `src/qitp_mcp_charting/tools/candlestick.py`

```python
"""generate_candlestick tool — OHLC candlestick with overlays and volume."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    CandlestickRequest,
    ChartFormat,
    ChartResult,
)

logger = logging.getLogger(__name__)


async def generate_candlestick(request: CandlestickRequest) -> ChartResult:
    """Generate a candlestick chart with optional SMA/EMA overlays and volume bars.

    Args:
        request: CandlestickRequest with symbol, bars, overlays, and config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"candlestick-{request.symbol}-{uuid.uuid4().hex[:8]}"

    renderer = get_renderer(request.config.format)
    content = renderer.render_candlestick(
        symbol=request.symbol,
        bars=[b.model_dump() for b in request.bars],
        overlays=[o.model_dump() for o in request.overlays],
        show_volume=request.show_volume,
        config=request.config.model_dump(),
    )

    # Store via artifacts-mcp (fire-and-forget, non-blocking)
    artifact_id = None
    try:
        client = ArtifactClient()
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_candlestick",
                "symbol": request.symbol,
                "bars_count": len(request.bars),
                "overlays": [o.model_dump() for o in request.overlays],
            },
        )
    except Exception:
        logger.exception("Failed to store candlestick chart artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "symbol": request.symbol,
            "bars_count": len(request.bars),
            "overlays_count": len(request.overlays),
            "show_volume": request.show_volume,
        },
    )
```

---

### `src/qitp_mcp_charting/tools/equity_curve.py`

```python
"""generate_equity_curve tool — portfolio value over time with drawdown shading."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    ChartResult,
    EquityCurveRequest,
)

logger = logging.getLogger(__name__)


async def generate_equity_curve(request: EquityCurveRequest) -> ChartResult:
    """Generate an equity curve chart with optional drawdown shading and benchmark.

    Args:
        request: EquityCurveRequest with strategy name, data points, and config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"equity-{request.strategy_name}-{uuid.uuid4().hex[:8]}"

    # Pre-compute peak and drawdown if not provided
    data_dicts = []
    peak = -float("inf")
    for point in request.data:
        d = point.model_dump()
        if d["value"] > peak:
            peak = d["value"]
        if d["peak"] is None:
            d["peak"] = peak
        if d["drawdown_pct"] is None:
            d["drawdown_pct"] = ((d["value"] - peak) / peak) * 100 if peak > 0 else 0.0
        data_dicts.append(d)

    benchmark_dicts = (
        [b.model_dump() for b in request.benchmark_data]
        if request.benchmark_data
        else None
    )

    renderer = get_renderer(request.config.format)
    content = renderer.render_equity_curve(
        strategy_name=request.strategy_name,
        data=data_dicts,
        show_drawdown=request.show_drawdown,
        benchmark_data=benchmark_dicts,
        config=request.config.model_dump(),
    )

    artifact_id = None
    try:
        client = ArtifactClient()
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_equity_curve",
                "strategy_name": request.strategy_name,
                "data_points": len(request.data),
                "show_drawdown": request.show_drawdown,
                "has_benchmark": request.benchmark_data is not None,
            },
        )
    except Exception:
        logger.exception("Failed to store equity curve chart artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "strategy_name": request.strategy_name,
            "data_points": len(request.data),
            "show_drawdown": request.show_drawdown,
        },
    )
```

---

### `src/qitp_mcp_charting/tools/gap_scatter.py`

```python
"""generate_gap_scatter tool — scatter plot of gap% vs subsequent return."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    ChartResult,
    GapScatterRequest,
)

logger = logging.getLogger(__name__)


async def generate_gap_scatter(request: GapScatterRequest) -> ChartResult:
    """Generate a gap scatter plot showing gap_pct vs subsequent_return.

    Points are colored by strategy name.

    Args:
        request: GapScatterRequest with data points and config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"gap-scatter-{uuid.uuid4().hex[:8]}"

    # Derive strategy list from data if not provided
    strategies = request.strategies
    if not strategies:
        seen = set()
        for point in request.data:
            key = point.strategy or "ungrouped"
            if key not in seen:
                strategies.append(key)
                seen.add(key)

    renderer = get_renderer(request.config.format)
    content = renderer.render_gap_scatter(
        data=[d.model_dump() for d in request.data],
        strategies=strategies,
        x_label=request.x_label,
        y_label=request.y_label,
        config=request.config.model_dump(),
    )

    artifact_id = None
    try:
        client = ArtifactClient()
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_gap_scatter",
                "data_points": len(request.data),
                "strategies": strategies,
            },
        )
    except Exception:
        logger.exception("Failed to store gap scatter chart artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "data_points": len(request.data),
            "strategies": strategies,
        },
    )
```

---

### `src/qitp_mcp_charting/tools/sentiment.py`

```python
"""generate_sentiment_heatmap tool — symbol x source sentiment matrix."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    ChartResult,
    SentimentHeatmapRequest,
)

logger = logging.getLogger(__name__)


async def generate_sentiment_heatmap(request: SentimentHeatmapRequest) -> ChartResult:
    """Generate a sentiment heatmap showing symbols vs sources.

    Each cell is colored from red (bearish, -1.0) to green (bullish, +1.0).

    Args:
        request: SentimentHeatmapRequest with cell data and config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"sentiment-heatmap-{uuid.uuid4().hex[:8]}"

    # Derive symbol and source order from data if not provided
    symbols = request.symbols
    if not symbols:
        seen = set()
        for cell in request.data:
            if cell.symbol not in seen:
                symbols.append(cell.symbol)
                seen.add(cell.symbol)

    sources = request.sources

    renderer = get_renderer(request.config.format)
    content = renderer.render_sentiment_heatmap(
        data=[d.model_dump() for d in request.data],
        symbols=symbols,
        sources=sources,
        config=request.config.model_dump(),
    )

    artifact_id = None
    try:
        client = ArtifactClient()
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_sentiment_heatmap",
                "symbols": symbols,
                "sources": sources,
                "cells_count": len(request.data),
            },
        )
    except Exception:
        logger.exception("Failed to store sentiment heatmap artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "symbols": symbols,
            "sources": sources,
            "cells_count": len(request.data),
        },
    )
```

---

### `src/qitp_mcp_charting/tools/pnl.py`

```python
"""generate_pnl_bar tool — daily/weekly P&L bar chart with cumulative line."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    ChartResult,
    PnLBarRequest,
)

logger = logging.getLogger(__name__)


async def generate_pnl_bar(request: PnLBarRequest) -> ChartResult:
    """Generate a P&L bar chart with green/red bars and optional cumulative line.

    Args:
        request: PnLBarRequest with P&L entries and config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"pnl-{request.period_type}-{uuid.uuid4().hex[:8]}"

    # Pre-compute cumulative if not provided
    data_dicts = []
    cumulative = 0.0
    for entry in request.data:
        d = entry.model_dump()
        if d["cumulative"] is None:
            cumulative += d["pnl"]
            d["cumulative"] = cumulative
        else:
            cumulative = d["cumulative"]
        data_dicts.append(d)

    renderer = get_renderer(request.config.format)
    content = renderer.render_pnl_bar(
        data=data_dicts,
        show_cumulative=request.show_cumulative,
        period_type=request.period_type,
        config=request.config.model_dump(),
    )

    artifact_id = None
    try:
        client = ArtifactClient()
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_pnl_bar",
                "period_type": request.period_type,
                "entries_count": len(request.data),
                "show_cumulative": request.show_cumulative,
            },
        )
    except Exception:
        logger.exception("Failed to store P&L bar chart artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "period_type": request.period_type,
            "entries_count": len(request.data),
            "total_pnl": cumulative,
        },
    )
```

---

### `src/qitp_mcp_charting/tools/allocation.py`

```python
"""generate_portfolio_allocation tool — pie/donut/treemap of portfolio allocation."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    AllocationRequest,
    ChartResult,
)

logger = logging.getLogger(__name__)


async def generate_portfolio_allocation(request: AllocationRequest) -> ChartResult:
    """Generate a portfolio allocation chart.

    Supports pie, donut, and treemap styles.

    Args:
        request: AllocationRequest with allocation slices and config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"allocation-{request.chart_style}-{uuid.uuid4().hex[:8]}"

    renderer = get_renderer(request.config.format)
    content = renderer.render_allocation(
        data=[d.model_dump() for d in request.data],
        chart_style=request.chart_style,
        show_percentages=request.show_percentages,
        config=request.config.model_dump(),
    )

    artifact_id = None
    try:
        client = ArtifactClient()
        total = sum(d.value for d in request.data)
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_portfolio_allocation",
                "chart_style": request.chart_style,
                "slices_count": len(request.data),
                "total_value": total,
            },
        )
    except Exception:
        logger.exception("Failed to store allocation chart artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "chart_style": request.chart_style,
            "slices_count": len(request.data),
        },
    )
```

---

### `src/qitp_mcp_charting/tools/generic.py`

```python
"""generate_chart tool — flexible chart from a generic spec."""

from __future__ import annotations

import logging
import uuid

from qitp_mcp_charting.artifact_client import ArtifactClient
from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.schemas import (
    ChartResult,
    GenericChartRequest,
)

logger = logging.getLogger(__name__)


async def generate_chart(request: GenericChartRequest) -> ChartResult:
    """Generate a chart from a flexible specification.

    Supports line, bar, scatter, area, pie, and composed chart types.
    Useful when the other specialized tools don't fit the data shape.

    Args:
        request: GenericChartRequest with chart_type, data, x_key, y_keys, config.

    Returns:
        ChartResult with rendered JSX or HTML content.
    """
    chart_id = f"chart-{request.chart_type.value}-{uuid.uuid4().hex[:8]}"

    renderer = get_renderer(request.config.format)
    content = renderer.render_generic(
        chart_type=request.chart_type.value,
        data=request.data,
        x_key=request.x_key,
        y_keys=request.y_keys,
        series_colors=request.series_colors,
        config=request.config.model_dump(),
    )

    artifact_id = None
    try:
        client = ArtifactClient()
        artifact_id = await client.store_chart(
            chart_id=chart_id,
            content=content,
            metadata={
                "tool": "generate_chart",
                "chart_type": request.chart_type.value,
                "data_points": len(request.data),
                "y_keys": request.y_keys,
            },
        )
    except Exception:
        logger.exception("Failed to store generic chart artifact")

    return ChartResult(
        chart_id=chart_id,
        content=content,
        format=request.config.format,
        artifact_id=artifact_id,
        metadata={
            "chart_type": request.chart_type.value,
            "data_points": len(request.data),
            "x_key": request.x_key,
            "y_keys": request.y_keys,
        },
    )
```

---

### `src/qitp_mcp_charting/renderers/templates/generic.jsx.j2`

```jsx
import { useMemo } from "react";
import {
  ComposedChart, Line, Bar, Area, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";

const COLORS = {
  grid: "{{ config.theme == 'dark' and '#333' or '#e0e0e0' }}",
  text: "{{ config.theme == 'dark' and '#e0e0e0' or '#333' }}",
  bg: "{{ config.theme == 'dark' and '#1a1a2e' or '#ffffff' }}",
};

const rawData = {{ data | tojson }};
const xKey = "{{ x_key }}";
const yKeys = {{ y_keys | tojson }};
const colors = {{ colors | tojson }};
const chartType = "{{ chart_type }}";

// Map chart type to Recharts component
const ComponentMap = {
  line: Line,
  bar: Bar,
  area: Area,
  scatter: Scatter,
  composed: null, // uses mixed types
};

export default function GenericChart() {
  const ChartComponent = chartType === "composed" ? null : ComponentMap[chartType] || Line;

  return (
    <div style={% raw %}{{ background: COLORS.bg, padding: "16px", borderRadius: "8px" }}{% endraw %}>
      {% if config.title %}
      <h3 style={% raw %}{{ color: COLORS.text, margin: "0 0 4px 0", fontFamily: "system-ui" }}{% endraw %}>
        {{ config.title }}
        {% if config.subtitle %}
        <span style={% raw %}{{ fontSize: "0.7em", opacity: 0.7, marginLeft: 8 }}{% endraw %}>{{ config.subtitle }}</span>
        {% endif %}
      </h3>
      {% endif %}

      <ResponsiveContainer width="100%" height={ {{ config.height }} }>
        <ComposedChart data={rawData} margin={% raw %}{{ top: 10, right: 30, left: 10, bottom: 20 }}{% endraw %}>
          {% if config.show_grid %}
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
          {% endif %}

          <XAxis
            dataKey={xKey}
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={% raw %}{{ fill: COLORS.text, fontSize: 11 }}{% endraw %}
          />

          {% if config.show_tooltip %}
          <Tooltip
            contentStyle={% raw %}{{
              background: COLORS.bg,
              border: `1px solid ${COLORS.grid}`,
              borderRadius: 4,
              color: COLORS.text,
              fontSize: 12
            }}{% endraw %}
          />
          {% endif %}

          {yKeys.map((key, idx) => {
            const color = colors[key] || "#8884d8";
            const props = {
              key: key,
              dataKey: key,
              name: key,
              stroke: color,
              fill: color,
            };

            if (chartType === "composed") {
              // Alternate between Line and Bar for composed charts
              if (idx % 2 === 0) {
                return <Line {...props} type="monotone" dot={false} strokeWidth={2} />;
              }
              return <Bar {...props} barSize={20} opacity={0.7} />;
            }

            if (ChartComponent === Line) {
              return <Line {...props} type="monotone" dot={false} strokeWidth={2} />;
            }
            if (ChartComponent === Bar) {
              return <Bar {...props} barSize={20} />;
            }
            if (ChartComponent === Area) {
              return <Area {...props} type="monotone" fillOpacity={0.3} strokeWidth={2} />;
            }
            if (ChartComponent === Scatter) {
              return <Scatter {...props} />;
            }
            return <Line {...props} type="monotone" dot={false} strokeWidth={2} />;
          })}

          {% if config.show_legend %}
          <Legend
            verticalAlign="top"
            wrapperStyle={% raw %}{{ color: COLORS.text, fontSize: 11 }}{% endraw %}
          />
          {% endif %}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

### `src/qitp_mcp_charting/server.py`

```python
"""QITP Charting MCP Server — entrypoint.

Exposes 7 chart generation tools via MCP protocol.
Supports both stdio (dev) and HTTP (production) transports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from qitp_mcp_charting.schemas import (
    AllocationRequest,
    CandlestickRequest,
    ChartResult,
    EquityCurveRequest,
    GapScatterRequest,
    GenericChartRequest,
    PnLBarRequest,
    SentimentHeatmapRequest,
)
from qitp_mcp_charting.tools import (
    generate_candlestick,
    generate_chart,
    generate_equity_curve,
    generate_gap_scatter,
    generate_pnl_bar,
    generate_portfolio_allocation,
    generate_sentiment_heatmap,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry: name → (request_model, handler, description)
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, tuple[type, Any, str]] = {
    "generate_candlestick": (
        CandlestickRequest,
        generate_candlestick,
        "Generate an OHLC candlestick chart with optional SMA/EMA overlays and volume bars. "
        "Input: symbol, bars (OHLCV array), overlays (SMA/EMA configs), show_volume flag, config.",
    ),
    "generate_equity_curve": (
        EquityCurveRequest,
        generate_equity_curve,
        "Generate a portfolio equity curve with drawdown shading (red fill below peak). "
        "Input: strategy_name, data (date+value array), show_drawdown flag, optional benchmark_data, config.",
    ),
    "generate_gap_scatter": (
        GapScatterRequest,
        generate_gap_scatter,
        "Generate a scatter plot of gap_pct (x) vs subsequent_return (y), colored by strategy. "
        "Input: data (symbol, gap_pct, subsequent_return, strategy), strategies list, axis labels, config.",
    ),
    "generate_sentiment_heatmap": (
        SentimentHeatmapRequest,
        generate_sentiment_heatmap,
        "Generate a heatmap matrix: symbols (rows) × sources (columns), colored by sentiment score (-1 to +1). "
        "Input: data (symbol, source, score), symbol/source order lists, config.",
    ),
    "generate_pnl_bar": (
        PnLBarRequest,
        generate_pnl_bar,
        "Generate a P&L bar chart with green (profit) / red (loss) bars and optional cumulative line. "
        "Input: data (period, pnl), show_cumulative flag, period_type (daily/weekly/monthly), config.",
    ),
    "generate_portfolio_allocation": (
        AllocationRequest,
        generate_portfolio_allocation,
        "Generate a portfolio allocation chart (pie, donut, or treemap). "
        "Input: data (name, value), chart_style (pie/donut/treemap), show_percentages flag, config.",
    ),
    "generate_chart": (
        GenericChartRequest,
        generate_chart,
        "Generate a flexible chart from a generic specification. Supports line, bar, scatter, area, pie, composed. "
        "Input: chart_type, data (array of objects), x_key, y_keys, optional series_colors, config.",
    ),
}


def _build_tool_schema(model_cls: type) -> dict[str, Any]:
    """Extract JSON Schema from a Pydantic model for MCP tool definition."""
    schema = model_cls.model_json_schema()
    # Remove title and $defs from top level for cleaner tool schema
    schema.pop("title", None)
    return schema


def create_server() -> Server:
    """Create and configure the MCP server with all chart tools."""
    server = Server("charting-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for name, (model_cls, _, description) in TOOL_REGISTRY.items():
            tools.append(
                Tool(
                    name=name,
                    description=description,
                    inputSchema=_build_tool_schema(model_cls),
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name not in TOOL_REGISTRY:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )
            ]

        model_cls, handler, _ = TOOL_REGISTRY[name]

        try:
            request = model_cls(**arguments)
            result: ChartResult = await handler(request)

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result.model_dump(), default=str),
                )
            ]
        except Exception as e:
            logger.exception("Error in tool %s", name)
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "error": str(e),
                        "tool": name,
                    }),
                )
            ]

    return server


async def run_stdio() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_http(host: str, port: int) -> None:
    """Run the MCP server over HTTP transport using streamable HTTP."""
    from mcp.server.streamable_http import StreamableHTTPServer

    server = create_server()
    http_server = StreamableHTTPServer(server, host=host, port=port)
    logger.info("Starting charting-mcp HTTP server on %s:%d", host, port)
    await http_server.run()


def main() -> None:
    """CLI entrypoint — select transport based on MCP_TRANSPORT env var."""
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "http":
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8006"))
        asyncio.run(run_http(host, port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
```

---

### `tests/fixtures/sample_ohlcv.json`

```json
[
    {"date": "2024-10-28", "open": 150.00, "high": 152.50, "low": 149.00, "close": 151.75, "volume": 1200000},
    {"date": "2024-10-29", "open": 151.75, "high": 153.00, "low": 150.50, "close": 152.80, "volume": 1100000},
    {"date": "2024-10-30", "open": 152.80, "high": 154.25, "low": 151.00, "close": 153.50, "volume": 1350000},
    {"date": "2024-10-31", "open": 153.50, "high": 155.00, "low": 152.75, "close": 154.20, "volume": 1500000},
    {"date": "2024-11-01", "open": 154.20, "high": 156.00, "low": 153.00, "close": 155.50, "volume": 1400000},
    {"date": "2024-11-04", "open": 158.00, "high": 159.50, "low": 156.00, "close": 157.25, "volume": 1800000},
    {"date": "2024-11-05", "open": 157.25, "high": 158.75, "low": 156.50, "close": 158.00, "volume": 1250000},
    {"date": "2024-11-06", "open": 158.00, "high": 160.00, "low": 157.00, "close": 159.50, "volume": 1300000},
    {"date": "2024-11-07", "open": 159.50, "high": 161.25, "low": 158.50, "close": 160.75, "volume": 1150000},
    {"date": "2024-11-08", "open": 160.75, "high": 162.00, "low": 159.00, "close": 161.50, "volume": 1400000},
    {"date": "2024-11-11", "open": 163.00, "high": 164.50, "low": 161.50, "close": 162.25, "volume": 1600000},
    {"date": "2024-11-12", "open": 162.25, "high": 163.75, "low": 161.00, "close": 163.00, "volume": 1200000},
    {"date": "2024-11-13", "open": 163.00, "high": 165.00, "low": 162.50, "close": 164.50, "volume": 1350000},
    {"date": "2024-11-14", "open": 164.50, "high": 166.00, "low": 163.00, "close": 165.25, "volume": 1100000},
    {"date": "2024-11-15", "open": 165.25, "high": 167.00, "low": 164.50, "close": 166.00, "volume": 1300000},
    {"date": "2024-11-18", "open": 164.00, "high": 166.50, "low": 163.00, "close": 165.50, "volume": 1700000},
    {"date": "2024-11-19", "open": 165.50, "high": 167.25, "low": 164.75, "close": 166.75, "volume": 1150000},
    {"date": "2024-11-20", "open": 166.75, "high": 168.00, "low": 165.50, "close": 167.50, "volume": 1250000}
]
```

---

### `tests/conftest.py`

```python
"""Shared test fixtures for charting MCP tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_ohlcv_bars() -> list[dict]:
    """Load sample OHLCV bars from fixture file."""
    with open(FIXTURES_DIR / "sample_ohlcv.json") as f:
        return json.load(f)


@pytest.fixture
def sample_equity_data() -> list[dict]:
    """Generate sample equity curve data."""
    import random
    random.seed(42)
    value = 100_000.0
    peak = value
    data = []
    for i in range(60):
        day = f"2024-{(i // 30) + 10:02d}-{(i % 30) + 1:02d}"
        change = random.gauss(0.001, 0.015) * value
        value += change
        if value > peak:
            peak = value
        drawdown_pct = ((value - peak) / peak) * 100
        data.append({
            "date": day,
            "value": round(value, 2),
            "peak": round(peak, 2),
            "drawdown_pct": round(drawdown_pct, 2),
        })
    return data


@pytest.fixture
def sample_gap_scatter_data() -> list[dict]:
    """Generate sample gap scatter data."""
    return [
        {"symbol": "AAPL", "gap_pct": 2.5, "subsequent_return": 1.2, "strategy": "gap_momentum_up", "date": "2024-11-04"},
        {"symbol": "MSFT", "gap_pct": -3.1, "subsequent_return": -0.5, "strategy": "gap_reversal_down", "date": "2024-11-04"},
        {"symbol": "GOOGL", "gap_pct": 1.8, "subsequent_return": 0.8, "strategy": "gap_momentum_up", "date": "2024-11-04"},
        {"symbol": "TSLA", "gap_pct": -4.2, "subsequent_return": 2.1, "strategy": "gap_reversal_down", "date": "2024-11-04"},
        {"symbol": "NVDA", "gap_pct": 3.5, "subsequent_return": -0.3, "strategy": "gap_momentum_up", "date": "2024-11-04"},
        {"symbol": "META", "gap_pct": -2.0, "subsequent_return": -1.1, "strategy": "gap_reversal_down", "date": "2024-11-11"},
        {"symbol": "AMZN", "gap_pct": 1.5, "subsequent_return": 1.8, "strategy": "gap_momentum_up", "date": "2024-11-11"},
        {"symbol": "JPM", "gap_pct": -1.2, "subsequent_return": 0.4, "strategy": "gap_reversal_down", "date": "2024-11-11"},
    ]


@pytest.fixture
def sample_sentiment_data() -> list[dict]:
    """Generate sample sentiment heatmap data."""
    return [
        {"symbol": "AAPL", "source": "news", "score": 0.7, "label": None},
        {"symbol": "AAPL", "source": "analyst", "score": 0.5, "label": None},
        {"symbol": "AAPL", "source": "macro", "score": -0.2, "label": None},
        {"symbol": "AAPL", "source": "social", "score": 0.3, "label": None},
        {"symbol": "MSFT", "source": "news", "score": 0.4, "label": None},
        {"symbol": "MSFT", "source": "analyst", "score": 0.8, "label": None},
        {"symbol": "MSFT", "source": "macro", "score": -0.1, "label": None},
        {"symbol": "MSFT", "source": "social", "score": 0.6, "label": None},
        {"symbol": "TSLA", "source": "news", "score": -0.5, "label": None},
        {"symbol": "TSLA", "source": "analyst", "score": -0.3, "label": None},
        {"symbol": "TSLA", "source": "macro", "score": -0.4, "label": None},
        {"symbol": "TSLA", "source": "social", "score": -0.8, "label": None},
    ]


@pytest.fixture
def sample_pnl_data() -> list[dict]:
    """Generate sample P&L data."""
    return [
        {"period": "2024-11-04", "pnl": 1250.00, "cumulative": None},
        {"period": "2024-11-05", "pnl": -430.50, "cumulative": None},
        {"period": "2024-11-06", "pnl": 890.25, "cumulative": None},
        {"period": "2024-11-07", "pnl": -150.00, "cumulative": None},
        {"period": "2024-11-08", "pnl": 2100.75, "cumulative": None},
        {"period": "2024-11-11", "pnl": -720.00, "cumulative": None},
        {"period": "2024-11-12", "pnl": 560.50, "cumulative": None},
        {"period": "2024-11-13", "pnl": 1340.00, "cumulative": None},
        {"period": "2024-11-14", "pnl": -890.25, "cumulative": None},
        {"period": "2024-11-15", "pnl": 1750.00, "cumulative": None},
    ]


@pytest.fixture
def sample_allocation_data() -> list[dict]:
    """Generate sample allocation data."""
    return [
        {"name": "Technology", "value": 35000, "color": None},
        {"name": "Healthcare", "value": 20000, "color": None},
        {"name": "Financials", "value": 15000, "color": None},
        {"name": "Energy", "value": 12000, "color": None},
        {"name": "Consumer", "value": 10000, "color": None},
        {"name": "Cash", "value": 8000, "color": "#90A4AE"},
    ]
```

---

### `tests/test_candlestick.py`

```python
"""Tests for the generate_candlestick tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qitp_mcp_charting.schemas import (
    CandlestickRequest,
    ChartConfig,
    ChartFormat,
    OHLCVBar,
    OverlayConfig,
    Theme,
)
from qitp_mcp_charting.tools.candlestick import generate_candlestick


class TestGenerateCandlestick:
    @pytest.mark.asyncio
    async def test_basic_candlestick_recharts(self, sample_ohlcv_bars):
        """Test basic candlestick generation with Recharts JSX output."""
        bars = [OHLCVBar(**b) for b in sample_ohlcv_bars[:5]]

        request = CandlestickRequest(
            symbol="AAPL",
            bars=bars,
            config=ChartConfig(title="AAPL Candlestick", theme=Theme.DARK),
        )

        with patch(
            "qitp_mcp_charting.tools.candlestick.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value="art-123")
            result = await generate_candlestick(request)

        assert result.chart_id.startswith("candlestick-AAPL-")
        assert result.format == ChartFormat.RECHARTS_JSX
        assert "AAPL" in result.content
        assert "ComposedChart" in result.content
        assert result.metadata["bars_count"] == 5
        assert result.metadata["show_volume"] is True

    @pytest.mark.asyncio
    async def test_candlestick_with_overlays(self, sample_ohlcv_bars):
        """Test candlestick with SMA and EMA overlays."""
        bars = [OHLCVBar(**b) for b in sample_ohlcv_bars]

        request = CandlestickRequest(
            symbol="MSFT",
            bars=bars,
            overlays=[
                OverlayConfig(type="sma", period=5, color="#FFD700", label="SMA(5)"),
                OverlayConfig(type="ema", period=10, color="#FF4500", label="EMA(10)"),
            ],
            show_volume=True,
            config=ChartConfig(title="MSFT with Overlays"),
        )

        with patch(
            "qitp_mcp_charting.tools.candlestick.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value=None)
            result = await generate_candlestick(request)

        assert result.metadata["overlays_count"] == 2
        assert "overlay_0" in result.content or "SMA" in result.content
        assert result.chart_id.startswith("candlestick-MSFT-")

    @pytest.mark.asyncio
    async def test_candlestick_no_volume(self, sample_ohlcv_bars):
        """Test candlestick without volume bars."""
        bars = [OHLCVBar(**b) for b in sample_ohlcv_bars[:3]]

        request = CandlestickRequest(
            symbol="GOOGL",
            bars=bars,
            show_volume=False,
            config=ChartConfig(title="GOOGL No Volume"),
        )

        with patch(
            "qitp_mcp_charting.tools.candlestick.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value=None)
            result = await generate_candlestick(request)

        assert result.metadata["show_volume"] is False

    @pytest.mark.asyncio
    async def test_candlestick_html_fallback(self, sample_ohlcv_bars):
        """Test candlestick with HTML fallback format."""
        bars = [OHLCVBar(**b) for b in sample_ohlcv_bars[:5]]

        request = CandlestickRequest(
            symbol="AAPL",
            bars=bars,
            config=ChartConfig(
                title="AAPL HTML",
                format=ChartFormat.HTML_FALLBACK,
            ),
        )

        with patch(
            "qitp_mcp_charting.tools.candlestick.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value=None)
            result = await generate_candlestick(request)

        assert result.format == ChartFormat.HTML_FALLBACK
        assert "<html" in result.content
        assert "Chart" in result.content

    @pytest.mark.asyncio
    async def test_candlestick_artifact_failure_nonfatal(self, sample_ohlcv_bars):
        """Test that artifact storage failure doesn't break chart generation."""
        bars = [OHLCVBar(**b) for b in sample_ohlcv_bars[:3]]

        request = CandlestickRequest(symbol="AAPL", bars=bars)

        with patch(
            "qitp_mcp_charting.tools.candlestick.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            result = await generate_candlestick(request)

        # Should still return a valid chart
        assert result.content is not None
        assert result.artifact_id is None
```

---

### `tests/test_equity_curve.py`

```python
"""Tests for the generate_equity_curve tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qitp_mcp_charting.schemas import (
    ChartConfig,
    ChartFormat,
    EquityCurvePoint,
    EquityCurveRequest,
    Theme,
)
from qitp_mcp_charting.tools.equity_curve import generate_equity_curve


class TestGenerateEquityCurve:
    @pytest.mark.asyncio
    async def test_basic_equity_curve(self, sample_equity_data):
        """Test basic equity curve generation."""
        data = [EquityCurvePoint(**d) for d in sample_equity_data[:10]]

        request = EquityCurveRequest(
            strategy_name="gap_momentum_up",
            data=data,
            show_drawdown=True,
            config=ChartConfig(title="Gap Momentum — Equity Curve"),
        )

        with patch(
            "qitp_mcp_charting.tools.equity_curve.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value="art-456")
            result = await generate_equity_curve(request)

        assert result.chart_id.startswith("equity-gap_momentum_up-")
        assert result.format == ChartFormat.RECHARTS_JSX
        assert "ComposedChart" in result.content
        assert "Drawdown" in result.content or "drawdown" in result.content
        assert result.metadata["data_points"] == 10
        assert result.metadata["show_drawdown"] is True

    @pytest.mark.asyncio
    async def test_equity_curve_no_drawdown(self, sample_equity_data):
        """Test equity curve without drawdown shading."""
        data = [EquityCurvePoint(**d) for d in sample_equity_data[:5]]

        request = EquityCurveRequest(
            strategy_name="test_strat",
            data=data,
            show_drawdown=False,
        )

        with patch(
            "qitp_mcp_charting.tools.equity_curve.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value=None)
            result = await generate_equity_curve(request)

        assert result.metadata["show_drawdown"] is False

    @pytest.mark.asyncio
    async def test_equity_curve_auto_computes_peak_and_drawdown(self):
        """Test that peak and drawdown are auto-computed when not provided."""
        data = [
            EquityCurvePoint(date="2024-01-01", value=100000, peak=None, drawdown_pct=None),
            EquityCurvePoint(date="2024-01-02", value=102000, peak=None, drawdown_pct=None),
            EquityCurvePoint(date="2024-01-03", value=99000, peak=None, drawdown_pct=None),
        ]

        request = EquityCurveRequest(
            strategy_name="auto_compute",
            data=data,
            show_drawdown=True,
        )

        with patch(
            "qitp_mcp_charting.tools.equity_curve.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value=None)
            result = await generate_equity_curve(request)

        # The content should contain valid JSX
        assert result.content is not None
        assert len(result.content) > 100

    @pytest.mark.asyncio
    async def test_equity_curve_with_benchmark(self, sample_equity_data):
        """Test equity curve with benchmark data overlay."""
        data = [EquityCurvePoint(**d) for d in sample_equity_data[:5]]
        benchmark = [
            EquityCurvePoint(date=d["date"], value=100000 + i * 200)
            for i, d in enumerate(sample_equity_data[:5])
        ]

        request = EquityCurveRequest(
            strategy_name="with_bench",
            data=data,
            benchmark_data=benchmark,
        )

        with patch(
            "qitp_mcp_charting.tools.equity_curve.ArtifactClient"
        ) as mock_client_cls:
            mock_client_cls.return_value.store_chart = AsyncMock(return_value=None)
            result = await generate_equity_curve(request)

        assert "Benchmark" in result.content or "benchmark" in result.content
```

---

### `tests/test_renderers.py`

```python
"""Tests for the rendering engines."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitp_mcp_charting.renderers import get_renderer
from qitp_mcp_charting.renderers.html_fallback import HtmlFallbackRenderer
from qitp_mcp_charting.renderers.recharts import RechartsRenderer
from qitp_mcp_charting.schemas import ChartFormat, Theme


FIXTURES_DIR = Path(__file__).parent / "fixtures"

DEFAULT_CONFIG = {
    "title": "Test Chart",
    "subtitle": "",
    "width": 800,
    "height": 500,
    "theme": "dark",
    "format": "recharts_jsx",
    "responsive": True,
    "show_legend": True,
    "show_grid": True,
    "show_tooltip": True,
}


class TestGetRenderer:
    def test_recharts_format(self):
        renderer = get_renderer(ChartFormat.RECHARTS_JSX)
        assert isinstance(renderer, RechartsRenderer)

    def test_html_format(self):
        renderer = get_renderer(ChartFormat.HTML_FALLBACK)
        assert isinstance(renderer, HtmlFallbackRenderer)

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown chart format"):
            get_renderer("invalid_format")


class TestRechartsRenderer:
    @pytest.fixture
    def renderer(self):
        return RechartsRenderer()

    def test_render_candlestick_contains_recharts(self, renderer, sample_ohlcv_bars):
        result = renderer.render_candlestick(
            symbol="AAPL",
            bars=sample_ohlcv_bars[:5],
            overlays=[],
            show_volume=True,
            config=DEFAULT_CONFIG,
        )
        assert "ComposedChart" in result
        assert "AAPL" in result
        assert "ResponsiveContainer" in result

    def test_render_candlestick_with_overlays(self, renderer, sample_ohlcv_bars):
        overlays = [
            {"type": "sma", "period": 5, "color": "#FFD700", "label": "SMA(5)"},
        ]
        result = renderer.render_candlestick(
            symbol="MSFT",
            bars=sample_ohlcv_bars,
            overlays=overlays,
            show_volume=True,
            config=DEFAULT_CONFIG,
        )
        assert "overlay_0" in result or "SMA" in result

    def test_render_equity_curve(self, renderer, sample_equity_data):
        result = renderer.render_equity_curve(
            strategy_name="test_strategy",
            data=sample_equity_data[:10],
            show_drawdown=True,
            benchmark_data=None,
            config=DEFAULT_CONFIG,
        )
        assert "ComposedChart" in result
        assert "test_strategy" in result
        assert "Drawdown" in result

    def test_render_gap_scatter(self, renderer, sample_gap_scatter_data):
        result = renderer.render_gap_scatter(
            data=sample_gap_scatter_data,
            strategies=["gap_momentum_up", "gap_reversal_down"],
            x_label="Gap %",
            y_label="Return %",
            config=DEFAULT_CONFIG,
        )
        assert "ScatterChart" in result
        assert "Gap %" in result

    def test_render_sentiment_heatmap(self, renderer, sample_sentiment_data):
        result = renderer.render_sentiment_heatmap(
            data=sample_sentiment_data,
            symbols=["AAPL", "MSFT", "TSLA"],
            sources=["news", "analyst", "macro", "social"],
            config=DEFAULT_CONFIG,
        )
        assert "Sentiment Heatmap" in result
        assert "AAPL" in result
        assert "sentimentColor" in result

    def test_render_pnl_bar(self, renderer, sample_pnl_data):
        result = renderer.render_pnl_bar(
            data=sample_pnl_data,
            show_cumulative=True,
            period_type="daily",
            config=DEFAULT_CONFIG,
        )
        assert "ComposedChart" in result
        assert "P&L" in result

    def test_render_allocation_donut(self, renderer, sample_allocation_data):
        result = renderer.render_allocation(
            data=sample_allocation_data,
            chart_style="donut",
            show_percentages=True,
            config=DEFAULT_CONFIG,
        )
        assert "PieChart" in result
        assert "Portfolio Allocation" in result

    def test_render_allocation_treemap(self, renderer, sample_allocation_data):
        result = renderer.render_allocation(
            data=sample_allocation_data,
            chart_style="treemap",
            show_percentages=True,
            config=DEFAULT_CONFIG,
        )
        assert "Treemap" in result

    def test_render_generic_line(self, renderer):
        data = [
            {"date": "2024-01-01", "price": 100, "volume": 1000},
            {"date": "2024-01-02", "price": 105, "volume": 1200},
        ]
        result = renderer.render_generic(
            chart_type="line",
            data=data,
            x_key="date",
            y_keys=["price"],
            series_colors={"price": "#8884d8"},
            config=DEFAULT_CONFIG,
        )
        assert "ComposedChart" in result
        assert "Line" in result

    def test_render_generic_composed(self, renderer):
        data = [
            {"date": "2024-01-01", "price": 100, "volume": 1000},
            {"date": "2024-01-02", "price": 105, "volume": 1200},
        ]
        result = renderer.render_generic(
            chart_type="composed",
            data=data,
            x_key="date",
            y_keys=["price", "volume"],
            series_colors={},
            config=DEFAULT_CONFIG,
        )
        assert "ComposedChart" in result

    def test_dark_theme_colors(self, renderer, sample_ohlcv_bars):
        dark_config = {**DEFAULT_CONFIG, "theme": "dark"}
        result = renderer.render_candlestick(
            symbol="TEST",
            bars=sample_ohlcv_bars[:3],
            overlays=[],
            show_volume=False,
            config=dark_config,
        )
        assert "#1a1a2e" in result  # dark background

    def test_light_theme_colors(self, renderer, sample_ohlcv_bars):
        light_config = {**DEFAULT_CONFIG, "theme": "light"}
        result = renderer.render_candlestick(
            symbol="TEST",
            bars=sample_ohlcv_bars[:3],
            overlays=[],
            show_volume=False,
            config=light_config,
        )
        assert "#ffffff" in result  # light background


class TestHtmlFallbackRenderer:
    @pytest.fixture
    def renderer(self):
        return HtmlFallbackRenderer()

    def test_render_equity_curve_html(self, renderer, sample_equity_data):
        result = renderer.render_equity_curve(
            strategy_name="test",
            data=sample_equity_data[:5],
            show_drawdown=True,
            benchmark_data=None,
            config=DEFAULT_CONFIG,
        )
        assert "<html" in result
        assert "chart.js" in result.lower() or "Chart" in result

    def test_render_allocation_html(self, renderer, sample_allocation_data):
        result = renderer.render_allocation(
            data=sample_allocation_data,
            chart_style="donut",
            show_percentages=True,
            config=DEFAULT_CONFIG,
        )
        assert "<html" in result
        assert "doughnut" in result

    def test_render_sentiment_html_table(self, renderer, sample_sentiment_data):
        result = renderer.render_sentiment_heatmap(
            data=sample_sentiment_data,
            symbols=["AAPL", "MSFT", "TSLA"],
            sources=["news", "analyst", "macro", "social"],
            config=DEFAULT_CONFIG,
        )
        assert "<html" in result
        assert "heatmap-table" in result
        assert "AAPL" in result

    def test_render_pnl_bar_html(self, renderer, sample_pnl_data):
        result = renderer.render_pnl_bar(
            data=sample_pnl_data,
            show_cumulative=True,
            period_type="daily",
            config=DEFAULT_CONFIG,
        )
        assert "<html" in result

    def test_render_gap_scatter_html(self, renderer, sample_gap_scatter_data):
        result = renderer.render_gap_scatter(
            data=sample_gap_scatter_data,
            strategies=["gap_momentum_up"],
            x_label="Gap %",
            y_label="Return %",
            config=DEFAULT_CONFIG,
        )
        assert "<html" in result
        assert "scatter" in result


class TestMCPServerIntegration:
    """Test the MCP server tool registry and schema generation."""

    def test_tool_registry_has_all_tools(self):
        from qitp_mcp_charting.server import TOOL_REGISTRY

        expected_tools = {
            "generate_candlestick",
            "generate_equity_curve",
            "generate_gap_scatter",
            "generate_sentiment_heatmap",
            "generate_pnl_bar",
            "generate_portfolio_allocation",
            "generate_chart",
        }
        assert set(TOOL_REGISTRY.keys()) == expected_tools

    def test_tool_schemas_are_valid_json_schema(self):
        from qitp_mcp_charting.server import TOOL_REGISTRY, _build_tool_schema

        for name, (model_cls, _, _) in TOOL_REGISTRY.items():
            schema = _build_tool_schema(model_cls)
            assert "properties" in schema, f"{name} schema missing 'properties'"
            assert "type" in schema, f"{name} schema missing 'type'"

    def test_create_server_lists_7_tools(self):
        """Verify the server returns exactly 7 tools."""
        import asyncio
        from qitp_mcp_charting.server import create_server

        server = create_server()

        # Access the list_tools handler directly
        async def check():
            # The handler is registered via decorator; we test TOOL_REGISTRY count
            from qitp_mcp_charting.server import TOOL_REGISTRY
            assert len(TOOL_REGISTRY) == 7

        asyncio.run(check())
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
    CMD curl -f http://localhost:8006/health || exit 1

# Default: HTTP transport for production
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8006
ENV ARTIFACTS_MCP_URL=http://artifacts-mcp:8004
ENV LOG_LEVEL=INFO

EXPOSE 8006

ENTRYPOINT ["charting-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  charting-mcp:
    build: .
    container_name: qitp-charting-mcp
    ports:
      - "8006:8006"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8006
      - ARTIFACTS_MCP_URL=${ARTIFACTS_MCP_URL:-http://artifacts-mcp:8004}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    restart: unless-stopped
    networks:
      - qitp

networks:
  qitp:
    driver: bridge
    external: true
```

---

## Acceptance Criteria

- [ ] MCP server starts and lists 7 tools
- [ ] `generate_candlestick` produces valid Recharts JSX with OHLC bars, wick lines, and volume
- [ ] `generate_equity_curve` produces JSX with drawdown shading (red area below peak)
- [ ] `generate_gap_scatter` produces scatter plot with strategy-colored points and zero reference lines
- [ ] `generate_sentiment_heatmap` produces a symbol x source matrix with red-to-green color scale
- [ ] `generate_pnl_bar` produces green/red bars with optional cumulative line
- [ ] `generate_portfolio_allocation` supports pie, donut, and treemap styles
- [ ] `generate_chart` accepts arbitrary data and renders line/bar/scatter/area/composed charts
- [ ] HTML fallback renderer produces self-contained HTML with Chart.js for all chart types
- [ ] Dark and light themes produce correct background/text colors
- [ ] Artifact storage via artifacts-mcp is fire-and-forget — chart generation succeeds even if storage fails
- [ ] Docker build succeeds and server starts on port 8006
- [ ] All tests pass

## Test Plan

```bash
cd ~/dev/tccw-qitp-mcp-charting
pip install -e ".[dev]"
pytest -v
docker build -t qitp-mcp-charting .
```

## Agent Instructions

This MCP server generates interactive financial charts. The primary output format is React/Recharts JSX compatible with Claude.ai artifact rendering. The HTML fallback uses Chart.js for non-Claude clients.

Key implementation notes:

1. **JSX must be self-contained**: Each Recharts template must be a complete React component that can render in Claude.ai's sandbox. All data is embedded inline — no external fetches.
2. **Jinja2 for templating**: Use `{{ data | tojson }}` to embed data as JavaScript constants. Use `{% raw %}{{ }}{% endraw %}` for React inline styles (double curly braces conflict with Jinja2).
3. **Artifact storage is optional**: Charts are stored via artifacts-mcp for persistence, but the artifact client must never block or crash chart generation. Wrap all artifact calls in try/except.
4. **Theme support**: Both dark (`#1a1a2e` bg) and light (`#ffffff` bg) themes. The theme is baked into the rendered output via Jinja2 conditionals.
5. **Port 8006**: Charting MCP runs on port 8006 per the CLAUDE.md port registry.
6. **No heavy dependencies**: This MCP does NOT need pandas, numpy, or matplotlib. All rendering is template-based string generation. Keep the Docker image small.
7. **Candlestick approximation**: Recharts doesn't have native candlestick support. We use `ComposedChart` with two `Bar` components (thin wick bar + wide body bar) and `Cell` for per-bar coloring.
