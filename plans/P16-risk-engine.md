# P16 — Risk Engine

## Objective
Build the Risk Engine as a dedicated Lambda function (plain Python, NOT a Strands agent). Implements 8 hard risk rules with DynamoDB-configurable thresholds. Circuit breaker state machine (CLOSED/OPEN/HALF_OPEN) with per-rule persistence. Trailing Stop Manager triggered via EventBridge every 15 minutes during market hours. Returns structured PASS/FAIL verdicts with detailed failure reasons. All checks logged to `qitp_audit_log`.

## Plane Tickets
ROOT-60

## Target Repo
`~/dev/tccw-qitp-risk-engine`

## Dependencies
P14 (ibkr-mcp for position reads)

## Repo Structure
```
tccw-qitp-risk-engine/
├── src/
│   └── qitp_risk_engine/
│       ├── __init__.py
│       ├── handler.py                    # Lambda handler: check_risk_limits
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── base.py                   # Abstract RiskRule
│       │   ├── max_positions.py          # Max 5 open positions
│       │   ├── position_size.py          # Max 20% NAV per position
│       │   ├── sector_concentration.py   # Max 40% per sector
│       │   ├── daily_loss.py             # -3% daily loss circuit breaker
│       │   ├── drawdown.py               # -10% drawdown circuit breaker
│       │   ├── trailing_stop.py          # Trailing stop mandatory check
│       │   ├── leverage.py               # ESMA CFD leverage limits
│       │   └── short_sell.py             # CNMV short-sell restrictions
│       ├── circuit_breaker.py            # Circuit breaker state machine (DynamoDB)
│       ├── trailing_stop_manager.py      # EventBridge-triggered trailing stop ratchet
│       ├── config.py                     # DynamoDB-based rule configuration loader
│       ├── schemas.py                    # RiskCheckRequest, RiskCheckResult, CircuitBreakerState
│       └── audit.py                      # Audit logging to qitp_audit_log
├── tests/
│   ├── conftest.py
│   ├── test_handler.py
│   ├── test_rules.py
│   ├── test_circuit_breaker.py
│   ├── test_trailing_stop_manager.py
│   └── test_config.py
└── pyproject.toml
```

---

## Risk Rules Summary

| # | Rule | Default Threshold | Circuit Breaker? | Recovery |
|---|---|---|---|---|
| 1 | `max_positions` | 5 open positions | Yes — blocks new orders | Automatic when position closed |
| 2 | `position_size` | 20% NAV | No — rejects single order | N/A (per-order check) |
| 3 | `sector_concentration` | 40% per sector | No — rejects single order | N/A (per-order check) |
| 4 | `daily_loss` | -3% portfolio daily | Yes — halts ALL trading 24h | Time-based: 24h auto-reset |
| 5 | `drawdown` | -10% from peak NAV | Yes — halts ALL trading | Manual reset only |
| 6 | `trailing_stop_mandatory` | All positions | No — rejects order without stop | N/A (per-order check) |
| 7 | `leverage` | ESMA limits (varies by asset class) | No — rejects overleveraged | N/A (per-order check) |
| 8 | `short_sell` | CNMV IBEX35 ban list | No — rejects banned shorts | N/A (per-order check) |

---

## Full Inline Code

---

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-risk-engine"
version = "0.1.0"
description = "QITP Risk Engine — hard risk rules, circuit breakers, and trailing stop management"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6.0",
    "boto3>=1.34",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "moto[all]>=5.0.0",
    "freezegun>=1.4.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_risk_engine"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### `src/qitp_risk_engine/__init__.py`

```python
"""QITP Risk Engine — hard risk rules, circuit breakers, and trailing stop management.

This is a plain Python Lambda, NOT a Strands agent. It runs as a deterministic
gate before any order submission in Step Functions.
"""

__version__ = "0.1.0"
```

---

### `src/qitp_risk_engine/schemas.py`

```python
"""Pydantic schemas for the Risk Engine.

Defines request/response models, circuit breaker state, and rule violation details.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    """Order side."""
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"


class AssetClass(str, Enum):
    """Asset class for ESMA leverage rules."""
    MAJOR_FOREX = "major_forex"
    MINOR_FOREX = "minor_forex"
    INDEX_CFD = "index_cfd"
    EQUITY_CFD = "equity_cfd"
    COMMODITY_CFD = "commodity_cfd"
    CRYPTO_CFD = "crypto_cfd"
    EQUITY = "equity"  # No leverage limit for cash equities


class CircuitBreakerStatus(str, Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"       # Normal operation — rules pass
    OPEN = "OPEN"           # Tripped — trading halted
    HALF_OPEN = "HALF_OPEN" # Awaiting manual reset (drawdown) or time expiry (daily_loss)


class RiskCheckRequest(BaseModel):
    """Input to the risk engine Lambda.

    This is the payload that Step Functions sends before any order execution.
    """
    # Order details
    symbol: str = Field(..., description="Ticker symbol (e.g., AAPL, SAN.MC)")
    side: OrderSide = Field(..., description="Order side: BUY, SELL, SHORT, COVER")
    quantity: int = Field(..., gt=0, description="Number of shares/contracts")
    price: float = Field(..., gt=0, description="Estimated execution price")
    asset_class: AssetClass = Field(
        default=AssetClass.EQUITY,
        description="Asset class for leverage classification",
    )
    sector: str = Field(default="unknown", description="GICS sector of the symbol")
    has_trailing_stop: bool = Field(
        default=False,
        description="Whether a trailing stop is attached to this order",
    )
    trailing_stop_pct: float | None = Field(
        default=None,
        description="Trailing stop percentage (e.g., 3.0 for 3%)",
    )
    is_cfd: bool = Field(default=False, description="Whether this is a CFD trade")
    leverage_ratio: float = Field(
        default=1.0,
        ge=1.0,
        description="Leverage ratio for CFD trades",
    )

    # Portfolio context (provided by Step Functions from ibkr-mcp reads)
    portfolio_nav: float = Field(..., gt=0, description="Current net asset value in EUR")
    peak_nav: float = Field(..., gt=0, description="Peak NAV since last drawdown reset")
    daily_pnl_pct: float = Field(
        default=0.0,
        description="Today's portfolio P&L as percentage (e.g., -2.5 for -2.5%)",
    )
    open_positions: list[PositionInfo] = Field(
        default_factory=list,
        description="Currently open positions",
    )

    # Execution context
    execution_mode: str = Field(default="backtest", description="backtest|paper|live")
    sfn_execution_id: str = Field(
        default="",
        description="Step Functions execution ID for audit correlation",
    )


class PositionInfo(BaseModel):
    """Summary of an existing open position."""
    symbol: str
    quantity: int
    market_value: float = Field(description="Current market value in EUR")
    sector: str = Field(default="unknown")
    has_trailing_stop: bool = Field(default=False)
    trailing_stop_price: float | None = Field(default=None)
    entry_price: float = Field(default=0.0)


# Fix forward reference — PositionInfo defined after RiskCheckRequest uses it
RiskCheckRequest.model_rebuild()


class RuleViolation(BaseModel):
    """Details of a single rule violation."""
    rule_id: str = Field(..., description="Rule identifier (e.g., max_positions)")
    rule_name: str = Field(..., description="Human-readable rule name")
    message: str = Field(..., description="Detailed violation message")
    current_value: Any = Field(description="Current value that violated the rule")
    threshold: Any = Field(description="Threshold that was exceeded")
    severity: str = Field(
        default="HARD",
        description="HARD (blocks order) or WARN (advisory only)",
    )


class CircuitBreakerState(BaseModel):
    """Persisted circuit breaker state in DynamoDB."""
    breaker_id: str = Field(..., description="e.g., daily_loss, drawdown, max_positions")
    status: CircuitBreakerStatus = Field(default=CircuitBreakerStatus.CLOSED)
    tripped_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(
        default=None,
        description="When the breaker auto-resets (None = manual only)",
    )
    tripped_value: float | None = Field(
        default=None,
        description="Value that caused the trip",
    )
    threshold: float | None = Field(default=None)
    last_checked: datetime | None = Field(default=None)


class RiskCheckResult(BaseModel):
    """Output from the risk engine Lambda.

    Step Functions reads `verdict` to decide whether to proceed with order execution.
    """
    verdict: str = Field(..., description="PASS or FAIL")
    violations: list[RuleViolation] = Field(
        default_factory=list,
        description="List of rule violations (empty if PASS)",
    )
    circuit_breakers_active: list[CircuitBreakerState] = Field(
        default_factory=list,
        description="Currently active (OPEN) circuit breakers",
    )
    rules_evaluated: int = Field(default=0, description="Number of rules evaluated")
    evaluation_ms: float = Field(default=0.0, description="Evaluation time in milliseconds")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (per-rule details, portfolio snapshot)",
    )


class TrailingStopUpdate(BaseModel):
    """Trailing stop ratchet update for a single position."""
    symbol: str
    old_stop_price: float | None
    new_stop_price: float
    current_price: float
    ratchet_pct: float
    updated: bool = Field(description="True if stop was actually moved up")
```

---

### `src/qitp_risk_engine/config.py`

```python
"""DynamoDB-based rule configuration loader.

All risk rule thresholds are stored in the `qitp_risk_state` DynamoDB table.
This module loads them at invocation time so thresholds can be changed without
redeploying the Lambda.

Table schema:
    PK: rule_id (str)  — e.g., "max_positions", "daily_loss"
    threshold (N)       — numeric threshold value
    enabled (BOOL)      — whether the rule is active
    metadata (M)        — rule-specific extra config (e.g., ESMA leverage table)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)

# Default thresholds — used if DynamoDB entry is missing
DEFAULTS: dict[str, dict[str, Any]] = {
    "max_positions": {
        "threshold": 5,
        "enabled": True,
        "metadata": {},
    },
    "position_size": {
        "threshold": 20.0,  # percent of NAV
        "enabled": True,
        "metadata": {},
    },
    "sector_concentration": {
        "threshold": 40.0,  # percent of NAV
        "enabled": True,
        "metadata": {},
    },
    "daily_loss": {
        "threshold": -3.0,  # percent
        "enabled": True,
        "metadata": {"halt_hours": 24},
    },
    "drawdown": {
        "threshold": -10.0,  # percent from peak
        "enabled": True,
        "metadata": {"recovery": "manual"},
    },
    "trailing_stop_mandatory": {
        "threshold": 1,  # boolean-like: 1 = mandatory
        "enabled": True,
        "metadata": {},
    },
    "leverage": {
        "threshold": 1.0,  # placeholder — actual limits in metadata
        "enabled": True,
        "metadata": {
            "limits": {
                "major_forex": 30.0,
                "minor_forex": 20.0,
                "index_cfd": 20.0,
                "equity_cfd": 5.0,
                "commodity_cfd": 10.0,
                "crypto_cfd": 2.0,
                "equity": 999.0,  # No leverage limit for cash equities
            }
        },
    },
    "short_sell": {
        "threshold": 1,  # boolean-like: 1 = check enabled
        "enabled": True,
        "metadata": {
            "cnmv_ban_list": [],  # Populated from DynamoDB at runtime
            "ibex35_symbols": [
                "SAN.MC", "BBVA.MC", "ITX.MC", "IBE.MC", "TEF.MC",
                "REP.MC", "CABK.MC", "FER.MC", "AMS.MC", "GRF.MC",
                "ENG.MC", "ACS.MC", "MAP.MC", "FLE.MC", "COL.MC",
                "RED.MC", "IAG.MC", "MRL.MC", "CLNX.MC", "LOG.MC",
                "ACX.MC", "SAB.MC", "BKT.MC", "SGRE.MC", "VIS.MC",
                "MTS.MC", "CIE.MC", "ALM.MC", "MEL.MC", "SOL.MC",
                "PHM.MC", "AENA.MC", "ELE.MC", "IDR.MC", "ROV.MC",
            ],
        },
    },
}


class RiskConfig:
    """Loads and caches risk rule configuration from DynamoDB.

    Usage:
        config = RiskConfig()
        max_pos = config.get_threshold("max_positions")  # -> 5
        leverage_limits = config.get_metadata("leverage", "limits")
    """

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_resource: Any = None,
    ) -> None:
        self._table_name = table_name or os.environ.get(
            "RISK_STATE_TABLE", "qitp_risk_state"
        )
        self._dynamodb = dynamodb_resource or boto3.resource(
            "dynamodb",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )
        self._cache: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all rule configurations from DynamoDB.

        Falls back to DEFAULTS for any rule not found in the table.
        """
        self._cache = {rule_id: dict(cfg) for rule_id, cfg in DEFAULTS.items()}

        try:
            table = self._dynamodb.Table(self._table_name)
            response = table.scan(
                FilterExpression="begins_with(PK, :prefix)",
                ExpressionAttributeValues={":prefix": "RULE#"},
            )

            for item in response.get("Items", []):
                rule_id = item["PK"].replace("RULE#", "")
                if rule_id in self._cache:
                    if "threshold" in item:
                        self._cache[rule_id]["threshold"] = float(item["threshold"])
                    if "enabled" in item:
                        self._cache[rule_id]["enabled"] = bool(item["enabled"])
                    if "metadata" in item:
                        meta = item["metadata"]
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        self._cache[rule_id]["metadata"] = meta

            logger.info(
                "Loaded risk config from DynamoDB",
                extra={"rules_loaded": len(response.get("Items", []))},
            )
        except Exception:
            logger.warning(
                "Failed to load risk config from DynamoDB, using defaults",
                exc_info=True,
            )

        self._loaded = True

    def get_threshold(self, rule_id: str) -> float:
        """Get the threshold for a rule."""
        if not self._loaded:
            self.load()
        cfg = self._cache.get(rule_id, DEFAULTS.get(rule_id, {}))
        return float(cfg.get("threshold", 0))

    def is_enabled(self, rule_id: str) -> bool:
        """Check if a rule is enabled."""
        if not self._loaded:
            self.load()
        cfg = self._cache.get(rule_id, DEFAULTS.get(rule_id, {}))
        return bool(cfg.get("enabled", True))

    def get_metadata(self, rule_id: str, key: str | None = None) -> Any:
        """Get metadata for a rule, optionally a specific key."""
        if not self._loaded:
            self.load()
        cfg = self._cache.get(rule_id, DEFAULTS.get(rule_id, {}))
        metadata = cfg.get("metadata", {})
        if key is not None:
            return metadata.get(key)
        return metadata

    def get_all_configs(self) -> dict[str, dict[str, Any]]:
        """Return all rule configurations."""
        if not self._loaded:
            self.load()
        return dict(self._cache)
```

---

### `src/qitp_risk_engine/circuit_breaker.py`

```python
"""Circuit breaker state machine persisted in DynamoDB.

States:
    CLOSED    — Normal. All checks pass.
    OPEN      — Tripped by a rule violation. Trading halted.
    HALF_OPEN — Pending reset. For daily_loss: auto-resets after 24h.
                For drawdown: requires manual reset via API/CLI.

DynamoDB table: qitp_risk_state
    PK: "BREAKER#{breaker_id}"
    status: CLOSED | OPEN | HALF_OPEN
    tripped_at: ISO timestamp
    expires_at: ISO timestamp (null for manual-reset breakers)
    tripped_value: float
    threshold: float
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from qitp_risk_engine.schemas import CircuitBreakerState, CircuitBreakerStatus

logger = logging.getLogger(__name__)


class CircuitBreakerManager:
    """Manages circuit breaker state transitions in DynamoDB.

    Usage:
        mgr = CircuitBreakerManager()
        state = mgr.get_state("daily_loss")
        if state.status == CircuitBreakerStatus.OPEN:
            # Trading halted
            ...
        mgr.trip("daily_loss", current_value=-3.5, threshold=-3.0, auto_reset_hours=24)
        mgr.reset("drawdown")  # Manual reset
    """

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_resource: Any = None,
    ) -> None:
        self._table_name = table_name or os.environ.get(
            "RISK_STATE_TABLE", "qitp_risk_state"
        )
        self._dynamodb = dynamodb_resource or boto3.resource(
            "dynamodb",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )

    def _pk(self, breaker_id: str) -> str:
        return f"BREAKER#{breaker_id}"

    def get_state(self, breaker_id: str) -> CircuitBreakerState:
        """Get current circuit breaker state.

        If the breaker is OPEN and has expired, transitions to HALF_OPEN
        (for time-based breakers) or stays OPEN (for manual-reset breakers).
        """
        table = self._dynamodb.Table(self._table_name)
        now = datetime.now(timezone.utc)

        try:
            response = table.get_item(Key={"PK": self._pk(breaker_id)})
            item = response.get("Item")

            if not item:
                return CircuitBreakerState(
                    breaker_id=breaker_id,
                    status=CircuitBreakerStatus.CLOSED,
                    last_checked=now,
                )

            state = CircuitBreakerState(
                breaker_id=breaker_id,
                status=CircuitBreakerStatus(item.get("status", "CLOSED")),
                tripped_at=(
                    datetime.fromisoformat(item["tripped_at"])
                    if item.get("tripped_at")
                    else None
                ),
                expires_at=(
                    datetime.fromisoformat(item["expires_at"])
                    if item.get("expires_at")
                    else None
                ),
                tripped_value=(
                    float(item["tripped_value"])
                    if item.get("tripped_value") is not None
                    else None
                ),
                threshold=(
                    float(item["threshold"])
                    if item.get("threshold") is not None
                    else None
                ),
                last_checked=now,
            )

            # Auto-transition OPEN -> HALF_OPEN if expired
            if (
                state.status == CircuitBreakerStatus.OPEN
                and state.expires_at is not None
                and now >= state.expires_at
            ):
                state.status = CircuitBreakerStatus.HALF_OPEN
                self._update_status(breaker_id, CircuitBreakerStatus.HALF_OPEN)
                logger.info(
                    "Circuit breaker auto-transitioned to HALF_OPEN",
                    extra={"breaker_id": breaker_id, "expired_at": str(state.expires_at)},
                )

            return state

        except Exception:
            logger.warning(
                "Failed to read circuit breaker state, defaulting to CLOSED",
                extra={"breaker_id": breaker_id},
                exc_info=True,
            )
            return CircuitBreakerState(
                breaker_id=breaker_id,
                status=CircuitBreakerStatus.CLOSED,
                last_checked=now,
            )

    def get_all_active(self) -> list[CircuitBreakerState]:
        """Get all circuit breakers that are currently OPEN or HALF_OPEN."""
        table = self._dynamodb.Table(self._table_name)
        now = datetime.now(timezone.utc)
        active = []

        try:
            response = table.scan(
                FilterExpression="begins_with(PK, :prefix) AND #s IN (:open, :half)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":prefix": "BREAKER#",
                    ":open": "OPEN",
                    ":half": "HALF_OPEN",
                },
            )

            for item in response.get("Items", []):
                breaker_id = item["PK"].replace("BREAKER#", "")
                state = self.get_state(breaker_id)  # Handles expiry transitions
                if state.status in (
                    CircuitBreakerStatus.OPEN,
                    CircuitBreakerStatus.HALF_OPEN,
                ):
                    active.append(state)

        except Exception:
            logger.warning("Failed to scan active circuit breakers", exc_info=True)

        return active

    def trip(
        self,
        breaker_id: str,
        current_value: float,
        threshold: float,
        auto_reset_hours: float | None = None,
    ) -> CircuitBreakerState:
        """Trip a circuit breaker to OPEN state.

        Args:
            breaker_id: Which breaker to trip.
            current_value: The value that caused the trip.
            threshold: The threshold that was exceeded.
            auto_reset_hours: If set, breaker auto-resets after this many hours.
                             If None, requires manual reset.
        """
        table = self._dynamodb.Table(self._table_name)
        now = datetime.now(timezone.utc)

        expires_at = None
        if auto_reset_hours is not None:
            expires_at = now + timedelta(hours=auto_reset_hours)

        item = {
            "PK": self._pk(breaker_id),
            "status": CircuitBreakerStatus.OPEN.value,
            "tripped_at": now.isoformat(),
            "tripped_value": str(current_value),
            "threshold": str(threshold),
            "last_checked": now.isoformat(),
        }
        if expires_at:
            item["expires_at"] = expires_at.isoformat()

        table.put_item(Item=item)

        state = CircuitBreakerState(
            breaker_id=breaker_id,
            status=CircuitBreakerStatus.OPEN,
            tripped_at=now,
            expires_at=expires_at,
            tripped_value=current_value,
            threshold=threshold,
            last_checked=now,
        )

        logger.warning(
            "Circuit breaker TRIPPED",
            extra={
                "breaker_id": breaker_id,
                "current_value": current_value,
                "threshold": threshold,
                "expires_at": str(expires_at),
            },
        )

        return state

    def reset(self, breaker_id: str) -> CircuitBreakerState:
        """Manually reset a circuit breaker to CLOSED.

        Used for drawdown breaker (manual resume required) or force-reset.
        """
        table = self._dynamodb.Table(self._table_name)
        now = datetime.now(timezone.utc)

        table.put_item(
            Item={
                "PK": self._pk(breaker_id),
                "status": CircuitBreakerStatus.CLOSED.value,
                "last_checked": now.isoformat(),
            }
        )

        logger.info(
            "Circuit breaker manually RESET",
            extra={"breaker_id": breaker_id},
        )

        return CircuitBreakerState(
            breaker_id=breaker_id,
            status=CircuitBreakerStatus.CLOSED,
            last_checked=now,
        )

    def _update_status(
        self, breaker_id: str, status: CircuitBreakerStatus
    ) -> None:
        """Update just the status field of a breaker."""
        table = self._dynamodb.Table(self._table_name)
        now = datetime.now(timezone.utc)

        table.update_item(
            Key={"PK": self._pk(breaker_id)},
            UpdateExpression="SET #s = :status, last_checked = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": status.value,
                ":now": now.isoformat(),
            },
        )
```

---

### `src/qitp_risk_engine/audit.py`

```python
"""Audit logging to qitp_audit_log DynamoDB table.

Every risk check — pass or fail — is recorded with full context for
MiFID II compliance (5-year retention).

Table schema:
    PK: "AUDIT#{iso_date}"
    SK: "{timestamp}#{sfn_execution_id}"
    event_type: "RISK_CHECK"
    verdict: "PASS" | "FAIL"
    symbol: str
    side: str
    violations: list[dict]
    circuit_breakers: list[dict]
    request_snapshot: dict
    ttl: int (epoch seconds, 5 years from now)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

from qitp_risk_engine.schemas import RiskCheckRequest, RiskCheckResult

logger = logging.getLogger(__name__)

# 5 years in seconds (MiFID II retention requirement)
RETENTION_SECONDS = 5 * 365 * 24 * 60 * 60  # ~157,680,000


class AuditLogger:
    """Logs risk check events to DynamoDB audit table."""

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_resource: Any = None,
    ) -> None:
        self._table_name = table_name or os.environ.get(
            "AUDIT_LOG_TABLE", "qitp_audit_log"
        )
        self._dynamodb = dynamodb_resource or boto3.resource(
            "dynamodb",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )

    def log_risk_check(
        self,
        request: RiskCheckRequest,
        result: RiskCheckResult,
    ) -> None:
        """Log a complete risk check event.

        Args:
            request: The incoming risk check request.
            result: The risk engine's verdict and details.
        """
        now = datetime.now(timezone.utc)
        iso_date = now.strftime("%Y-%m-%d")
        timestamp_ms = int(now.timestamp() * 1000)
        ttl = int(now.timestamp()) + RETENTION_SECONDS

        item = {
            "PK": f"AUDIT#{iso_date}",
            "SK": f"{timestamp_ms}#{request.sfn_execution_id or 'no-sfn'}",
            "event_type": "RISK_CHECK",
            "timestamp": now.isoformat(),
            "verdict": result.verdict,
            "symbol": request.symbol,
            "side": request.side.value,
            "quantity": request.quantity,
            "price": str(request.price),
            "portfolio_nav": str(request.portfolio_nav),
            "execution_mode": request.execution_mode,
            "sfn_execution_id": request.sfn_execution_id,
            "rules_evaluated": result.rules_evaluated,
            "evaluation_ms": str(result.evaluation_ms),
            "violations": [v.model_dump() for v in result.violations],
            "circuit_breakers_active": [
                cb.model_dump(mode="json") for cb in result.circuit_breakers_active
            ],
            "ttl": ttl,
        }

        try:
            table = self._dynamodb.Table(self._table_name)
            table.put_item(Item=item)
            logger.info(
                "Audit log written",
                extra={
                    "verdict": result.verdict,
                    "symbol": request.symbol,
                    "violations": len(result.violations),
                },
            )
        except Exception:
            # Audit logging failure must NOT block order processing.
            # Log the error and continue — but this should trigger an alert.
            logger.error(
                "AUDIT LOG WRITE FAILED — compliance gap",
                extra={"symbol": request.symbol, "verdict": result.verdict},
                exc_info=True,
            )
```

---

### `src/qitp_risk_engine/rules/__init__.py`

```python
"""Risk rules registry.

All rules are registered here and evaluated in order by the handler.
"""

from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.rules.daily_loss import DailyLossRule
from qitp_risk_engine.rules.drawdown import DrawdownRule
from qitp_risk_engine.rules.leverage import LeverageRule
from qitp_risk_engine.rules.max_positions import MaxPositionsRule
from qitp_risk_engine.rules.position_size import PositionSizeRule
from qitp_risk_engine.rules.sector_concentration import SectorConcentrationRule
from qitp_risk_engine.rules.short_sell import ShortSellRule
from qitp_risk_engine.rules.trailing_stop import TrailingStopMandatoryRule

# Evaluation order matters: circuit breakers first, then per-order checks
ALL_RULES: list[type[RiskRule]] = [
    DailyLossRule,          # Circuit breaker — check first
    DrawdownRule,           # Circuit breaker — check first
    MaxPositionsRule,       # Circuit breaker — blocks new orders
    PositionSizeRule,       # Per-order check
    SectorConcentrationRule,  # Per-order check
    TrailingStopMandatoryRule,  # Per-order check
    LeverageRule,           # Per-order check (ESMA)
    ShortSellRule,          # Per-order check (CNMV)
]

__all__ = [
    "RiskRule",
    "ALL_RULES",
    "DailyLossRule",
    "DrawdownRule",
    "LeverageRule",
    "MaxPositionsRule",
    "PositionSizeRule",
    "SectorConcentrationRule",
    "ShortSellRule",
    "TrailingStopMandatoryRule",
]
```

---

### `src/qitp_risk_engine/rules/base.py`

```python
"""Abstract base class for all risk rules.

Every rule follows the same interface:
    1. `rule_id` — unique identifier, matches DynamoDB config key
    2. `rule_name` — human-readable name
    3. `has_circuit_breaker` — whether this rule can trip a circuit breaker
    4. `evaluate(request, config, breaker_mgr)` — returns RuleViolation or None
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.schemas import RiskCheckRequest, RuleViolation


class RiskRule(ABC):
    """Abstract risk rule. All 8 rules extend this."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier (matches DynamoDB config key)."""
        ...

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Human-readable rule name."""
        ...

    @property
    def has_circuit_breaker(self) -> bool:
        """Whether this rule can trip a circuit breaker. Override to return True."""
        return False

    @abstractmethod
    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        """Evaluate the rule against the request.

        Args:
            request: The risk check request with order and portfolio context.
            config: DynamoDB-loaded rule configuration.
            breaker_mgr: Circuit breaker manager for state checks/trips.

        Returns:
            RuleViolation if the rule is violated, None if it passes.
        """
        ...
```

---

### `src/qitp_risk_engine/rules/max_positions.py`

```python
"""Rule 1: Maximum open positions.

Default: 5 open positions.
Circuit breaker: Yes — blocks new BUY/SHORT orders when at max.
SELL/COVER orders always pass (they reduce position count).
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import OrderSide, RiskCheckRequest, RuleViolation


class MaxPositionsRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "max_positions"

    @property
    def rule_name(self) -> str:
        return "Maximum Open Positions"

    @property
    def has_circuit_breaker(self) -> bool:
        return True

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # SELL/COVER always passes — they reduce position count
        if request.side in (OrderSide.SELL, OrderSide.COVER):
            return None

        max_positions = int(config.get_threshold(self.rule_id))
        current_count = len(request.open_positions)

        # Check if this order opens a new position (not adding to existing)
        existing_symbols = {p.symbol for p in request.open_positions}
        is_new_position = request.symbol not in existing_symbols

        if is_new_position and current_count >= max_positions:
            # Trip the circuit breaker
            breaker_mgr.trip(
                breaker_id=self.rule_id,
                current_value=float(current_count),
                threshold=float(max_positions),
                auto_reset_hours=None,  # Resets automatically when position closed
            )

            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Cannot open new position: {current_count}/{max_positions} "
                    f"positions already open. Close an existing position first."
                ),
                current_value=current_count,
                threshold=max_positions,
                severity="HARD",
            )

        # If we're below max, ensure breaker is closed
        if current_count < max_positions:
            state = breaker_mgr.get_state(self.rule_id)
            if state.status.value != "CLOSED":
                breaker_mgr.reset(self.rule_id)

        return None
```

---

### `src/qitp_risk_engine/rules/position_size.py`

```python
"""Rule 2: Maximum position size as percentage of NAV.

Default: 20% of NAV per single position.
No circuit breaker — rejects the specific order.
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import OrderSide, RiskCheckRequest, RuleViolation


class PositionSizeRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "position_size"

    @property
    def rule_name(self) -> str:
        return "Maximum Position Size"

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # SELL/COVER always passes
        if request.side in (OrderSide.SELL, OrderSide.COVER):
            return None

        max_pct = config.get_threshold(self.rule_id)
        order_value = request.quantity * request.price

        # Add existing position value if adding to an existing position
        existing_value = 0.0
        for pos in request.open_positions:
            if pos.symbol == request.symbol:
                existing_value = pos.market_value
                break

        total_position_value = existing_value + order_value
        position_pct = (total_position_value / request.portfolio_nav) * 100

        if position_pct > max_pct:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Position in {request.symbol} would be {position_pct:.1f}% of NAV "
                    f"(limit: {max_pct:.1f}%). Order value: {order_value:.2f}, "
                    f"existing: {existing_value:.2f}, total: {total_position_value:.2f}, "
                    f"NAV: {request.portfolio_nav:.2f}."
                ),
                current_value=round(position_pct, 2),
                threshold=max_pct,
                severity="HARD",
            )

        return None
```

---

### `src/qitp_risk_engine/rules/sector_concentration.py`

```python
"""Rule 3: Maximum sector concentration as percentage of NAV.

Default: 40% of NAV per sector.
No circuit breaker — rejects the specific order.
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import OrderSide, RiskCheckRequest, RuleViolation


class SectorConcentrationRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "sector_concentration"

    @property
    def rule_name(self) -> str:
        return "Maximum Sector Concentration"

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # SELL/COVER always passes
        if request.side in (OrderSide.SELL, OrderSide.COVER):
            return None

        # Skip if sector is unknown
        if request.sector == "unknown":
            return None

        max_pct = config.get_threshold(self.rule_id)
        order_value = request.quantity * request.price

        # Sum existing positions in the same sector
        sector_value = sum(
            p.market_value
            for p in request.open_positions
            if p.sector == request.sector
        )

        total_sector_value = sector_value + order_value
        sector_pct = (total_sector_value / request.portfolio_nav) * 100

        if sector_pct > max_pct:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Sector '{request.sector}' would be {sector_pct:.1f}% of NAV "
                    f"(limit: {max_pct:.1f}%). Existing sector exposure: "
                    f"{sector_value:.2f}, order adds: {order_value:.2f}."
                ),
                current_value=round(sector_pct, 2),
                threshold=max_pct,
                severity="HARD",
            )

        return None
```

---

### `src/qitp_risk_engine/rules/daily_loss.py`

```python
"""Rule 4: Daily portfolio loss circuit breaker.

Default: -3% daily P&L triggers 24-hour trading halt.
Circuit breaker: Yes — halts ALL trading for 24 hours (time-based auto-reset).
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import CircuitBreakerStatus, RiskCheckRequest, RuleViolation


class DailyLossRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "daily_loss"

    @property
    def rule_name(self) -> str:
        return "Daily Loss Circuit Breaker"

    @property
    def has_circuit_breaker(self) -> bool:
        return True

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # Check if breaker is already open
        state = breaker_mgr.get_state(self.rule_id)
        if state.status == CircuitBreakerStatus.OPEN:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Daily loss circuit breaker is OPEN. Trading halted until "
                    f"{state.expires_at.isoformat() if state.expires_at else 'manual reset'}. "
                    f"Triggered at {state.tripped_value}% daily loss "
                    f"(threshold: {state.threshold}%)."
                ),
                current_value=state.tripped_value,
                threshold=state.threshold,
                severity="HARD",
            )

        # Evaluate current daily P&L
        threshold_pct = config.get_threshold(self.rule_id)  # -3.0
        halt_hours = config.get_metadata(self.rule_id, "halt_hours") or 24

        if request.daily_pnl_pct <= threshold_pct:
            # Trip the circuit breaker with 24h auto-reset
            breaker_mgr.trip(
                breaker_id=self.rule_id,
                current_value=request.daily_pnl_pct,
                threshold=threshold_pct,
                auto_reset_hours=float(halt_hours),
            )

            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Daily portfolio loss of {request.daily_pnl_pct:.2f}% exceeds "
                    f"threshold of {threshold_pct:.1f}%. ALL trading halted for "
                    f"{halt_hours} hours."
                ),
                current_value=round(request.daily_pnl_pct, 4),
                threshold=threshold_pct,
                severity="HARD",
            )

        return None
```

---

### `src/qitp_risk_engine/rules/drawdown.py`

```python
"""Rule 5: Drawdown from peak NAV circuit breaker.

Default: -10% from peak NAV triggers full halt requiring manual resume.
Circuit breaker: Yes — halts ALL trading, manual reset only.
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import CircuitBreakerStatus, RiskCheckRequest, RuleViolation


class DrawdownRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "drawdown"

    @property
    def rule_name(self) -> str:
        return "Drawdown Circuit Breaker"

    @property
    def has_circuit_breaker(self) -> bool:
        return True

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # Check if breaker is already open
        state = breaker_mgr.get_state(self.rule_id)
        if state.status == CircuitBreakerStatus.OPEN:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Drawdown circuit breaker is OPEN. ALL trading halted. "
                    f"Manual reset required. Triggered at {state.tripped_value}% "
                    f"drawdown from peak (threshold: {state.threshold}%)."
                ),
                current_value=state.tripped_value,
                threshold=state.threshold,
                severity="HARD",
            )

        # Calculate current drawdown
        threshold_pct = config.get_threshold(self.rule_id)  # -10.0

        if request.peak_nav <= 0:
            return None  # Cannot compute drawdown without peak

        drawdown_pct = ((request.portfolio_nav - request.peak_nav) / request.peak_nav) * 100

        if drawdown_pct <= threshold_pct:
            # Trip the circuit breaker — NO auto-reset (manual only)
            breaker_mgr.trip(
                breaker_id=self.rule_id,
                current_value=drawdown_pct,
                threshold=threshold_pct,
                auto_reset_hours=None,  # Manual reset required
            )

            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Portfolio drawdown of {drawdown_pct:.2f}% from peak NAV "
                    f"({request.peak_nav:.2f}) exceeds threshold of "
                    f"{threshold_pct:.1f}%. ALL trading halted. Manual resume required."
                ),
                current_value=round(drawdown_pct, 4),
                threshold=threshold_pct,
                severity="HARD",
            )

        return None
```

---

### `src/qitp_risk_engine/rules/trailing_stop.py`

```python
"""Rule 6: Trailing stop mandatory for all positions.

Every order must have a trailing stop attached. Orders without a trailing
stop are rejected. This ensures every position has downside protection.
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import OrderSide, RiskCheckRequest, RuleViolation


class TrailingStopMandatoryRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "trailing_stop_mandatory"

    @property
    def rule_name(self) -> str:
        return "Trailing Stop Mandatory"

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # Only applies to BUY/SHORT (opening positions)
        if request.side in (OrderSide.SELL, OrderSide.COVER):
            return None

        if not request.has_trailing_stop:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Order for {request.symbol} ({request.side.value}) rejected: "
                    f"trailing stop is mandatory for all positions. "
                    f"Attach a trailing stop before submitting."
                ),
                current_value=False,
                threshold=True,
                severity="HARD",
            )

        # Validate trailing stop percentage is reasonable (0.5% to 25%)
        if request.trailing_stop_pct is not None:
            if request.trailing_stop_pct < 0.5 or request.trailing_stop_pct > 25.0:
                return RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    message=(
                        f"Trailing stop percentage {request.trailing_stop_pct}% "
                        f"is outside valid range (0.5% to 25%). "
                        f"Adjust the trailing stop before submitting."
                    ),
                    current_value=request.trailing_stop_pct,
                    threshold="0.5% - 25.0%",
                    severity="HARD",
                )

        return None
```

---

### `src/qitp_risk_engine/rules/leverage.py`

```python
"""Rule 7: ESMA CFD leverage limits.

Enforces maximum leverage ratios per asset class as defined by ESMA regulation:
    - Major forex pairs: 30:1
    - Minor forex pairs: 20:1
    - Index CFDs: 20:1
    - Equity CFDs: 5:1
    - Commodity CFDs: 10:1
    - Crypto CFDs: 2:1
    - Cash equities: no leverage limit

Only applies to CFD trades (request.is_cfd == True).
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import AssetClass, RiskCheckRequest, RuleViolation

# Hardcoded fallback if DynamoDB metadata is empty
DEFAULT_LEVERAGE_LIMITS: dict[str, float] = {
    "major_forex": 30.0,
    "minor_forex": 20.0,
    "index_cfd": 20.0,
    "equity_cfd": 5.0,
    "commodity_cfd": 10.0,
    "crypto_cfd": 2.0,
    "equity": 999.0,  # Effectively unlimited for cash equities
}


class LeverageRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "leverage"

    @property
    def rule_name(self) -> str:
        return "ESMA CFD Leverage Limits"

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # Only applies to CFD trades
        if not request.is_cfd:
            return None

        # Get leverage limits from config (DynamoDB) or use defaults
        limits = config.get_metadata(self.rule_id, "limits") or DEFAULT_LEVERAGE_LIMITS
        asset_class_key = request.asset_class.value
        max_leverage = float(limits.get(asset_class_key, 999.0))

        if request.leverage_ratio > max_leverage:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Leverage ratio {request.leverage_ratio:.1f}:1 for "
                    f"{request.asset_class.value} exceeds ESMA limit of "
                    f"{max_leverage:.0f}:1. Reduce position size or leverage."
                ),
                current_value=request.leverage_ratio,
                threshold=max_leverage,
                severity="HARD",
            )

        return None
```

---

### `src/qitp_risk_engine/rules/short_sell.py`

```python
"""Rule 8: CNMV short-sell restrictions for IBEX35 symbols.

Spain's CNMV can impose temporary short-selling bans on IBEX35 constituents.
This rule checks against a configurable ban list stored in DynamoDB.

Only applies to SHORT orders on symbols in the IBEX35 universe.
"""

from __future__ import annotations

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules.base import RiskRule
from qitp_risk_engine.schemas import OrderSide, RiskCheckRequest, RuleViolation


class ShortSellRule(RiskRule):
    @property
    def rule_id(self) -> str:
        return "short_sell"

    @property
    def rule_name(self) -> str:
        return "CNMV Short-Sell Restrictions"

    def evaluate(
        self,
        request: RiskCheckRequest,
        config: RiskConfig,
        breaker_mgr: CircuitBreakerManager,
    ) -> RuleViolation | None:
        # Only applies to SHORT orders
        if request.side != OrderSide.SHORT:
            return None

        # Get IBEX35 universe and ban list from config
        ibex35_symbols = set(
            config.get_metadata(self.rule_id, "ibex35_symbols") or []
        )
        cnmv_ban_list = set(
            config.get_metadata(self.rule_id, "cnmv_ban_list") or []
        )

        # Only check IBEX35 symbols
        if request.symbol not in ibex35_symbols:
            return None

        # Check against CNMV ban list
        if request.symbol in cnmv_ban_list:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                message=(
                    f"Short selling of {request.symbol} is currently prohibited "
                    f"by CNMV. The symbol is on the active short-sell ban list. "
                    f"Check CNMV announcements for ban expiry."
                ),
                current_value=request.symbol,
                threshold="CNMV ban list",
                severity="HARD",
            )

        return None
```

---

### `src/qitp_risk_engine/trailing_stop_manager.py`

```python
"""Trailing Stop Manager — EventBridge-triggered ratchet mechanism.

Runs every 15 minutes during market hours (08:00-21:00 CET) via EventBridge.
For each open position with a trailing stop, checks current price and ratchets
the stop UP only (never down).

EventBridge rule: rate(15 minutes), filtered to market hours by the handler.

This is a SEPARATE Lambda handler from the risk check handler.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from qitp_risk_engine.audit import AuditLogger
from qitp_risk_engine.schemas import TrailingStopUpdate

logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Madrid")

# Market hours in CET (08:00 to 21:00 covers EU + US pre/post market)
MARKET_OPEN_HOUR = 8
MARKET_CLOSE_HOUR = 21


def trailing_stop_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """EventBridge-triggered trailing stop ratchet handler.

    Fetches all open positions from ibkr-mcp, checks current prices,
    and ratchets trailing stops UP only.

    Args:
        event: EventBridge scheduled event payload.
        context: Lambda context (optional).

    Returns:
        Summary of trailing stop updates.
    """
    now_cet = datetime.now(CET)
    current_hour = now_cet.hour

    # Only run during market hours
    if current_hour < MARKET_OPEN_HOUR or current_hour >= MARKET_CLOSE_HOUR:
        logger.info(
            "Outside market hours, skipping trailing stop ratchet",
            extra={"current_hour_cet": current_hour},
        )
        return {
            "status": "SKIPPED",
            "reason": "outside_market_hours",
            "current_hour_cet": current_hour,
        }

    execution_mode = os.environ.get("EXECUTION_MODE", "backtest")

    # In backtest mode, trailing stops are managed by the simulation engine
    if execution_mode == "backtest":
        logger.info("Backtest mode — trailing stops managed by simulation engine")
        return {"status": "SKIPPED", "reason": "backtest_mode"}

    ibkr_mcp_uri = os.environ.get("IBKR_MCP_URI", "http://localhost:8001")
    updates: list[dict[str, Any]] = []

    try:
        positions = _fetch_positions(ibkr_mcp_uri)
        prices = _fetch_current_prices(ibkr_mcp_uri, [p["symbol"] for p in positions])

        for position in positions:
            symbol = position["symbol"]
            current_price = prices.get(symbol)

            if current_price is None:
                logger.warning(f"No price available for {symbol}, skipping")
                continue

            if not position.get("has_trailing_stop"):
                logger.warning(f"Position {symbol} has no trailing stop — compliance gap!")
                continue

            update = _ratchet_stop(
                symbol=symbol,
                current_price=current_price,
                current_stop=position.get("trailing_stop_price", 0.0),
                trailing_pct=position.get("trailing_stop_pct", 3.0),
                ibkr_mcp_uri=ibkr_mcp_uri,
            )

            if update and update.updated:
                updates.append(update.model_dump())
                logger.info(
                    "Trailing stop ratcheted",
                    extra={
                        "symbol": symbol,
                        "old_stop": update.old_stop_price,
                        "new_stop": update.new_stop_price,
                        "current_price": current_price,
                    },
                )

        return {
            "status": "OK",
            "positions_checked": len(positions),
            "stops_updated": len(updates),
            "updates": updates,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception:
        logger.exception("Trailing stop ratchet failed")
        return {"status": "ERROR", "error": "trailing_stop_ratchet_failed"}


def _fetch_positions(ibkr_mcp_uri: str) -> list[dict[str, Any]]:
    """Fetch open positions from ibkr-mcp.

    Calls the get_positions tool via MCP HTTP endpoint.
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{ibkr_mcp_uri}/tools/get_positions",
            json={"include_trailing_stops": True},
        )
        response.raise_for_status()
        return response.json().get("positions", [])


def _fetch_current_prices(
    ibkr_mcp_uri: str, symbols: list[str]
) -> dict[str, float]:
    """Fetch current prices for a list of symbols.

    Uses ibkr-mcp get_quotes tool for batch price fetches.
    """
    if not symbols:
        return {}

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{ibkr_mcp_uri}/tools/get_quotes",
            json={"symbols": symbols},
        )
        response.raise_for_status()
        quotes = response.json().get("quotes", {})
        return {sym: float(q["last_price"]) for sym, q in quotes.items() if "last_price" in q}


def _ratchet_stop(
    symbol: str,
    current_price: float,
    current_stop: float,
    trailing_pct: float,
    ibkr_mcp_uri: str,
) -> TrailingStopUpdate | None:
    """Ratchet a trailing stop UP only.

    New stop = current_price * (1 - trailing_pct / 100).
    Only update if new_stop > current_stop (never move stop DOWN).
    """
    new_stop = current_price * (1.0 - trailing_pct / 100.0)

    update = TrailingStopUpdate(
        symbol=symbol,
        old_stop_price=current_stop if current_stop > 0 else None,
        new_stop_price=round(new_stop, 4),
        current_price=current_price,
        ratchet_pct=trailing_pct,
        updated=False,
    )

    # Only ratchet UP — never move stop down
    if new_stop > current_stop:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{ibkr_mcp_uri}/tools/modify_trailing_stop",
                    json={
                        "symbol": symbol,
                        "new_stop_price": round(new_stop, 4),
                    },
                )
                response.raise_for_status()
                update.updated = True
        except Exception:
            logger.error(f"Failed to update trailing stop for {symbol}", exc_info=True)
            update.updated = False
    else:
        logger.debug(
            f"Stop for {symbol} not ratcheted: new={new_stop:.4f} <= current={current_stop:.4f}"
        )

    return update
```

---

### `src/qitp_risk_engine/handler.py`

```python
"""Risk Engine Lambda handler — the main entry point.

Called by Step Functions BEFORE every order submission. Returns a structured
RiskCheckResult with PASS/FAIL verdict.

This is a plain Python Lambda, NOT a Strands agent. Deterministic evaluation
of 8 hard rules. No LLM calls. No reasoning. Pure logic.

Input:  RiskCheckRequest JSON (from Step Functions)
Output: RiskCheckResult JSON (verdict, violations, circuit breakers)

Step Functions Choice state reads `$.verdict` to proceed or reject.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from qitp_risk_engine.audit import AuditLogger
from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.rules import ALL_RULES
from qitp_risk_engine.schemas import RiskCheckRequest, RiskCheckResult

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# --- Warm-start initialization (outside handler) ---
CONFIG = RiskConfig()
BREAKER_MGR = CircuitBreakerManager()
AUDIT = AuditLogger()


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler: check_risk_limits.

    Evaluates all 8 risk rules against the incoming order request.
    Returns structured PASS/FAIL result.

    Args:
        event: RiskCheckRequest as JSON dict.
        context: Lambda context (optional).

    Returns:
        RiskCheckResult as JSON dict. Step Functions reads $.verdict.
    """
    start_ms = time.monotonic() * 1000

    try:
        request = RiskCheckRequest.model_validate(event)
    except Exception as e:
        logger.error("Invalid risk check request", exc_info=True)
        return RiskCheckResult(
            verdict="FAIL",
            violations=[],
            rules_evaluated=0,
            evaluation_ms=0,
            details={"error": f"Invalid request: {e}"},
        ).model_dump(mode="json")

    logger.info(
        "Risk check started",
        extra={
            "symbol": request.symbol,
            "side": request.side.value,
            "quantity": request.quantity,
            "execution_mode": request.execution_mode,
            "sfn_execution_id": request.sfn_execution_id,
        },
    )

    # Load config from DynamoDB (cached per invocation)
    CONFIG.load()

    # Check all active circuit breakers first
    active_breakers = BREAKER_MGR.get_all_active()

    # Evaluate all rules
    violations = []
    rules_evaluated = 0

    for rule_cls in ALL_RULES:
        rule = rule_cls()

        # Skip disabled rules
        if not CONFIG.is_enabled(rule.rule_id):
            logger.debug(f"Rule {rule.rule_id} is disabled, skipping")
            continue

        try:
            violation = rule.evaluate(request, CONFIG, BREAKER_MGR)
            rules_evaluated += 1

            if violation is not None:
                violations.append(violation)
                logger.warning(
                    "Risk rule violated",
                    extra={
                        "rule_id": rule.rule_id,
                        "symbol": request.symbol,
                        "message": violation.message,
                    },
                )
        except Exception:
            logger.exception(f"Rule {rule.rule_id} evaluation failed")
            # Rule evaluation failure is treated as a violation (fail-safe)
            from qitp_risk_engine.schemas import RuleViolation

            violations.append(
                RuleViolation(
                    rule_id=rule.rule_id,
                    rule_name=rule.rule_name,
                    message=f"Rule evaluation failed: {rule.rule_id}. Fail-safe: blocking order.",
                    current_value="ERROR",
                    threshold="N/A",
                    severity="HARD",
                )
            )
            rules_evaluated += 1

    # Refresh active breakers after evaluation (rules may have tripped new ones)
    active_breakers = BREAKER_MGR.get_all_active()

    elapsed_ms = (time.monotonic() * 1000) - start_ms

    result = RiskCheckResult(
        verdict="FAIL" if violations else "PASS",
        violations=violations,
        circuit_breakers_active=active_breakers,
        rules_evaluated=rules_evaluated,
        evaluation_ms=round(elapsed_ms, 2),
        details={
            "symbol": request.symbol,
            "side": request.side.value,
            "portfolio_nav": request.portfolio_nav,
            "open_positions_count": len(request.open_positions),
            "daily_pnl_pct": request.daily_pnl_pct,
            "execution_mode": request.execution_mode,
        },
    )

    # Audit log every check (MiFID II compliance)
    try:
        AUDIT.log_risk_check(request, result)
    except Exception:
        logger.error("Audit logging failed — compliance gap", exc_info=True)

    logger.info(
        "Risk check completed",
        extra={
            "verdict": result.verdict,
            "violations": len(violations),
            "rules_evaluated": rules_evaluated,
            "evaluation_ms": result.evaluation_ms,
        },
    )

    return result.model_dump(mode="json")
```

---

## Tests

---

### `tests/conftest.py`

```python
"""Shared test fixtures for the Risk Engine test suite."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Generator
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from qitp_risk_engine.audit import AuditLogger
from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.config import RiskConfig
from qitp_risk_engine.schemas import (
    AssetClass,
    OrderSide,
    PositionInfo,
    RiskCheckRequest,
)

# Ensure test environment
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("EXECUTION_MODE", "backtest")


@pytest.fixture
def dynamodb_resource():
    """Create a mocked DynamoDB resource with required tables."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")

        # Create qitp_risk_state table
        dynamodb.create_table(
            TableName="qitp_risk_state",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create qitp_audit_log table
        dynamodb.create_table(
            TableName="qitp_audit_log",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield dynamodb


@pytest.fixture
def risk_config(dynamodb_resource) -> RiskConfig:
    """RiskConfig backed by mocked DynamoDB."""
    config = RiskConfig(
        table_name="qitp_risk_state",
        dynamodb_resource=dynamodb_resource,
    )
    config.load()
    return config


@pytest.fixture
def breaker_mgr(dynamodb_resource) -> CircuitBreakerManager:
    """CircuitBreakerManager backed by mocked DynamoDB."""
    return CircuitBreakerManager(
        table_name="qitp_risk_state",
        dynamodb_resource=dynamodb_resource,
    )


@pytest.fixture
def audit_logger(dynamodb_resource) -> AuditLogger:
    """AuditLogger backed by mocked DynamoDB."""
    return AuditLogger(
        table_name="qitp_audit_log",
        dynamodb_resource=dynamodb_resource,
    )


@pytest.fixture
def sample_buy_request() -> RiskCheckRequest:
    """A standard BUY request that should PASS all rules."""
    return RiskCheckRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=150.0,
        asset_class=AssetClass.EQUITY,
        sector="Technology",
        has_trailing_stop=True,
        trailing_stop_pct=3.0,
        is_cfd=False,
        leverage_ratio=1.0,
        portfolio_nav=100000.0,
        peak_nav=105000.0,
        daily_pnl_pct=-0.5,
        open_positions=[
            PositionInfo(
                symbol="MSFT",
                quantity=20,
                market_value=8000.0,
                sector="Technology",
                has_trailing_stop=True,
                trailing_stop_price=380.0,
                entry_price=370.0,
            ),
        ],
        execution_mode="paper",
        sfn_execution_id="sfn-test-001",
    )


@pytest.fixture
def sample_sell_request() -> RiskCheckRequest:
    """A SELL request — should always pass risk checks."""
    return RiskCheckRequest(
        symbol="MSFT",
        side=OrderSide.SELL,
        quantity=10,
        price=400.0,
        portfolio_nav=100000.0,
        peak_nav=105000.0,
        open_positions=[
            PositionInfo(
                symbol="MSFT",
                quantity=20,
                market_value=8000.0,
                sector="Technology",
                has_trailing_stop=True,
            ),
        ],
        has_trailing_stop=True,
        execution_mode="paper",
    )


@pytest.fixture
def maxed_out_positions() -> list[PositionInfo]:
    """5 open positions — at maximum."""
    return [
        PositionInfo(symbol="AAPL", quantity=10, market_value=15000.0, sector="Technology", has_trailing_stop=True),
        PositionInfo(symbol="MSFT", quantity=10, market_value=15000.0, sector="Technology", has_trailing_stop=True),
        PositionInfo(symbol="GOOGL", quantity=5, market_value=15000.0, sector="Technology", has_trailing_stop=True),
        PositionInfo(symbol="JPM", quantity=20, market_value=15000.0, sector="Financials", has_trailing_stop=True),
        PositionInfo(symbol="XOM", quantity=30, market_value=15000.0, sector="Energy", has_trailing_stop=True),
    ]
```

---

### `tests/test_handler.py`

```python
"""Tests for the main Lambda handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from moto import mock_aws

from qitp_risk_engine.handler import handler
from qitp_risk_engine.schemas import OrderSide, PositionInfo, RiskCheckRequest


class TestHandlerPassingRequest:
    """Tests for requests that should PASS."""

    @mock_aws
    def test_simple_buy_passes(self, dynamodb_resource, sample_buy_request):
        """A well-formed BUY with trailing stop and healthy portfolio passes."""
        with (
            patch("qitp_risk_engine.handler.CONFIG") as mock_config,
            patch("qitp_risk_engine.handler.BREAKER_MGR") as mock_breaker,
            patch("qitp_risk_engine.handler.AUDIT") as mock_audit,
        ):
            from qitp_risk_engine.config import RiskConfig

            config = RiskConfig(
                table_name="qitp_risk_state",
                dynamodb_resource=dynamodb_resource,
            )
            mock_config.load = config.load
            mock_config.get_threshold = config.get_threshold
            mock_config.is_enabled = config.is_enabled
            mock_config.get_metadata = config.get_metadata

            from qitp_risk_engine.circuit_breaker import CircuitBreakerManager

            breaker = CircuitBreakerManager(
                table_name="qitp_risk_state",
                dynamodb_resource=dynamodb_resource,
            )
            mock_breaker.get_state = breaker.get_state
            mock_breaker.get_all_active = breaker.get_all_active
            mock_breaker.trip = breaker.trip
            mock_breaker.reset = breaker.reset

            mock_audit.log_risk_check = MagicMock()

            result = handler(sample_buy_request.model_dump(mode="json"))

            assert result["verdict"] == "PASS"
            assert len(result["violations"]) == 0
            assert result["rules_evaluated"] == 8
            mock_audit.log_risk_check.assert_called_once()

    @mock_aws
    def test_sell_always_passes(self, dynamodb_resource, sample_sell_request):
        """SELL orders always pass — they reduce risk."""
        with (
            patch("qitp_risk_engine.handler.CONFIG") as mock_config,
            patch("qitp_risk_engine.handler.BREAKER_MGR") as mock_breaker,
            patch("qitp_risk_engine.handler.AUDIT") as mock_audit,
        ):
            from qitp_risk_engine.config import RiskConfig

            config = RiskConfig(
                table_name="qitp_risk_state",
                dynamodb_resource=dynamodb_resource,
            )
            mock_config.load = config.load
            mock_config.get_threshold = config.get_threshold
            mock_config.is_enabled = config.is_enabled
            mock_config.get_metadata = config.get_metadata

            from qitp_risk_engine.circuit_breaker import CircuitBreakerManager

            breaker = CircuitBreakerManager(
                table_name="qitp_risk_state",
                dynamodb_resource=dynamodb_resource,
            )
            mock_breaker.get_state = breaker.get_state
            mock_breaker.get_all_active = breaker.get_all_active
            mock_breaker.trip = breaker.trip
            mock_breaker.reset = breaker.reset

            mock_audit.log_risk_check = MagicMock()

            result = handler(sample_sell_request.model_dump(mode="json"))

            assert result["verdict"] == "PASS"


class TestHandlerFailingRequest:
    """Tests for requests that should FAIL."""

    @mock_aws
    def test_invalid_request_fails(self, dynamodb_resource):
        """Invalid JSON payload returns FAIL with error details."""
        result = handler({"garbage": "data"})
        assert result["verdict"] == "FAIL"
        assert "error" in result["details"]

    @mock_aws
    def test_no_trailing_stop_fails(self, dynamodb_resource, sample_buy_request):
        """BUY without trailing stop is rejected."""
        sample_buy_request.has_trailing_stop = False

        with (
            patch("qitp_risk_engine.handler.CONFIG") as mock_config,
            patch("qitp_risk_engine.handler.BREAKER_MGR") as mock_breaker,
            patch("qitp_risk_engine.handler.AUDIT") as mock_audit,
        ):
            from qitp_risk_engine.config import RiskConfig

            config = RiskConfig(
                table_name="qitp_risk_state",
                dynamodb_resource=dynamodb_resource,
            )
            mock_config.load = config.load
            mock_config.get_threshold = config.get_threshold
            mock_config.is_enabled = config.is_enabled
            mock_config.get_metadata = config.get_metadata

            from qitp_risk_engine.circuit_breaker import CircuitBreakerManager

            breaker = CircuitBreakerManager(
                table_name="qitp_risk_state",
                dynamodb_resource=dynamodb_resource,
            )
            mock_breaker.get_state = breaker.get_state
            mock_breaker.get_all_active = breaker.get_all_active
            mock_breaker.trip = breaker.trip
            mock_breaker.reset = breaker.reset

            mock_audit.log_risk_check = MagicMock()

            result = handler(sample_buy_request.model_dump(mode="json"))

            assert result["verdict"] == "FAIL"
            rule_ids = [v["rule_id"] for v in result["violations"]]
            assert "trailing_stop_mandatory" in rule_ids
```

---

### `tests/test_rules.py`

```python
"""Tests for individual risk rules."""

from __future__ import annotations

import pytest

from qitp_risk_engine.schemas import (
    AssetClass,
    OrderSide,
    PositionInfo,
    RiskCheckRequest,
)
from qitp_risk_engine.rules.max_positions import MaxPositionsRule
from qitp_risk_engine.rules.position_size import PositionSizeRule
from qitp_risk_engine.rules.sector_concentration import SectorConcentrationRule
from qitp_risk_engine.rules.daily_loss import DailyLossRule
from qitp_risk_engine.rules.drawdown import DrawdownRule
from qitp_risk_engine.rules.trailing_stop import TrailingStopMandatoryRule
from qitp_risk_engine.rules.leverage import LeverageRule
from qitp_risk_engine.rules.short_sell import ShortSellRule


class TestMaxPositionsRule:
    def test_passes_below_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = MaxPositionsRule()
        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_at_limit(self, risk_config, breaker_mgr, sample_buy_request, maxed_out_positions):
        rule = MaxPositionsRule()
        sample_buy_request.open_positions = maxed_out_positions
        sample_buy_request.symbol = "NVDA"  # New symbol not in existing positions

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "max_positions"
        assert result.current_value == 5
        assert result.threshold == 5

    def test_passes_for_existing_symbol_at_limit(self, risk_config, breaker_mgr, sample_buy_request, maxed_out_positions):
        """Adding to an existing position at max count should pass."""
        rule = MaxPositionsRule()
        sample_buy_request.open_positions = maxed_out_positions
        sample_buy_request.symbol = "AAPL"  # Already in positions

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_sell_always_passes(self, risk_config, breaker_mgr, sample_buy_request, maxed_out_positions):
        rule = MaxPositionsRule()
        sample_buy_request.side = OrderSide.SELL
        sample_buy_request.open_positions = maxed_out_positions

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None


class TestPositionSizeRule:
    def test_passes_within_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = PositionSizeRule()
        # Order: 10 * 150 = 1500 = 1.5% of 100K NAV
        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_exceeding_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = PositionSizeRule()
        sample_buy_request.quantity = 200
        sample_buy_request.price = 150.0
        # Order: 200 * 150 = 30000 = 30% of 100K NAV (limit 20%)

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "position_size"

    def test_includes_existing_position_value(self, risk_config, breaker_mgr, sample_buy_request):
        """Existing + new must not exceed threshold."""
        rule = PositionSizeRule()
        sample_buy_request.symbol = "MSFT"  # Already held
        sample_buy_request.quantity = 100
        sample_buy_request.price = 150.0
        # Existing MSFT: 8000, New: 15000, Total: 23000 = 23% > 20%

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None

    def test_sell_always_passes(self, risk_config, breaker_mgr, sample_buy_request):
        rule = PositionSizeRule()
        sample_buy_request.side = OrderSide.SELL
        sample_buy_request.quantity = 9999
        sample_buy_request.price = 9999.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None


class TestSectorConcentrationRule:
    def test_passes_within_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = SectorConcentrationRule()
        # Order: 1500 + existing Tech (8000) = 9500 = 9.5% of 100K
        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_exceeding_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = SectorConcentrationRule()
        sample_buy_request.quantity = 200
        sample_buy_request.price = 150.0
        # Order: 30000 + existing Tech (8000) = 38000
        # Need to push over 40%: add more existing tech
        sample_buy_request.open_positions.append(
            PositionInfo(symbol="GOOGL", quantity=10, market_value=15000.0, sector="Technology", has_trailing_stop=True)
        )
        # Now: 30000 + 8000 + 15000 = 53000 = 53% > 40%

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "sector_concentration"

    def test_unknown_sector_passes(self, risk_config, breaker_mgr, sample_buy_request):
        rule = SectorConcentrationRule()
        sample_buy_request.sector = "unknown"

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None


class TestDailyLossRule:
    def test_passes_within_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DailyLossRule()
        sample_buy_request.daily_pnl_pct = -1.5

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_exceeding_threshold(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DailyLossRule()
        sample_buy_request.daily_pnl_pct = -3.5  # Exceeds -3%

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "daily_loss"

    def test_exactly_at_threshold_fails(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DailyLossRule()
        sample_buy_request.daily_pnl_pct = -3.0  # Exactly at threshold

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None

    def test_positive_pnl_passes(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DailyLossRule()
        sample_buy_request.daily_pnl_pct = 2.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None


class TestDrawdownRule:
    def test_passes_within_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DrawdownRule()
        # NAV 100K, peak 105K = -4.76% drawdown (within -10%)
        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_exceeding_threshold(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DrawdownRule()
        sample_buy_request.portfolio_nav = 88000.0
        sample_buy_request.peak_nav = 100000.0
        # Drawdown: (88000 - 100000) / 100000 = -12%

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "drawdown"

    def test_no_drawdown_passes(self, risk_config, breaker_mgr, sample_buy_request):
        rule = DrawdownRule()
        sample_buy_request.portfolio_nav = 110000.0
        sample_buy_request.peak_nav = 100000.0  # NAV above peak

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None


class TestTrailingStopMandatoryRule:
    def test_passes_with_trailing_stop(self, risk_config, breaker_mgr, sample_buy_request):
        rule = TrailingStopMandatoryRule()
        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_without_trailing_stop(self, risk_config, breaker_mgr, sample_buy_request):
        rule = TrailingStopMandatoryRule()
        sample_buy_request.has_trailing_stop = False

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "trailing_stop_mandatory"

    def test_sell_always_passes_without_stop(self, risk_config, breaker_mgr, sample_buy_request):
        rule = TrailingStopMandatoryRule()
        sample_buy_request.side = OrderSide.SELL
        sample_buy_request.has_trailing_stop = False

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_rejects_extreme_trailing_stop_pct(self, risk_config, breaker_mgr, sample_buy_request):
        rule = TrailingStopMandatoryRule()
        sample_buy_request.trailing_stop_pct = 50.0  # 50% is unreasonable

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None

    def test_accepts_valid_trailing_stop_pct(self, risk_config, breaker_mgr, sample_buy_request):
        rule = TrailingStopMandatoryRule()
        sample_buy_request.trailing_stop_pct = 5.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None


class TestLeverageRule:
    def test_passes_for_cash_equity(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = False

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_passes_within_esma_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = True
        sample_buy_request.asset_class = AssetClass.EQUITY_CFD
        sample_buy_request.leverage_ratio = 4.0  # Limit is 5:1

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_exceeding_esma_limit(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = True
        sample_buy_request.asset_class = AssetClass.EQUITY_CFD
        sample_buy_request.leverage_ratio = 6.0  # Limit is 5:1

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "leverage"
        assert result.threshold == 5.0

    def test_major_forex_30x_passes(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = True
        sample_buy_request.asset_class = AssetClass.MAJOR_FOREX
        sample_buy_request.leverage_ratio = 30.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_major_forex_31x_fails(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = True
        sample_buy_request.asset_class = AssetClass.MAJOR_FOREX
        sample_buy_request.leverage_ratio = 31.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None

    def test_crypto_2x_passes(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = True
        sample_buy_request.asset_class = AssetClass.CRYPTO_CFD
        sample_buy_request.leverage_ratio = 2.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_crypto_3x_fails(self, risk_config, breaker_mgr, sample_buy_request):
        rule = LeverageRule()
        sample_buy_request.is_cfd = True
        sample_buy_request.asset_class = AssetClass.CRYPTO_CFD
        sample_buy_request.leverage_ratio = 3.0

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None


class TestShortSellRule:
    def test_passes_non_short_order(self, risk_config, breaker_mgr, sample_buy_request):
        rule = ShortSellRule()
        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_passes_non_ibex35_short(self, risk_config, breaker_mgr, sample_buy_request):
        rule = ShortSellRule()
        sample_buy_request.side = OrderSide.SHORT
        sample_buy_request.symbol = "AAPL"  # Not in IBEX35

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_passes_ibex35_not_banned(self, risk_config, breaker_mgr, sample_buy_request):
        rule = ShortSellRule()
        sample_buy_request.side = OrderSide.SHORT
        sample_buy_request.symbol = "SAN.MC"  # In IBEX35 but not on ban list

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is None

    def test_fails_ibex35_banned_symbol(self, risk_config, breaker_mgr, sample_buy_request):
        """Symbol on CNMV ban list should be rejected."""
        rule = ShortSellRule()
        sample_buy_request.side = OrderSide.SHORT
        sample_buy_request.symbol = "TEF.MC"

        # Manually set ban list in config cache
        risk_config._cache["short_sell"]["metadata"]["cnmv_ban_list"] = ["TEF.MC", "SAN.MC"]

        result = rule.evaluate(sample_buy_request, risk_config, breaker_mgr)
        assert result is not None
        assert result.rule_id == "short_sell"
        assert "TEF.MC" in result.message
```

---

### `tests/test_circuit_breaker.py`

```python
"""Tests for the circuit breaker state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from qitp_risk_engine.circuit_breaker import CircuitBreakerManager
from qitp_risk_engine.schemas import CircuitBreakerStatus


class TestCircuitBreakerTrip:
    def test_trip_with_auto_reset(self, breaker_mgr):
        """Trip a breaker with 24h auto-reset."""
        state = breaker_mgr.trip(
            breaker_id="daily_loss",
            current_value=-3.5,
            threshold=-3.0,
            auto_reset_hours=24,
        )

        assert state.status == CircuitBreakerStatus.OPEN
        assert state.tripped_value == -3.5
        assert state.threshold == -3.0
        assert state.expires_at is not None

    def test_trip_without_auto_reset(self, breaker_mgr):
        """Trip a breaker that requires manual reset."""
        state = breaker_mgr.trip(
            breaker_id="drawdown",
            current_value=-12.0,
            threshold=-10.0,
            auto_reset_hours=None,
        )

        assert state.status == CircuitBreakerStatus.OPEN
        assert state.expires_at is None


class TestCircuitBreakerGetState:
    def test_default_closed(self, breaker_mgr):
        """Non-existent breaker returns CLOSED."""
        state = breaker_mgr.get_state("nonexistent")
        assert state.status == CircuitBreakerStatus.CLOSED

    def test_tripped_breaker_returns_open(self, breaker_mgr):
        """After trip, get_state returns OPEN."""
        breaker_mgr.trip("daily_loss", -3.5, -3.0, auto_reset_hours=24)
        state = breaker_mgr.get_state("daily_loss")
        assert state.status == CircuitBreakerStatus.OPEN

    def test_expired_breaker_transitions_to_half_open(self, breaker_mgr, dynamodb_resource):
        """Expired auto-reset breaker transitions to HALF_OPEN on read."""
        # Trip the breaker
        breaker_mgr.trip("daily_loss", -3.5, -3.0, auto_reset_hours=24)

        # Manually set expires_at to the past
        table = dynamodb_resource.Table("qitp_risk_state")
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        table.update_item(
            Key={"PK": "BREAKER#daily_loss"},
            UpdateExpression="SET expires_at = :past",
            ExpressionAttributeValues={":past": past},
        )

        state = breaker_mgr.get_state("daily_loss")
        assert state.status == CircuitBreakerStatus.HALF_OPEN

    def test_manual_reset_breaker_stays_open(self, breaker_mgr):
        """Breaker without auto-reset stays OPEN indefinitely."""
        breaker_mgr.trip("drawdown", -12.0, -10.0, auto_reset_hours=None)
        state = breaker_mgr.get_state("drawdown")
        assert state.status == CircuitBreakerStatus.OPEN


class TestCircuitBreakerReset:
    def test_manual_reset(self, breaker_mgr):
        """Manual reset transitions to CLOSED."""
        breaker_mgr.trip("drawdown", -12.0, -10.0, auto_reset_hours=None)
        state = breaker_mgr.reset("drawdown")
        assert state.status == CircuitBreakerStatus.CLOSED

        # Verify persistent state
        state = breaker_mgr.get_state("drawdown")
        assert state.status == CircuitBreakerStatus.CLOSED


class TestCircuitBreakerGetAllActive:
    def test_returns_active_breakers(self, breaker_mgr):
        """get_all_active returns only OPEN/HALF_OPEN breakers."""
        breaker_mgr.trip("daily_loss", -3.5, -3.0, auto_reset_hours=24)
        breaker_mgr.trip("drawdown", -12.0, -10.0, auto_reset_hours=None)

        active = breaker_mgr.get_all_active()
        assert len(active) == 2
        breaker_ids = {b.breaker_id for b in active}
        assert "daily_loss" in breaker_ids
        assert "drawdown" in breaker_ids

    def test_returns_empty_when_all_closed(self, breaker_mgr):
        active = breaker_mgr.get_all_active()
        assert len(active) == 0
```

---

### `tests/test_trailing_stop_manager.py`

```python
"""Tests for the trailing stop manager."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from qitp_risk_engine.trailing_stop_manager import (
    MARKET_CLOSE_HOUR,
    MARKET_OPEN_HOUR,
    _ratchet_stop,
    trailing_stop_handler,
)


class TestMarketHoursFilter:
    def test_skips_outside_market_hours(self):
        """Handler skips execution before market open."""
        with patch(
            "qitp_risk_engine.trailing_stop_manager.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 6  # Before 08:00 CET
            mock_dt.now.return_value = mock_now

            result = trailing_stop_handler({})
            assert result["status"] == "SKIPPED"
            assert result["reason"] == "outside_market_hours"

    def test_skips_after_market_close(self):
        """Handler skips execution after market close."""
        with patch(
            "qitp_risk_engine.trailing_stop_manager.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 22  # After 21:00 CET
            mock_dt.now.return_value = mock_now

            result = trailing_stop_handler({})
            assert result["status"] == "SKIPPED"
            assert result["reason"] == "outside_market_hours"

    def test_skips_in_backtest_mode(self):
        """Handler skips in backtest mode."""
        os.environ["EXECUTION_MODE"] = "backtest"
        with patch(
            "qitp_risk_engine.trailing_stop_manager.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 14  # During market hours
            mock_dt.now.return_value = mock_now

            result = trailing_stop_handler({})
            assert result["status"] == "SKIPPED"
            assert result["reason"] == "backtest_mode"

        os.environ["EXECUTION_MODE"] = "backtest"  # Reset


class TestRatchetStop:
    def test_ratchets_up(self):
        """Stop moves UP when new stop > current stop."""
        with patch("qitp_risk_engine.trailing_stop_manager.httpx") as mock_httpx:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_httpx.Client.return_value = mock_client

            update = _ratchet_stop(
                symbol="AAPL",
                current_price=200.0,
                current_stop=180.0,
                trailing_pct=3.0,
                ibkr_mcp_uri="http://localhost:8001",
            )

            assert update is not None
            # New stop = 200 * (1 - 0.03) = 194.0 > 180.0
            assert update.new_stop_price == 194.0
            assert update.updated is True

    def test_does_not_ratchet_down(self):
        """Stop does NOT move down when new stop < current stop."""
        update = _ratchet_stop(
            symbol="AAPL",
            current_price=180.0,
            current_stop=190.0,  # Current stop is higher
            trailing_pct=3.0,
            ibkr_mcp_uri="http://localhost:8001",
        )

        assert update is not None
        # New stop = 180 * 0.97 = 174.6 < 190.0
        assert update.updated is False

    def test_ratchet_calculation(self):
        """Verify the ratchet formula: new_stop = price * (1 - pct/100)."""
        update = _ratchet_stop(
            symbol="AAPL",
            current_price=100.0,
            current_stop=90.0,
            trailing_pct=5.0,
            ibkr_mcp_uri="http://localhost:8001",
        )

        # new_stop = 100 * (1 - 0.05) = 95.0 > 90.0 => ratchet up
        # But we need to mock httpx for the update call
        assert update is not None
        assert update.new_stop_price == 95.0
```

---

### `tests/test_config.py`

```python
"""Tests for DynamoDB-based risk configuration."""

from __future__ import annotations

import pytest

from qitp_risk_engine.config import DEFAULTS, RiskConfig


class TestDefaultConfig:
    def test_loads_defaults_when_table_empty(self, risk_config):
        """With empty DynamoDB table, defaults are used."""
        assert risk_config.get_threshold("max_positions") == 5
        assert risk_config.get_threshold("position_size") == 20.0
        assert risk_config.get_threshold("sector_concentration") == 40.0
        assert risk_config.get_threshold("daily_loss") == -3.0
        assert risk_config.get_threshold("drawdown") == -10.0

    def test_all_rules_enabled_by_default(self, risk_config):
        for rule_id in DEFAULTS:
            assert risk_config.is_enabled(rule_id) is True

    def test_leverage_metadata_has_all_asset_classes(self, risk_config):
        limits = risk_config.get_metadata("leverage", "limits")
        assert limits is not None
        assert limits["major_forex"] == 30.0
        assert limits["minor_forex"] == 20.0
        assert limits["index_cfd"] == 20.0
        assert limits["equity_cfd"] == 5.0
        assert limits["commodity_cfd"] == 10.0
        assert limits["crypto_cfd"] == 2.0


class TestDynamoDBOverrides:
    def test_overrides_threshold_from_dynamodb(self, dynamodb_resource):
        """DynamoDB entries override defaults."""
        table = dynamodb_resource.Table("qitp_risk_state")
        table.put_item(
            Item={
                "PK": "RULE#max_positions",
                "threshold": "10",
                "enabled": True,
            }
        )

        config = RiskConfig(
            table_name="qitp_risk_state",
            dynamodb_resource=dynamodb_resource,
        )
        config.load()

        assert config.get_threshold("max_positions") == 10.0

    def test_can_disable_rule(self, dynamodb_resource):
        """Rules can be disabled via DynamoDB."""
        table = dynamodb_resource.Table("qitp_risk_state")
        table.put_item(
            Item={
                "PK": "RULE#short_sell",
                "enabled": False,
            }
        )

        config = RiskConfig(
            table_name="qitp_risk_state",
            dynamodb_resource=dynamodb_resource,
        )
        config.load()

        assert config.is_enabled("short_sell") is False

    def test_unknown_rule_returns_zero_threshold(self, risk_config):
        assert risk_config.get_threshold("nonexistent_rule") == 0

    def test_get_all_configs(self, risk_config):
        configs = risk_config.get_all_configs()
        assert len(configs) == len(DEFAULTS)
        assert "max_positions" in configs
        assert "leverage" in configs
```

---

## Acceptance Criteria

- [ ] Lambda handler returns structured `RiskCheckResult` JSON with `verdict`, `violations`, `circuit_breakers_active`
- [ ] All 8 risk rules evaluate correctly (see test matrix)
- [ ] Circuit breaker state machine: CLOSED -> OPEN on violation, OPEN -> HALF_OPEN on expiry, HALF_OPEN -> CLOSED on manual reset
- [ ] `daily_loss` circuit breaker auto-resets after 24h
- [ ] `drawdown` circuit breaker requires manual reset (no auto-reset)
- [ ] `max_positions` circuit breaker auto-clears when position count drops below threshold
- [ ] SELL/COVER orders always pass all per-order rules (they reduce risk)
- [ ] ESMA leverage limits enforced correctly per asset class
- [ ] CNMV short-sell ban list checked for IBEX35 symbols only
- [ ] Trailing stop mandatory for all BUY/SHORT orders
- [ ] All thresholds configurable via DynamoDB `qitp_risk_state` table
- [ ] Audit log written to `qitp_audit_log` for every risk check (5-year TTL)
- [ ] Trailing Stop Manager runs only during market hours (08:00-21:00 CET)
- [ ] Trailing stops ratchet UP only, never DOWN
- [ ] Rule evaluation failure is fail-safe (treated as violation, blocks order)
- [ ] All tests pass

## Test Plan

```bash
cd ~/dev/tccw-qitp-risk-engine
pip install -e ".[dev]"
pytest -v --cov=qitp_risk_engine --cov-report=term-missing
```

## Agent Instructions

The Risk Engine is the hardest architectural boundary in the platform. It is NOT a Strands agent — it is a plain Python Lambda with deterministic logic. No LLM calls. No reasoning. Pure rule evaluation.

Key implementation notes:

1. **Fail-safe design**: If any rule evaluation throws an exception, treat it as a violation and block the order. Never let an error result in an unchecked order passing through.
2. **Circuit breaker persistence**: All circuit breaker state lives in DynamoDB `qitp_risk_state` table. The handler is stateless — it reads state on every invocation.
3. **SELL/COVER always passes**: These orders reduce risk. Every per-order rule (position_size, sector_concentration, trailing_stop, leverage, short_sell) must short-circuit to `None` for SELL/COVER.
4. **Evaluation order matters**: Circuit breaker rules (daily_loss, drawdown) run FIRST. If a circuit breaker is OPEN, the order is rejected immediately regardless of other rules. All rules still evaluate so violations are comprehensive.
5. **DynamoDB config is hot-reloadable**: Thresholds are loaded on every invocation (`CONFIG.load()`). No Lambda redeploy needed to change limits.
6. **Audit is non-blocking**: If the audit log write fails, log the error but do NOT block the risk check result. However, this is a compliance gap and should trigger an alert.
7. **Trailing Stop Manager is a SEPARATE Lambda**: It has its own handler (`trailing_stop_handler`) and is triggered by EventBridge, not by Step Functions.
8. **Credentials**: `AWS_DEFAULT_REGION`, `RISK_STATE_TABLE`, `AUDIT_LOG_TABLE`, and `IBKR_MCP_URI` are all via environment variables. Never hardcode.
