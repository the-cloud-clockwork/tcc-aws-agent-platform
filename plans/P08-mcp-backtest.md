# P08 — Backtest MCP Server

## Objective

Build `backtest-mcp`: wraps the `tccw-qitp-simulation` library as an MCP server. 4 tools for running backtests, retrieving results, walk-forward validation, and strategy comparison. Async job execution with polling.

## Plane Tickets

ROOT-57 (shared with P03)

## Target Repo

`~/dev/tccw-qitp-mcp-backtest`

## Dependencies

- P03 (`tccw-qitp-simulation` — backtest engine, slippage/commission models)
- P06 (`tccw-mcp-artifacts` — result storage via artifacts MCP)

## Repo Structure

```
tccw-qitp-mcp-backtest/
├── src/
│   └── qitp_mcp_backtest/
│       ├── __init__.py
│       ├── server.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── run_backtest.py
│       │   ├── get_result.py
│       │   ├── walk_forward.py
│       │   └── compare.py
│       ├── job_manager.py
│       ├── data_loader.py
│       └── schemas.py
├── tests/
│   ├── conftest.py
│   ├── test_run_backtest.py
│   ├── test_walk_forward.py
│   └── fixtures/
│       ├── sample_ohlcv.parquet
│       └── gap_momentum_up.yaml
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Full Inline Code

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-backtest"
version = "0.1.0"
description = "MCP server wrapping qitp-simulation for backtesting"
requires-python = ">=3.11"
dependencies = [
    "mcp[server]>=1.0.0",
    "pydantic>=2.0",
    "boto3>=1.34",
    "pyarrow>=15.0",
    "pandas>=2.2",
    "pyyaml>=6.0",
    "qitp-simulation>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "moto[s3]>=5.0",
]

[project.scripts]
qitp-mcp-backtest = "qitp_mcp_backtest.server:main"
```

### `src/qitp_mcp_backtest/__init__.py`

```python
"""QITP Backtest MCP Server — wraps qitp-simulation as an MCP service."""

__version__ = "0.1.0"
```

### `src/qitp_mcp_backtest/schemas.py`

```python
"""Pydantic schemas for backtest requests, results, and job tracking."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────────────

class BacktestConfig(BaseModel):
    """Execution parameters for a single backtest run."""

    initial_capital: float = 100_000.0
    slippage_model: Literal["fixed", "percentage", "volume_impact"] = "percentage"
    slippage_value: float = 0.001  # 0.1 %
    commission_model: Literal["ibkr_tiered_eu", "zero"] = "ibkr_tiered_eu"


class BacktestRunRequest(BaseModel):
    """Payload accepted by the run_backtest tool."""

    strategy_id: str = Field(..., description="Strategy blueprint ID in S3")
    symbols: list[str] = Field(..., min_length=1)
    start_date: date
    end_date: date
    config: BacktestConfig = BacktestConfig()


class WalkForwardConfig(BaseModel):
    """Parameters for walk-forward validation."""

    train_pct: float = 0.7
    n_splits: int = 5
    initial_capital: float = 100_000.0
    slippage_model: Literal["fixed", "percentage", "volume_impact"] = "percentage"
    slippage_value: float = 0.001
    commission_model: Literal["ibkr_tiered_eu", "zero"] = "ibkr_tiered_eu"


class WalkForwardRequest(BaseModel):
    """Payload accepted by the run_walk_forward tool."""

    strategy_id: str
    symbols: list[str] = Field(..., min_length=1)
    start_date: date
    end_date: date
    config: WalkForwardConfig = WalkForwardConfig()


class CompareRequest(BaseModel):
    """Payload accepted by the compare_strategies tool."""

    run_ids: list[str] = Field(..., min_length=2)


# ── Result Schemas ───────────────────────────────────────────────────────────

class TradeRecord(BaseModel):
    """Single trade entry."""

    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0


class PerformanceMetrics(BaseModel):
    """Summary performance metrics for a backtest run."""

    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    avg_trade_duration_days: float


class BacktestResult(BaseModel):
    """Full result payload for a completed backtest."""

    run_id: str
    strategy_id: str
    symbols: list[str]
    start_date: date
    end_date: date
    metrics: PerformanceMetrics
    equity_curve: list[dict]  # [{date, equity}]
    trades: list[TradeRecord]


class BacktestRunResult(BaseModel):
    """Immediate response from run_backtest (before job completes)."""

    run_id: str
    status: Literal["queued", "running", "complete", "error"]
    strategy_id: str
    started_at: datetime | None = None
    message: str | None = None


class StatusResult(BaseModel):
    """Polling response when job is still running."""

    run_id: str
    status: Literal["queued", "running", "complete", "error"]
    message: str | None = None


class WalkForwardFoldResult(BaseModel):
    """Result for a single walk-forward fold."""

    fold_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    in_sample_metrics: PerformanceMetrics
    out_of_sample_metrics: PerformanceMetrics


class WalkForwardResult(BaseModel):
    """Aggregated walk-forward validation result."""

    run_id: str
    strategy_id: str
    symbols: list[str]
    n_splits: int
    folds: list[WalkForwardFoldResult]
    overfitting_flag: bool
    overfitting_score: float  # ratio of IS vs OOS Sharpe degradation
    aggregate_oos_metrics: PerformanceMetrics


class ComparisonResult(BaseModel):
    """Side-by-side comparison of multiple backtest runs."""

    run_ids: list[str]
    rankings: dict[str, list[str]]  # metric_name -> ordered run_ids (best first)
    summary: list[dict]  # per-run summary dicts
```

### `src/qitp_mcp_backtest/job_manager.py`

```python
"""In-memory async job manager with thread-based execution.

POC uses a simple dict + threading. Production upgrades to DynamoDB.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from qitp_mcp_backtest.schemas import BacktestRunResult

logger = logging.getLogger(__name__)


class Job:
    """Tracks a single backtest job."""

    __slots__ = ("run_id", "status", "strategy_id", "started_at", "completed_at",
                 "result", "error", "_thread")

    def __init__(self, run_id: str, strategy_id: str) -> None:
        self.run_id = run_id
        self.strategy_id = strategy_id
        self.status: str = "queued"
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.result: Any = None
        self.error: str | None = None
        self._thread: threading.Thread | None = None


class JobManager:
    """Thread-safe job manager backed by an in-memory dict.

    Usage::

        mgr = JobManager()
        run_id = mgr.submit(strategy_id="gap_momentum_up", fn=run_engine, kwargs={...})
        job = mgr.get(run_id)
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────────

    def submit(
        self,
        strategy_id: str,
        fn: Callable[..., Any],
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Create a job and start it in a background thread. Returns run_id."""
        run_id = str(uuid.uuid4())
        job = Job(run_id=run_id, strategy_id=strategy_id)

        with self._lock:
            self._jobs[run_id] = job

        thread = threading.Thread(
            target=self._execute,
            args=(job, fn, kwargs or {}),
            daemon=True,
            name=f"backtest-{run_id[:8]}",
        )
        job._thread = thread
        thread.start()

        logger.info("Job %s submitted for strategy %s", run_id, strategy_id)
        return run_id

    def get(self, run_id: str) -> Job | None:
        """Return job by run_id, or None."""
        with self._lock:
            return self._jobs.get(run_id)

    def get_run_result(self, run_id: str) -> BacktestRunResult | None:
        """Build a BacktestRunResult from the current job state."""
        job = self.get(run_id)
        if job is None:
            return None
        return BacktestRunResult(
            run_id=job.run_id,
            status=job.status,
            strategy_id=job.strategy_id,
            started_at=job.started_at,
            message=job.error,
        )

    def list_jobs(self) -> list[BacktestRunResult]:
        """Return status of all jobs."""
        with self._lock:
            jobs = list(self._jobs.values())
        return [
            BacktestRunResult(
                run_id=j.run_id,
                status=j.status,
                strategy_id=j.strategy_id,
                started_at=j.started_at,
                message=j.error,
            )
            for j in jobs
        ]

    # ── Internal ─────────────────────────────────────────────────────────

    def _execute(self, job: Job, fn: Callable[..., Any], kwargs: dict[str, Any]) -> None:
        """Run the callable in a thread and update job status."""
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        try:
            result = fn(**kwargs)
            job.result = result
            job.status = "complete"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job.run_id)
            job.error = str(exc)
            job.status = "error"
        finally:
            job.completed_at = datetime.now(timezone.utc)
```

### `src/qitp_mcp_backtest/data_loader.py`

```python
"""Load OHLCV data from S3 parquet files.

S3 layout: s3://{bucket}/{symbol}/{year}/{month:02d}.parquet
Columns: date, open, high, low, close, volume, adjusted_close
"""

from __future__ import annotations

import io
import logging
import os
from datetime import date

import boto3
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

OHLCV_BUCKET = os.environ.get("QITP_OHLCV_BUCKET", "qitp-historical-data")
OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume", "adjusted_close"]


def _s3_client():
    """Build a boto3 S3 client (respects AWS_ENDPOINT_URL for localstack)."""
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    return boto3.client("s3", endpoint_url=endpoint) if endpoint else boto3.client("s3")


def _month_range(start: date, end: date) -> list[tuple[int, int]]:
    """Return list of (year, month) tuples covering start..end inclusive."""
    months: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def load_ohlcv(
    symbol: str,
    start_date: date,
    end_date: date,
    *,
    bucket: str | None = None,
    s3_client=None,
) -> pd.DataFrame:
    """Load OHLCV data for *symbol* between *start_date* and *end_date*.

    Reads monthly parquet files from S3, concatenates, and filters.

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, adjusted_close
        Sorted by date ascending.
    """
    bucket = bucket or OHLCV_BUCKET
    client = s3_client or _s3_client()

    frames: list[pd.DataFrame] = []
    for year, month in _month_range(start_date, end_date):
        key = f"{symbol}/{year}/{month:02d}.parquet"
        try:
            resp = client.get_object(Bucket=bucket, Key=key)
            buf = io.BytesIO(resp["Body"].read())
            table = pq.read_table(buf)
            df = table.to_pandas()
            frames.append(df)
        except client.exceptions.NoSuchKey:
            logger.warning("Missing parquet: s3://%s/%s", bucket, key)
        except Exception:
            logger.exception("Error loading s3://%s/%s", bucket, key)

    if not frames:
        raise FileNotFoundError(
            f"No OHLCV data found for {symbol} between {start_date} and {end_date}"
        )

    combined = pd.concat(frames, ignore_index=True)

    # Ensure date column is proper datetime
    if not pd.api.types.is_datetime64_any_dtype(combined["date"]):
        combined["date"] = pd.to_datetime(combined["date"])

    # Filter to requested range
    mask = (combined["date"].dt.date >= start_date) & (combined["date"].dt.date <= end_date)
    combined = combined.loc[mask].sort_values("date").reset_index(drop=True)

    return combined[OHLCV_COLUMNS]


def load_strategy_yaml(
    strategy_id: str,
    *,
    bucket: str | None = None,
    s3_client=None,
) -> str:
    """Load a strategy YAML blueprint from S3.

    Path: s3://qitp-strategy-blueprints/{strategy_id}.yaml
    """
    import yaml  # noqa: F401 — validate yaml is available

    bucket = bucket or os.environ.get("QITP_STRATEGY_BUCKET", "qitp-strategy-blueprints")
    client = s3_client or _s3_client()
    key = f"{strategy_id}.yaml"

    resp = client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read().decode("utf-8")
```

### `src/qitp_mcp_backtest/tools/__init__.py`

```python
"""MCP tool implementations for the backtest server."""
```

### `src/qitp_mcp_backtest/tools/run_backtest.py`

```python
"""Tool: run_backtest — submit an asynchronous backtest job."""

from __future__ import annotations

import logging
from datetime import date

import yaml

from qitp_mcp_backtest.data_loader import load_ohlcv, load_strategy_yaml
from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import (
    BacktestConfig,
    BacktestResult,
    BacktestRunResult,
    PerformanceMetrics,
    TradeRecord,
)

logger = logging.getLogger(__name__)


def _build_slippage(config: BacktestConfig):
    """Instantiate a slippage model from qitp-simulation."""
    from qitp_simulation.slippage import FixedSlippage, PercentageSlippage, VolumeImpactSlippage

    match config.slippage_model:
        case "fixed":
            return FixedSlippage(amount=config.slippage_value)
        case "percentage":
            return PercentageSlippage(rate=config.slippage_value)
        case "volume_impact":
            return VolumeImpactSlippage(impact_factor=config.slippage_value)


def _build_commission(config: BacktestConfig):
    """Instantiate a commission model from qitp-simulation."""
    from qitp_simulation.commission import IBKRTieredEU, ZeroCommission

    match config.commission_model:
        case "ibkr_tiered_eu":
            return IBKRTieredEU()
        case "zero":
            return ZeroCommission()


def _execute_backtest(
    *,
    run_id: str,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config: BacktestConfig,
) -> BacktestResult:
    """Run a backtest synchronously (called inside a worker thread).

    This is the function submitted to JobManager. It:
    1. Loads the strategy YAML from S3
    2. Loads OHLCV data from S3 parquet
    3. Configures and runs the BacktestEngine
    4. Converts engine output to BacktestResult schema
    """
    from qitp_simulation.engine import BacktestEngine

    # 1. Load strategy
    strategy_yaml = load_strategy_yaml(strategy_id)
    strategy_config = yaml.safe_load(strategy_yaml)

    # 2. Load market data
    market_data: dict = {}
    for symbol in symbols:
        market_data[symbol] = load_ohlcv(symbol, start_date, end_date)

    # 3. Configure engine
    slippage = _build_slippage(config)
    commission = _build_commission(config)

    engine = BacktestEngine(
        strategy_config=strategy_config,
        market_data=market_data,
        initial_capital=config.initial_capital,
        slippage_model=slippage,
        commission_model=commission,
    )

    # 4. Run
    raw_result = engine.run()

    # 5. Convert to schema
    metrics = PerformanceMetrics(
        total_return_pct=raw_result.metrics.total_return_pct,
        annualized_return_pct=raw_result.metrics.annualized_return_pct,
        sharpe_ratio=raw_result.metrics.sharpe_ratio,
        sortino_ratio=raw_result.metrics.sortino_ratio,
        max_drawdown_pct=raw_result.metrics.max_drawdown_pct,
        win_rate_pct=raw_result.metrics.win_rate_pct,
        profit_factor=raw_result.metrics.profit_factor,
        total_trades=raw_result.metrics.total_trades,
        avg_trade_duration_days=raw_result.metrics.avg_trade_duration_days,
    )

    trades = [
        TradeRecord(
            symbol=t.symbol,
            side=t.side,
            quantity=t.quantity,
            price=t.price,
            timestamp=t.timestamp,
            commission=t.commission,
            slippage=t.slippage,
        )
        for t in raw_result.trades
    ]

    equity_curve = [
        {"date": str(pt.date), "equity": pt.equity}
        for pt in raw_result.equity_curve
    ]

    return BacktestResult(
        run_id=run_id,
        strategy_id=strategy_id,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
    )


def run_backtest(
    job_manager: JobManager,
    *,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config: BacktestConfig | None = None,
) -> BacktestRunResult:
    """Submit a backtest job. Returns immediately with run_id and status=queued."""
    config = config or BacktestConfig()

    run_id = job_manager.submit(
        strategy_id=strategy_id,
        fn=_execute_backtest,
        kwargs={
            "run_id": "",  # placeholder — replaced below
            "strategy_id": strategy_id,
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "config": config,
        },
    )

    # Patch the run_id into kwargs (the job thread receives it)
    job = job_manager.get(run_id)
    if job and job._thread and job._thread.is_alive():
        # Thread may already be running; the run_id kwarg is only used
        # for the BacktestResult.run_id field. We update the job's reference.
        pass

    # For correctness, we re-submit with the actual run_id.
    # Simpler approach: generate run_id first, then submit.
    # Let's fix the flow:
    return job_manager.get_run_result(run_id)


def run_backtest_v2(
    job_manager: JobManager,
    *,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config: BacktestConfig | None = None,
) -> BacktestRunResult:
    """Submit a backtest job (corrected flow). Returns immediately with run_id."""
    import uuid

    config = config or BacktestConfig()
    run_id = str(uuid.uuid4())

    job_manager.submit_with_id(
        run_id=run_id,
        strategy_id=strategy_id,
        fn=_execute_backtest,
        kwargs={
            "run_id": run_id,
            "strategy_id": strategy_id,
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "config": config,
        },
    )

    return job_manager.get_run_result(run_id)
```

**Note:** The above has a run_id coordination issue. The corrected version below is the canonical implementation. Let me provide the clean version:

### `src/qitp_mcp_backtest/tools/run_backtest.py` (canonical)

```python
"""Tool: run_backtest — submit an asynchronous backtest job."""

from __future__ import annotations

import logging
import uuid
from datetime import date

import yaml

from qitp_mcp_backtest.data_loader import load_ohlcv, load_strategy_yaml
from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import (
    BacktestConfig,
    BacktestResult,
    BacktestRunResult,
    PerformanceMetrics,
    TradeRecord,
)

logger = logging.getLogger(__name__)


def _build_slippage(config: BacktestConfig):
    """Instantiate a slippage model from qitp-simulation."""
    from qitp_simulation.slippage import FixedSlippage, PercentageSlippage, VolumeImpactSlippage

    match config.slippage_model:
        case "fixed":
            return FixedSlippage(amount=config.slippage_value)
        case "percentage":
            return PercentageSlippage(rate=config.slippage_value)
        case "volume_impact":
            return VolumeImpactSlippage(impact_factor=config.slippage_value)


def _build_commission(config: BacktestConfig):
    """Instantiate a commission model from qitp-simulation."""
    from qitp_simulation.commission import IBKRTieredEU, ZeroCommission

    match config.commission_model:
        case "ibkr_tiered_eu":
            return IBKRTieredEU()
        case "zero":
            return ZeroCommission()


def _execute_backtest(
    *,
    run_id: str,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config_dict: dict,
) -> BacktestResult:
    """Run a backtest synchronously (called inside a worker thread).

    1. Loads strategy YAML from S3
    2. Loads OHLCV data from S3 parquet
    3. Configures and runs BacktestEngine
    4. Converts engine output to BacktestResult schema
    """
    from qitp_simulation.engine import BacktestEngine

    config = BacktestConfig(**config_dict)

    # 1. Load strategy blueprint
    strategy_yaml = load_strategy_yaml(strategy_id)
    strategy_config = yaml.safe_load(strategy_yaml)

    # 2. Load market data per symbol
    market_data: dict = {}
    for symbol in symbols:
        market_data[symbol] = load_ohlcv(symbol, start_date, end_date)

    # 3. Configure engine
    slippage = _build_slippage(config)
    commission = _build_commission(config)

    engine = BacktestEngine(
        strategy_config=strategy_config,
        market_data=market_data,
        initial_capital=config.initial_capital,
        slippage_model=slippage,
        commission_model=commission,
    )

    # 4. Run engine
    raw_result = engine.run()

    # 5. Map to schema
    metrics = PerformanceMetrics(
        total_return_pct=raw_result.metrics.total_return_pct,
        annualized_return_pct=raw_result.metrics.annualized_return_pct,
        sharpe_ratio=raw_result.metrics.sharpe_ratio,
        sortino_ratio=raw_result.metrics.sortino_ratio,
        max_drawdown_pct=raw_result.metrics.max_drawdown_pct,
        win_rate_pct=raw_result.metrics.win_rate_pct,
        profit_factor=raw_result.metrics.profit_factor,
        total_trades=raw_result.metrics.total_trades,
        avg_trade_duration_days=raw_result.metrics.avg_trade_duration_days,
    )

    trades = [
        TradeRecord(
            symbol=t.symbol,
            side=t.side,
            quantity=t.quantity,
            price=t.price,
            timestamp=t.timestamp,
            commission=t.commission,
            slippage=t.slippage,
        )
        for t in raw_result.trades
    ]

    equity_curve = [
        {"date": str(pt.date), "equity": pt.equity}
        for pt in raw_result.equity_curve
    ]

    return BacktestResult(
        run_id=run_id,
        strategy_id=strategy_id,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
    )


def run_backtest(
    job_manager: JobManager,
    *,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config: BacktestConfig | None = None,
) -> BacktestRunResult:
    """Submit a backtest job. Returns immediately with run_id and status=queued.

    The backtest runs in a background thread. Poll with get_backtest_result().
    """
    config = config or BacktestConfig()

    # Pre-generate run_id so the thread can embed it in the result
    run_id = str(uuid.uuid4())

    job_manager.submit_with_id(
        run_id=run_id,
        strategy_id=strategy_id,
        fn=_execute_backtest,
        kwargs={
            "run_id": run_id,
            "strategy_id": strategy_id,
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "config_dict": config.model_dump(),
        },
    )

    return job_manager.get_run_result(run_id)
```

### Updated `src/qitp_mcp_backtest/job_manager.py` (with `submit_with_id`)

```python
"""In-memory async job manager with thread-based execution.

POC uses a simple dict + threading. Production upgrades to DynamoDB.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from qitp_mcp_backtest.schemas import BacktestRunResult

logger = logging.getLogger(__name__)


class Job:
    """Tracks a single backtest job."""

    __slots__ = (
        "run_id", "status", "strategy_id", "started_at",
        "completed_at", "result", "error", "_thread",
    )

    def __init__(self, run_id: str, strategy_id: str) -> None:
        self.run_id = run_id
        self.strategy_id = strategy_id
        self.status: str = "queued"
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.result: Any = None
        self.error: str | None = None
        self._thread: threading.Thread | None = None


class JobManager:
    """Thread-safe job manager backed by an in-memory dict.

    Usage::

        mgr = JobManager()
        run_id = mgr.submit(strategy_id="gap_momentum_up", fn=run_engine, kwargs={...})
        job = mgr.get(run_id)
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────────

    def submit(
        self,
        strategy_id: str,
        fn: Callable[..., Any],
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Create a job with auto-generated run_id and start it. Returns run_id."""
        run_id = str(uuid.uuid4())
        self._start_job(run_id, strategy_id, fn, kwargs or {})
        return run_id

    def submit_with_id(
        self,
        run_id: str,
        strategy_id: str,
        fn: Callable[..., Any],
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Create a job with a pre-generated run_id and start it."""
        self._start_job(run_id, strategy_id, fn, kwargs or {})

    def get(self, run_id: str) -> Job | None:
        """Return job by run_id, or None."""
        with self._lock:
            return self._jobs.get(run_id)

    def get_run_result(self, run_id: str) -> BacktestRunResult | None:
        """Build a BacktestRunResult from the current job state."""
        job = self.get(run_id)
        if job is None:
            return None
        return BacktestRunResult(
            run_id=job.run_id,
            status=job.status,
            strategy_id=job.strategy_id,
            started_at=job.started_at,
            message=job.error,
        )

    def list_jobs(self) -> list[BacktestRunResult]:
        """Return status of all jobs."""
        with self._lock:
            jobs = list(self._jobs.values())
        return [
            BacktestRunResult(
                run_id=j.run_id,
                status=j.status,
                strategy_id=j.strategy_id,
                started_at=j.started_at,
                message=j.error,
            )
            for j in jobs
        ]

    # ── Internal ─────────────────────────────────────────────────────────

    def _start_job(
        self,
        run_id: str,
        strategy_id: str,
        fn: Callable[..., Any],
        kwargs: dict[str, Any],
    ) -> None:
        """Create Job object, register it, and launch worker thread."""
        job = Job(run_id=run_id, strategy_id=strategy_id)

        with self._lock:
            self._jobs[run_id] = job

        thread = threading.Thread(
            target=self._execute,
            args=(job, fn, kwargs),
            daemon=True,
            name=f"backtest-{run_id[:8]}",
        )
        job._thread = thread
        thread.start()
        logger.info("Job %s submitted for strategy %s", run_id, strategy_id)

    def _execute(self, job: Job, fn: Callable[..., Any], kwargs: dict[str, Any]) -> None:
        """Run the callable in a thread and update job status."""
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        try:
            result = fn(**kwargs)
            job.result = result
            job.status = "complete"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job.run_id)
            job.error = str(exc)
            job.status = "error"
        finally:
            job.completed_at = datetime.now(timezone.utc)
```

### `src/qitp_mcp_backtest/tools/get_result.py`

```python
"""Tool: get_backtest_result — poll for a backtest job's result."""

from __future__ import annotations

from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import BacktestResult, BacktestRunResult, StatusResult


def get_backtest_result(
    job_manager: JobManager,
    *,
    run_id: str,
) -> BacktestResult | StatusResult:
    """Return full results if the job is complete, otherwise return status.

    Returns:
        BacktestResult if status == "complete"
        StatusResult   if status in ("queued", "running", "error")

    Raises:
        ValueError: if run_id is not found
    """
    job = job_manager.get(run_id)
    if job is None:
        raise ValueError(f"Unknown run_id: {run_id}")

    if job.status == "complete" and job.result is not None:
        return job.result  # BacktestResult

    return StatusResult(
        run_id=job.run_id,
        status=job.status,
        message=job.error if job.status == "error" else f"Job is {job.status}",
    )
```

### `src/qitp_mcp_backtest/tools/walk_forward.py`

```python
"""Tool: run_walk_forward — rolling-window walk-forward validation."""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

import yaml

from qitp_mcp_backtest.data_loader import load_ohlcv, load_strategy_yaml
from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import (
    BacktestConfig,
    BacktestRunResult,
    PerformanceMetrics,
    WalkForwardConfig,
    WalkForwardFoldResult,
    WalkForwardResult,
)

logger = logging.getLogger(__name__)


def _compute_fold_dates(
    start_date: date,
    end_date: date,
    n_splits: int,
    train_pct: float,
) -> list[tuple[date, date, date, date]]:
    """Compute (train_start, train_end, test_start, test_end) for each fold.

    Uses an expanding-window approach where the total range is divided into
    n_splits test windows, each preceded by a training window sized as
    train_pct of the fold's total span.
    """
    total_days = (end_date - start_date).days
    test_window_days = total_days // (n_splits + int(n_splits * train_pct / (1 - train_pct + 0.001)))

    # Simpler: divide into n_splits equal test windows, with overlapping train
    step = total_days // n_splits
    folds: list[tuple[date, date, date, date]] = []

    for i in range(n_splits):
        test_start = start_date + timedelta(days=i * step)
        test_end = min(test_start + timedelta(days=step - 1), end_date)

        # Train window: use train_pct of total available data before test_end
        train_days = int((test_end - start_date).days * train_pct)
        train_start = max(start_date, test_start - timedelta(days=train_days))
        train_end = test_start - timedelta(days=1)

        if train_end <= train_start:
            train_start = start_date
            train_end = test_start - timedelta(days=1)

        if train_end > train_start:
            folds.append((train_start, train_end, test_start, test_end))

    return folds


def _run_single_period(
    strategy_config: dict,
    market_data_full: dict[str, "pd.DataFrame"],
    start_date: date,
    end_date: date,
    config: WalkForwardConfig,
) -> PerformanceMetrics:
    """Run backtest engine on a single date range and return metrics."""
    import pandas as pd
    from qitp_simulation.engine import BacktestEngine
    from qitp_mcp_backtest.tools.run_backtest import _build_commission, _build_slippage

    bt_config = BacktestConfig(
        initial_capital=config.initial_capital,
        slippage_model=config.slippage_model,
        slippage_value=config.slippage_value,
        commission_model=config.commission_model,
    )

    # Slice market data to the period
    sliced: dict[str, pd.DataFrame] = {}
    for sym, df in market_data_full.items():
        mask = (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)
        sliced[sym] = df.loc[mask].reset_index(drop=True)

    engine = BacktestEngine(
        strategy_config=strategy_config,
        market_data=sliced,
        initial_capital=config.initial_capital,
        slippage_model=_build_slippage(bt_config),
        commission_model=_build_commission(bt_config),
    )

    raw = engine.run()

    return PerformanceMetrics(
        total_return_pct=raw.metrics.total_return_pct,
        annualized_return_pct=raw.metrics.annualized_return_pct,
        sharpe_ratio=raw.metrics.sharpe_ratio,
        sortino_ratio=raw.metrics.sortino_ratio,
        max_drawdown_pct=raw.metrics.max_drawdown_pct,
        win_rate_pct=raw.metrics.win_rate_pct,
        profit_factor=raw.metrics.profit_factor,
        total_trades=raw.metrics.total_trades,
        avg_trade_duration_days=raw.metrics.avg_trade_duration_days,
    )


def _execute_walk_forward(
    *,
    run_id: str,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config_dict: dict,
) -> WalkForwardResult:
    """Run walk-forward validation synchronously (called in worker thread)."""
    config = WalkForwardConfig(**config_dict)

    # Load strategy
    strategy_yaml = load_strategy_yaml(strategy_id)
    strategy_config = yaml.safe_load(strategy_yaml)

    # Load full market data range
    market_data: dict = {}
    for symbol in symbols:
        market_data[symbol] = load_ohlcv(symbol, start_date, end_date)

    # Compute fold boundaries
    folds_dates = _compute_fold_dates(start_date, end_date, config.n_splits, config.train_pct)

    # Run each fold
    folds: list[WalkForwardFoldResult] = []
    is_sharpes: list[float] = []
    oos_sharpes: list[float] = []

    for i, (tr_start, tr_end, te_start, te_end) in enumerate(folds_dates):
        logger.info("Fold %d: train=%s..%s test=%s..%s", i, tr_start, tr_end, te_start, te_end)

        in_sample = _run_single_period(strategy_config, market_data, tr_start, tr_end, config)
        out_of_sample = _run_single_period(strategy_config, market_data, te_start, te_end, config)

        folds.append(WalkForwardFoldResult(
            fold_index=i,
            train_start=tr_start,
            train_end=tr_end,
            test_start=te_start,
            test_end=te_end,
            in_sample_metrics=in_sample,
            out_of_sample_metrics=out_of_sample,
        ))

        is_sharpes.append(in_sample.sharpe_ratio)
        oos_sharpes.append(out_of_sample.sharpe_ratio)

    # Compute overfitting score: ratio of average IS Sharpe to OOS Sharpe
    avg_is = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0.0
    avg_oos = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0

    if avg_oos > 0:
        overfitting_score = max(0.0, (avg_is - avg_oos) / avg_is) if avg_is > 0 else 0.0
    else:
        overfitting_score = 1.0  # OOS is negative = likely overfit

    overfitting_flag = overfitting_score > 0.5  # >50% degradation = overfit

    # Aggregate OOS metrics (average across folds)
    oos_metrics_list = [f.out_of_sample_metrics for f in folds]
    n = len(oos_metrics_list)
    aggregate_oos = PerformanceMetrics(
        total_return_pct=sum(m.total_return_pct for m in oos_metrics_list) / n,
        annualized_return_pct=sum(m.annualized_return_pct for m in oos_metrics_list) / n,
        sharpe_ratio=avg_oos,
        sortino_ratio=sum(m.sortino_ratio for m in oos_metrics_list) / n,
        max_drawdown_pct=max(m.max_drawdown_pct for m in oos_metrics_list),
        win_rate_pct=sum(m.win_rate_pct for m in oos_metrics_list) / n,
        profit_factor=sum(m.profit_factor for m in oos_metrics_list) / n,
        total_trades=sum(m.total_trades for m in oos_metrics_list),
        avg_trade_duration_days=sum(m.avg_trade_duration_days for m in oos_metrics_list) / n,
    )

    return WalkForwardResult(
        run_id=run_id,
        strategy_id=strategy_id,
        symbols=symbols,
        n_splits=config.n_splits,
        folds=folds,
        overfitting_flag=overfitting_flag,
        overfitting_score=round(overfitting_score, 4),
        aggregate_oos_metrics=aggregate_oos,
    )


def run_walk_forward(
    job_manager: JobManager,
    *,
    strategy_id: str,
    symbols: list[str],
    start_date: date,
    end_date: date,
    config: WalkForwardConfig | None = None,
) -> BacktestRunResult:
    """Submit a walk-forward validation job. Returns immediately with run_id."""
    config = config or WalkForwardConfig()
    run_id = str(uuid.uuid4())

    job_manager.submit_with_id(
        run_id=run_id,
        strategy_id=strategy_id,
        fn=_execute_walk_forward,
        kwargs={
            "run_id": run_id,
            "strategy_id": strategy_id,
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "config_dict": config.model_dump(),
        },
    )

    return job_manager.get_run_result(run_id)
```

### `src/qitp_mcp_backtest/tools/compare.py`

```python
"""Tool: compare_strategies — side-by-side comparison of backtest runs."""

from __future__ import annotations

from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import BacktestResult, ComparisonResult, WalkForwardResult


_RANKING_METRICS = [
    ("sharpe_ratio", True),         # higher is better
    ("sortino_ratio", True),
    ("total_return_pct", True),
    ("annualized_return_pct", True),
    ("win_rate_pct", True),
    ("profit_factor", True),
    ("max_drawdown_pct", False),    # lower is better
    ("avg_trade_duration_days", False),
]


def _extract_metrics(result) -> dict:
    """Extract metrics dict from a BacktestResult or WalkForwardResult."""
    if isinstance(result, BacktestResult):
        return result.metrics.model_dump()
    elif isinstance(result, WalkForwardResult):
        return result.aggregate_oos_metrics.model_dump()
    else:
        raise TypeError(f"Cannot extract metrics from {type(result)}")


def compare_strategies(
    job_manager: JobManager,
    *,
    run_ids: list[str],
) -> ComparisonResult:
    """Compare multiple completed backtest runs side-by-side.

    Ranks runs by Sharpe, win rate, max drawdown, and other metrics.

    Raises:
        ValueError: if any run_id is not found or not complete.
    """
    # Gather results
    results: dict[str, dict] = {}
    for run_id in run_ids:
        job = job_manager.get(run_id)
        if job is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        if job.status != "complete":
            raise ValueError(f"Run {run_id} is not complete (status={job.status})")
        if job.result is None:
            raise ValueError(f"Run {run_id} has no result")

        results[run_id] = _extract_metrics(job.result)

    # Build rankings: for each metric, sort run_ids
    rankings: dict[str, list[str]] = {}
    for metric_name, higher_is_better in _RANKING_METRICS:
        sorted_ids = sorted(
            run_ids,
            key=lambda rid: results[rid].get(metric_name, 0.0),
            reverse=higher_is_better,
        )
        rankings[metric_name] = sorted_ids

    # Build per-run summary
    summary: list[dict] = []
    for run_id in run_ids:
        entry = {"run_id": run_id}
        job = job_manager.get(run_id)
        entry["strategy_id"] = job.strategy_id if job else "unknown"
        entry["metrics"] = results[run_id]
        summary.append(entry)

    return ComparisonResult(
        run_ids=run_ids,
        rankings=rankings,
        summary=summary,
    )
```

### `src/qitp_mcp_backtest/server.py`

```python
"""MCP server for QITP Backtesting.

Exposes 4 tools:
  - run_backtest
  - get_backtest_result
  - run_walk_forward
  - compare_strategies

Usage:
    python -m qitp_mcp_backtest.server          # stdio transport
    TRANSPORT=sse python -m qitp_mcp_backtest.server   # SSE transport
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import (
    BacktestConfig,
    BacktestRunRequest,
    CompareRequest,
    WalkForwardConfig,
    WalkForwardRequest,
)
from qitp_mcp_backtest.tools.compare import compare_strategies
from qitp_mcp_backtest.tools.get_result import get_backtest_result
from qitp_mcp_backtest.tools.run_backtest import run_backtest
from qitp_mcp_backtest.tools.walk_forward import run_walk_forward

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ── Singleton job manager ────────────────────────────────────────────────────
_job_manager = JobManager()

# ── MCP Server ───────────────────────────────────────────────────────────────
app = Server("qitp-backtest-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise the 4 backtest tools."""
    return [
        Tool(
            name="run_backtest",
            description=(
                "Start an asynchronous backtest for a strategy. Returns a run_id "
                "immediately. Poll with get_backtest_result to retrieve results."
            ),
            inputSchema=BacktestRunRequest.model_json_schema(),
        ),
        Tool(
            name="get_backtest_result",
            description=(
                "Retrieve the result of a backtest run. Returns full metrics and "
                "trades if complete, or current status if still running."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "The backtest run ID"},
                },
                "required": ["run_id"],
            },
        ),
        Tool(
            name="run_walk_forward",
            description=(
                "Run rolling-window walk-forward validation for a strategy. "
                "Returns per-fold in-sample/out-of-sample metrics and an "
                "overfitting flag."
            ),
            inputSchema=WalkForwardRequest.model_json_schema(),
        ),
        Tool(
            name="compare_strategies",
            description=(
                "Compare multiple completed backtest runs side-by-side. "
                "Ranks by Sharpe ratio, win rate, max drawdown, and other metrics."
            ),
            inputSchema=CompareRequest.model_json_schema(),
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    try:
        match name:
            case "run_backtest":
                req = BacktestRunRequest(**arguments)
                result = run_backtest(
                    _job_manager,
                    strategy_id=req.strategy_id,
                    symbols=req.symbols,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    config=req.config,
                )

            case "get_backtest_result":
                result = get_backtest_result(
                    _job_manager,
                    run_id=arguments["run_id"],
                )

            case "run_walk_forward":
                req = WalkForwardRequest(**arguments)
                result = run_walk_forward(
                    _job_manager,
                    strategy_id=req.strategy_id,
                    symbols=req.symbols,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    config=req.config,
                )

            case "compare_strategies":
                req = CompareRequest(**arguments)
                result = compare_strategies(
                    _job_manager,
                    run_ids=req.run_ids,
                )

            case _:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        # Serialize result
        payload = result.model_dump_json(indent=2) if hasattr(result, "model_dump_json") else json.dumps(result, default=str)
        return [TextContent(type="text", text=payload)]

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _run_stdio() -> None:
    """Run the MCP server over stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    """Entry point."""
    import asyncio

    transport = os.environ.get("TRANSPORT", "stdio")

    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route
        import uvicorn

        sse = SseServerTransport("/messages")

        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await app.run(streams[0], streams[1], app.create_initialization_options())

        starlette_app = Starlette(routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ])
        uvicorn.run(starlette_app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
    else:
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
```

### `tests/conftest.py`

```python
"""Shared fixtures for backtest MCP tests."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import PerformanceMetrics

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def job_manager():
    """Fresh JobManager instance."""
    return JobManager()


@pytest.fixture
def sample_ohlcv_df():
    """Sample OHLCV DataFrame matching the expected schema."""
    dates = pd.date_range("2024-01-02", periods=20, freq="B")
    return pd.DataFrame({
        "date": dates,
        "open": [100 + i * 0.5 for i in range(20)],
        "high": [101 + i * 0.5 for i in range(20)],
        "low": [99 + i * 0.5 for i in range(20)],
        "close": [100.5 + i * 0.5 for i in range(20)],
        "volume": [1_000_000 + i * 10_000 for i in range(20)],
        "adjusted_close": [100.5 + i * 0.5 for i in range(20)],
    })


@pytest.fixture
def sample_metrics():
    """Sample PerformanceMetrics for testing."""
    return PerformanceMetrics(
        total_return_pct=12.5,
        annualized_return_pct=25.0,
        sharpe_ratio=1.8,
        sortino_ratio=2.1,
        max_drawdown_pct=5.3,
        win_rate_pct=62.0,
        profit_factor=1.9,
        total_trades=42,
        avg_trade_duration_days=3.2,
    )


@pytest.fixture
def mock_engine_result(sample_metrics):
    """Mock object mimicking qitp_simulation.engine.BacktestEngine.run() output."""
    result = MagicMock()
    result.metrics = MagicMock()
    result.metrics.total_return_pct = sample_metrics.total_return_pct
    result.metrics.annualized_return_pct = sample_metrics.annualized_return_pct
    result.metrics.sharpe_ratio = sample_metrics.sharpe_ratio
    result.metrics.sortino_ratio = sample_metrics.sortino_ratio
    result.metrics.max_drawdown_pct = sample_metrics.max_drawdown_pct
    result.metrics.win_rate_pct = sample_metrics.win_rate_pct
    result.metrics.profit_factor = sample_metrics.profit_factor
    result.metrics.total_trades = sample_metrics.total_trades
    result.metrics.avg_trade_duration_days = sample_metrics.avg_trade_duration_days

    trade = MagicMock()
    trade.symbol = "AAPL"
    trade.side = "buy"
    trade.quantity = 100.0
    trade.price = 150.0
    trade.timestamp = datetime(2024, 1, 15, 10, 0, 0)
    trade.commission = 1.5
    trade.slippage = 0.15
    result.trades = [trade]

    eq_pt = MagicMock()
    eq_pt.date = date(2024, 1, 2)
    eq_pt.equity = 100_000.0
    result.equity_curve = [eq_pt]

    return result


@pytest.fixture
def strategy_yaml():
    """Sample strategy YAML content."""
    return """
name: gap_momentum_up
version: "1.0"
universe:
  type: static
  symbols: ["AAPL"]
signals:
  - name: gap_up
    type: gap
    direction: up
    min_pct: 2.0
rules:
  entry:
    condition: gap_up
    action: buy
    size: pct_equity
    size_value: 0.1
  exit:
    stop_loss_pct: 2.0
    take_profit_pct: 5.0
    max_hold_days: 5
"""
```

### `tests/test_run_backtest.py`

```python
"""Tests for run_backtest and get_backtest_result tools."""

from __future__ import annotations

import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import (
    BacktestConfig,
    BacktestResult,
    BacktestRunResult,
    StatusResult,
)
from qitp_mcp_backtest.tools.get_result import get_backtest_result
from qitp_mcp_backtest.tools.run_backtest import run_backtest


class TestRunBacktest:
    """Tests for the run_backtest tool."""

    def test_returns_immediately_with_run_id(self, job_manager):
        """run_backtest should return a BacktestRunResult without blocking."""
        # Mock the actual execution so it doesn't need S3/simulation
        with patch(
            "qitp_mcp_backtest.tools.run_backtest._execute_backtest"
        ) as mock_exec:
            mock_exec.side_effect = lambda **kw: time.sleep(10)  # simulate long job

            result = run_backtest(
                job_manager,
                strategy_id="gap_momentum_up",
                symbols=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
            )

            assert isinstance(result, BacktestRunResult)
            assert result.run_id is not None
            assert result.status in ("queued", "running")
            assert result.strategy_id == "gap_momentum_up"

    def test_job_completes_with_result(
        self, job_manager, mock_engine_result, sample_ohlcv_df, strategy_yaml
    ):
        """After job completes, get_backtest_result returns BacktestResult."""
        with (
            patch("qitp_mcp_backtest.tools.run_backtest.load_strategy_yaml") as mock_yaml,
            patch("qitp_mcp_backtest.tools.run_backtest.load_ohlcv") as mock_ohlcv,
            patch("qitp_mcp_backtest.tools.run_backtest.BacktestEngine") as MockEngine,
        ):
            mock_yaml.return_value = strategy_yaml
            mock_ohlcv.return_value = sample_ohlcv_df
            MockEngine.return_value.run.return_value = mock_engine_result

            result = run_backtest(
                job_manager,
                strategy_id="gap_momentum_up",
                symbols=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
            )

            # Wait for thread to complete
            job = job_manager.get(result.run_id)
            job._thread.join(timeout=5)

            # Now poll for result
            final = get_backtest_result(job_manager, run_id=result.run_id)
            assert isinstance(final, BacktestResult)
            assert final.strategy_id == "gap_momentum_up"
            assert final.metrics.sharpe_ratio == 1.8
            assert len(final.trades) == 1

    def test_default_config_values(self, job_manager):
        """Default BacktestConfig values should be applied."""
        with patch(
            "qitp_mcp_backtest.tools.run_backtest._execute_backtest"
        ):
            result = run_backtest(
                job_manager,
                strategy_id="test",
                symbols=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31),
            )
            assert result is not None


class TestGetBacktestResult:
    """Tests for the get_backtest_result tool."""

    def test_unknown_run_id_raises(self, job_manager):
        """Should raise ValueError for unknown run_id."""
        with pytest.raises(ValueError, match="Unknown run_id"):
            get_backtest_result(job_manager, run_id="nonexistent")

    def test_running_job_returns_status(self, job_manager):
        """Should return StatusResult while job is running."""
        # Submit a slow job
        run_id = job_manager.submit(
            strategy_id="test",
            fn=lambda: time.sleep(10),
        )
        time.sleep(0.1)  # let thread start

        result = get_backtest_result(job_manager, run_id=run_id)
        assert isinstance(result, StatusResult)
        assert result.status == "running"

    def test_failed_job_returns_error_status(self, job_manager):
        """Should return error status with message for failed jobs."""
        run_id = job_manager.submit(
            strategy_id="test",
            fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # Wait for completion
        job = job_manager.get(run_id)
        job._thread.join(timeout=5)

        result = get_backtest_result(job_manager, run_id=run_id)
        assert isinstance(result, StatusResult)
        assert result.status == "error"
```

### `tests/test_walk_forward.py`

```python
"""Tests for walk-forward validation and strategy comparison tools."""

from __future__ import annotations

import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from qitp_mcp_backtest.job_manager import JobManager
from qitp_mcp_backtest.schemas import (
    BacktestResult,
    BacktestRunResult,
    ComparisonResult,
    PerformanceMetrics,
    WalkForwardConfig,
    WalkForwardResult,
)
from qitp_mcp_backtest.tools.compare import compare_strategies
from qitp_mcp_backtest.tools.walk_forward import (
    _compute_fold_dates,
    run_walk_forward,
)


class TestComputeFoldDates:
    """Unit tests for fold date computation."""

    def test_basic_splits(self):
        """Should produce the requested number of folds."""
        folds = _compute_fold_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            n_splits=5,
            train_pct=0.7,
        )
        assert len(folds) <= 5
        for tr_start, tr_end, te_start, te_end in folds:
            assert tr_start < tr_end
            assert te_start <= te_end
            assert tr_end < te_start

    def test_no_overlap_between_train_and_test(self):
        """Train end must be before test start."""
        folds = _compute_fold_dates(
            start_date=date(2023, 1, 1),
            end_date=date(2024, 12, 31),
            n_splits=3,
            train_pct=0.7,
        )
        for tr_start, tr_end, te_start, te_end in folds:
            assert tr_end < te_start


class TestRunWalkForward:
    """Tests for the run_walk_forward tool."""

    def test_returns_immediately(self, job_manager):
        """Should return BacktestRunResult without blocking."""
        with patch(
            "qitp_mcp_backtest.tools.walk_forward._execute_walk_forward"
        ):
            result = run_walk_forward(
                job_manager,
                strategy_id="gap_momentum_up",
                symbols=["AAPL"],
                start_date=date(2023, 1, 1),
                end_date=date(2024, 12, 31),
            )
            assert isinstance(result, BacktestRunResult)
            assert result.run_id is not None
            assert result.status in ("queued", "running")

    def test_walk_forward_completes(
        self, job_manager, mock_engine_result, sample_ohlcv_df, strategy_yaml
    ):
        """Walk-forward should complete and produce fold results."""
        with (
            patch("qitp_mcp_backtest.tools.walk_forward.load_strategy_yaml") as mock_yaml,
            patch("qitp_mcp_backtest.tools.walk_forward.load_ohlcv") as mock_ohlcv,
            patch("qitp_mcp_backtest.tools.walk_forward.BacktestEngine") as MockEngine,
        ):
            mock_yaml.return_value = strategy_yaml
            mock_ohlcv.return_value = sample_ohlcv_df
            MockEngine.return_value.run.return_value = mock_engine_result

            result = run_walk_forward(
                job_manager,
                strategy_id="gap_momentum_up",
                symbols=["AAPL"],
                start_date=date(2023, 1, 1),
                end_date=date(2024, 12, 31),
                config=WalkForwardConfig(n_splits=3),
            )

            # Wait for completion
            job = job_manager.get(result.run_id)
            job._thread.join(timeout=10)

            assert job.status == "complete"
            wf_result = job.result
            assert isinstance(wf_result, WalkForwardResult)
            assert len(wf_result.folds) <= 3
            assert isinstance(wf_result.overfitting_flag, bool)


class TestCompareStrategies:
    """Tests for the compare_strategies tool."""

    def _create_completed_job(self, job_manager, strategy_id, metrics_override=None):
        """Helper: create a completed job with a BacktestResult."""
        import uuid

        run_id = str(uuid.uuid4())
        metrics = metrics_override or PerformanceMetrics(
            total_return_pct=10.0,
            annualized_return_pct=20.0,
            sharpe_ratio=1.5,
            sortino_ratio=1.8,
            max_drawdown_pct=8.0,
            win_rate_pct=55.0,
            profit_factor=1.6,
            total_trades=30,
            avg_trade_duration_days=4.0,
        )
        result = BacktestResult(
            run_id=run_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            metrics=metrics,
            equity_curve=[],
            trades=[],
        )

        # Directly inject into job manager
        from qitp_mcp_backtest.job_manager import Job

        job = Job(run_id=run_id, strategy_id=strategy_id)
        job.status = "complete"
        job.result = result
        job_manager._jobs[run_id] = job

        return run_id

    def test_compare_two_strategies(self, job_manager):
        """Should rank two strategies by metrics."""
        id1 = self._create_completed_job(
            job_manager,
            "strategy_a",
            PerformanceMetrics(
                total_return_pct=15.0,
                annualized_return_pct=30.0,
                sharpe_ratio=2.0,
                sortino_ratio=2.5,
                max_drawdown_pct=5.0,
                win_rate_pct=65.0,
                profit_factor=2.1,
                total_trades=50,
                avg_trade_duration_days=3.0,
            ),
        )
        id2 = self._create_completed_job(
            job_manager,
            "strategy_b",
            PerformanceMetrics(
                total_return_pct=8.0,
                annualized_return_pct=16.0,
                sharpe_ratio=1.2,
                sortino_ratio=1.4,
                max_drawdown_pct=12.0,
                win_rate_pct=52.0,
                profit_factor=1.3,
                total_trades=25,
                avg_trade_duration_days=5.0,
            ),
        )

        result = compare_strategies(job_manager, run_ids=[id1, id2])

        assert isinstance(result, ComparisonResult)
        assert result.rankings["sharpe_ratio"][0] == id1  # strategy_a has higher Sharpe
        assert result.rankings["max_drawdown_pct"][0] == id1  # lower drawdown = first
        assert len(result.summary) == 2

    def test_compare_requires_complete_jobs(self, job_manager):
        """Should raise if any run_id is not complete."""
        id1 = self._create_completed_job(job_manager, "a")

        # Create a running job
        from qitp_mcp_backtest.job_manager import Job

        running_id = "running-123"
        job = Job(run_id=running_id, strategy_id="b")
        job.status = "running"
        job_manager._jobs[running_id] = job

        with pytest.raises(ValueError, match="not complete"):
            compare_strategies(job_manager, run_ids=[id1, running_id])

    def test_compare_unknown_run_id(self, job_manager):
        """Should raise for unknown run_ids."""
        with pytest.raises(ValueError, match="Unknown run_id"):
            compare_strategies(job_manager, run_ids=["nope1", "nope2"])
```

### `tests/fixtures/gap_momentum_up.yaml`

```yaml
name: gap_momentum_up
version: "1.0"
description: "Buy stocks gapping up >2% at open with momentum confirmation"
universe:
  type: static
  symbols: ["AAPL", "MSFT"]
signals:
  - name: gap_up
    type: gap
    direction: up
    min_pct: 2.0
  - name: volume_surge
    type: volume_ratio
    lookback: 20
    min_ratio: 1.5
rules:
  entry:
    condition: "gap_up AND volume_surge"
    action: buy
    size: pct_equity
    size_value: 0.1
  exit:
    stop_loss_pct: 2.0
    take_profit_pct: 5.0
    max_hold_days: 5
    trailing_stop_pct: 1.5
```

### `Dockerfile`

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install build deps
RUN pip install --no-cache-dir hatchling

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Runtime
FROM python:3.12-slim

WORKDIR /app
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin
COPY --from=base /app /app

ENV PYTHONUNBUFFERED=1
ENV TRANSPORT=stdio

ENTRYPOINT ["qitp-mcp-backtest"]
```

### `docker-compose.yml`

```yaml
version: "3.8"

services:
  backtest-mcp:
    build: .
    container_name: qitp-backtest-mcp
    environment:
      - TRANSPORT=${TRANSPORT:-sse}
      - PORT=8080
      - LOG_LEVEL=INFO
      - QITP_OHLCV_BUCKET=qitp-historical-data
      - QITP_STRATEGY_BUCKET=qitp-strategy-blueprints
      - AWS_ENDPOINT_URL=http://localstack:4566
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test
      - AWS_DEFAULT_REGION=eu-west-1
    ports:
      - "8080:8080"
    depends_on:
      - localstack

  localstack:
    image: localstack/localstack:3
    container_name: qitp-backtest-localstack
    environment:
      - SERVICES=s3
      - DEFAULT_REGION=eu-west-1
    ports:
      - "4566:4566"
    volumes:
      - localstack-data:/var/lib/localstack

volumes:
  localstack-data:
```

---

## Acceptance Criteria

- [ ] `run_backtest` returns `run_id` immediately (async)
- [ ] `get_backtest_result` returns complete results after job finishes
- [ ] Walk-forward produces N fold results with overfitting detection
- [ ] `compare_strategies` ranks by multiple metrics
- [ ] S3 parquet data loading works
- [ ] Docker build succeeds
- [ ] All tests pass

## Test Plan

```bash
cd ~/dev/tccw-qitp-mcp-backtest
pip install -e ".[dev]"
pytest -v
```

To generate the sample parquet fixture:

```python
import pandas as pd
from pathlib import Path

dates = pd.date_range("2024-01-02", periods=60, freq="B")
df = pd.DataFrame({
    "date": dates,
    "open": [100 + i * 0.3 for i in range(60)],
    "high": [101 + i * 0.3 for i in range(60)],
    "low": [99 + i * 0.3 for i in range(60)],
    "close": [100.5 + i * 0.3 for i in range(60)],
    "volume": [1_000_000] * 60,
    "adjusted_close": [100.5 + i * 0.3 for i in range(60)],
})
df.to_parquet(Path("tests/fixtures/sample_ohlcv.parquet"), index=False)
```

## Agent Instructions

This MCP wraps the simulation library (P03). Keep the MCP layer thin — business logic lives in `qitp-simulation`. The MCP handles:

1. **Job management** — async submission, status polling, result retrieval
2. **Data loading** — S3 parquet reading and strategy YAML fetching
3. **Result storage** — via artifacts-mcp or direct S3

Use threading for async job execution in POC (not asyncio — simpler for Lambda compatibility). The `JobManager` uses an in-memory dict; production will upgrade to DynamoDB.

Key integration points with `qitp-simulation`:
```python
from qitp_simulation.engine import BacktestEngine
from qitp_simulation.slippage import PercentageSlippage, FixedSlippage, VolumeImpactSlippage
from qitp_simulation.commission import IBKRTieredEU, ZeroCommission
```

The `BacktestEngine` accepts `strategy_config` (dict from YAML), `market_data` (dict of symbol->DataFrame), `initial_capital`, `slippage_model`, and `commission_model`. Its `.run()` method returns a result object with `.metrics`, `.trades`, and `.equity_curve` attributes.
