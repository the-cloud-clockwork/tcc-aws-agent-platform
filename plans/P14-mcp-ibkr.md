# P14 — IBKR MCP Server

## Objective
Build `ibkr-mcp`: an MCP server wrapping Interactive Brokers Client Portal API (REST). 8 tools for broker operations: positions, account summary, market data, order management, executions, and trailing stops. EXECUTION_MODE routing: backtest returns simulated no-op responses, paper connects to IBKR paper account, live connects to IBKR live account with 2FA token required on order submission.

## Plane Tickets
ROOT-50

## Target Repo
`~/dev/tccw-qitp-mcp-ibkr`

## Dependencies
P01 (skeleton), P02 (core schemas)

## Repo Structure
```
tccw-qitp-mcp-ibkr/
├── src/
│   └── qitp_mcp_ibkr/
│       ├── __init__.py
│       ├── server.py           # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── positions.py    # get_positions, get_account_summary
│       │   ├── market_data.py  # get_market_data (IBKR-native)
│       │   ├── orders.py       # place_order, cancel_order, get_order_status, get_executions
│       │   └── risk_mgmt.py    # set_trailing_stop
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract IBKRProvider
│       │   ├── simulated.py    # SimulatedProvider (backtest mode — no-op responses)
│       │   ├── paper.py        # PaperProvider (IBKR paper account)
│       │   └── live.py         # LiveProvider (IBKR live + 2FA requirement)
│       ├── client.py           # IBKR Client Portal REST API client
│       ├── session.py          # Session management, auto-reconnect, heartbeat
│       ├── schemas.py          # Position, Order, AccountSummary, TrailingStop schemas
│       └── compliance.py       # ESMA leverage validation, CNMV checks
├── tests/
│   ├── conftest.py
│   ├── test_orders.py
│   ├── test_positions.py
│   ├── test_session.py
│   ├── test_compliance.py
│   └── fixtures/
│       └── sample_responses.json
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
name = "qitp-mcp-ibkr"
version = "0.1.0"
description = "QITP IBKR MCP Server — Interactive Brokers broker integration for positions, orders, and risk management"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0",
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
ibkr-mcp = "qitp_mcp_ibkr.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_ibkr"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

### `src/qitp_mcp_ibkr/__init__.py`

```python
"""QITP IBKR MCP Server — Interactive Brokers broker integration."""

__version__ = "0.1.0"
```

---

### `src/qitp_mcp_ibkr/schemas.py`

```python
"""Schemas for IBKR MCP server — positions, orders, account, compliance."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderSide(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"
    SSHORT = "SSHORT"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"
    TRAILING_STOP = "TRAIL"


class OrderStatus(str, Enum):
    """Order lifecycle status."""

    SUBMITTED = "submitted"
    PRE_SUBMITTED = "pre_submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    INACTIVE = "inactive"


class Currency(str, Enum):
    """Supported currencies."""

    USD = "USD"
    EUR = "EUR"


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """An open position in the account."""

    symbol: str
    con_id: int = Field(description="IBKR contract ID")
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    currency: Currency = Currency.USD
    asset_class: str = "STK"
    account_id: str = ""


# ---------------------------------------------------------------------------
# Account Summary
# ---------------------------------------------------------------------------


class AccountSummary(BaseModel):
    """Account-level financial summary."""

    account_id: str
    net_liquidation: float = Field(description="Total account NAV")
    buying_power: float
    available_funds: float
    excess_liquidity: float
    margin_used: float = 0.0
    cash_balance: float = 0.0
    currency: Currency = Currency.USD
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Market Data (IBKR-native quote)
# ---------------------------------------------------------------------------


class MarketDataQuote(BaseModel):
    """Real-time quote from IBKR."""

    symbol: str
    con_id: int = 0
    last: float
    bid: float
    ask: float
    volume: int
    change_pct: float = Field(description="Percent change from previous close")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class PlaceOrderRequest(BaseModel):
    """Request to place an order. Requires idempotency_key for retry safety."""

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: Literal["DAY", "GTC", "IOC"] = "DAY"
    idempotency_key: str = Field(
        description="Client-generated unique key for retry safety"
    )
    agent_reasoning_summary: str = Field(
        default="",
        description="Brief explanation of why the agent placed this order (audit trail)",
    )
    twofa_approval_token: str | None = Field(
        default=None,
        description="2FA approval token — REQUIRED in live mode",
    )
    currency: Currency = Currency.USD
    isin: str | None = Field(
        default=None,
        description="ISIN for MiFID II best execution logging",
    )
    venue: str = Field(
        default="SMART",
        description="Execution venue for MiFID II logging",
    )


class OrderResult(BaseModel):
    """Result of an order submission."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    status: OrderStatus
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    limit_price: float | None = None
    stop_price: float | None = None
    idempotency_key: str = ""
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = ""


class Execution(BaseModel):
    """A single fill/execution record for audit trail."""

    execution_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float = 0.0
    currency: Currency = Currency.USD
    isin: str | None = None
    venue: str = "SMART"
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    # MiFID II fields
    timestamp_ms: int = Field(
        default=0,
        description="Execution timestamp in milliseconds for MiFID II",
    )
    agent_reasoning_summary: str = ""


# ---------------------------------------------------------------------------
# Trailing Stop
# ---------------------------------------------------------------------------


class TrailingStopRequest(BaseModel):
    """Request to attach a trailing stop to a position."""

    symbol: str
    trail_amount: float | None = Field(
        default=None,
        description="Trailing amount in absolute price terms",
    )
    trail_pct: float | None = Field(
        default=None,
        description="Trailing percentage (e.g., 2.0 for 2%)",
    )
    quantity: float | None = Field(
        default=None,
        description="Quantity to protect — defaults to full position",
    )
    idempotency_key: str = Field(
        description="Client-generated unique key for retry safety"
    )


class TrailingStopResult(BaseModel):
    """Result of setting a trailing stop."""

    order_id: str
    symbol: str
    trail_amount: float | None = None
    trail_pct: float | None = None
    quantity: float
    status: OrderStatus
    message: str = ""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LiveModeRequires2FAError(Exception):
    """Raised when a live-mode order is attempted without 2FA token."""

    def __init__(self) -> None:
        super().__init__(
            "Live mode orders require a 2FA approval token. "
            "Provide 'twofa_approval_token' in the order request."
        )


class ComplianceError(Exception):
    """Raised when a compliance check fails (ESMA leverage, CNMV restrictions)."""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"Compliance violation [{rule}]: {detail}")
        self.rule = rule
        self.detail = detail
```

---

### `src/qitp_mcp_ibkr/compliance.py`

```python
"""Compliance checks — ESMA leverage limits and CNMV short-sell restrictions.

These checks run BEFORE any order submission. They are not a substitute for the
Risk Engine Lambda (P16), but provide fast-fail validation at the MCP layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qitp_mcp_ibkr.schemas import ComplianceError, OrderSide, PlaceOrderRequest

if TYPE_CHECKING:
    from qitp_mcp_ibkr.schemas import AccountSummary, Position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IBEX 35 symbols — CNMV short-sell restriction scope
# ---------------------------------------------------------------------------

IBEX35_SYMBOLS: set[str] = {
    "SAN",
    "BBVA",
    "ITX",
    "IBE",
    "TEF",
    "REP",
    "CABK",
    "AMS",
    "FER",
    "ACS",
    "GRF",
    "MAP",
    "ENG",
    "RED",
    "SAB",
    "BKT",
    "MRL",
    "CLNX",
    "IAG",
    "MEL",
    "CIE",
    "FDR",
    "COL",
    "ACX",
    "VIS",
    "ALM",
    "AENA",
    "LOG",
    "PHM",
    "SGRE",
    "NTGY",
    "ELE",
    "SLR",
    "UNI",
    "ROVI",
    # Include common IBKR suffixes for Madrid
    "SAN.MC",
    "BBVA.MC",
    "ITX.MC",
    "IBE.MC",
    "TEF.MC",
    "REP.MC",
}


# ---------------------------------------------------------------------------
# ESMA CFD leverage limits (retail client defaults)
# ---------------------------------------------------------------------------

ESMA_MAX_LEVERAGE: dict[str, float] = {
    "major_fx": 30.0,  # 1:30
    "minor_fx": 20.0,
    "major_index": 20.0,
    "minor_index": 10.0,
    "commodity": 10.0,
    "equity": 5.0,  # 1:5 for individual equities
    "crypto": 2.0,
}


def check_cnmv_short_sell(request: PlaceOrderRequest) -> None:
    """Check CNMV short-sell restrictions on IBEX35 symbols.

    The CNMV can impose temporary short-selling bans on IBEX35 constituents.
    This check rejects SSHORT orders on those symbols.

    Raises:
        ComplianceError: If short-selling is restricted for this symbol.
    """
    if request.side != OrderSide.SSHORT:
        return

    # Normalize symbol — strip exchange suffix for matching
    base_symbol = request.symbol.split(".")[0].upper()

    if base_symbol in IBEX35_SYMBOLS or request.symbol.upper() in IBEX35_SYMBOLS:
        raise ComplianceError(
            rule="CNMV-SHORT-SELL",
            detail=(
                f"Short-selling of {request.symbol} is subject to CNMV restrictions. "
                f"IBEX35 constituents require explicit regulatory clearance for short positions."
            ),
        )


def check_esma_leverage(
    request: PlaceOrderRequest,
    account_summary: AccountSummary | None = None,
) -> None:
    """Check ESMA CFD leverage limits for retail clients.

    For equity CFDs, max leverage is 1:5 (20% margin).
    This check validates that the notional order value does not exceed
    5x the available funds.

    Raises:
        ComplianceError: If the order would exceed ESMA leverage limits.
    """
    if account_summary is None:
        # Cannot check leverage without account data — log warning, allow
        logger.warning(
            "ESMA leverage check skipped — no account summary available for %s",
            request.symbol,
        )
        return

    # Estimate notional value
    if request.limit_price is not None:
        price = request.limit_price
    elif request.stop_price is not None:
        price = request.stop_price
    else:
        # Market order — we don't have the current price here.
        # The Risk Engine (P16) will perform the definitive check.
        logger.info(
            "ESMA leverage check: market order for %s — price unknown at MCP layer, "
            "deferring to Risk Engine",
            request.symbol,
        )
        return

    notional = price * request.quantity
    max_leverage = ESMA_MAX_LEVERAGE.get("equity", 5.0)
    max_notional = account_summary.net_liquidation * max_leverage

    if notional > max_notional:
        raise ComplianceError(
            rule="ESMA-CFD-LEVERAGE",
            detail=(
                f"Order notional {notional:.2f} {request.currency.value} exceeds "
                f"ESMA max leverage ({max_leverage}x) on NAV "
                f"{account_summary.net_liquidation:.2f} {request.currency.value}. "
                f"Max allowed notional: {max_notional:.2f}"
            ),
        )


def run_all_compliance_checks(
    request: PlaceOrderRequest,
    account_summary: AccountSummary | None = None,
) -> None:
    """Run all pre-order compliance checks.

    Raises:
        ComplianceError: On first failing check.
    """
    check_cnmv_short_sell(request)
    check_esma_leverage(request, account_summary)
    logger.info(
        "Compliance checks passed for %s %s %s qty=%.2f",
        request.side.value,
        request.symbol,
        request.order_type.value,
        request.quantity,
    )
```

---

### `src/qitp_mcp_ibkr/client.py`

```python
"""IBKR Client Portal REST API client.

Wraps the IBKR Client Portal Gateway REST API. The gateway must be running
separately (either the official IBKR Client Portal Gateway or a compatible
proxy).

API docs: https://www.interactivebrokers.com/api/doc.html
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class IBKRClientError(Exception):
    """Error from the IBKR Client Portal API."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"IBKR API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class IBKRClient:
    """Low-level HTTP client for the IBKR Client Portal REST API.

    The Client Portal Gateway runs locally (typically https://localhost:5000)
    and handles authentication with IBKR servers.

    Environment variables:
        IBKR_GATEWAY_URL: Base URL for the gateway (default: https://localhost:5000)
        IBKR_GATEWAY_SSL_VERIFY: Set to "false" to skip SSL verification (dev only)
    """

    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("IBKR_GATEWAY_URL", "https://localhost:5000")
        ).rstrip("/")

        ssl_verify = os.environ.get("IBKR_GATEWAY_SSL_VERIFY", "true").lower() != "false"

        self._client = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            verify=ssl_verify,
            timeout=30.0,
        )

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        """Make a request to the IBKR gateway."""
        try:
            resp = await self._client.request(
                method,
                f"/v1/api{path}",
                json=json_body,
                params=params,
            )
        except httpx.ConnectError as e:
            raise IBKRClientError(
                status_code=0,
                detail=f"Cannot connect to IBKR gateway at {self._base_url}: {e}",
            ) from e

        if resp.status_code == 401:
            raise IBKRClientError(
                status_code=401,
                detail="Session expired or not authenticated — re-auth required",
            )

        if resp.status_code >= 400:
            detail = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
            raise IBKRClientError(status_code=resp.status_code, detail=detail)

        if resp.status_code == 204:
            return {}

        return resp.json()

    async def get(self, path: str, params: dict | None = None) -> Any:
        """HTTP GET."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json_body: dict | None = None) -> Any:
        """HTTP POST."""
        return await self._request("POST", path, json_body=json_body)

    async def delete(self, path: str) -> Any:
        """HTTP DELETE."""
        return await self._request("DELETE", path)

    # ------------------------------------------------------------------
    # Convenience methods for common endpoints
    # ------------------------------------------------------------------

    async def ping(self) -> dict:
        """Tickle/ping the session to keep it alive."""
        return await self.post("/tickle")

    async def auth_status(self) -> dict:
        """Check authentication status."""
        return await self.post("/iserver/auth/status")

    async def reauthenticate(self) -> dict:
        """Trigger re-authentication."""
        return await self.post("/iserver/reauthenticate")

    async def get_accounts(self) -> list[dict]:
        """Get list of accounts."""
        data = await self.get("/iserver/accounts")
        return data.get("accounts", [])

    async def get_positions(self, account_id: str) -> list[dict]:
        """Get positions for an account."""
        # Must call /portfolio/accounts first to initialize
        await self.get("/portfolio/accounts")
        return await self.get(f"/portfolio/{account_id}/positions/0")

    async def get_account_summary(self, account_id: str) -> dict:
        """Get account summary/ledger."""
        await self.get("/portfolio/accounts")
        data = await self.get(f"/portfolio/{account_id}/summary")
        return data

    async def get_market_data(self, con_ids: list[int], fields: list[str]) -> list[dict]:
        """Get real-time market data snapshot for contract IDs.

        Fields: 31=last, 84=bid, 86=ask, 87=volume, 82=change_pct, etc.
        """
        con_ids_str = ",".join(str(c) for c in con_ids)
        fields_str = ",".join(fields)
        return await self.get(
            "/iserver/marketdata/snapshot",
            params={"conids": con_ids_str, "fields": fields_str},
        )

    async def search_contract(self, symbol: str) -> list[dict]:
        """Search for a contract by symbol to get con_id."""
        return await self.post(
            "/iserver/secdef/search",
            json_body={"symbol": symbol, "secType": "STK"},
        )

    async def place_order(self, account_id: str, orders: list[dict]) -> list[dict]:
        """Submit order(s).

        Returns list of order responses. May require confirmation reply.
        """
        return await self.post(
            f"/iserver/account/{account_id}/orders",
            json_body={"orders": orders},
        )

    async def confirm_order(self, reply_id: str, confirmed: bool = True) -> list[dict]:
        """Confirm an order that requires user confirmation."""
        return await self.post(
            f"/iserver/reply/{reply_id}",
            json_body={"confirmed": confirmed},
        )

    async def cancel_order(self, account_id: str, order_id: str) -> dict:
        """Cancel a pending order."""
        return await self.delete(f"/iserver/account/{account_id}/order/{order_id}")

    async def get_order_status(self, order_id: str) -> dict:
        """Get status of a specific order."""
        return await self.get(f"/iserver/account/order/status/{order_id}")

    async def get_live_orders(self) -> dict:
        """Get all live orders."""
        return await self.get("/iserver/account/orders")

    async def get_executions(self) -> list[dict]:
        """Get recent executions/trades."""
        data = await self.get("/iserver/account/trades")
        return data if isinstance(data, list) else []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
```

---

### `src/qitp_mcp_ibkr/session.py`

```python
"""Session management for the IBKR Client Portal Gateway.

Handles heartbeat pings (every 30s), auto-reconnect on 401, and
session status monitoring. The gateway session expires after ~30 minutes
of inactivity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qitp_mcp_ibkr.client import IBKRClient

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages the IBKR gateway session lifecycle.

    - Pings the gateway every `heartbeat_interval` seconds to keep alive
    - Re-authenticates automatically on 401
    - Tracks session status (authenticated, competing, disconnected)
    """

    def __init__(
        self,
        client: IBKRClient,
        heartbeat_interval: int = 30,
    ) -> None:
        self._client = client
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_task: asyncio.Task | None = None
        self._authenticated = False
        self._competing = False

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def competing(self) -> bool:
        return self._competing

    async def start(self) -> None:
        """Start the session heartbeat loop."""
        logger.info("Starting IBKR session manager (heartbeat every %ds)", self._heartbeat_interval)
        await self._check_auth()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop the heartbeat loop."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        logger.info("IBKR session manager stopped")

    async def ensure_authenticated(self) -> None:
        """Ensure the session is authenticated; re-auth if needed."""
        if not self._authenticated:
            await self._check_auth()
        if not self._authenticated:
            logger.warning("Session not authenticated — attempting re-auth")
            await self._reauthenticate()

    async def _check_auth(self) -> None:
        """Check current authentication status."""
        try:
            status = await self._client.auth_status()
            self._authenticated = status.get("authenticated", False)
            self._competing = status.get("competing", False)

            if self._competing:
                logger.warning(
                    "IBKR session is COMPETING — another session is active. "
                    "Only one session can place orders at a time."
                )

            if self._authenticated:
                logger.info("IBKR session authenticated")
            else:
                logger.warning("IBKR session NOT authenticated")
        except Exception:
            logger.exception("Failed to check IBKR auth status")
            self._authenticated = False

    async def _reauthenticate(self) -> None:
        """Trigger re-authentication with the IBKR gateway."""
        try:
            await self._client.reauthenticate()
            # Wait briefly for re-auth to complete
            await asyncio.sleep(2)
            await self._check_auth()
        except Exception:
            logger.exception("Re-authentication failed")
            self._authenticated = False

    async def _heartbeat_loop(self) -> None:
        """Periodically ping the gateway to keep the session alive."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self._client.ping()
                logger.debug("IBKR heartbeat OK")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("IBKR heartbeat failed — checking auth status")
                await self._check_auth()
                if not self._authenticated:
                    await self._reauthenticate()
```

---

### `src/qitp_mcp_ibkr/providers/__init__.py`

```python
"""IBKR provider implementations — routed by EXECUTION_MODE."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import IBKRProvider


def get_provider() -> IBKRProvider:
    """Return the appropriate IBKRProvider based on EXECUTION_MODE env var.

    - backtest  -> SimulatedProvider (no-op, canned responses)
    - paper     -> PaperProvider (IBKR paper trading account)
    - live      -> LiveProvider (IBKR live account, 2FA required)
    """
    mode = os.environ.get("EXECUTION_MODE", "backtest").lower()

    if mode == "backtest":
        from .simulated import SimulatedProvider

        return SimulatedProvider()
    elif mode == "paper":
        from .paper import PaperProvider

        return PaperProvider()
    elif mode == "live":
        from .live import LiveProvider

        return LiveProvider()
    else:
        raise ValueError(
            f"Unknown EXECUTION_MODE={mode!r}. Expected: backtest, paper, live"
        )
```

---

### `src/qitp_mcp_ibkr/providers/base.py`

```python
"""Abstract base class for IBKR providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from qitp_mcp_ibkr.schemas import (
    AccountSummary,
    Execution,
    MarketDataQuote,
    OrderResult,
    PlaceOrderRequest,
    Position,
    TrailingStopRequest,
    TrailingStopResult,
)


class IBKRProvider(ABC):
    """Abstract IBKR provider — all providers implement this interface."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        ...

    @abstractmethod
    async def get_account_summary(self) -> AccountSummary:
        """Get account NAV, buying power, margin, cash."""
        ...

    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketDataQuote:
        """Get real-time quote for a symbol."""
        ...

    @abstractmethod
    async def place_order(self, request: PlaceOrderRequest) -> OrderResult:
        """Submit an order. Live mode requires 2FA token."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel a pending order by order_id."""
        ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderResult:
        """Get current status of an order."""
        ...

    @abstractmethod
    async def get_executions(self, symbol: str | None = None) -> list[Execution]:
        """Get recent executions/fills. Optionally filter by symbol."""
        ...

    @abstractmethod
    async def set_trailing_stop(self, request: TrailingStopRequest) -> TrailingStopResult:
        """Attach a trailing stop to an existing position."""
        ...
```

---

### `src/qitp_mcp_ibkr/providers/simulated.py`

```python
"""Simulated provider for backtest mode — returns canned no-op responses.

No network calls. No IBKR gateway needed. All responses are deterministic
so agents can test their logic without broker connectivity.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from qitp_mcp_ibkr.schemas import (
    AccountSummary,
    Currency,
    Execution,
    MarketDataQuote,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PlaceOrderRequest,
    Position,
    TrailingStopRequest,
    TrailingStopResult,
)

from .base import IBKRProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Simulated static data
# ---------------------------------------------------------------------------

_SIMULATED_POSITIONS: list[Position] = [
    Position(
        symbol="AAPL",
        con_id=265598,
        quantity=100.0,
        avg_cost=150.0,
        market_value=17500.0,
        unrealized_pnl=2500.0,
        currency=Currency.USD,
        asset_class="STK",
        account_id="SIM_ACCOUNT",
    ),
    Position(
        symbol="MSFT",
        con_id=272093,
        quantity=50.0,
        avg_cost=350.0,
        market_value=19500.0,
        unrealized_pnl=2000.0,
        currency=Currency.USD,
        asset_class="STK",
        account_id="SIM_ACCOUNT",
    ),
]

_SIMULATED_ACCOUNT = AccountSummary(
    account_id="SIM_ACCOUNT",
    net_liquidation=100000.0,
    buying_power=200000.0,
    available_funds=60000.0,
    excess_liquidity=55000.0,
    margin_used=40000.0,
    cash_balance=63000.0,
    currency=Currency.USD,
)

_SIMULATED_QUOTES: dict[str, MarketDataQuote] = {
    "AAPL": MarketDataQuote(
        symbol="AAPL",
        con_id=265598,
        last=175.0,
        bid=174.95,
        ask=175.05,
        volume=45000000,
        change_pct=1.25,
    ),
    "MSFT": MarketDataQuote(
        symbol="MSFT",
        con_id=272093,
        last=390.0,
        bid=389.90,
        ask=390.10,
        volume=22000000,
        change_pct=-0.30,
    ),
}


class SimulatedProvider(IBKRProvider):
    """Simulated IBKR provider for backtest mode.

    Returns deterministic canned responses. No network calls.
    Maintains a simple in-memory order book for consistency.
    """

    def __init__(self) -> None:
        self._orders: dict[str, OrderResult] = {}
        self._executions: list[Execution] = []
        logger.info("SimulatedProvider initialized (backtest mode)")

    async def get_positions(self) -> list[Position]:
        return list(_SIMULATED_POSITIONS)

    async def get_account_summary(self) -> AccountSummary:
        return _SIMULATED_ACCOUNT.model_copy()

    async def get_market_data(self, symbol: str) -> MarketDataQuote:
        if symbol in _SIMULATED_QUOTES:
            return _SIMULATED_QUOTES[symbol].model_copy(
                update={"timestamp": datetime.utcnow()}
            )
        # Return a generic quote for unknown symbols
        return MarketDataQuote(
            symbol=symbol,
            con_id=0,
            last=100.0,
            bid=99.95,
            ask=100.05,
            volume=1000000,
            change_pct=0.0,
        )

    async def place_order(self, request: PlaceOrderRequest) -> OrderResult:
        order_id = f"SIM-{uuid.uuid4().hex[:8]}"
        fill_price = request.limit_price or 100.0

        result = OrderResult(
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            avg_fill_price=fill_price,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            idempotency_key=request.idempotency_key,
            message="Simulated fill (backtest mode)",
        )
        self._orders[order_id] = result

        # Create simulated execution
        execution = Execution(
            execution_id=f"EXEC-{uuid.uuid4().hex[:8]}",
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=fill_price,
            commission=1.0,
            currency=request.currency,
            isin=request.isin,
            venue=request.venue,
            timestamp_ms=int(datetime.utcnow().timestamp() * 1000),
            agent_reasoning_summary=request.agent_reasoning_summary,
        )
        self._executions.append(execution)

        logger.info(
            "Simulated order: %s %s %.0f %s @ %.2f (key=%s)",
            request.side.value,
            request.symbol,
            request.quantity,
            request.order_type.value,
            fill_price,
            request.idempotency_key,
        )
        return result

    async def cancel_order(self, order_id: str) -> OrderResult:
        if order_id in self._orders:
            order = self._orders[order_id]
            cancelled = order.model_copy(
                update={"status": OrderStatus.CANCELLED, "message": "Simulated cancel"}
            )
            self._orders[order_id] = cancelled
            return cancelled

        return OrderResult(
            order_id=order_id,
            symbol="UNKNOWN",
            side=OrderSide.BUY,
            quantity=0,
            order_type=OrderType.MARKET,
            status=OrderStatus.CANCELLED,
            message=f"Simulated cancel — order {order_id} not found in simulation",
        )

    async def get_order_status(self, order_id: str) -> OrderResult:
        if order_id in self._orders:
            return self._orders[order_id]

        return OrderResult(
            order_id=order_id,
            symbol="UNKNOWN",
            side=OrderSide.BUY,
            quantity=0,
            order_type=OrderType.MARKET,
            status=OrderStatus.INACTIVE,
            message=f"Order {order_id} not found in simulation",
        )

    async def get_executions(self, symbol: str | None = None) -> list[Execution]:
        if symbol is None:
            return list(self._executions)
        return [e for e in self._executions if e.symbol == symbol]

    async def set_trailing_stop(self, request: TrailingStopRequest) -> TrailingStopResult:
        order_id = f"SIM-TS-{uuid.uuid4().hex[:8]}"
        quantity = request.quantity or 100.0  # Default from simulated positions

        result = TrailingStopResult(
            order_id=order_id,
            symbol=request.symbol,
            trail_amount=request.trail_amount,
            trail_pct=request.trail_pct,
            quantity=quantity,
            status=OrderStatus.SUBMITTED,
            message="Simulated trailing stop (backtest mode)",
        )

        logger.info(
            "Simulated trailing stop: %s trail_amt=%s trail_pct=%s qty=%.0f",
            request.symbol,
            request.trail_amount,
            request.trail_pct,
            quantity,
        )
        return result
```

---

### `src/qitp_mcp_ibkr/providers/paper.py`

```python
"""Paper provider — connects to IBKR paper trading account via Client Portal Gateway.

Paper mode uses the same IBKR API as live but connects to a paper trading account.
No 2FA is required for paper trading.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from qitp_mcp_ibkr.client import IBKRClient
from qitp_mcp_ibkr.compliance import run_all_compliance_checks
from qitp_mcp_ibkr.schemas import (
    AccountSummary,
    Currency,
    Execution,
    MarketDataQuote,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PlaceOrderRequest,
    Position,
    TrailingStopRequest,
    TrailingStopResult,
)
from qitp_mcp_ibkr.session import SessionManager

from .base import IBKRProvider

logger = logging.getLogger(__name__)


class PaperProvider(IBKRProvider):
    """IBKR paper trading provider.

    Connects to the IBKR Client Portal Gateway configured for a paper account.
    """

    def __init__(
        self,
        client: IBKRClient | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._client = client or IBKRClient()
        self._session = session_manager or SessionManager(self._client)
        self._account_id = os.environ.get("IBKR_ACCOUNT_ID", "")
        self._initialized = False

    async def _ensure_init(self) -> None:
        """Ensure session is started and account ID is known."""
        if not self._initialized:
            await self._session.start()
            if not self._account_id:
                accounts = await self._client.get_accounts()
                if accounts:
                    self._account_id = accounts[0] if isinstance(accounts[0], str) else accounts[0].get("accountId", "")
                    logger.info("Using IBKR paper account: %s", self._account_id)
                else:
                    raise RuntimeError("No IBKR accounts found")
            self._initialized = True

    async def get_positions(self) -> list[Position]:
        await self._ensure_init()
        await self._session.ensure_authenticated()
        raw = await self._client.get_positions(self._account_id)

        positions: list[Position] = []
        for p in raw:
            positions.append(
                Position(
                    symbol=p.get("contractDesc", p.get("ticker", "UNKNOWN")),
                    con_id=p.get("conid", 0),
                    quantity=float(p.get("position", 0)),
                    avg_cost=float(p.get("avgCost", 0)),
                    market_value=float(p.get("mktValue", 0)),
                    unrealized_pnl=float(p.get("unrealizedPnl", 0)),
                    realized_pnl=float(p.get("realizedPnl", 0)),
                    currency=Currency(p.get("currency", "USD")),
                    asset_class=p.get("assetClass", "STK"),
                    account_id=self._account_id,
                )
            )
        return positions

    async def get_account_summary(self) -> AccountSummary:
        await self._ensure_init()
        await self._session.ensure_authenticated()
        raw = await self._client.get_account_summary(self._account_id)

        def _val(key: str) -> float:
            v = raw.get(key, {})
            if isinstance(v, dict):
                return float(v.get("amount", 0))
            return float(v or 0)

        return AccountSummary(
            account_id=self._account_id,
            net_liquidation=_val("netliquidation"),
            buying_power=_val("buyingpower"),
            available_funds=_val("availablefunds"),
            excess_liquidity=_val("excessliquidity"),
            margin_used=_val("initmarginreq"),
            cash_balance=_val("totalcashvalue"),
            currency=Currency.USD,
        )

    async def get_market_data(self, symbol: str) -> MarketDataQuote:
        await self._ensure_init()
        await self._session.ensure_authenticated()

        # Resolve con_id
        contracts = await self._client.search_contract(symbol)
        if not contracts:
            raise ValueError(f"No contract found for symbol: {symbol}")
        con_id = contracts[0].get("conid", 0)

        # Request snapshot: 31=last, 84=bid, 86=ask, 87=volume, 82=change%
        snapshots = await self._client.get_market_data(
            con_ids=[con_id],
            fields=["31", "84", "86", "87", "82"],
        )

        if not snapshots:
            raise ValueError(f"No market data returned for {symbol}")

        snap = snapshots[0]
        return MarketDataQuote(
            symbol=symbol,
            con_id=con_id,
            last=float(snap.get("31", 0)),
            bid=float(snap.get("84", 0)),
            ask=float(snap.get("86", 0)),
            volume=int(float(snap.get("87", 0))),
            change_pct=float(snap.get("82", 0)),
        )

    async def place_order(self, request: PlaceOrderRequest) -> OrderResult:
        await self._ensure_init()
        await self._session.ensure_authenticated()

        # Run compliance checks (account summary for ESMA leverage)
        try:
            summary = await self.get_account_summary()
        except Exception:
            summary = None
        run_all_compliance_checks(request, summary)

        # Resolve con_id
        contracts = await self._client.search_contract(request.symbol)
        if not contracts:
            raise ValueError(f"No contract found for symbol: {request.symbol}")
        con_id = contracts[0].get("conid", 0)

        # Build IBKR order payload
        order_payload = {
            "conid": con_id,
            "orderType": request.order_type.value,
            "side": request.side.value,
            "quantity": request.quantity,
            "tif": request.time_in_force,
            "cOID": request.idempotency_key,
        }
        if request.limit_price is not None:
            order_payload["price"] = request.limit_price
        if request.stop_price is not None:
            order_payload["auxPrice"] = request.stop_price

        # Submit
        responses = await self._client.place_order(self._account_id, [order_payload])

        # Handle confirmation flow
        if responses and isinstance(responses, list):
            for resp in responses:
                if "id" in resp and resp.get("message"):
                    # Order requires confirmation
                    confirm_resp = await self._client.confirm_order(resp["id"])
                    if confirm_resp:
                        responses = confirm_resp
                        break

        # Parse response
        order_resp = responses[0] if responses else {}
        order_id = str(order_resp.get("order_id", order_resp.get("orderId", "")))

        logger.info(
            "Paper order submitted: %s %s %.0f %s (key=%s, order_id=%s)",
            request.side.value,
            request.symbol,
            request.quantity,
            request.order_type.value,
            request.idempotency_key,
            order_id,
        )

        return OrderResult(
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.SUBMITTED,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            idempotency_key=request.idempotency_key,
            message=order_resp.get("message", "Order submitted to IBKR paper"),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        await self._ensure_init()
        await self._session.ensure_authenticated()

        resp = await self._client.cancel_order(self._account_id, order_id)
        return OrderResult(
            order_id=order_id,
            symbol=resp.get("symbol", ""),
            side=OrderSide.BUY,
            quantity=0,
            order_type=OrderType.MARKET,
            status=OrderStatus.CANCELLED,
            message=resp.get("msg", "Cancellation submitted"),
        )

    async def get_order_status(self, order_id: str) -> OrderResult:
        await self._ensure_init()
        await self._session.ensure_authenticated()

        resp = await self._client.get_order_status(order_id)
        status_map = {
            "Submitted": OrderStatus.SUBMITTED,
            "PreSubmitted": OrderStatus.PRE_SUBMITTED,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.INACTIVE,
        }
        raw_status = resp.get("order_status", resp.get("status", ""))
        status = status_map.get(raw_status, OrderStatus.SUBMITTED)

        return OrderResult(
            order_id=order_id,
            symbol=resp.get("symbol", resp.get("ticker", "")),
            side=OrderSide(resp.get("side", "BUY")),
            quantity=float(resp.get("totalSize", resp.get("quantity", 0))),
            order_type=OrderType(resp.get("orderType", "MKT")),
            status=status,
            filled_quantity=float(resp.get("filledQuantity", 0)),
            avg_fill_price=float(resp.get("avgPrice", 0)),
        )

    async def get_executions(self, symbol: str | None = None) -> list[Execution]:
        await self._ensure_init()
        await self._session.ensure_authenticated()

        raw = await self._client.get_executions()
        executions: list[Execution] = []
        for trade in raw:
            trade_symbol = trade.get("symbol", trade.get("ticker", ""))
            if symbol and trade_symbol != symbol:
                continue
            executions.append(
                Execution(
                    execution_id=str(trade.get("execution_id", trade.get("tradeId", ""))),
                    order_id=str(trade.get("order_ref", trade.get("orderId", ""))),
                    symbol=trade_symbol,
                    side=OrderSide(trade.get("side", "BUY")),
                    quantity=float(trade.get("size", trade.get("quantity", 0))),
                    price=float(trade.get("price", 0)),
                    commission=float(trade.get("commission", 0)),
                    currency=Currency(trade.get("currency", "USD")),
                    venue=trade.get("exchange", "SMART"),
                    timestamp_ms=int(
                        trade.get("trade_time_r", datetime.utcnow().timestamp() * 1000)
                    ),
                )
            )
        return executions

    async def set_trailing_stop(self, request: TrailingStopRequest) -> TrailingStopResult:
        await self._ensure_init()
        await self._session.ensure_authenticated()

        # Resolve con_id
        contracts = await self._client.search_contract(request.symbol)
        if not contracts:
            raise ValueError(f"No contract found for symbol: {request.symbol}")
        con_id = contracts[0].get("conid", 0)

        # Build trailing stop order
        quantity = request.quantity
        if quantity is None:
            # Default to full position
            positions = await self.get_positions()
            pos = next((p for p in positions if p.symbol == request.symbol), None)
            quantity = pos.quantity if pos else 0

        order_payload = {
            "conid": con_id,
            "orderType": "TRAIL",
            "side": "SELL",
            "quantity": quantity,
            "tif": "GTC",
            "cOID": request.idempotency_key,
        }
        if request.trail_amount is not None:
            order_payload["trailingAmt"] = request.trail_amount
            order_payload["trailingType"] = "amt"
        elif request.trail_pct is not None:
            order_payload["trailingAmt"] = request.trail_pct
            order_payload["trailingType"] = "%"

        responses = await self._client.place_order(self._account_id, [order_payload])
        order_resp = responses[0] if responses else {}
        order_id = str(order_resp.get("order_id", order_resp.get("orderId", "")))

        return TrailingStopResult(
            order_id=order_id,
            symbol=request.symbol,
            trail_amount=request.trail_amount,
            trail_pct=request.trail_pct,
            quantity=quantity,
            status=OrderStatus.SUBMITTED,
            message="Trailing stop submitted to IBKR paper",
        )
```

---

### `src/qitp_mcp_ibkr/providers/live.py`

```python
"""Live provider — connects to IBKR live trading account.

Identical to PaperProvider except:
1. Requires 2FA approval token on every place_order call
2. Logs all orders with MiFID II best execution fields
3. Additional compliance strictness
"""

from __future__ import annotations

import logging

from qitp_mcp_ibkr.schemas import (
    LiveModeRequires2FAError,
    OrderResult,
    PlaceOrderRequest,
)

from .paper import PaperProvider

logger = logging.getLogger(__name__)


class LiveProvider(PaperProvider):
    """IBKR live trading provider.

    Extends PaperProvider with 2FA enforcement and enhanced audit logging.
    All other operations (positions, account, market data) are identical.
    """

    async def place_order(self, request: PlaceOrderRequest) -> OrderResult:
        """Submit an order to IBKR live account.

        REQUIRES twofa_approval_token. This token comes from the 2FA gate
        in Step Functions (waitForTaskToken -> Telegram approval -> biometric).

        Raises:
            LiveModeRequires2FAError: If twofa_approval_token is missing or empty.
        """
        # Enforce 2FA — this is a non-negotiable constraint
        if not request.twofa_approval_token:
            logger.error(
                "LIVE MODE: place_order rejected — no 2FA token for %s %s %s qty=%.0f",
                request.side.value,
                request.symbol,
                request.order_type.value,
                request.quantity,
            )
            raise LiveModeRequires2FAError()

        logger.info(
            "LIVE ORDER (2FA verified): %s %s %.0f %s (key=%s, isin=%s, venue=%s)",
            request.side.value,
            request.symbol,
            request.quantity,
            request.order_type.value,
            request.idempotency_key,
            request.isin or "N/A",
            request.venue,
        )

        # MiFID II best execution log
        logger.info(
            "MiFID-II-EXEC: symbol=%s isin=%s venue=%s side=%s qty=%.0f "
            "order_type=%s limit=%.4f rationale=%s",
            request.symbol,
            request.isin or "N/A",
            request.venue,
            request.side.value,
            request.quantity,
            request.order_type.value,
            request.limit_price or 0.0,
            request.agent_reasoning_summary[:200] if request.agent_reasoning_summary else "N/A",
        )

        # Delegate to parent (PaperProvider) for actual IBKR API call
        return await super().place_order(request)
```

---

### `src/qitp_mcp_ibkr/tools/__init__.py`

```python
"""MCP tool implementations for IBKR broker server."""
```

---

### `src/qitp_mcp_ibkr/tools/positions.py`

```python
"""get_positions and get_account_summary tools."""

from __future__ import annotations

from qitp_mcp_ibkr.providers import get_provider


async def get_positions() -> list[dict]:
    """Get all open positions in the account.

    Returns:
        List of position dictionaries with symbol, quantity, avg_cost,
        market_value, unrealized_pnl, etc.
    """
    provider = get_provider()
    positions = await provider.get_positions()
    return [p.model_dump(mode="json") for p in positions]


async def get_account_summary() -> dict:
    """Get account summary: NAV, buying power, margin, cash.

    Returns:
        AccountSummary dictionary with net_liquidation, buying_power,
        available_funds, margin_used, cash_balance.
    """
    provider = get_provider()
    summary = await provider.get_account_summary()
    return summary.model_dump(mode="json")
```

---

### `src/qitp_mcp_ibkr/tools/market_data.py`

```python
"""get_market_data tool — IBKR-native real-time quote."""

from __future__ import annotations

from qitp_mcp_ibkr.providers import get_provider


async def get_market_data(symbol: str) -> dict:
    """Get a real-time quote for a symbol via IBKR.

    Args:
        symbol: Ticker symbol (e.g., "AAPL", "MSFT").

    Returns:
        MarketDataQuote dictionary with last, bid, ask, volume, change_pct.
    """
    provider = get_provider()
    quote = await provider.get_market_data(symbol)
    return quote.model_dump(mode="json")
```

---

### `src/qitp_mcp_ibkr/tools/orders.py`

```python
"""Order management tools — place_order, cancel_order, get_order_status, get_executions."""

from __future__ import annotations

import logging

from qitp_mcp_ibkr.providers import get_provider
from qitp_mcp_ibkr.schemas import (
    OrderSide,
    OrderType,
    PlaceOrderRequest,
)

logger = logging.getLogger(__name__)


async def place_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MKT",
    limit_price: float | None = None,
    stop_price: float | None = None,
    time_in_force: str = "DAY",
    idempotency_key: str = "",
    agent_reasoning_summary: str = "",
    twofa_approval_token: str | None = None,
    currency: str = "USD",
    isin: str | None = None,
    venue: str = "SMART",
) -> dict:
    """Submit an order to the broker.

    In live mode, twofa_approval_token is REQUIRED (enforced by provider).
    All orders are logged with MiFID II fields for audit trail.

    Args:
        symbol: Ticker symbol.
        side: Order side — "BUY", "SELL", or "SSHORT".
        quantity: Number of shares/contracts.
        order_type: Order type — "MKT", "LMT", "STP", "STP_LMT", "TRAIL".
        limit_price: Limit price (for LMT and STP_LMT orders).
        stop_price: Stop price (for STP and STP_LMT orders).
        time_in_force: "DAY", "GTC", or "IOC".
        idempotency_key: Unique key for retry safety (REQUIRED).
        agent_reasoning_summary: Why the agent placed this order.
        twofa_approval_token: 2FA token (REQUIRED in live mode).
        currency: "USD" or "EUR".
        isin: ISIN for MiFID II logging.
        venue: Execution venue for MiFID II logging.

    Returns:
        OrderResult dictionary.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key is required for all orders")

    request = PlaceOrderRequest(
        symbol=symbol,
        side=OrderSide(side),
        quantity=quantity,
        order_type=OrderType(order_type),
        limit_price=limit_price,
        stop_price=stop_price,
        time_in_force=time_in_force,
        idempotency_key=idempotency_key,
        agent_reasoning_summary=agent_reasoning_summary,
        twofa_approval_token=twofa_approval_token,
        currency=currency,
        isin=isin,
        venue=venue,
    )

    logger.info(
        "Order request: %s %s %.0f %s key=%s",
        request.side.value,
        request.symbol,
        request.quantity,
        request.order_type.value,
        request.idempotency_key,
    )

    provider = get_provider()
    result = await provider.place_order(request)
    return result.model_dump(mode="json")


async def cancel_order(order_id: str) -> dict:
    """Cancel a pending order.

    Args:
        order_id: The broker order ID to cancel.

    Returns:
        OrderResult dictionary with updated status.
    """
    provider = get_provider()
    result = await provider.cancel_order(order_id)
    return result.model_dump(mode="json")


async def get_order_status(order_id: str) -> dict:
    """Get the current status of an order.

    Args:
        order_id: The broker order ID to check.

    Returns:
        OrderResult dictionary with current status.
    """
    provider = get_provider()
    result = await provider.get_order_status(order_id)
    return result.model_dump(mode="json")


async def get_executions(symbol: str | None = None) -> list[dict]:
    """Get recent executions/fills for the audit trail.

    Args:
        symbol: Optional — filter by symbol. Returns all if not specified.

    Returns:
        List of Execution dictionaries.
    """
    provider = get_provider()
    executions = await provider.get_executions(symbol)
    return [e.model_dump(mode="json") for e in executions]
```

---

### `src/qitp_mcp_ibkr/tools/risk_mgmt.py`

```python
"""set_trailing_stop tool — mandatory per risk rules."""

from __future__ import annotations

import logging

from qitp_mcp_ibkr.providers import get_provider
from qitp_mcp_ibkr.schemas import TrailingStopRequest

logger = logging.getLogger(__name__)


async def set_trailing_stop(
    symbol: str,
    trail_amount: float | None = None,
    trail_pct: float | None = None,
    quantity: float | None = None,
    idempotency_key: str = "",
) -> dict:
    """Attach a trailing stop to an existing position.

    Per risk rules, ALL positions must have a trailing stop. Orders submitted
    without a corresponding trailing stop will be rejected by the Risk Engine.

    You must provide either trail_amount OR trail_pct (not both).

    Args:
        symbol: Ticker symbol of the position to protect.
        trail_amount: Trailing amount in absolute price terms (e.g., 5.0 = $5).
        trail_pct: Trailing percentage (e.g., 2.0 = 2%).
        quantity: Shares to protect — defaults to full position.
        idempotency_key: Unique key for retry safety (REQUIRED).

    Returns:
        TrailingStopResult dictionary.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key is required for trailing stop orders")

    if trail_amount is None and trail_pct is None:
        raise ValueError("Either trail_amount or trail_pct must be provided")

    if trail_amount is not None and trail_pct is not None:
        raise ValueError("Provide either trail_amount OR trail_pct, not both")

    request = TrailingStopRequest(
        symbol=symbol,
        trail_amount=trail_amount,
        trail_pct=trail_pct,
        quantity=quantity,
        idempotency_key=idempotency_key,
    )

    logger.info(
        "Trailing stop request: %s trail_amt=%s trail_pct=%s qty=%s key=%s",
        request.symbol,
        request.trail_amount,
        request.trail_pct,
        request.quantity,
        request.idempotency_key,
    )

    provider = get_provider()
    result = await provider.set_trailing_stop(request)
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_ibkr/server.py`

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
logger = logging.getLogger("qitp_mcp_ibkr")

# ---------------------------------------------------------------------------
# Build the MCP server
# ---------------------------------------------------------------------------

server = Server("ibkr-mcp")


# ---------------------------------------------------------------------------
# Tool definitions (list_tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="get_positions",
        description=(
            "Get all open positions in the broker account. "
            "Returns symbol, quantity, avg_cost, market_value, unrealized_pnl."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_account_summary",
        description=(
            "Get account-level financial summary: NAV, buying power, "
            "margin used, available funds, cash balance."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_market_data",
        description=(
            "Get a real-time IBKR-native quote for a symbol: "
            "last, bid, ask, volume, change_pct."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL)"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="place_order",
        description=(
            "Submit an order to the broker. "
            "Requires idempotency_key. In LIVE mode, twofa_approval_token is REQUIRED. "
            "Runs ESMA leverage and CNMV short-sell compliance checks before submission."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "side": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "SSHORT"],
                    "description": "Order side",
                },
                "quantity": {"type": "number", "description": "Number of shares"},
                "order_type": {
                    "type": "string",
                    "enum": ["MKT", "LMT", "STP", "STP_LMT", "TRAIL"],
                    "default": "MKT",
                    "description": "Order type",
                },
                "limit_price": {
                    "type": "number",
                    "description": "Limit price (for LMT/STP_LMT orders)",
                },
                "stop_price": {
                    "type": "number",
                    "description": "Stop price (for STP/STP_LMT orders)",
                },
                "time_in_force": {
                    "type": "string",
                    "enum": ["DAY", "GTC", "IOC"],
                    "default": "DAY",
                    "description": "Time in force",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Unique key for retry safety (REQUIRED)",
                },
                "agent_reasoning_summary": {
                    "type": "string",
                    "description": "Why the agent placed this order (audit trail)",
                },
                "twofa_approval_token": {
                    "type": "string",
                    "description": "2FA approval token — REQUIRED in live mode",
                },
                "currency": {
                    "type": "string",
                    "enum": ["USD", "EUR"],
                    "default": "USD",
                },
                "isin": {
                    "type": "string",
                    "description": "ISIN for MiFID II logging",
                },
                "venue": {
                    "type": "string",
                    "default": "SMART",
                    "description": "Execution venue for MiFID II logging",
                },
            },
            "required": ["symbol", "side", "quantity", "idempotency_key"],
        },
    ),
    Tool(
        name="cancel_order",
        description="Cancel a pending order by order_id.",
        inputSchema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Broker order ID to cancel"},
            },
            "required": ["order_id"],
        },
    ),
    Tool(
        name="get_order_status",
        description=(
            "Get the current status of an order: submitted, filled, cancelled, rejected."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Broker order ID"},
            },
            "required": ["order_id"],
        },
    ),
    Tool(
        name="get_executions",
        description=(
            "Get recent executions/fills for the audit trail. "
            "Optionally filter by symbol."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Filter by symbol (optional — returns all if omitted)",
                },
            },
        },
    ),
    Tool(
        name="set_trailing_stop",
        description=(
            "Attach a trailing stop to an existing position. "
            "Mandatory per risk rules — all positions must have a trailing stop. "
            "Provide either trail_amount (absolute) or trail_pct (percentage)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol of the position to protect"},
                "trail_amount": {
                    "type": "number",
                    "description": "Trailing amount in absolute price terms (e.g., 5.0 = $5)",
                },
                "trail_pct": {
                    "type": "number",
                    "description": "Trailing percentage (e.g., 2.0 = 2%)",
                },
                "quantity": {
                    "type": "number",
                    "description": "Shares to protect — defaults to full position",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Unique key for retry safety (REQUIRED)",
                },
            },
            "required": ["symbol", "idempotency_key"],
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
    if name == "get_positions":
        from qitp_mcp_ibkr.tools.positions import get_positions

        return await get_positions()

    elif name == "get_account_summary":
        from qitp_mcp_ibkr.tools.positions import get_account_summary

        return await get_account_summary()

    elif name == "get_market_data":
        from qitp_mcp_ibkr.tools.market_data import get_market_data

        return await get_market_data(symbol=arguments["symbol"])

    elif name == "place_order":
        from qitp_mcp_ibkr.tools.orders import place_order

        return await place_order(
            symbol=arguments["symbol"],
            side=arguments["side"],
            quantity=arguments["quantity"],
            order_type=arguments.get("order_type", "MKT"),
            limit_price=arguments.get("limit_price"),
            stop_price=arguments.get("stop_price"),
            time_in_force=arguments.get("time_in_force", "DAY"),
            idempotency_key=arguments["idempotency_key"],
            agent_reasoning_summary=arguments.get("agent_reasoning_summary", ""),
            twofa_approval_token=arguments.get("twofa_approval_token"),
            currency=arguments.get("currency", "USD"),
            isin=arguments.get("isin"),
            venue=arguments.get("venue", "SMART"),
        )

    elif name == "cancel_order":
        from qitp_mcp_ibkr.tools.orders import cancel_order

        return await cancel_order(order_id=arguments["order_id"])

    elif name == "get_order_status":
        from qitp_mcp_ibkr.tools.orders import get_order_status

        return await get_order_status(order_id=arguments["order_id"])

    elif name == "get_executions":
        from qitp_mcp_ibkr.tools.orders import get_executions

        return await get_executions(symbol=arguments.get("symbol"))

    elif name == "set_trailing_stop":
        from qitp_mcp_ibkr.tools.risk_mgmt import set_trailing_stop

        return await set_trailing_stop(
            symbol=arguments["symbol"],
            trail_amount=arguments.get("trail_amount"),
            trail_pct=arguments.get("trail_pct"),
            quantity=arguments.get("quantity"),
            idempotency_key=arguments["idempotency_key"],
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
        # Streamable HTTP transport for production
        from mcp.server.streamable_http import StreamableHTTPServer

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8001"))
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

### `tests/fixtures/sample_responses.json`

```json
{
    "positions": [
        {
            "contractDesc": "AAPL",
            "conid": 265598,
            "position": 100.0,
            "avgCost": 150.0,
            "mktValue": 17500.0,
            "unrealizedPnl": 2500.0,
            "realizedPnl": 0.0,
            "currency": "USD",
            "assetClass": "STK"
        },
        {
            "contractDesc": "MSFT",
            "conid": 272093,
            "position": 50.0,
            "avgCost": 350.0,
            "mktValue": 19500.0,
            "unrealizedPnl": 2000.0,
            "realizedPnl": 100.0,
            "currency": "USD",
            "assetClass": "STK"
        }
    ],
    "account_summary": {
        "netliquidation": {"amount": 100000.0, "currency": "USD"},
        "buyingpower": {"amount": 200000.0, "currency": "USD"},
        "availablefunds": {"amount": 60000.0, "currency": "USD"},
        "excessliquidity": {"amount": 55000.0, "currency": "USD"},
        "initmarginreq": {"amount": 40000.0, "currency": "USD"},
        "totalcashvalue": {"amount": 63000.0, "currency": "USD"}
    },
    "market_data_snapshot": [
        {
            "conid": 265598,
            "31": "175.50",
            "84": "175.45",
            "86": "175.55",
            "87": "45000000",
            "82": "1.25"
        }
    ],
    "order_submit": [
        {
            "order_id": "1234567890",
            "orderId": 1234567890,
            "message": "Order submitted successfully"
        }
    ],
    "order_status": {
        "order_id": "1234567890",
        "symbol": "AAPL",
        "side": "BUY",
        "order_status": "Filled",
        "totalSize": 100,
        "filledQuantity": 100,
        "avgPrice": 175.50,
        "orderType": "MKT"
    },
    "executions": [
        {
            "execution_id": "EXEC-001",
            "tradeId": "T001",
            "orderId": "1234567890",
            "symbol": "AAPL",
            "side": "BUY",
            "size": 100,
            "price": 175.50,
            "commission": 1.00,
            "currency": "USD",
            "exchange": "SMART",
            "trade_time_r": 1700000000000
        }
    ],
    "contract_search": [
        {
            "conid": 265598,
            "companyName": "APPLE INC",
            "symbol": "AAPL",
            "secType": "STK",
            "exchange": "NASDAQ"
        }
    ],
    "auth_status": {
        "authenticated": true,
        "competing": false,
        "connected": true,
        "message": "",
        "MAC": "00:00:00:00:00:00"
    },
    "tickle": {
        "session": "active",
        "ssoExpires": 1700000000,
        "collission": false,
        "iserver": {
            "authStatus": {
                "authenticated": true,
                "competing": false,
                "connected": true
            }
        }
    }
}
```

---

### `tests/conftest.py`

```python
"""Shared test fixtures for IBKR MCP server tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _set_backtest_mode(monkeypatch):
    """Default all tests to backtest mode."""
    monkeypatch.setenv("EXECUTION_MODE", "backtest")


@pytest.fixture
def sample_responses() -> dict:
    """Load the sample IBKR API responses from fixtures."""
    fixtures_path = Path(__file__).parent / "fixtures" / "sample_responses.json"
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def mock_ibkr_client(sample_responses):
    """Mock IBKRClient that returns canned responses."""
    from qitp_mcp_ibkr.client import IBKRClient

    client = AsyncMock(spec=IBKRClient)

    client.ping.return_value = sample_responses["tickle"]
    client.auth_status.return_value = sample_responses["auth_status"]
    client.reauthenticate.return_value = {}
    client.get_accounts.return_value = ["DU1234567"]
    client.get_positions.return_value = sample_responses["positions"]
    client.get_account_summary.return_value = sample_responses["account_summary"]
    client.get_market_data.return_value = sample_responses["market_data_snapshot"]
    client.search_contract.return_value = sample_responses["contract_search"]
    client.place_order.return_value = sample_responses["order_submit"]
    client.confirm_order.return_value = sample_responses["order_submit"]
    client.cancel_order.return_value = {"msg": "Cancellation submitted", "symbol": "AAPL"}
    client.get_order_status.return_value = sample_responses["order_status"]
    client.get_live_orders.return_value = {"orders": []}
    client.get_executions.return_value = sample_responses["executions"]
    client.close.return_value = None

    return client
```

---

### `tests/test_positions.py`

```python
"""Tests for positions and account summary tools."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qitp_mcp_ibkr.providers.simulated import SimulatedProvider
from qitp_mcp_ibkr.tools.positions import get_account_summary, get_positions


# ---------------------------------------------------------------------------
# Simulated provider tests (backtest mode)
# ---------------------------------------------------------------------------


class TestSimulatedPositions:
    @pytest.mark.asyncio
    async def test_get_positions_returns_simulated_data(self):
        """SimulatedProvider should return canned positions."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.positions.get_provider", return_value=provider):
            result = await get_positions()

        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["quantity"] == 100.0
        assert result[0]["avg_cost"] == 150.0
        assert result[0]["unrealized_pnl"] == 2500.0
        assert result[1]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_get_account_summary_returns_simulated_data(self):
        """SimulatedProvider should return canned account summary."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.positions.get_provider", return_value=provider):
            result = await get_account_summary()

        assert result["account_id"] == "SIM_ACCOUNT"
        assert result["net_liquidation"] == 100000.0
        assert result["buying_power"] == 200000.0
        assert result["cash_balance"] == 63000.0


# ---------------------------------------------------------------------------
# Paper provider tests (with mock IBKR client)
# ---------------------------------------------------------------------------


class TestPaperPositions:
    @pytest.mark.asyncio
    async def test_get_positions_paper_mode(self, mock_ibkr_client, monkeypatch):
        """PaperProvider should parse IBKR API responses into Position models."""
        monkeypatch.setenv("EXECUTION_MODE", "paper")
        monkeypatch.setenv("IBKR_ACCOUNT_ID", "DU1234567")

        from qitp_mcp_ibkr.providers.paper import PaperProvider
        from qitp_mcp_ibkr.session import SessionManager

        session = SessionManager(mock_ibkr_client)
        provider = PaperProvider(client=mock_ibkr_client, session_manager=session)

        with patch("qitp_mcp_ibkr.tools.positions.get_provider", return_value=provider):
            result = await get_positions()

        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["con_id"] == 265598
        assert result[0]["quantity"] == 100.0

    @pytest.mark.asyncio
    async def test_get_account_summary_paper_mode(self, mock_ibkr_client, monkeypatch):
        """PaperProvider should parse IBKR account summary response."""
        monkeypatch.setenv("EXECUTION_MODE", "paper")
        monkeypatch.setenv("IBKR_ACCOUNT_ID", "DU1234567")

        from qitp_mcp_ibkr.providers.paper import PaperProvider
        from qitp_mcp_ibkr.session import SessionManager

        session = SessionManager(mock_ibkr_client)
        provider = PaperProvider(client=mock_ibkr_client, session_manager=session)

        with patch("qitp_mcp_ibkr.tools.positions.get_provider", return_value=provider):
            result = await get_account_summary()

        assert result["account_id"] == "DU1234567"
        assert result["net_liquidation"] == 100000.0
        assert result["buying_power"] == 200000.0
```

---

### `tests/test_orders.py`

```python
"""Tests for order management tools — place, cancel, status, executions."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qitp_mcp_ibkr.providers.simulated import SimulatedProvider
from qitp_mcp_ibkr.schemas import LiveModeRequires2FAError, OrderStatus
from qitp_mcp_ibkr.tools.orders import (
    cancel_order,
    get_executions,
    get_order_status,
    place_order,
)


# ---------------------------------------------------------------------------
# Simulated provider tests (backtest mode)
# ---------------------------------------------------------------------------


class TestSimulatedOrders:
    @pytest.mark.asyncio
    async def test_place_order_simulated(self):
        """Simulated orders should return FILLED status immediately."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            result = await place_order(
                symbol="AAPL",
                side="BUY",
                quantity=100,
                order_type="LMT",
                limit_price=175.0,
                idempotency_key="test-key-001",
                agent_reasoning_summary="Gap up detected, momentum entry",
            )

        assert result["symbol"] == "AAPL"
        assert result["side"] == "BUY"
        assert result["quantity"] == 100.0
        assert result["status"] == "filled"
        assert result["filled_quantity"] == 100.0
        assert result["avg_fill_price"] == 175.0
        assert result["idempotency_key"] == "test-key-001"
        assert "SIM-" in result["order_id"]

    @pytest.mark.asyncio
    async def test_place_order_requires_idempotency_key(self):
        """Orders without idempotency_key should be rejected."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            with pytest.raises(ValueError, match="idempotency_key is required"):
                await place_order(
                    symbol="AAPL",
                    side="BUY",
                    quantity=100,
                    idempotency_key="",
                )

    @pytest.mark.asyncio
    async def test_cancel_order_simulated(self):
        """Cancel should work on simulated orders."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            # Place first
            order = await place_order(
                symbol="AAPL",
                side="BUY",
                quantity=50,
                idempotency_key="cancel-test-001",
            )
            order_id = order["order_id"]

            # Then cancel
            result = await cancel_order(order_id)

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_get_order_status_simulated(self):
        """get_order_status should return the order's current state."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            order = await place_order(
                symbol="MSFT",
                side="BUY",
                quantity=25,
                idempotency_key="status-test-001",
            )
            order_id = order["order_id"]

            result = await get_order_status(order_id)

        assert result["order_id"] == order_id
        assert result["status"] == "filled"
        assert result["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_get_order_status_unknown_order(self):
        """Unknown order IDs should return inactive status."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            result = await get_order_status("NONEXISTENT-123")

        assert result["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_get_executions_simulated(self):
        """get_executions should return fills from simulated orders."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            await place_order(
                symbol="AAPL",
                side="BUY",
                quantity=100,
                idempotency_key="exec-test-001",
            )
            await place_order(
                symbol="MSFT",
                side="SELL",
                quantity=50,
                idempotency_key="exec-test-002",
            )

            # Get all
            all_execs = await get_executions()
            assert len(all_execs) == 2

            # Filter by symbol
            aapl_execs = await get_executions(symbol="AAPL")
            assert len(aapl_execs) == 1
            assert aapl_execs[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_simulated_execution_has_audit_fields(self):
        """Simulated executions should include MiFID II audit fields."""
        provider = SimulatedProvider()

        with patch("qitp_mcp_ibkr.tools.orders.get_provider", return_value=provider):
            await place_order(
                symbol="AAPL",
                side="BUY",
                quantity=100,
                idempotency_key="audit-test-001",
                agent_reasoning_summary="Testing audit fields",
                isin="US0378331005",
                venue="SMART",
            )
            execs = await get_executions()

        assert len(execs) == 1
        assert execs[0]["isin"] == "US0378331005"
        assert execs[0]["venue"] == "SMART"
        assert execs[0]["timestamp_ms"] > 0
        assert execs[0]["agent_reasoning_summary"] == "Testing audit fields"


# ---------------------------------------------------------------------------
# Live mode 2FA enforcement
# ---------------------------------------------------------------------------


class TestLiveMode2FA:
    @pytest.mark.asyncio
    async def test_live_mode_rejects_without_2fa(self, monkeypatch):
        """Live mode place_order must reject orders without 2FA token."""
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("IBKR_ACCOUNT_ID", "U1234567")

        from qitp_mcp_ibkr.providers.live import LiveProvider

        provider = LiveProvider.__new__(LiveProvider)
        provider._client = None
        provider._session = None
        provider._account_id = "U1234567"
        provider._initialized = True

        from qitp_mcp_ibkr.schemas import PlaceOrderRequest

        request = PlaceOrderRequest(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            idempotency_key="live-no-2fa",
            twofa_approval_token=None,
        )

        with pytest.raises(LiveModeRequires2FAError):
            await provider.place_order(request)

    @pytest.mark.asyncio
    async def test_live_mode_rejects_empty_2fa(self, monkeypatch):
        """Live mode should also reject empty string 2FA tokens."""
        monkeypatch.setenv("EXECUTION_MODE", "live")

        from qitp_mcp_ibkr.providers.live import LiveProvider

        provider = LiveProvider.__new__(LiveProvider)
        provider._client = None
        provider._session = None
        provider._account_id = "U1234567"
        provider._initialized = True

        from qitp_mcp_ibkr.schemas import PlaceOrderRequest

        request = PlaceOrderRequest(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            idempotency_key="live-empty-2fa",
            twofa_approval_token="",
        )

        with pytest.raises(LiveModeRequires2FAError):
            await provider.place_order(request)
```

---

### `tests/test_session.py`

```python
"""Tests for session management — heartbeat, auth status, re-authentication."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from qitp_mcp_ibkr.session import SessionManager


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_start_checks_auth(self):
        """Starting the session manager should check auth status."""
        client = AsyncMock()
        client.auth_status.return_value = {"authenticated": True, "competing": False}
        client.ping.return_value = {}

        session = SessionManager(client, heartbeat_interval=60)
        await session.start()

        assert session.authenticated is True
        assert session.competing is False

        await session.stop()
        client.auth_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_detects_not_authenticated(self):
        """Session should report not authenticated when gateway says so."""
        client = AsyncMock()
        client.auth_status.return_value = {"authenticated": False, "competing": False}
        client.ping.return_value = {}

        session = SessionManager(client, heartbeat_interval=60)
        await session.start()

        assert session.authenticated is False

        await session.stop()

    @pytest.mark.asyncio
    async def test_start_detects_competing_session(self):
        """Session should flag competing when another session is active."""
        client = AsyncMock()
        client.auth_status.return_value = {"authenticated": True, "competing": True}
        client.ping.return_value = {}

        session = SessionManager(client, heartbeat_interval=60)
        await session.start()

        assert session.authenticated is True
        assert session.competing is True

        await session.stop()

    @pytest.mark.asyncio
    async def test_ensure_authenticated_triggers_reauth(self):
        """ensure_authenticated should re-auth when not authenticated."""
        client = AsyncMock()
        # First call: not auth. After reauth: auth.
        client.auth_status.side_effect = [
            {"authenticated": False, "competing": False},
            {"authenticated": True, "competing": False},
        ]
        client.reauthenticate.return_value = {}
        client.ping.return_value = {}

        session = SessionManager(client, heartbeat_interval=60)
        await session.start()
        assert session.authenticated is False

        await session.ensure_authenticated()
        assert session.authenticated is True
        client.reauthenticate.assert_called_once()

        await session.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_heartbeat(self):
        """Stopping should cancel the heartbeat task cleanly."""
        client = AsyncMock()
        client.auth_status.return_value = {"authenticated": True, "competing": False}
        client.ping.return_value = {}

        session = SessionManager(client, heartbeat_interval=1)
        await session.start()
        assert session._heartbeat_task is not None

        await session.stop()
        assert session._heartbeat_task is None
```

---

### `tests/test_compliance.py`

```python
"""Tests for compliance checks — ESMA leverage and CNMV short-sell restrictions."""

from __future__ import annotations

import pytest

from qitp_mcp_ibkr.compliance import (
    check_cnmv_short_sell,
    check_esma_leverage,
    run_all_compliance_checks,
)
from qitp_mcp_ibkr.schemas import (
    AccountSummary,
    ComplianceError,
    Currency,
    OrderSide,
    OrderType,
    PlaceOrderRequest,
)


# ---------------------------------------------------------------------------
# CNMV Short-Sell Tests
# ---------------------------------------------------------------------------


class TestCNMVShortSell:
    def test_sshort_ibex35_symbol_rejected(self):
        """Short-selling IBEX35 symbols should raise ComplianceError."""
        request = PlaceOrderRequest(
            symbol="SAN",
            side=OrderSide.SSHORT,
            quantity=100,
            idempotency_key="cnmv-test-001",
        )
        with pytest.raises(ComplianceError, match="CNMV-SHORT-SELL"):
            check_cnmv_short_sell(request)

    def test_sshort_ibex35_with_exchange_suffix(self):
        """IBEX35 symbols with .MC suffix should also be caught."""
        request = PlaceOrderRequest(
            symbol="SAN.MC",
            side=OrderSide.SSHORT,
            quantity=100,
            idempotency_key="cnmv-test-002",
        )
        with pytest.raises(ComplianceError, match="CNMV-SHORT-SELL"):
            check_cnmv_short_sell(request)

    def test_sshort_non_ibex35_allowed(self):
        """Short-selling non-IBEX35 symbols should pass."""
        request = PlaceOrderRequest(
            symbol="AAPL",
            side=OrderSide.SSHORT,
            quantity=100,
            idempotency_key="cnmv-test-003",
        )
        # Should not raise
        check_cnmv_short_sell(request)

    def test_buy_ibex35_allowed(self):
        """BUY orders on IBEX35 symbols should pass (only SSHORT is restricted)."""
        request = PlaceOrderRequest(
            symbol="SAN",
            side=OrderSide.BUY,
            quantity=100,
            idempotency_key="cnmv-test-004",
        )
        check_cnmv_short_sell(request)

    def test_sell_ibex35_allowed(self):
        """SELL orders on IBEX35 symbols should pass (closing a long position)."""
        request = PlaceOrderRequest(
            symbol="BBVA",
            side=OrderSide.SELL,
            quantity=100,
            idempotency_key="cnmv-test-005",
        )
        check_cnmv_short_sell(request)


# ---------------------------------------------------------------------------
# ESMA Leverage Tests
# ---------------------------------------------------------------------------


class TestESMALeverage:
    @pytest.fixture
    def account(self) -> AccountSummary:
        return AccountSummary(
            account_id="TEST",
            net_liquidation=100000.0,
            buying_power=200000.0,
            available_funds=60000.0,
            excess_liquidity=55000.0,
            currency=Currency.USD,
        )

    def test_within_leverage_limit(self, account):
        """Order within ESMA leverage limits should pass."""
        request = PlaceOrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=175.0,  # Notional: 17500, max: 500000 (5x NAV)
            idempotency_key="esma-test-001",
        )
        # Should not raise
        check_esma_leverage(request, account)

    def test_exceeds_leverage_limit(self, account):
        """Order exceeding ESMA 5x leverage should raise ComplianceError."""
        request = PlaceOrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5000,
            order_type=OrderType.LIMIT,
            limit_price=175.0,  # Notional: 875000 > 500000
            idempotency_key="esma-test-002",
        )
        with pytest.raises(ComplianceError, match="ESMA-CFD-LEVERAGE"):
            check_esma_leverage(request, account)

    def test_market_order_deferred_to_risk_engine(self, account):
        """Market orders without price should defer to Risk Engine (no raise)."""
        request = PlaceOrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5000,
            order_type=OrderType.MARKET,
            idempotency_key="esma-test-003",
        )
        # Should not raise — deferred to Risk Engine
        check_esma_leverage(request, account)

    def test_no_account_summary_logs_warning(self):
        """Without account summary, ESMA check should pass with a warning."""
        request = PlaceOrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=175.0,
            idempotency_key="esma-test-004",
        )
        # Should not raise
        check_esma_leverage(request, None)


# ---------------------------------------------------------------------------
# Combined Compliance Tests
# ---------------------------------------------------------------------------


class TestRunAllCompliance:
    def test_all_checks_pass(self):
        """All compliance checks should pass for a normal BUY order."""
        account = AccountSummary(
            account_id="TEST",
            net_liquidation=100000.0,
            buying_power=200000.0,
            available_funds=60000.0,
            excess_liquidity=55000.0,
            currency=Currency.USD,
        )
        request = PlaceOrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=175.0,
            idempotency_key="combined-test-001",
        )
        # Should not raise
        run_all_compliance_checks(request, account)

    def test_cnmv_fails_first(self):
        """CNMV check should fail before ESMA check runs."""
        request = PlaceOrderRequest(
            symbol="SAN",
            side=OrderSide.SSHORT,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=3.50,
            idempotency_key="combined-test-002",
        )
        with pytest.raises(ComplianceError, match="CNMV-SHORT-SELL"):
            run_all_compliance_checks(request, None)
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
    CMD curl -f http://localhost:8001/health || exit 1

# Default: HTTP transport for production
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8001
ENV EXECUTION_MODE=backtest

EXPOSE 8001

ENTRYPOINT ["ibkr-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  ibkr-mcp:
    build: .
    container_name: qitp-ibkr-mcp
    ports:
      - "8001:8001"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8001
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - IBKR_GATEWAY_URL=${IBKR_GATEWAY_URL:-https://localhost:5000}
      - IBKR_GATEWAY_SSL_VERIFY=${IBKR_GATEWAY_SSL_VERIFY:-false}
      - IBKR_ACCOUNT_ID=${IBKR_ACCOUNT_ID:-}
    restart: unless-stopped
    networks:
      - qitp

  # IBKR Client Portal Gateway (must be configured separately)
  # See: https://www.interactivebrokers.com/en/trading/ib-api.php
  #
  # ibkr-gateway:
  #   image: ghcr.io/extrange/ibkr-docker:latest
  #   container_name: ibkr-gateway
  #   ports:
  #     - "5000:5000"
  #   environment:
  #     - TRADING_MODE=${TRADING_MODE:-paper}
  #   networks:
  #     - qitp

networks:
  qitp:
    driver: bridge
```

---

## Acceptance Criteria

- [ ] MCP server starts and lists 8 tools
- [ ] `get_positions` returns positions in all 3 modes (simulated data in backtest)
- [ ] `get_account_summary` returns NAV, buying power, margin, cash
- [ ] `get_market_data` returns real-time quote with last, bid, ask, volume, change_pct
- [ ] `place_order` requires idempotency_key — rejects without it
- [ ] `place_order` in live mode requires twofa_approval_token — rejects without it
- [ ] `place_order` runs ESMA leverage check and CNMV short-sell check before submission
- [ ] `cancel_order` cancels a pending order by order_id
- [ ] `get_order_status` returns current status (submitted, filled, cancelled, rejected)
- [ ] `get_executions` returns fills with MiFID II audit fields (timestamp_ms, isin, venue)
- [ ] `set_trailing_stop` requires either trail_amount or trail_pct, not both
- [ ] EXECUTION_MODE routing works: backtest -> Simulated, paper -> Paper, live -> Live
- [ ] SimulatedProvider makes zero network calls
- [ ] Session manager heartbeats every 30s, auto-reconnects on 401
- [ ] Docker build succeeds
- [ ] All tests pass

## Test Plan

```bash
cd ~/dev/tccw-qitp-mcp-ibkr
pip install -e ".[dev]"
pytest -v
docker build -t qitp-mcp-ibkr .
```

## Agent Instructions

This MCP server is the broker control plane. It is the most security-critical component in the platform. Every order flows through here. The 2FA gate is non-negotiable: in live mode, no order can be placed without a token. The compliance checks (ESMA, CNMV) are fast-fail validations at the MCP layer, but they do not replace the Risk Engine Lambda (P16) which runs as a separate Step Functions state before any order.

Key implementation notes:
1. **2FA is sacred in live mode**: `LiveProvider.place_order()` must check `twofa_approval_token` FIRST, before any IBKR API call. Empty string counts as missing. This is a non-negotiable constraint.
2. **Idempotency keys on all write operations**: `place_order` and `set_trailing_stop` both require `idempotency_key`. The key maps to IBKR's `cOID` (client order ID) for dedup.
3. **Provider routing**: `EXECUTION_MODE` env var controls which provider is used. `SimulatedProvider` makes ZERO network calls. Paper and Live both connect to IBKR gateway but paper skips 2FA.
4. **Session management**: The IBKR Client Portal Gateway session expires after ~30 minutes of inactivity. The `SessionManager` pings every 30s and re-authenticates on 401.
5. **Compliance checks**: Run `check_cnmv_short_sell()` before `check_esma_leverage()`. Both must pass before the order reaches IBKR. Market orders defer ESMA leverage check to Risk Engine (no price known at MCP layer).
6. **MiFID II audit logging**: Every `place_order` call in live mode logs: timestamp_ms, symbol, ISIN, venue, price, qty, rationale. Executions store the same fields.
7. **Error handling**: Return structured error JSON from tool calls, never crash the server. `LiveModeRequires2FAError` and `ComplianceError` are expected errors that agents should handle.
8. **Credentials**: `IBKR_GATEWAY_URL`, `IBKR_ACCOUNT_ID`, `IBKR_GATEWAY_SSL_VERIFY` are all via environment variables. Never hardcode. The gateway handles IBKR authentication — this MCP server never touches IBKR credentials directly.
