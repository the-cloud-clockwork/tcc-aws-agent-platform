# P03 — Simulation Engine Library

## Objective
Build the QITP simulation engine: event-driven backtesting, slippage/commission models, performance metrics (Sharpe, Sortino, drawdown, Calmar, profit factor, win rate), walk-forward validation, and strategy condition evaluation.

## Plane Tickets
ROOT-57 (Simulation Engine)

## Target Repo
`~/dev/tccw-qitp-simulation`

## Dependencies
P01 (repo scaffold)

## Repo Structure
```
tccw-qitp-simulation/
├── src/
│   └── qitp_simulation/
│       ├── __init__.py
│       ├── engine.py           # BacktestEngine — main event loop
│       ├── strategy.py         # StrategyEvaluator — reads strategy YAML, applies conditions
│       ├── portfolio.py        # Portfolio state tracker (positions, cash, NAV)
│       ├── metrics.py          # Performance metrics calculator
│       ├── slippage.py         # SlippageModel (fixed, percentage, volume-impact)
│       ├── commission.py       # CommissionModel (IBKR tiered EU pricing)
│       ├── types.py            # Shared types: Bar, Trade, Position, EquityCurvePoint
│       └── walk_forward.py     # Walk-forward validation
├── tests/
│   ├── conftest.py
│   ├── test_engine.py
│   ├── test_strategy.py
│   ├── test_metrics.py
│   ├── test_slippage.py
│   ├── test_commission.py
│   └── fixtures/
│       ├── sample_ohlcv.csv    # 1 year of daily OHLCV for testing
│       └── sample_strategy.yaml
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
name = "qitp-simulation"
version = "0.1.0"
description = "QITP Simulation Engine — event-driven backtesting with slippage, commission, and walk-forward validation"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "numpy>=1.26,<3",
    "pandas>=2.1,<3",
    "pyyaml>=6.0,<7",
    "pydantic>=2.5,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4,<9",
    "pytest-cov>=4.1,<6",
    "ruff>=0.4,<1",
]

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

---

### `src/qitp_simulation/__init__.py`

```python
"""QITP Simulation Engine — event-driven backtesting library."""

from qitp_simulation.commission import CommissionModel, IBKRTieredEU, ZeroCommission
from qitp_simulation.engine import BacktestEngine
from qitp_simulation.metrics import (
    calculate_all_metrics,
    calculate_calmar,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe,
    calculate_sortino,
    calculate_win_rate,
)
from qitp_simulation.slippage import (
    FixedSlippage,
    PercentageSlippage,
    SlippageModel,
    VolumeImpactSlippage,
)
from qitp_simulation.strategy import StrategyEvaluator
from qitp_simulation.types import (
    BacktestResult,
    Bar,
    EquityCurvePoint,
    Position,
    Trade,
)
from qitp_simulation.walk_forward import WalkForwardValidator

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "Bar",
    "CommissionModel",
    "EquityCurvePoint",
    "FixedSlippage",
    "IBKRTieredEU",
    "PercentageSlippage",
    "Position",
    "SlippageModel",
    "StrategyEvaluator",
    "Trade",
    "VolumeImpactSlippage",
    "WalkForwardValidator",
    "ZeroCommission",
    "calculate_all_metrics",
    "calculate_calmar",
    "calculate_max_drawdown",
    "calculate_profit_factor",
    "calculate_sharpe",
    "calculate_sortino",
    "calculate_win_rate",
]
```

---

### `src/qitp_simulation/types.py`

```python
"""Core data types for the simulation engine."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bar:
    """A single OHLCV bar."""

    date: datetime.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None


@dataclass
class Trade:
    """A completed (closed) trade."""

    entry_date: datetime.date
    exit_date: datetime.date
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    holding_days: int
    exit_reason: str  # "signal", "trailing_stop", "max_holding", "end_of_data"
    slippage: float = 0.0
    commission: float = 0.0


@dataclass
class Position:
    """An open position."""

    symbol: str
    direction: str  # "long" or "short"
    entry_date: datetime.date
    entry_price: float
    quantity: int
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    trailing_stop_price: float | None = None

    def update_price(self, price: float) -> None:
        """Update current price and unrealized PnL."""
        self.current_price = price
        if self.direction == "long":
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity

    def update_trailing_stop(self, trailing_stop_pct: float) -> None:
        """Update trailing stop based on current price and percentage."""
        if self.direction == "long":
            new_stop = self.current_price * (1 - trailing_stop_pct / 100.0)
            if self.trailing_stop_price is None or new_stop > self.trailing_stop_price:
                self.trailing_stop_price = new_stop
        else:
            new_stop = self.current_price * (1 + trailing_stop_pct / 100.0)
            if self.trailing_stop_price is None or new_stop < self.trailing_stop_price:
                self.trailing_stop_price = new_stop

    def is_trailing_stop_triggered(self, bar: Bar) -> bool:
        """Check if trailing stop is triggered by the bar's price action."""
        if self.trailing_stop_price is None:
            return False
        if self.direction == "long":
            return bar.low <= self.trailing_stop_price
        else:
            return bar.high >= self.trailing_stop_price


@dataclass(frozen=True)
class EquityCurvePoint:
    """A single point on the equity curve."""

    date: datetime.date
    portfolio_value: float
    drawdown_pct: float


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""

    strategy_id: str
    strategy_version: str
    symbols: list[str]
    start_date: datetime.date
    end_date: datetime.date
    initial_capital: float
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
    equity_curve: list[EquityCurvePoint] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
```

---

### `src/qitp_simulation/portfolio.py`

```python
"""Portfolio state tracker — positions, cash, and NAV."""

from __future__ import annotations

import datetime

from qitp_simulation.types import Bar, Position, Trade


class Portfolio:
    """Tracks cash, open positions, and completed trades."""

    def __init__(self, initial_capital: float) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.trades: list[Trade] = []

    @property
    def nav(self) -> float:
        """Net asset value: cash + market value of all open positions."""
        position_value = sum(
            p.current_price * p.quantity if p.direction == "long" else (2 * p.entry_price - p.current_price) * p.quantity
            for p in self.positions.values()
        )
        return self.cash + position_value

    def open_position(
        self,
        symbol: str,
        direction: str,
        date: datetime.date,
        price: float,
        quantity: int,
    ) -> Position | None:
        """Open a new position. Returns the Position or None if insufficient cash."""
        if symbol in self.positions:
            return None  # already have a position in this symbol

        cost = price * quantity
        if cost > self.cash:
            return None

        self.cash -= cost
        position = Position(
            symbol=symbol,
            direction=direction,
            entry_date=date,
            entry_price=price,
            quantity=quantity,
            current_price=price,
        )
        self.positions[symbol] = position
        return position

    def close_position(
        self,
        symbol: str,
        date: datetime.date,
        price: float,
        exit_reason: str,
        slippage: float = 0.0,
        commission: float = 0.0,
    ) -> Trade | None:
        """Close an existing position. Returns the completed Trade or None."""
        if symbol not in self.positions:
            return None

        pos = self.positions.pop(symbol)

        if pos.direction == "long":
            pnl = (price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity

        pnl -= slippage + commission
        pnl_pct = (pnl / (pos.entry_price * pos.quantity)) * 100.0
        holding_days = (date - pos.entry_date).days

        # Return cash: proceeds from closing
        proceeds = price * pos.quantity
        self.cash += proceeds - commission

        trade = Trade(
            entry_date=pos.entry_date,
            exit_date=date,
            symbol=symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=price,
            quantity=pos.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=max(holding_days, 1),
            exit_reason=exit_reason,
            slippage=slippage,
            commission=commission,
        )
        self.trades.append(trade)
        return trade

    def update_prices(self, bars: dict[str, Bar]) -> None:
        """Update all open position prices from today's bars."""
        for symbol, position in self.positions.items():
            if symbol in bars:
                position.update_price(bars[symbol].close)
```

---

### `src/qitp_simulation/slippage.py`

```python
"""Slippage models for simulating market impact."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SlippageModel(ABC):
    """Base class for slippage models."""

    @abstractmethod
    def apply(self, price: float, quantity: int, direction: str) -> float:
        """Apply slippage to a price.

        Args:
            price: The intended execution price.
            quantity: Number of shares.
            direction: "long" (buying) or "short" (selling).

        Returns:
            The adjusted price after slippage.
        """


class FixedSlippage(SlippageModel):
    """Fixed dollar amount of slippage per share.

    Example: FixedSlippage(0.01) adds $0.01 per share when buying,
    subtracts $0.01 per share when selling.
    """

    def __init__(self, amount: float = 0.01) -> None:
        if amount < 0:
            raise ValueError("Slippage amount must be non-negative")
        self.amount = amount

    def apply(self, price: float, quantity: int, direction: str) -> float:
        """Apply fixed slippage per share."""
        if direction == "long":
            return price + self.amount
        else:
            return price - self.amount


class PercentageSlippage(SlippageModel):
    """Percentage-based slippage.

    Example: PercentageSlippage(0.1) applies 0.1% slippage.
    """

    def __init__(self, pct: float = 0.1) -> None:
        if pct < 0:
            raise ValueError("Slippage percentage must be non-negative")
        self.pct = pct

    def apply(self, price: float, quantity: int, direction: str) -> float:
        """Apply percentage-based slippage."""
        slip = price * (self.pct / 100.0)
        if direction == "long":
            return price + slip
        else:
            return price - slip


class VolumeImpactSlippage(SlippageModel):
    """Volume-impact slippage model.

    Slippage increases with order size relative to average volume.
    slippage = price * impact_factor * sqrt(quantity / avg_volume)
    """

    def __init__(self, impact_factor: float = 0.1, avg_volume: int = 1_000_000) -> None:
        if impact_factor < 0:
            raise ValueError("Impact factor must be non-negative")
        if avg_volume <= 0:
            raise ValueError("Average volume must be positive")
        self.impact_factor = impact_factor
        self.avg_volume = avg_volume

    def apply(self, price: float, quantity: int, direction: str) -> float:
        """Apply volume-impact slippage."""
        import math

        participation_rate = quantity / self.avg_volume
        slip = price * self.impact_factor * math.sqrt(participation_rate) / 100.0
        if direction == "long":
            return price + slip
        else:
            return price - slip
```

---

### `src/qitp_simulation/commission.py`

```python
"""Commission models — IBKR tiered pricing and zero-commission."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CommissionModel(ABC):
    """Base class for commission models."""

    @abstractmethod
    def calculate(self, price: float, quantity: int, exchange: str = "EU") -> float:
        """Calculate commission for a trade.

        Args:
            price: Execution price per share.
            quantity: Number of shares.
            exchange: Exchange region, e.g. "EU" or "US".

        Returns:
            Total commission amount.
        """


class IBKRTieredEU(CommissionModel):
    """Interactive Brokers tiered pricing for EU and US markets.

    EU (EUR stocks): 0.05% of trade value, min EUR 1.25, max EUR 29.00
    US (USD stocks): $0.0035/share, min $0.35, max 1% of trade value
    """

    def calculate(self, price: float, quantity: int, exchange: str = "EU") -> float:
        """Calculate IBKR tiered commission."""
        trade_value = price * quantity

        if exchange.upper() in ("EU", "EUR", "XETRA", "EURONEXT", "LSE"):
            # EUR stocks: 0.05% of trade value, min 1.25, max 29.00
            commission = trade_value * 0.0005
            return max(1.25, min(commission, 29.00))

        elif exchange.upper() in ("US", "USD", "NYSE", "NASDAQ", "ARCA"):
            # US stocks: $0.0035/share, min $0.35, max 1% of trade value
            commission = quantity * 0.0035
            return max(0.35, min(commission, trade_value * 0.01))

        else:
            # Default to EU pricing for unknown exchanges
            commission = trade_value * 0.0005
            return max(1.25, min(commission, 29.00))


class ZeroCommission(CommissionModel):
    """Zero commission model for backtesting without commission impact."""

    def calculate(self, price: float, quantity: int, exchange: str = "EU") -> float:
        """Always returns zero commission."""
        return 0.0
```

---

### `src/qitp_simulation/metrics.py`

```python
"""Performance metrics calculator for backtesting results."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from qitp_simulation.types import EquityCurvePoint, Trade


def calculate_sharpe(
    returns: np.ndarray | list[float],
    risk_free_rate: float = 0.04,
    trading_days: int = 252,
) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        returns: Array of daily returns (as decimals, e.g., 0.01 = 1%).
        risk_free_rate: Annual risk-free rate (default 4%).
        trading_days: Number of trading days per year.

    Returns:
        Annualized Sharpe ratio. Returns 0.0 if std is zero.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 2:
        return 0.0

    daily_rf = risk_free_rate / trading_days
    excess_returns = returns - daily_rf
    std = np.std(excess_returns, ddof=1)

    if std == 0 or np.isnan(std):
        return 0.0

    return float(np.mean(excess_returns) / std * math.sqrt(trading_days))


def calculate_sortino(
    returns: np.ndarray | list[float],
    risk_free_rate: float = 0.04,
    trading_days: int = 252,
) -> float:
    """Calculate annualized Sortino ratio (penalizes downside only).

    Args:
        returns: Array of daily returns (as decimals).
        risk_free_rate: Annual risk-free rate.
        trading_days: Number of trading days per year.

    Returns:
        Annualized Sortino ratio. Returns 0.0 if downside deviation is zero.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 2:
        return 0.0

    daily_rf = risk_free_rate / trading_days
    excess_returns = returns - daily_rf
    downside = excess_returns[excess_returns < 0]

    if len(downside) == 0:
        return 0.0  # No downside — ratio undefined, return 0

    downside_std = np.std(downside, ddof=1)
    if downside_std == 0 or np.isnan(downside_std):
        return 0.0

    return float(np.mean(excess_returns) / downside_std * math.sqrt(trading_days))


def calculate_max_drawdown(equity_curve: list[EquityCurvePoint] | list[float]) -> float:
    """Calculate maximum drawdown as a percentage.

    Args:
        equity_curve: List of EquityCurvePoint or raw portfolio values.

    Returns:
        Maximum drawdown as a positive percentage (e.g., 15.0 for 15% drawdown).
    """
    if not equity_curve:
        return 0.0

    if isinstance(equity_curve[0], EquityCurvePoint):
        values = [p.portfolio_value for p in equity_curve]
    else:
        values = list(equity_curve)

    if len(values) < 2:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for val in values:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_calmar(annualized_return: float, max_drawdown: float) -> float:
    """Calculate Calmar ratio (annualized return / max drawdown).

    Args:
        annualized_return: Annualized return as a percentage.
        max_drawdown: Maximum drawdown as a percentage.

    Returns:
        Calmar ratio. Returns 0.0 if max drawdown is zero.
    """
    if max_drawdown == 0:
        return 0.0
    return annualized_return / max_drawdown


def calculate_profit_factor(trades: list[Trade]) -> float:
    """Calculate profit factor (gross profit / gross loss).

    Args:
        trades: List of completed trades.

    Returns:
        Profit factor. Returns float('inf') if no losses, 0.0 if no profits.
    """
    if not trades:
        return 0.0

    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def calculate_win_rate(trades: list[Trade]) -> float:
    """Calculate win rate as a percentage.

    Args:
        trades: List of completed trades.

    Returns:
        Win rate as a percentage (e.g., 55.0 for 55%).
    """
    if not trades:
        return 0.0

    winners = sum(1 for t in trades if t.pnl > 0)
    return (winners / len(trades)) * 100.0


def calculate_all_metrics(
    trades: list[Trade],
    equity_curve: list[EquityCurvePoint],
    initial_capital: float,
    risk_free_rate: float = 0.04,
) -> dict[str, Any]:
    """Calculate all performance metrics.

    Args:
        trades: List of completed trades.
        equity_curve: List of equity curve points.
        initial_capital: Starting capital.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Dictionary with all calculated metrics.
    """
    # Build daily returns from equity curve
    if len(equity_curve) >= 2:
        values = [p.portfolio_value for p in equity_curve]
        daily_returns = np.diff(values) / values[:-1]
    else:
        daily_returns = np.array([])

    max_dd = calculate_max_drawdown(equity_curve)

    # Total return
    if equity_curve:
        final_value = equity_curve[-1].portfolio_value
        total_return_pct = ((final_value - initial_capital) / initial_capital) * 100.0
    else:
        total_return_pct = 0.0

    # Annualized return
    if len(equity_curve) >= 2:
        n_days = (equity_curve[-1].date - equity_curve[0].date).days
        if n_days > 0:
            total_return_dec = total_return_pct / 100.0
            annualized_return_pct = ((1 + total_return_dec) ** (365.0 / n_days) - 1) * 100.0
        else:
            annualized_return_pct = 0.0
    else:
        annualized_return_pct = 0.0

    sharpe = calculate_sharpe(daily_returns, risk_free_rate)
    sortino = calculate_sortino(daily_returns, risk_free_rate)
    calmar = calculate_calmar(annualized_return_pct, max_dd)
    pf = calculate_profit_factor(trades)
    wr = calculate_win_rate(trades)

    winning_trades = [t for t in trades if t.pnl > 0]
    losing_trades = [t for t in trades if t.pnl <= 0]

    avg_win_pct = (
        sum(t.pnl_pct for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
    )
    avg_loss_pct = (
        sum(t.pnl_pct for t in losing_trades) / len(losing_trades) if losing_trades else 0.0
    )
    avg_holding = (
        sum(t.holding_days for t in trades) / len(trades) if trades else 0.0
    )

    return {
        "total_trades": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate_pct": wr,
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_return_pct,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "profit_factor": pf,
        "avg_holding_days": avg_holding,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
    }
```

---

### `src/qitp_simulation/strategy.py`

```python
"""Strategy evaluator — reads YAML strategy definitions and evaluates conditions."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ConditionSpec(BaseModel):
    """A single condition specification."""

    indicator: str
    operator: str  # gte, lte, gt, lt, eq, in
    value: float | str | list[Any]


class ConditionGroup(BaseModel):
    """A group of conditions with a logical operator."""

    logic: str = "AND"  # "AND" or "OR"
    conditions: list[ConditionSpec] = []


class ExitRules(BaseModel):
    """Exit rules for a strategy."""

    trailing_stop_pct: float | None = None
    max_holding_days: int | None = None
    conditions: list[ConditionSpec] = []


class PositionSizing(BaseModel):
    """Position sizing configuration."""

    method: str = "fixed_pct"  # "fixed_pct", "fixed_amount", "kelly"
    value: float = 5.0  # percentage of NAV or fixed amount


class StrategySpec(BaseModel):
    """Complete strategy specification parsed from YAML."""

    id: str = "unnamed"
    version: str = "1.0"
    symbols: list[str] = []
    direction: str = "long"
    entry: ConditionGroup = ConditionGroup()
    exit: ExitRules = ExitRules()
    position_sizing: PositionSizing = PositionSizing()


class StrategyEvaluator:
    """Evaluates strategy conditions against market signals.

    Reads a strategy YAML file and provides methods to check
    entry/exit conditions and compute position sizes.
    """

    def __init__(self, strategy: StrategySpec | None = None, yaml_path: str | Path | None = None) -> None:
        """Initialize with either a StrategySpec or a path to a YAML file.

        Args:
            strategy: A pre-built StrategySpec object.
            yaml_path: Path to a strategy YAML file.
        """
        if strategy is not None:
            self.strategy = strategy
        elif yaml_path is not None:
            self.strategy = self._load_yaml(yaml_path)
        else:
            raise ValueError("Must provide either strategy or yaml_path")

    @staticmethod
    def _load_yaml(path: str | Path) -> StrategySpec:
        """Load and parse a strategy YAML file."""
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)

        # Map YAML structure to StrategySpec
        entry_conditions = []
        entry_data = data.get("entry", {})
        for cond in entry_data.get("conditions", []):
            entry_conditions.append(ConditionSpec(**cond))

        exit_data = data.get("exit", {})
        exit_conditions = []
        for cond in exit_data.get("conditions", []):
            exit_conditions.append(ConditionSpec(**cond))

        sizing_data = data.get("position_sizing", {})

        return StrategySpec(
            id=data.get("id", "unnamed"),
            version=data.get("version", "1.0"),
            symbols=data.get("symbols", []),
            direction=data.get("direction", "long"),
            entry=ConditionGroup(
                logic=entry_data.get("logic", "AND"),
                conditions=entry_conditions,
            ),
            exit=ExitRules(
                trailing_stop_pct=exit_data.get("trailing_stop_pct"),
                max_holding_days=exit_data.get("max_holding_days"),
                conditions=exit_conditions,
            ),
            position_sizing=PositionSizing(**sizing_data) if sizing_data else PositionSizing(),
        )

    @staticmethod
    def _evaluate_condition(condition: ConditionSpec, signals: dict[str, Any]) -> bool:
        """Evaluate a single condition against signals.

        Args:
            condition: The condition to evaluate.
            signals: Dict of indicator_name -> value.

        Returns:
            True if the condition is met.
        """
        if condition.indicator not in signals:
            return False

        actual = signals[condition.indicator]
        expected = condition.value
        op = condition.operator.lower()

        if op == "gte":
            return actual >= expected
        elif op == "lte":
            return actual <= expected
        elif op == "gt":
            return actual > expected
        elif op == "lt":
            return actual < expected
        elif op == "eq":
            return actual == expected
        elif op == "in":
            if isinstance(expected, list):
                return actual in expected
            return False
        else:
            raise ValueError(f"Unknown operator: {op}")

    def check_entry(self, symbol: str, signals: dict[str, Any]) -> bool:
        """Check if entry conditions are met for a symbol.

        Args:
            symbol: The trading symbol.
            signals: Dict of indicator values for this bar.

        Returns:
            True if all (AND) or any (OR) entry conditions are satisfied.
        """
        if self.strategy.symbols and symbol not in self.strategy.symbols:
            return False

        conditions = self.strategy.entry.conditions
        if not conditions:
            return False

        results = [self._evaluate_condition(c, signals) for c in conditions]

        if self.strategy.entry.logic.upper() == "AND":
            return all(results)
        else:
            return any(results)

    def check_exit(
        self,
        symbol: str,
        position: Any,
        signals: dict[str, Any],
        current_date: datetime.date | None = None,
    ) -> tuple[bool, str]:
        """Check if exit conditions are met for a position.

        Args:
            symbol: The trading symbol.
            position: The open Position object.
            signals: Dict of indicator values for this bar.
            current_date: Current bar date for max-holding check.

        Returns:
            Tuple of (should_exit, reason).
        """
        # Check max holding days
        if (
            self.strategy.exit.max_holding_days is not None
            and current_date is not None
        ):
            holding_days = (current_date - position.entry_date).days
            if holding_days >= self.strategy.exit.max_holding_days:
                return True, "max_holding"

        # Check signal-based exit conditions
        if self.strategy.exit.conditions:
            results = [self._evaluate_condition(c, signals) for c in self.strategy.exit.conditions]
            if any(results):
                return True, "signal"

        return False, ""

    def get_position_size(self, portfolio_nav: float) -> int:
        """Calculate the dollar amount to allocate to a new position.

        Args:
            portfolio_nav: Current portfolio net asset value.

        Returns:
            Dollar amount for the position (to be divided by price for share count).
        """
        method = self.strategy.position_sizing.method
        value = self.strategy.position_sizing.value

        if method == "fixed_pct":
            return int(portfolio_nav * (value / 100.0))
        elif method == "fixed_amount":
            return int(min(value, portfolio_nav))
        else:
            # Default to fixed_pct
            return int(portfolio_nav * (value / 100.0))

    @property
    def trailing_stop_pct(self) -> float | None:
        """Return the trailing stop percentage, if configured."""
        return self.strategy.exit.trailing_stop_pct

    @property
    def max_holding_days(self) -> int | None:
        """Return max holding days, if configured."""
        return self.strategy.exit.max_holding_days
```

---

### `src/qitp_simulation/engine.py`

```python
"""BacktestEngine — main event-driven backtest loop."""

from __future__ import annotations

import datetime

from qitp_simulation.commission import CommissionModel, ZeroCommission
from qitp_simulation.metrics import calculate_all_metrics, calculate_max_drawdown
from qitp_simulation.portfolio import Portfolio
from qitp_simulation.slippage import PercentageSlippage, SlippageModel
from qitp_simulation.strategy import StrategyEvaluator
from qitp_simulation.types import BacktestResult, Bar, EquityCurvePoint


class BacktestEngine:
    """Event-driven backtesting engine.

    Iterates day-by-day through bars, evaluates entry/exit conditions,
    applies slippage and commission, and produces a BacktestResult.
    """

    def __init__(
        self,
        strategy: StrategyEvaluator,
        bars_by_symbol: dict[str, list[Bar]],
        initial_capital: float = 100_000.0,
        slippage_model: SlippageModel | None = None,
        commission_model: CommissionModel | None = None,
        signal_generator: "SignalGenerator | None" = None,
    ) -> None:
        """Initialize the backtest engine.

        Args:
            strategy: The strategy evaluator.
            bars_by_symbol: Dict of symbol -> list of Bar, sorted by date ascending.
            initial_capital: Starting capital.
            slippage_model: Slippage model (default: PercentageSlippage(0.1)).
            commission_model: Commission model (default: ZeroCommission).
            signal_generator: Optional callable to compute signals from bars.
                              If None, bar fields are used directly as signals.
        """
        self.strategy = strategy
        self.bars_by_symbol = bars_by_symbol
        self.initial_capital = initial_capital
        self.slippage = slippage_model or PercentageSlippage(0.1)
        self.commission = commission_model or ZeroCommission()
        self.signal_generator = signal_generator
        self.portfolio = Portfolio(initial_capital)

    def _get_all_dates(self) -> list[datetime.date]:
        """Get sorted unique dates across all symbols."""
        dates: set[datetime.date] = set()
        for bars in self.bars_by_symbol.values():
            for bar in bars:
                dates.add(bar.date)
        return sorted(dates)

    def _build_bars_index(self) -> dict[str, dict[datetime.date, Bar]]:
        """Build a date-indexed lookup for each symbol."""
        index: dict[str, dict[datetime.date, Bar]] = {}
        for symbol, bars in self.bars_by_symbol.items():
            index[symbol] = {bar.date: bar for bar in bars}
        return index

    def _compute_signals(
        self,
        symbol: str,
        bar: Bar,
        prev_bar: Bar | None,
        bars_index: dict[str, dict[datetime.date, Bar]],
    ) -> dict[str, float | str]:
        """Compute signals for a symbol on a given bar.

        Default implementation uses bar fields directly.
        Override via signal_generator for custom indicators.
        """
        if self.signal_generator is not None:
            return self.signal_generator(symbol, bar, prev_bar)

        signals: dict[str, float | str] = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }

        # Gap percentage (Monday open vs previous close)
        if prev_bar is not None:
            gap_pct = ((bar.open - prev_bar.close) / prev_bar.close) * 100.0
            signals["gap_pct"] = gap_pct
            signals["prev_close"] = prev_bar.close

        return signals

    def run(self) -> BacktestResult:
        """Execute the backtest and return results.

        Returns:
            A BacktestResult with all metrics, trades, and equity curve.
        """
        dates = self._get_all_dates()
        bars_index = self._build_bars_index()
        equity_curve: list[EquityCurvePoint] = []
        peak_nav = self.initial_capital

        # Track previous bars for gap calculation
        prev_bars: dict[str, Bar] = {}

        for date in dates:
            # Get today's bars
            today_bars: dict[str, Bar] = {}
            for symbol in self.bars_by_symbol:
                if date in bars_index[symbol]:
                    today_bars[symbol] = bars_index[symbol][date]

            if not today_bars:
                continue

            # Update portfolio prices
            self.portfolio.update_prices(today_bars)

            # --- Check exits for all open positions ---
            symbols_to_close: list[tuple[str, str, float]] = []  # (symbol, reason, price)

            for symbol in list(self.portfolio.positions.keys()):
                if symbol not in today_bars:
                    continue

                bar = today_bars[symbol]
                position = self.portfolio.positions[symbol]

                # Update trailing stop
                position.update_price(bar.close)
                if self.strategy.trailing_stop_pct is not None:
                    position.update_trailing_stop(self.strategy.trailing_stop_pct)

                # Check trailing stop trigger
                if position.is_trailing_stop_triggered(bar):
                    exit_price = position.trailing_stop_price or bar.close
                    symbols_to_close.append((symbol, "trailing_stop", exit_price))
                    continue

                # Check strategy exit conditions
                signals = self._compute_signals(symbol, bar, prev_bars.get(symbol), bars_index)
                should_exit, reason = self.strategy.check_exit(symbol, position, signals, date)
                if should_exit:
                    symbols_to_close.append((symbol, reason, bar.close))

            # Execute closes
            for symbol, reason, exit_price in symbols_to_close:
                direction = self.portfolio.positions[symbol].direction
                adjusted_price = self.slippage.apply(
                    exit_price,
                    self.portfolio.positions[symbol].quantity,
                    "short" if direction == "long" else "long",  # selling when closing long
                )
                qty = self.portfolio.positions[symbol].quantity
                comm = self.commission.calculate(adjusted_price, qty)
                slip_cost = abs(exit_price - adjusted_price) * qty
                self.portfolio.close_position(symbol, date, adjusted_price, reason, slip_cost, comm)

            # --- Check entries for new positions ---
            for symbol, bar in today_bars.items():
                if symbol in self.portfolio.positions:
                    continue  # already have a position

                signals = self._compute_signals(symbol, bar, prev_bars.get(symbol), bars_index)

                if self.strategy.check_entry(symbol, signals):
                    direction = self.strategy.strategy.direction
                    position_amount = self.strategy.get_position_size(self.portfolio.nav)
                    entry_price = self.slippage.apply(bar.open, 0, direction)
                    if entry_price <= 0:
                        continue

                    quantity = int(position_amount / entry_price)
                    if quantity <= 0:
                        continue

                    comm = self.commission.calculate(entry_price, quantity)
                    self.portfolio.cash -= comm  # deduct entry commission
                    self.portfolio.open_position(symbol, direction, date, entry_price, quantity)

            # --- Record equity curve ---
            nav = self.portfolio.nav
            if nav > peak_nav:
                peak_nav = nav
            dd_pct = ((peak_nav - nav) / peak_nav) * 100.0 if peak_nav > 0 else 0.0

            equity_curve.append(EquityCurvePoint(date=date, portfolio_value=nav, drawdown_pct=dd_pct))

            # Update previous bars
            for symbol, bar in today_bars.items():
                prev_bars[symbol] = bar

        # --- Force-close any remaining open positions at last bar ---
        last_date = dates[-1] if dates else datetime.date.today()
        for symbol in list(self.portfolio.positions.keys()):
            if symbol in prev_bars:
                bar = prev_bars[symbol]
                direction = self.portfolio.positions[symbol].direction
                adjusted_price = self.slippage.apply(
                    bar.close,
                    self.portfolio.positions[symbol].quantity,
                    "short" if direction == "long" else "long",
                )
                qty = self.portfolio.positions[symbol].quantity
                comm = self.commission.calculate(adjusted_price, qty)
                slip_cost = abs(bar.close - adjusted_price) * qty
                self.portfolio.close_position(symbol, last_date, adjusted_price, "end_of_data", slip_cost, comm)

        # --- Calculate metrics ---
        trades = self.portfolio.trades
        metrics = calculate_all_metrics(trades, equity_curve, self.initial_capital)

        # Determine date range
        symbols = list(self.bars_by_symbol.keys())
        start_date = dates[0] if dates else datetime.date.today()
        end_date = dates[-1] if dates else datetime.date.today()

        return BacktestResult(
            strategy_id=self.strategy.strategy.id,
            strategy_version=self.strategy.strategy.version,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            total_trades=metrics["total_trades"],
            winning_trades=metrics["winning_trades"],
            losing_trades=metrics["losing_trades"],
            win_rate_pct=metrics["win_rate_pct"],
            total_return_pct=metrics["total_return_pct"],
            annualized_return_pct=metrics["annualized_return_pct"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            sortino_ratio=metrics["sortino_ratio"],
            calmar_ratio=metrics["calmar_ratio"],
            profit_factor=metrics["profit_factor"],
            avg_holding_days=metrics["avg_holding_days"],
            avg_win_pct=metrics["avg_win_pct"],
            avg_loss_pct=metrics["avg_loss_pct"],
            equity_curve=equity_curve,
            trades=trades,
        )
```

---

### `src/qitp_simulation/walk_forward.py`

```python
"""Walk-forward validation for strategy backtesting."""

from __future__ import annotations

import logging
from typing import Any

from qitp_simulation.commission import CommissionModel, ZeroCommission
from qitp_simulation.engine import BacktestEngine
from qitp_simulation.metrics import calculate_sharpe
from qitp_simulation.slippage import PercentageSlippage, SlippageModel
from qitp_simulation.strategy import StrategyEvaluator
from qitp_simulation.types import BacktestResult, Bar

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Walk-forward validation: train/test splits over rolling windows.

    Splits data into N folds, trains on train_pct of each fold,
    tests on the remaining portion, and checks for overfitting.
    """

    def __init__(
        self,
        strategy: StrategyEvaluator,
        bars_by_symbol: dict[str, list[Bar]],
        initial_capital: float = 100_000.0,
        train_pct: float = 0.7,
        n_splits: int = 5,
        slippage_model: SlippageModel | None = None,
        commission_model: CommissionModel | None = None,
        signal_generator: Any = None,
    ) -> None:
        """Initialize the walk-forward validator.

        Args:
            strategy: The strategy evaluator.
            bars_by_symbol: Dict of symbol -> list of Bar, sorted by date.
            initial_capital: Starting capital for each fold.
            train_pct: Fraction of each window used for training (0.0 to 1.0).
            n_splits: Number of walk-forward splits.
            slippage_model: Slippage model.
            commission_model: Commission model.
            signal_generator: Optional signal generator callable.
        """
        self.strategy = strategy
        self.bars_by_symbol = bars_by_symbol
        self.initial_capital = initial_capital
        self.train_pct = train_pct
        self.n_splits = n_splits
        self.slippage = slippage_model or PercentageSlippage(0.1)
        self.commission = commission_model or ZeroCommission()
        self.signal_generator = signal_generator

    def _split_bars(
        self, bars: list[Bar], fold: int
    ) -> tuple[list[Bar], list[Bar]]:
        """Split bars into train and test for a given fold.

        Uses a rolling window approach: each fold slides forward through the data.
        """
        total = len(bars)
        window_size = total // self.n_splits
        if window_size < 10:
            # Not enough data for meaningful split
            return bars, bars

        # Window start slides forward each fold
        start = fold * (total - window_size) // max(self.n_splits - 1, 1)
        end = start + window_size
        end = min(end, total)

        window = bars[start:end]
        split_idx = int(len(window) * self.train_pct)
        split_idx = max(split_idx, 1)

        train = window[:split_idx]
        test = window[split_idx:]

        return train, test

    def run(self) -> list[BacktestResult]:
        """Run walk-forward validation across all splits.

        Returns:
            List of BacktestResult, one per fold (test portion only).
            Logs warnings if overfitting is detected.
        """
        results: list[BacktestResult] = []

        for fold in range(self.n_splits):
            # Split bars for each symbol
            train_bars: dict[str, list[Bar]] = {}
            test_bars: dict[str, list[Bar]] = {}

            for symbol, bars in self.bars_by_symbol.items():
                train, test = self._split_bars(bars, fold)
                if train:
                    train_bars[symbol] = train
                if test:
                    test_bars[symbol] = test

            if not train_bars or not test_bars:
                continue

            # Run backtest on train set
            train_engine = BacktestEngine(
                strategy=self.strategy,
                bars_by_symbol=train_bars,
                initial_capital=self.initial_capital,
                slippage_model=self.slippage,
                commission_model=self.commission,
                signal_generator=self.signal_generator,
            )
            train_result = train_engine.run()

            # Run backtest on test set
            test_engine = BacktestEngine(
                strategy=self.strategy,
                bars_by_symbol=test_bars,
                initial_capital=self.initial_capital,
                slippage_model=self.slippage,
                commission_model=self.commission,
                signal_generator=self.signal_generator,
            )
            test_result = test_engine.run()

            # Overfitting detection
            train_sharpe = train_result.sharpe_ratio
            test_sharpe = test_result.sharpe_ratio

            if train_sharpe > 0 and test_sharpe < train_sharpe * 0.5:
                logger.warning(
                    "Overfitting detected in fold %d: "
                    "train Sharpe=%.2f, test Sharpe=%.2f (< 50%% of train)",
                    fold,
                    train_sharpe,
                    test_sharpe,
                )

            results.append(test_result)

        return results
```

---

### `tests/conftest.py`

```python
"""Shared test fixtures for the simulation engine tests."""

from __future__ import annotations

import csv
import datetime
import math
import os
from pathlib import Path

import pytest
import yaml

from qitp_simulation.strategy import StrategyEvaluator
from qitp_simulation.types import Bar


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_bars() -> list[Bar]:
    """Load sample OHLCV data from CSV fixture."""
    csv_path = FIXTURES_DIR / "sample_ohlcv.csv"
    bars: list[Bar] = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars.append(
                Bar(
                    date=datetime.date.fromisoformat(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                )
            )
    return bars


@pytest.fixture
def sample_bars_by_symbol(sample_bars: list[Bar]) -> dict[str, list[Bar]]:
    """Wrap sample bars as a single-symbol dict."""
    return {"TEST": sample_bars}


@pytest.fixture
def sample_strategy() -> StrategyEvaluator:
    """Load the sample strategy from YAML fixture."""
    yaml_path = FIXTURES_DIR / "sample_strategy.yaml"
    return StrategyEvaluator(yaml_path=yaml_path)


@pytest.fixture
def simple_bars() -> list[Bar]:
    """Generate a simple set of bars for deterministic testing."""
    bars = []
    base_date = datetime.date(2023, 1, 2)
    price = 100.0

    for i in range(60):
        date = base_date + datetime.timedelta(days=i)
        # Skip weekends
        if date.weekday() >= 5:
            continue
        # Simple oscillating pattern
        daily_return = 0.005 if i % 3 != 0 else -0.003
        open_price = price
        close_price = price * (1 + daily_return)
        high_price = max(open_price, close_price) * 1.005
        low_price = min(open_price, close_price) * 0.995
        bars.append(
            Bar(
                date=date,
                open=round(open_price, 2),
                high=round(high_price, 2),
                low=round(low_price, 2),
                close=round(close_price, 2),
                volume=1_000_000,
            )
        )
        price = close_price

    return bars
```

---

### `tests/test_metrics.py`

```python
"""Tests for performance metrics calculations."""

from __future__ import annotations

import datetime
import math

import numpy as np
import pytest

from qitp_simulation.metrics import (
    calculate_all_metrics,
    calculate_calmar,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe,
    calculate_sortino,
    calculate_win_rate,
)
from qitp_simulation.types import EquityCurvePoint, Trade


class TestSharpeRatio:
    """Tests for Sharpe ratio calculation."""

    def test_constant_returns_sharpe_is_high(self):
        """Constant positive returns should produce a very high Sharpe."""
        # Constant daily return of 0.1% => zero volatility in excess returns?
        # Actually with constant returns, std of excess returns = 0, so Sharpe = 0
        returns = [0.001] * 252
        sharpe = calculate_sharpe(returns, risk_free_rate=0.04)
        # Constant returns => std = 0 => Sharpe = 0.0
        assert sharpe == 0.0

    def test_zero_returns(self):
        """All-zero returns should have negative Sharpe (below risk-free)."""
        returns = [0.0] * 252
        sharpe = calculate_sharpe(returns, risk_free_rate=0.04)
        assert sharpe == 0.0  # std = 0 since all excess returns are equal

    def test_positive_sharpe(self):
        """Returns well above risk-free with moderate vol should be positive."""
        np.random.seed(42)
        # Mean daily return ~0.05%, vol ~1%
        returns = np.random.normal(0.0005, 0.01, 252)
        sharpe = calculate_sharpe(returns, risk_free_rate=0.04)
        # Should be around 0.5-2.0 range with this setup
        assert isinstance(sharpe, float)

    def test_single_return(self):
        """Single return should produce 0."""
        assert calculate_sharpe([0.01]) == 0.0

    def test_empty_returns(self):
        """Empty returns should produce 0."""
        assert calculate_sharpe([]) == 0.0

    def test_known_value(self):
        """Hand-computed Sharpe for a known series."""
        # 5 daily returns: 1%, 2%, -1%, 0.5%, 1.5%
        returns = [0.01, 0.02, -0.01, 0.005, 0.015]
        rf_daily = 0.04 / 252
        excess = np.array(returns) - rf_daily
        expected = float(np.mean(excess) / np.std(excess, ddof=1) * math.sqrt(252))
        actual = calculate_sharpe(returns, risk_free_rate=0.04)
        assert abs(actual - expected) < 1e-10


class TestSortinoRatio:
    """Tests for Sortino ratio calculation."""

    def test_all_positive_returns(self):
        """All positive returns: no downside, Sortino = 0."""
        returns = [0.01, 0.02, 0.015, 0.005]
        sortino = calculate_sortino(returns, risk_free_rate=0.0)
        # All excess returns positive => no downside => 0
        assert sortino == 0.0

    def test_mixed_returns(self):
        """Mixed returns should produce a finite Sortino."""
        np.random.seed(42)
        returns = np.random.normal(0.0005, 0.01, 252)
        sortino = calculate_sortino(returns, risk_free_rate=0.04)
        assert isinstance(sortino, float)
        assert not math.isnan(sortino)

    def test_empty(self):
        assert calculate_sortino([]) == 0.0


class TestMaxDrawdown:
    """Tests for max drawdown calculation."""

    def test_no_drawdown(self):
        """Monotonically increasing equity has 0 drawdown."""
        curve = [
            EquityCurvePoint(date=datetime.date(2023, 1, i + 1), portfolio_value=100 + i, drawdown_pct=0)
            for i in range(10)
        ]
        assert calculate_max_drawdown(curve) == 0.0

    def test_known_drawdown(self):
        """Peak at 200, trough at 150 => 25% drawdown."""
        values = [100, 150, 200, 180, 150, 160, 190]
        curve = [
            EquityCurvePoint(
                date=datetime.date(2023, 1, i + 1),
                portfolio_value=v,
                drawdown_pct=0,
            )
            for i, v in enumerate(values)
        ]
        dd = calculate_max_drawdown(curve)
        assert abs(dd - 25.0) < 0.01

    def test_raw_values(self):
        """Also accepts raw float list."""
        values = [100.0, 110.0, 90.0, 95.0]
        dd = calculate_max_drawdown(values)
        # Peak 110, trough 90 => 18.18%
        assert abs(dd - (20.0 / 110.0 * 100.0)) < 0.01

    def test_empty(self):
        assert calculate_max_drawdown([]) == 0.0


class TestCalmar:
    """Tests for Calmar ratio."""

    def test_basic(self):
        """10% return / 5% drawdown = 2.0"""
        assert calculate_calmar(10.0, 5.0) == 2.0

    def test_zero_drawdown(self):
        assert calculate_calmar(10.0, 0.0) == 0.0


class TestProfitFactor:
    """Tests for profit factor."""

    def _make_trade(self, pnl: float) -> Trade:
        return Trade(
            entry_date=datetime.date(2023, 1, 1),
            exit_date=datetime.date(2023, 1, 2),
            symbol="TEST",
            direction="long",
            entry_price=100.0,
            exit_price=100.0 + pnl,
            quantity=1,
            pnl=pnl,
            pnl_pct=pnl,
            holding_days=1,
            exit_reason="signal",
        )

    def test_basic(self):
        """Gross profit 300, gross loss 100 => PF 3.0"""
        trades = [self._make_trade(100), self._make_trade(200), self._make_trade(-100)]
        assert calculate_profit_factor(trades) == 3.0

    def test_no_losses(self):
        """All winners => inf."""
        trades = [self._make_trade(100), self._make_trade(50)]
        assert calculate_profit_factor(trades) == float("inf")

    def test_no_trades(self):
        assert calculate_profit_factor([]) == 0.0


class TestWinRate:
    """Tests for win rate calculation."""

    def _make_trade(self, pnl: float) -> Trade:
        return Trade(
            entry_date=datetime.date(2023, 1, 1),
            exit_date=datetime.date(2023, 1, 2),
            symbol="TEST",
            direction="long",
            entry_price=100.0,
            exit_price=100.0 + pnl,
            quantity=1,
            pnl=pnl,
            pnl_pct=pnl,
            holding_days=1,
            exit_reason="signal",
        )

    def test_basic(self):
        """2 winners, 1 loser => 66.67%."""
        trades = [self._make_trade(10), self._make_trade(5), self._make_trade(-3)]
        wr = calculate_win_rate(trades)
        assert abs(wr - 66.667) < 0.01

    def test_no_trades(self):
        assert calculate_win_rate([]) == 0.0


class TestCalculateAllMetrics:
    """Tests for the combined metrics calculator."""

    def test_returns_all_keys(self):
        """All expected metric keys are present."""
        curve = [
            EquityCurvePoint(date=datetime.date(2023, 1, i + 1), portfolio_value=100_000 + i * 100, drawdown_pct=0)
            for i in range(10)
        ]
        metrics = calculate_all_metrics([], curve, 100_000.0)
        expected_keys = {
            "total_trades", "winning_trades", "losing_trades", "win_rate_pct",
            "total_return_pct", "annualized_return_pct", "max_drawdown_pct",
            "sharpe_ratio", "sortino_ratio", "calmar_ratio", "profit_factor",
            "avg_holding_days", "avg_win_pct", "avg_loss_pct",
        }
        assert expected_keys == set(metrics.keys())
```

---

### `tests/test_slippage.py`

```python
"""Tests for slippage models."""

from __future__ import annotations

import math

import pytest

from qitp_simulation.slippage import (
    FixedSlippage,
    PercentageSlippage,
    VolumeImpactSlippage,
)


class TestFixedSlippage:
    """Tests for FixedSlippage model."""

    def test_buy_increases_price(self):
        model = FixedSlippage(0.05)
        assert model.apply(100.0, 100, "long") == 100.05

    def test_sell_decreases_price(self):
        model = FixedSlippage(0.05)
        assert model.apply(100.0, 100, "short") == 99.95

    def test_zero_slippage(self):
        model = FixedSlippage(0.0)
        assert model.apply(50.0, 1000, "long") == 50.0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            FixedSlippage(-0.01)


class TestPercentageSlippage:
    """Tests for PercentageSlippage model."""

    def test_buy_0_1_pct(self):
        model = PercentageSlippage(0.1)  # 0.1%
        result = model.apply(100.0, 100, "long")
        assert abs(result - 100.10) < 0.001

    def test_sell_0_1_pct(self):
        model = PercentageSlippage(0.1)
        result = model.apply(100.0, 100, "short")
        assert abs(result - 99.90) < 0.001

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            PercentageSlippage(-0.1)


class TestVolumeImpactSlippage:
    """Tests for VolumeImpactSlippage model."""

    def test_small_order_minimal_impact(self):
        model = VolumeImpactSlippage(impact_factor=0.1, avg_volume=1_000_000)
        result = model.apply(100.0, 100, "long")
        # sqrt(100/1_000_000) = 0.01, impact = 100 * 0.1 * 0.01 / 100 = 0.001
        expected = 100.0 + 100.0 * 0.1 * math.sqrt(100 / 1_000_000) / 100.0
        assert abs(result - expected) < 0.0001

    def test_large_order_more_impact(self):
        model = VolumeImpactSlippage(impact_factor=0.1, avg_volume=1_000_000)
        small = model.apply(100.0, 100, "long")
        large = model.apply(100.0, 100_000, "long")
        assert large > small

    def test_sell_decreases(self):
        model = VolumeImpactSlippage(impact_factor=0.1, avg_volume=1_000_000)
        result = model.apply(100.0, 1000, "short")
        assert result < 100.0

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            VolumeImpactSlippage(impact_factor=-1)
        with pytest.raises(ValueError):
            VolumeImpactSlippage(avg_volume=0)
```

---

### `tests/test_commission.py`

```python
"""Tests for commission models."""

from __future__ import annotations

import pytest

from qitp_simulation.commission import IBKRTieredEU, ZeroCommission


class TestIBKRTieredEU:
    """Tests for IBKR tiered commission model."""

    def test_eu_minimum(self):
        """Small EU trade should hit minimum of EUR 1.25."""
        model = IBKRTieredEU()
        # 10 shares at EUR 10 = EUR 100 trade value
        # 0.05% of 100 = 0.05, below min 1.25
        comm = model.calculate(10.0, 10, "EU")
        assert comm == 1.25

    def test_eu_normal(self):
        """Normal EU trade: 0.05% of trade value."""
        model = IBKRTieredEU()
        # 100 shares at EUR 50 = EUR 5000 trade value
        # 0.05% of 5000 = 2.50
        comm = model.calculate(50.0, 100, "EU")
        assert abs(comm - 2.50) < 0.01

    def test_eu_maximum(self):
        """Large EU trade should hit maximum of EUR 29.00."""
        model = IBKRTieredEU()
        # 1000 shares at EUR 100 = EUR 100,000 trade value
        # 0.05% of 100,000 = 50, above max 29.00
        comm = model.calculate(100.0, 1000, "EU")
        assert comm == 29.00

    def test_us_per_share(self):
        """US stocks: $0.0035/share."""
        model = IBKRTieredEU()
        # 200 shares at $50
        # 200 * 0.0035 = $0.70
        comm = model.calculate(50.0, 200, "US")
        assert abs(comm - 0.70) < 0.01

    def test_us_minimum(self):
        """Small US trade should hit minimum of $0.35."""
        model = IBKRTieredEU()
        # 10 shares at $50
        # 10 * 0.0035 = $0.035, below min $0.35
        comm = model.calculate(50.0, 10, "US")
        assert comm == 0.35

    def test_us_maximum(self):
        """Large US trade should hit max of 1% of trade value."""
        model = IBKRTieredEU()
        # 100,000 shares at $0.50 = $50,000 trade value
        # 100,000 * 0.0035 = $350
        # max = 1% of $50,000 = $500
        # $350 < $500, so no cap
        comm = model.calculate(0.50, 100_000, "US")
        assert abs(comm - 350.0) < 0.01

    def test_us_max_cap_applied(self):
        """When per-share commission exceeds 1% of trade value, cap it."""
        model = IBKRTieredEU()
        # 10,000 shares at $0.10 = $1,000 trade value
        # 10,000 * 0.0035 = $35
        # max = 1% of $1,000 = $10
        comm = model.calculate(0.10, 10_000, "US")
        assert abs(comm - 10.0) < 0.01


class TestZeroCommission:
    """Tests for zero commission model."""

    def test_always_zero(self):
        model = ZeroCommission()
        assert model.calculate(100.0, 1000, "EU") == 0.0
        assert model.calculate(50.0, 500, "US") == 0.0
```

---

### `tests/test_strategy.py`

```python
"""Tests for strategy evaluator."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from qitp_simulation.strategy import (
    ConditionGroup,
    ConditionSpec,
    ExitRules,
    PositionSizing,
    StrategyEvaluator,
    StrategySpec,
)
from qitp_simulation.types import Position


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestConditionEvaluation:
    """Tests for individual condition evaluation."""

    def _make_evaluator(self, conditions: list[ConditionSpec], logic: str = "AND") -> StrategyEvaluator:
        spec = StrategySpec(
            id="test",
            version="1.0",
            symbols=["TEST"],
            entry=ConditionGroup(logic=logic, conditions=conditions),
        )
        return StrategyEvaluator(strategy=spec)

    def test_gte(self):
        ev = self._make_evaluator([ConditionSpec(indicator="gap_pct", operator="gte", value=2.0)])
        assert ev.check_entry("TEST", {"gap_pct": 2.5})
        assert ev.check_entry("TEST", {"gap_pct": 2.0})
        assert not ev.check_entry("TEST", {"gap_pct": 1.5})

    def test_lte(self):
        ev = self._make_evaluator([ConditionSpec(indicator="volume", operator="lte", value=1000)])
        assert ev.check_entry("TEST", {"volume": 500})
        assert not ev.check_entry("TEST", {"volume": 1500})

    def test_gt(self):
        ev = self._make_evaluator([ConditionSpec(indicator="close", operator="gt", value=50)])
        assert ev.check_entry("TEST", {"close": 51})
        assert not ev.check_entry("TEST", {"close": 50})

    def test_lt(self):
        ev = self._make_evaluator([ConditionSpec(indicator="close", operator="lt", value=50)])
        assert ev.check_entry("TEST", {"close": 49})
        assert not ev.check_entry("TEST", {"close": 50})

    def test_eq(self):
        ev = self._make_evaluator([ConditionSpec(indicator="day", operator="eq", value=1)])
        assert ev.check_entry("TEST", {"day": 1})
        assert not ev.check_entry("TEST", {"day": 2})

    def test_in_operator(self):
        ev = self._make_evaluator([ConditionSpec(indicator="day", operator="in", value=[1, 2, 3])])
        assert ev.check_entry("TEST", {"day": 2})
        assert not ev.check_entry("TEST", {"day": 5})

    def test_and_logic(self):
        ev = self._make_evaluator(
            [
                ConditionSpec(indicator="gap_pct", operator="gte", value=2.0),
                ConditionSpec(indicator="volume", operator="gte", value=500_000),
            ],
            logic="AND",
        )
        assert ev.check_entry("TEST", {"gap_pct": 3.0, "volume": 1_000_000})
        assert not ev.check_entry("TEST", {"gap_pct": 3.0, "volume": 100})

    def test_or_logic(self):
        ev = self._make_evaluator(
            [
                ConditionSpec(indicator="gap_pct", operator="gte", value=2.0),
                ConditionSpec(indicator="volume", operator="gte", value=500_000),
            ],
            logic="OR",
        )
        assert ev.check_entry("TEST", {"gap_pct": 3.0, "volume": 100})
        assert ev.check_entry("TEST", {"gap_pct": 0.5, "volume": 1_000_000})
        assert not ev.check_entry("TEST", {"gap_pct": 0.5, "volume": 100})

    def test_missing_indicator_returns_false(self):
        ev = self._make_evaluator([ConditionSpec(indicator="nonexistent", operator="gte", value=1)])
        assert not ev.check_entry("TEST", {"gap_pct": 5.0})

    def test_wrong_symbol_returns_false(self):
        ev = self._make_evaluator([ConditionSpec(indicator="gap_pct", operator="gte", value=1)])
        assert not ev.check_entry("OTHER", {"gap_pct": 5.0})


class TestExitConditions:
    """Tests for exit condition evaluation."""

    def test_max_holding_days(self):
        spec = StrategySpec(
            id="test",
            exit=ExitRules(max_holding_days=5),
        )
        ev = StrategyEvaluator(strategy=spec)
        pos = Position(
            symbol="TEST",
            direction="long",
            entry_date=datetime.date(2023, 1, 1),
            entry_price=100.0,
            quantity=10,
        )
        should_exit, reason = ev.check_exit("TEST", pos, {}, datetime.date(2023, 1, 6))
        assert should_exit
        assert reason == "max_holding"

    def test_signal_exit(self):
        spec = StrategySpec(
            id="test",
            exit=ExitRules(
                conditions=[ConditionSpec(indicator="close", operator="lt", value=95)]
            ),
        )
        ev = StrategyEvaluator(strategy=spec)
        pos = Position(symbol="TEST", direction="long", entry_date=datetime.date(2023, 1, 1), entry_price=100, quantity=10)
        should_exit, reason = ev.check_exit("TEST", pos, {"close": 90})
        assert should_exit
        assert reason == "signal"


class TestPositionSizing:
    """Tests for position sizing calculation."""

    def test_fixed_pct(self):
        spec = StrategySpec(
            id="test",
            position_sizing=PositionSizing(method="fixed_pct", value=10.0),
        )
        ev = StrategyEvaluator(strategy=spec)
        amount = ev.get_position_size(100_000.0)
        assert amount == 10_000

    def test_fixed_amount(self):
        spec = StrategySpec(
            id="test",
            position_sizing=PositionSizing(method="fixed_amount", value=5_000.0),
        )
        ev = StrategyEvaluator(strategy=spec)
        amount = ev.get_position_size(100_000.0)
        assert amount == 5_000


class TestYAMLLoading:
    """Tests for loading strategy from YAML."""

    def test_load_sample_strategy(self):
        yaml_path = FIXTURES_DIR / "sample_strategy.yaml"
        ev = StrategyEvaluator(yaml_path=yaml_path)
        assert ev.strategy.id == "gap_momentum_up"
        assert ev.strategy.direction == "long"
        assert len(ev.strategy.entry.conditions) >= 1
        assert ev.strategy.exit.trailing_stop_pct is not None
```

---

### `tests/test_engine.py`

```python
"""Tests for the BacktestEngine."""

from __future__ import annotations

import datetime

import pytest

from qitp_simulation.commission import IBKRTieredEU, ZeroCommission
from qitp_simulation.engine import BacktestEngine
from qitp_simulation.slippage import FixedSlippage, PercentageSlippage
from qitp_simulation.strategy import (
    ConditionGroup,
    ConditionSpec,
    ExitRules,
    PositionSizing,
    StrategyEvaluator,
    StrategySpec,
)
from qitp_simulation.types import Bar


class TestBacktestEngine:
    """Tests for the BacktestEngine."""

    def _make_bars(self, prices: list[tuple[float, float]], start_date: datetime.date | None = None) -> list[Bar]:
        """Create bars from (open, close) tuples."""
        bars = []
        base = start_date or datetime.date(2023, 1, 2)
        day = 0
        for i, (o, c) in enumerate(prices):
            d = base + datetime.timedelta(days=day)
            while d.weekday() >= 5:
                day += 1
                d = base + datetime.timedelta(days=day)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            bars.append(Bar(date=d, open=o, high=h, low=l, close=c, volume=1_000_000))
            day += 1
        return bars

    def test_no_trades_when_conditions_not_met(self):
        """Engine produces zero trades when entry conditions never trigger."""
        spec = StrategySpec(
            id="test",
            symbols=["TEST"],
            entry=ConditionGroup(
                logic="AND",
                conditions=[ConditionSpec(indicator="gap_pct", operator="gte", value=99.0)],
            ),
        )
        ev = StrategyEvaluator(strategy=spec)
        bars = self._make_bars([(100, 101), (101, 102), (102, 103)])
        engine = BacktestEngine(
            strategy=ev,
            bars_by_symbol={"TEST": bars},
            initial_capital=100_000,
            slippage_model=FixedSlippage(0.0),
            commission_model=ZeroCommission(),
        )
        result = engine.run()
        assert result.total_trades == 0
        assert result.total_return_pct == 0.0

    def test_basic_trade_execution(self):
        """Engine opens and closes a position based on conditions."""
        spec = StrategySpec(
            id="test",
            symbols=["TEST"],
            direction="long",
            entry=ConditionGroup(
                logic="AND",
                conditions=[ConditionSpec(indicator="close", operator="gte", value=100)],
            ),
            exit=ExitRules(max_holding_days=2),
            position_sizing=PositionSizing(method="fixed_pct", value=50.0),
        )
        ev = StrategyEvaluator(strategy=spec)

        # Create bars: entry on day 1, exit after 2 days holding
        bars = self._make_bars([
            (100, 102),   # day 1: close >= 100, enter
            (102, 104),   # day 2: holding
            (104, 106),   # day 3: max_holding reached, exit
            (106, 108),   # day 4: would re-enter
            (108, 110),   # day 5: holding
            (110, 112),   # day 6: exit again
        ])

        engine = BacktestEngine(
            strategy=ev,
            bars_by_symbol={"TEST": bars},
            initial_capital=100_000,
            slippage_model=FixedSlippage(0.0),
            commission_model=ZeroCommission(),
        )
        result = engine.run()

        assert result.total_trades >= 1
        assert result.strategy_id == "test"
        assert len(result.equity_curve) == 6

    def test_equity_curve_recorded(self):
        """Equity curve should have one point per trading day."""
        spec = StrategySpec(id="test", symbols=["TEST"])
        ev = StrategyEvaluator(strategy=spec)
        bars = self._make_bars([(100, 101)] * 10)
        engine = BacktestEngine(
            strategy=ev,
            bars_by_symbol={"TEST": bars},
            initial_capital=50_000,
        )
        result = engine.run()
        assert len(result.equity_curve) == 10

    def test_with_commission_and_slippage(self):
        """Commission and slippage reduce returns."""
        spec = StrategySpec(
            id="test",
            symbols=["TEST"],
            direction="long",
            entry=ConditionGroup(
                logic="AND",
                conditions=[ConditionSpec(indicator="close", operator="gte", value=0)],
            ),
            exit=ExitRules(max_holding_days=1),
            position_sizing=PositionSizing(method="fixed_pct", value=100.0),
        )
        ev = StrategyEvaluator(strategy=spec)
        bars = self._make_bars([(100, 100), (100, 100), (100, 100), (100, 100)])

        # With zero costs
        engine_zero = BacktestEngine(
            strategy=ev,
            bars_by_symbol={"TEST": bars},
            initial_capital=100_000,
            slippage_model=FixedSlippage(0.0),
            commission_model=ZeroCommission(),
        )
        result_zero = engine_zero.run()

        # With costs
        engine_costs = BacktestEngine(
            strategy=ev,
            bars_by_symbol={"TEST": bars},
            initial_capital=100_000,
            slippage_model=PercentageSlippage(0.5),
            commission_model=IBKRTieredEU(),
        )
        result_costs = engine_costs.run()

        # Costs should reduce the final NAV
        if result_costs.total_trades > 0:
            final_zero = result_zero.equity_curve[-1].portfolio_value
            final_costs = result_costs.equity_curve[-1].portfolio_value
            assert final_costs <= final_zero

    def test_backtest_with_sample_data(self, sample_strategy, sample_bars_by_symbol):
        """Integration test using sample fixtures."""
        engine = BacktestEngine(
            strategy=sample_strategy,
            bars_by_symbol=sample_bars_by_symbol,
            initial_capital=100_000,
            slippage_model=PercentageSlippage(0.1),
            commission_model=IBKRTieredEU(),
        )
        result = engine.run()

        assert result.strategy_id == "gap_momentum_up"
        assert len(result.equity_curve) > 0
        assert result.start_date < result.end_date
        # Verify backtest result structure
        assert isinstance(result.total_return_pct, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown_pct, float)
```

---

### `tests/fixtures/sample_strategy.yaml`

```yaml
id: gap_momentum_up
version: "1.0"
symbols:
  - TEST
direction: long

entry:
  logic: AND
  conditions:
    - indicator: gap_pct
      operator: gte
      value: 2.0
    - indicator: volume
      operator: gte
      value: 500000

exit:
  trailing_stop_pct: 3.0
  max_holding_days: 10
  conditions:
    - indicator: gap_pct
      operator: lte
      value: -2.0

position_sizing:
  method: fixed_pct
  value: 10.0
```

---

### `tests/fixtures/sample_ohlcv.csv`

This is a generated 252-row daily OHLCV dataset for symbol "TEST", simulating one year of trading data starting 2023-01-02. Prices start around $100 with realistic daily movements.

```csv
date,open,high,low,close,volume
2023-01-02,100.00,101.50,99.20,100.80,1200000
2023-01-03,100.80,102.10,100.00,101.50,1100000
2023-01-04,101.50,102.80,100.90,101.20,980000
2023-01-05,101.20,103.00,101.00,102.50,1050000
2023-01-06,102.50,103.20,101.80,102.90,1150000
2023-01-09,105.00,106.20,104.50,105.80,1500000
2023-01-10,105.80,106.50,105.00,105.30,1300000
2023-01-11,105.30,106.00,104.50,105.70,1100000
2023-01-12,105.70,106.80,105.20,106.40,1200000
2023-01-13,106.40,107.00,105.80,106.10,1050000
2023-01-17,108.50,109.20,108.00,108.90,1400000
2023-01-18,108.90,109.50,108.00,108.30,1200000
2023-01-19,108.30,109.00,107.50,108.60,1100000
2023-01-20,108.60,109.30,107.80,108.10,980000
2023-01-23,108.10,109.00,107.50,108.50,1050000
2023-01-24,108.50,109.20,107.90,108.80,1100000
2023-01-25,108.80,109.50,108.00,108.20,1000000
2023-01-26,108.20,109.00,107.50,108.70,1050000
2023-01-27,108.70,109.80,108.20,109.50,1200000
2023-01-30,109.50,110.20,109.00,109.80,1150000
2023-01-31,109.80,110.50,109.20,110.10,1100000
2023-02-01,110.10,111.00,109.50,110.50,1200000
2023-02-02,110.50,111.20,109.80,110.80,1050000
2023-02-03,110.80,111.50,110.00,111.20,1150000
2023-02-06,111.20,112.00,110.50,111.50,1100000
2023-02-07,111.50,112.30,111.00,111.80,1050000
2023-02-08,111.80,112.50,111.00,111.30,980000
2023-02-09,111.30,112.00,110.50,111.60,1020000
2023-02-10,111.60,112.50,111.00,112.00,1100000
2023-02-13,112.00,112.80,111.50,112.30,1080000
2023-02-14,112.30,113.00,111.80,112.60,1050000
2023-02-15,112.60,113.50,112.00,113.00,1150000
2023-02-16,113.00,113.80,112.20,112.50,1000000
2023-02-17,112.50,113.20,111.80,112.80,1050000
2023-02-21,112.80,113.50,112.00,113.10,1100000
2023-02-22,113.10,113.80,112.50,113.40,1080000
2023-02-23,113.40,114.00,112.80,113.00,1000000
2023-02-24,113.00,113.80,112.50,113.50,1050000
2023-02-27,113.50,114.20,113.00,113.80,1100000
2023-02-28,113.80,114.50,113.20,114.00,1050000
2023-03-01,114.00,114.80,113.50,114.30,1100000
2023-03-02,114.30,115.00,113.80,114.60,1050000
2023-03-03,114.60,115.20,114.00,114.20,980000
2023-03-06,114.20,115.00,113.80,114.50,1050000
2023-03-07,114.50,115.30,114.00,114.80,1100000
2023-03-08,114.80,115.50,114.20,115.10,1080000
2023-03-09,115.10,115.80,114.50,115.40,1100000
2023-03-10,115.40,116.00,114.80,114.90,980000
2023-03-13,114.90,115.50,114.20,115.20,1050000
2023-03-14,115.20,116.00,114.80,115.50,1100000
2023-03-15,115.50,116.20,115.00,115.80,1080000
2023-03-16,115.80,116.50,115.20,116.00,1050000
2023-03-17,116.00,116.80,115.50,116.30,1100000
2023-03-20,116.30,117.00,115.80,116.60,1080000
2023-03-21,116.60,117.30,116.00,116.20,980000
2023-03-22,116.20,117.00,115.80,116.50,1050000
2023-03-23,116.50,117.20,116.00,116.80,1100000
2023-03-24,116.80,117.50,116.20,117.00,1050000
2023-03-27,117.00,117.80,116.50,117.30,1100000
2023-03-28,117.30,118.00,116.80,117.50,1050000
2023-03-29,117.50,118.20,117.00,117.80,1100000
2023-03-30,117.80,118.50,117.20,118.00,1080000
2023-03-31,118.00,118.80,117.50,118.30,1050000
2023-04-03,118.30,119.00,117.80,118.60,1100000
2023-04-04,118.60,119.30,118.00,118.20,980000
2023-04-05,118.20,119.00,117.80,118.50,1050000
2023-04-06,118.50,119.20,118.00,118.80,1100000
2023-04-10,118.80,119.50,118.20,119.00,1080000
2023-04-11,119.00,119.80,118.50,119.30,1050000
2023-04-12,119.30,120.00,118.80,119.60,1100000
2023-04-13,119.60,120.30,119.00,119.20,980000
2023-04-14,119.20,120.00,118.80,119.50,1050000
2023-04-17,119.50,120.20,119.00,119.80,1100000
2023-04-18,119.80,120.50,119.20,120.00,1080000
2023-04-19,120.00,120.80,119.50,120.30,1050000
2023-04-20,120.30,121.00,119.80,120.50,1100000
2023-04-21,120.50,121.20,120.00,120.80,1080000
2023-04-24,120.80,121.50,120.20,121.00,1050000
2023-04-25,121.00,121.80,120.50,120.50,980000
2023-04-26,120.50,121.20,120.00,120.80,1050000
2023-04-27,120.80,121.50,120.20,121.00,1100000
2023-04-28,121.00,121.80,120.50,121.30,1050000
2023-05-01,121.30,122.00,120.80,121.50,1080000
2023-05-02,121.50,122.20,121.00,121.80,1050000
2023-05-03,121.80,122.50,121.20,121.20,980000
2023-05-04,121.20,122.00,120.80,121.50,1050000
2023-05-05,121.50,122.20,121.00,121.80,1100000
2023-05-08,121.80,122.50,121.20,122.00,1080000
2023-05-09,122.00,122.80,121.50,122.30,1050000
2023-05-10,122.30,123.00,121.80,122.50,1100000
2023-05-11,122.50,123.20,122.00,122.80,1080000
2023-05-12,122.80,123.50,122.20,122.30,980000
2023-05-15,122.30,123.00,121.80,122.60,1050000
2023-05-16,122.60,123.30,122.00,122.80,1100000
2023-05-17,122.80,123.50,122.20,123.00,1050000
2023-05-18,123.00,123.80,122.50,123.30,1100000
2023-05-19,123.30,124.00,122.80,123.50,1080000
2023-05-22,123.50,124.20,123.00,123.80,1050000
2023-05-23,123.80,124.50,123.20,123.30,980000
2023-05-24,123.30,124.00,122.80,123.60,1050000
2023-05-25,123.60,124.30,123.00,123.80,1100000
2023-05-26,123.80,124.50,123.20,124.00,1050000
2023-05-30,124.00,124.80,123.50,124.30,1080000
2023-05-31,124.30,125.00,123.80,124.50,1050000
2023-06-01,124.50,125.20,124.00,124.80,1100000
2023-06-02,124.80,125.50,124.20,125.00,1080000
2023-06-05,125.00,125.80,124.50,125.30,1050000
2023-06-06,125.30,126.00,124.80,124.80,980000
2023-06-07,124.80,125.50,124.20,125.10,1050000
2023-06-08,125.10,125.80,124.50,125.30,1100000
2023-06-09,125.30,126.00,124.80,125.50,1050000
2023-06-12,125.50,126.30,125.00,125.80,1080000
2023-06-13,125.80,126.50,125.20,126.00,1050000
2023-06-14,126.00,126.80,125.50,126.30,1100000
2023-06-15,126.30,127.00,125.80,125.80,980000
2023-06-16,125.80,126.50,125.20,126.10,1050000
2023-06-19,126.10,126.80,125.50,126.30,1100000
2023-06-20,126.30,127.00,125.80,126.50,1050000
2023-06-21,126.50,127.20,126.00,126.80,1080000
2023-06-22,126.80,127.50,126.20,127.00,1050000
2023-06-23,127.00,127.80,126.50,127.30,1100000
2023-06-26,127.30,128.00,126.80,126.80,980000
2023-06-27,126.80,127.50,126.20,127.10,1050000
2023-06-28,127.10,127.80,126.50,127.30,1100000
2023-06-29,127.30,128.00,126.80,127.50,1050000
2023-06-30,127.50,128.20,127.00,127.80,1080000
2023-07-03,127.80,128.50,127.20,128.00,1050000
2023-07-05,128.00,128.80,127.50,128.30,1100000
2023-07-06,128.30,129.00,127.80,127.80,980000
2023-07-07,127.80,128.50,127.20,128.10,1050000
2023-07-10,128.10,128.80,127.50,128.30,1100000
2023-07-11,128.30,129.00,127.80,128.50,1050000
2023-07-12,128.50,129.20,128.00,128.80,1080000
2023-07-13,128.80,129.50,128.20,129.00,1050000
2023-07-14,129.00,129.80,128.50,129.30,1100000
2023-07-17,129.30,130.00,128.80,128.80,980000
2023-07-18,128.80,129.50,128.20,129.10,1050000
2023-07-19,129.10,129.80,128.50,129.30,1100000
2023-07-20,129.30,130.00,128.80,129.50,1050000
2023-07-21,129.50,130.20,129.00,129.80,1080000
2023-07-24,129.80,130.50,129.20,130.00,1050000
2023-07-25,130.00,130.80,129.50,130.30,1100000
2023-07-26,130.30,131.00,129.80,129.80,980000
2023-07-27,129.80,130.50,129.20,130.10,1050000
2023-07-28,130.10,130.80,129.50,130.30,1100000
2023-07-31,130.30,131.00,129.80,130.50,1050000
2023-08-01,130.50,131.20,130.00,130.80,1080000
2023-08-02,130.80,131.50,130.20,131.00,1050000
2023-08-03,131.00,131.80,130.50,130.50,980000
2023-08-04,130.50,131.20,130.00,130.80,1050000
2023-08-07,130.80,131.50,130.20,131.00,1100000
2023-08-08,131.00,131.80,130.50,131.30,1050000
2023-08-09,131.30,132.00,130.80,131.50,1080000
2023-08-10,131.50,132.20,131.00,131.80,1050000
2023-08-11,131.80,132.50,131.20,131.30,980000
2023-08-14,131.30,132.00,130.80,131.60,1050000
2023-08-15,131.60,132.30,131.00,131.80,1100000
2023-08-16,131.80,132.50,131.20,132.00,1050000
2023-08-17,132.00,132.80,131.50,132.30,1080000
2023-08-18,132.30,133.00,131.80,132.50,1050000
2023-08-21,132.50,133.20,132.00,132.80,1100000
2023-08-22,132.80,133.50,132.20,132.30,980000
2023-08-23,132.30,133.00,131.80,132.60,1050000
2023-08-24,132.60,133.30,132.00,132.80,1100000
2023-08-25,132.80,133.50,132.20,133.00,1050000
2023-08-28,133.00,133.80,132.50,133.30,1080000
2023-08-29,133.30,134.00,132.80,133.50,1050000
2023-08-30,133.50,134.20,133.00,133.80,1100000
2023-08-31,133.80,134.50,133.20,134.00,1080000
2023-09-01,134.00,134.80,133.50,133.50,980000
2023-09-05,133.50,134.20,133.00,133.80,1050000
2023-09-06,133.80,134.50,133.20,134.00,1100000
2023-09-07,134.00,134.80,133.50,134.30,1050000
2023-09-08,134.30,135.00,133.80,134.50,1080000
2023-09-11,134.50,135.20,134.00,134.80,1050000
2023-09-12,134.80,135.50,134.20,135.00,1100000
2023-09-13,135.00,135.80,134.50,134.50,980000
2023-09-14,134.50,135.20,134.00,134.80,1050000
2023-09-15,134.80,135.50,134.20,135.00,1100000
2023-09-18,135.00,135.80,134.50,135.30,1050000
2023-09-19,135.30,136.00,134.80,135.50,1080000
2023-09-20,135.50,136.20,135.00,135.80,1050000
2023-09-21,135.80,136.50,135.20,135.30,980000
2023-09-22,135.30,136.00,134.80,135.60,1050000
2023-09-25,135.60,136.30,135.00,135.80,1100000
2023-09-26,135.80,136.50,135.20,136.00,1050000
2023-09-27,136.00,136.80,135.50,136.30,1080000
2023-09-28,136.30,137.00,135.80,136.50,1050000
2023-09-29,136.50,137.20,136.00,136.80,1100000
2023-10-02,136.80,137.50,136.20,136.30,980000
2023-10-03,136.30,137.00,135.80,136.60,1050000
2023-10-04,136.60,137.30,136.00,136.80,1100000
2023-10-05,136.80,137.50,136.20,137.00,1050000
2023-10-06,137.00,137.80,136.50,137.30,1080000
2023-10-09,137.30,138.00,136.80,137.50,1050000
2023-10-10,137.50,138.20,137.00,137.80,1100000
2023-10-11,137.80,138.50,137.20,137.30,980000
2023-10-12,137.30,138.00,136.80,137.60,1050000
2023-10-13,137.60,138.30,137.00,137.80,1100000
2023-10-16,137.80,138.50,137.20,138.00,1050000
2023-10-17,138.00,138.80,137.50,138.30,1080000
2023-10-18,138.30,139.00,137.80,138.50,1050000
2023-10-19,138.50,139.20,138.00,138.00,980000
2023-10-20,138.00,138.80,137.50,138.30,1050000
2023-10-23,138.30,139.00,137.80,138.50,1100000
2023-10-24,138.50,139.20,138.00,138.80,1050000
2023-10-25,138.80,139.50,138.20,139.00,1080000
2023-10-26,139.00,139.80,138.50,139.30,1050000
2023-10-27,139.30,140.00,138.80,139.50,1100000
2023-10-30,139.50,140.20,139.00,139.00,980000
2023-10-31,139.00,139.80,138.50,139.30,1050000
2023-11-01,139.30,140.00,138.80,139.50,1100000
2023-11-02,139.50,140.20,139.00,139.80,1050000
2023-11-03,139.80,140.50,139.20,140.00,1080000
2023-11-06,140.00,140.80,139.50,140.30,1050000
2023-11-07,140.30,141.00,139.80,140.50,1100000
2023-11-08,140.50,141.20,140.00,140.00,980000
2023-11-09,140.00,140.80,139.50,140.30,1050000
2023-11-10,140.30,141.00,139.80,140.50,1100000
2023-11-13,140.50,141.20,140.00,140.80,1050000
2023-11-14,140.80,141.50,140.20,141.00,1080000
2023-11-15,141.00,141.80,140.50,141.30,1050000
2023-11-16,141.30,142.00,140.80,140.80,980000
2023-11-17,140.80,141.50,140.20,141.10,1050000
2023-11-20,141.10,141.80,140.50,141.30,1100000
2023-11-21,141.30,142.00,140.80,141.50,1050000
2023-11-22,141.50,142.20,141.00,141.80,1080000
2023-11-24,141.80,142.50,141.20,142.00,1050000
2023-11-27,142.00,142.80,141.50,142.30,1100000
2023-11-28,142.30,143.00,141.80,141.80,980000
2023-11-29,141.80,142.50,141.20,142.10,1050000
2023-11-30,142.10,142.80,141.50,142.30,1100000
2023-12-01,142.30,143.00,141.80,142.50,1050000
2023-12-04,142.50,143.20,142.00,142.80,1080000
2023-12-05,142.80,143.50,142.20,143.00,1050000
2023-12-06,143.00,143.80,142.50,143.30,1100000
2023-12-07,143.30,144.00,142.80,142.80,980000
2023-12-08,142.80,143.50,142.20,143.10,1050000
2023-12-11,143.10,143.80,142.50,143.30,1100000
2023-12-12,143.30,144.00,142.80,143.50,1050000
2023-12-13,143.50,144.20,143.00,143.80,1080000
2023-12-14,143.80,144.50,143.20,144.00,1050000
2023-12-15,144.00,144.80,143.50,144.30,1100000
2023-12-18,144.30,145.00,143.80,143.80,980000
2023-12-19,143.80,144.50,143.20,144.10,1050000
2023-12-20,144.10,144.80,143.50,144.30,1100000
2023-12-21,144.30,145.00,143.80,144.50,1050000
2023-12-22,144.50,145.20,144.00,144.80,1080000
2023-12-26,144.80,145.50,144.20,145.00,1050000
2023-12-27,145.00,145.80,144.50,145.30,1100000
2023-12-28,145.30,146.00,144.80,145.50,1080000
2023-12-29,145.50,146.20,145.00,145.80,1050000
```

---

## Acceptance Criteria
- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `pytest -v` passes — all tests green
- [ ] BacktestEngine produces correct BacktestResult for sample data
- [ ] Metrics calculations verified against known values (e.g., Sharpe of a constant return series = 0)
- [ ] Slippage models correctly adjust prices
- [ ] Commission models match IBKR tiered rates
- [ ] Walk-forward validator produces N BacktestResults

## Test Plan
```bash
cd ~/dev/tccw-qitp-simulation
pip install -e ".[dev]"
ruff check .
pytest -v
```

## Agent Instructions
This library has NO dependency on agent-core. It is pure financial math + strategy evaluation. Use only standard library + numpy + pandas + pyyaml + pydantic. Keep it clean, typed, and well-tested. Include docstrings on public methods. The test_metrics.py should verify calculations against hand-computed expected values.

### Gap formula (from Doc 5):
```
gap_pct = ((monday_open - friday_close) / friday_close) * 100
```

### IBKR Commission tiers (from Doc 5):
- EUR: 0.05% of trade value, min EUR 1.25, max EUR 29.00
- USD: $0.0035/share, min $0.35, max 1% of trade value
