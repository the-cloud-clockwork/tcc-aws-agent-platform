# P23 — Advanced 2FA (Mobile Push + Hardware Key)

## Objective
Extend the base 2FA gate (P15) with progressive security tiers: Tier 1 (Telegram inline buttons, orders < EUR 5K), Tier 2 (Mobile Push + WebAuthn/FIDO2 biometric, orders EUR 5K-25K), Tier 3 (YubiKey OTP, orders > EUR 25K). Adds WebAuthn credential registration, YubiKey validation, tier routing, escalation logic, and full audit trail.

## Plane Tickets
ROOT-69 (extends ROOT-51)

## Target Repo
`~/dev/tccw-qitp-mcp-2fa`

## Dependencies
P15 (base 2FA gate — Telegram channel, Step Functions `waitForTaskToken`, DynamoDB `qitp_2fa_events`)

## Security Tiers

| Tier | Channel | Order Value | Timeout | Fallback |
|---|---|---|---|---|
| 1 | Telegram inline buttons | < EUR 5,000 | 5 min | Auto-reject |
| 2 | Mobile push + biometric (WebAuthn) | EUR 5,000 - EUR 25,000 | 3 min | Escalate to Tier 3 |
| 3 | YubiKey OTP | > EUR 25,000 | 2 min | Reject (no fallback) |

## Repo Structure
```
tccw-qitp-mcp-2fa/
├── src/
│   └── qitp_mcp_2fa/
│       ├── __init__.py
│       ├── tools/
│       │   ├── __init__.py
│       │   └── approval.py         # Updated: tier routing based on order value
│       ├── channels/
│       │   ├── __init__.py
│       │   ├── base.py             # Abstract ApprovalChannel
│       │   ├── telegram.py         # Tier 1: Telegram (from P15, refactored)
│       │   ├── mobile_push.py      # Tier 2: SNS push + biometric verification
│       │   ├── webauthn.py         # Tier 2: WebAuthn/FIDO2 biometric registration/verification
│       │   └── yubikey.py          # Tier 3: YubiKey OTP validation
│       ├── tier_router.py          # Route approval to correct channel by order value
│       ├── webauthn/
│       │   ├── __init__.py
│       │   ├── registration.py     # WebAuthn credential registration flow
│       │   ├── authentication.py   # WebAuthn assertion verification
│       │   └── credential_store.py # DynamoDB credential storage
│       ├── yubikey/
│       │   ├── __init__.py
│       │   ├── validator.py        # YubiKey OTP validation (Yubico API)
│       │   └── key_registry.py     # Registered YubiKey IDs in DynamoDB
│       ├── webhook/
│       │   ├── __init__.py
│       │   └── handler.py          # API Gateway webhook for WebAuthn/push callbacks
│       └── schemas.py              # ApprovalTier, WebAuthnCredential, YubiKeyDevice, etc.
├── tests/
│   ├── conftest.py
│   ├── test_tier_router.py
│   ├── test_webauthn.py
│   ├── test_yubikey.py
│   └── test_mobile_push.py
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
name = "qitp-mcp-2fa"
version = "0.2.0"
description = "QITP 2FA MCP Server — progressive security tiers for order approval"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0",
    "boto3>=1.34",
    "httpx>=0.27",
    "uvicorn>=0.27",
    "py-webauthn>=2.1.0",
    "cbor2>=5.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "moto[dynamodb,sns]>=5.0",
    "freezegun>=1.4",
    "respx>=0.21",
]

[project.scripts]
2fa-mcp = "qitp_mcp_2fa.server:main"
```

---

### `src/qitp_mcp_2fa/__init__.py`

```python
"""QITP 2FA MCP Server — progressive security tiers."""

__version__ = "0.2.0"
```

---

### `src/qitp_mcp_2fa/schemas.py`

```python
"""Schemas for the advanced 2FA system."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApprovalTier(str, enum.Enum):
    """Security tier levels based on order value."""

    TIER_1 = "tier_1"  # Telegram — < EUR 5,000
    TIER_2 = "tier_2"  # Mobile push + WebAuthn — EUR 5,000-25,000
    TIER_3 = "tier_3"  # YubiKey OTP — > EUR 25,000


class ApprovalStatus(str, enum.Enum):
    """Approval lifecycle states."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"


class ApprovalRequest(BaseModel):
    """Incoming approval request from Step Functions."""

    request_id: str = Field(description="Idempotency key for this approval request")
    task_token: str = Field(description="Step Functions waitForTaskToken callback token")
    order_symbol: str
    order_side: Literal["BUY", "SELL"]
    order_qty: int
    order_price: float
    order_value_eur: float = Field(description="Total order value in EUR for tier routing")
    execution_mode: Literal["paper", "live"] = "live"
    requester_agent: str = Field(description="Agent ID that initiated the order")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ApprovalResponse(BaseModel):
    """Result of an approval attempt."""

    request_id: str
    status: ApprovalStatus
    tier: ApprovalTier
    channel: str  # "telegram" | "mobile_push" | "yubikey"
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    escalated_from: ApprovalTier | None = None
    escalation_reason: str | None = None
    credential_id: str | None = None  # WebAuthn credential or YubiKey ID used
    user_agent: str | None = None  # Browser/device info for WebAuthn


class TierConfig(BaseModel):
    """Configuration for a single security tier."""

    tier: ApprovalTier
    min_value_eur: float
    max_value_eur: float | None  # None = no upper bound
    timeout_seconds: int
    fallback_tier: ApprovalTier | None  # None = reject on timeout


class WebAuthnCredential(BaseModel):
    """Stored WebAuthn/FIDO2 credential."""

    credential_id: str = Field(description="Base64url-encoded credential ID")
    user_id: str = Field(description="QITP user ID")
    public_key: str = Field(description="Base64url-encoded COSE public key")
    sign_count: int = Field(default=0, description="Signature counter for clone detection")
    aaguid: str | None = Field(default=None, description="Authenticator AAGUID")
    device_name: str = Field(default="Unknown device")
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    active: bool = True


class YubiKeyDevice(BaseModel):
    """Registered YubiKey device."""

    device_id: str = Field(description="YubiKey public ID (first 12 chars of OTP)")
    user_id: str = Field(description="QITP user ID")
    serial_number: str | None = None
    device_name: str = Field(default="YubiKey")
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    active: bool = True


class WebAuthnChallenge(BaseModel):
    """Transient WebAuthn challenge for registration or authentication."""

    challenge_id: str
    challenge: str = Field(description="Base64url-encoded challenge bytes")
    request_id: str = Field(description="Linked approval request ID")
    purpose: Literal["registration", "authentication"]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    consumed: bool = False


class TwoFAEvent(BaseModel):
    """Audit log entry for the qitp_2fa_events table."""

    event_id: str
    request_id: str
    event_type: str  # "approval_requested", "tier_routed", "challenge_sent", "approved", "rejected", "escalated", "timed_out"
    tier: ApprovalTier
    channel: str
    details: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

---

### `src/qitp_mcp_2fa/tier_router.py`

```python
"""Tier routing logic — determines which security tier and channel to use."""

from __future__ import annotations

import logging
import os

from qitp_mcp_2fa.schemas import ApprovalTier, TierConfig

logger = logging.getLogger(__name__)

# Default tier boundaries — overridable via env vars
_DEFAULT_TIERS: list[TierConfig] = [
    TierConfig(
        tier=ApprovalTier.TIER_1,
        min_value_eur=0.0,
        max_value_eur=5000.0,
        timeout_seconds=300,  # 5 minutes
        fallback_tier=None,  # Auto-reject on timeout
    ),
    TierConfig(
        tier=ApprovalTier.TIER_2,
        min_value_eur=5000.0,
        max_value_eur=25000.0,
        timeout_seconds=180,  # 3 minutes
        fallback_tier=ApprovalTier.TIER_3,  # Escalate to YubiKey
    ),
    TierConfig(
        tier=ApprovalTier.TIER_3,
        min_value_eur=25000.0,
        max_value_eur=None,  # No upper bound
        timeout_seconds=120,  # 2 minutes
        fallback_tier=None,  # Reject on timeout — no further escalation
    ),
]


def get_tier_configs() -> list[TierConfig]:
    """Load tier configs. Uses env var overrides if set, otherwise defaults.

    Env vars:
        TIER_1_MAX_EUR — upper bound for Tier 1 (default 5000)
        TIER_2_MAX_EUR — upper bound for Tier 2 (default 25000)
        TIER_1_TIMEOUT — timeout in seconds for Tier 1 (default 300)
        TIER_2_TIMEOUT — timeout in seconds for Tier 2 (default 180)
        TIER_3_TIMEOUT — timeout in seconds for Tier 3 (default 120)
    """
    tier_1_max = float(os.environ.get("TIER_1_MAX_EUR", "5000"))
    tier_2_max = float(os.environ.get("TIER_2_MAX_EUR", "25000"))
    tier_1_timeout = int(os.environ.get("TIER_1_TIMEOUT", "300"))
    tier_2_timeout = int(os.environ.get("TIER_2_TIMEOUT", "180"))
    tier_3_timeout = int(os.environ.get("TIER_3_TIMEOUT", "120"))

    return [
        TierConfig(
            tier=ApprovalTier.TIER_1,
            min_value_eur=0.0,
            max_value_eur=tier_1_max,
            timeout_seconds=tier_1_timeout,
            fallback_tier=None,
        ),
        TierConfig(
            tier=ApprovalTier.TIER_2,
            min_value_eur=tier_1_max,
            max_value_eur=tier_2_max,
            timeout_seconds=tier_2_timeout,
            fallback_tier=ApprovalTier.TIER_3,
        ),
        TierConfig(
            tier=ApprovalTier.TIER_3,
            min_value_eur=tier_2_max,
            max_value_eur=None,
            timeout_seconds=tier_3_timeout,
            fallback_tier=None,
        ),
    ]


def resolve_tier(order_value_eur: float) -> TierConfig:
    """Determine the security tier for a given order value.

    Args:
        order_value_eur: Total order value in EUR.

    Returns:
        TierConfig for the appropriate tier.

    Raises:
        ValueError: If order value is negative.
    """
    if order_value_eur < 0:
        raise ValueError(f"Order value cannot be negative: {order_value_eur}")

    configs = get_tier_configs()

    for config in configs:
        if config.max_value_eur is None:
            # Tier 3: no upper bound
            if order_value_eur >= config.min_value_eur:
                logger.info(
                    "Order value EUR %.2f -> %s (>= EUR %.2f)",
                    order_value_eur,
                    config.tier.value,
                    config.min_value_eur,
                )
                return config
        else:
            if config.min_value_eur <= order_value_eur < config.max_value_eur:
                logger.info(
                    "Order value EUR %.2f -> %s (EUR %.2f - %.2f)",
                    order_value_eur,
                    config.tier.value,
                    config.min_value_eur,
                    config.max_value_eur,
                )
                return config

    # Should never reach here, but defensive
    logger.warning(
        "No tier matched for EUR %.2f — defaulting to TIER_3", order_value_eur
    )
    return configs[-1]


def get_escalation_target(current_tier: ApprovalTier) -> TierConfig | None:
    """Get the fallback tier config when the current tier times out.

    Returns None if there is no escalation path (reject on timeout).
    """
    configs = get_tier_configs()
    current_config = next(c for c in configs if c.tier == current_tier)

    if current_config.fallback_tier is None:
        return None

    return next(
        (c for c in configs if c.tier == current_config.fallback_tier),
        None,
    )


def tier_to_channel(tier: ApprovalTier) -> str:
    """Map a tier to its primary channel name."""
    mapping = {
        ApprovalTier.TIER_1: "telegram",
        ApprovalTier.TIER_2: "mobile_push",
        ApprovalTier.TIER_3: "yubikey",
    }
    return mapping[tier]
```

---

### `src/qitp_mcp_2fa/channels/__init__.py`

```python
"""Approval channel implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qitp_mcp_2fa.schemas import ApprovalTier

if TYPE_CHECKING:
    from .base import ApprovalChannel


def get_channel(tier: ApprovalTier) -> ApprovalChannel:
    """Return the appropriate approval channel for a given tier.

    Args:
        tier: The security tier that determines which channel to use.

    Returns:
        An ApprovalChannel instance for the specified tier.
    """
    if tier == ApprovalTier.TIER_1:
        from .telegram import TelegramChannel

        return TelegramChannel()
    elif tier == ApprovalTier.TIER_2:
        from .mobile_push import MobilePushChannel

        return MobilePushChannel()
    elif tier == ApprovalTier.TIER_3:
        from .yubikey import YubiKeyChannel

        return YubiKeyChannel()
    else:
        raise ValueError(f"Unknown tier: {tier}")
```

---

### `src/qitp_mcp_2fa/channels/base.py`

```python
"""Abstract base class for approval channels."""

from __future__ import annotations

from abc import ABC, abstractmethod

from qitp_mcp_2fa.schemas import ApprovalRequest, ApprovalResponse, ApprovalTier


class ApprovalChannel(ABC):
    """Abstract approval channel — all channels implement this interface.

    Each channel handles one security tier's approval flow:
    1. Send a challenge/prompt to the user
    2. Wait for response within the timeout
    3. Return an ApprovalResponse with the result
    """

    @property
    @abstractmethod
    def tier(self) -> ApprovalTier:
        """The security tier this channel handles."""
        ...

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Human-readable channel name for audit logging."""
        ...

    @abstractmethod
    async def send_challenge(self, request: ApprovalRequest) -> str:
        """Send an approval challenge to the user.

        Args:
            request: The approval request details.

        Returns:
            A challenge_id that can be used to match the response.
        """
        ...

    @abstractmethod
    async def await_response(
        self,
        request: ApprovalRequest,
        challenge_id: str,
        timeout_seconds: int,
    ) -> ApprovalResponse:
        """Wait for the user's response to the challenge.

        Args:
            request: The original approval request.
            challenge_id: The challenge ID returned by send_challenge.
            timeout_seconds: Maximum time to wait for a response.

        Returns:
            ApprovalResponse with the result (approved, rejected, or timed_out).
        """
        ...

    @abstractmethod
    async def cancel(self, challenge_id: str) -> None:
        """Cancel an outstanding challenge (e.g., on escalation).

        Args:
            challenge_id: The challenge to cancel.
        """
        ...
```

---

### `src/qitp_mcp_2fa/channels/telegram.py`

```python
"""Tier 1: Telegram inline button approval channel.

Refactored from P15 base implementation. Sends an inline keyboard message
with Approve/Reject buttons. Waits for callback_query via Telegram Bot API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime

import httpx

from qitp_mcp_2fa.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    ApprovalTier,
)

from .base import ApprovalChannel

logger = logging.getLogger(__name__)

# Pending challenges: challenge_id -> asyncio.Future
_pending_challenges: dict[str, asyncio.Future] = {}


class TelegramChannel(ApprovalChannel):
    """Telegram inline button approval for Tier 1 (orders < EUR 5K)."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._http = http_client or httpx.AsyncClient(timeout=30)

    @property
    def tier(self) -> ApprovalTier:
        return ApprovalTier.TIER_1

    @property
    def channel_name(self) -> str:
        return "telegram"

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._bot_token}/{method}"

    def _format_message(self, request: ApprovalRequest) -> str:
        """Format the order approval message."""
        return (
            f"🔐 *Order Approval Required*\n\n"
            f"*Symbol*: `{request.order_symbol}`\n"
            f"*Side*: {request.order_side}\n"
            f"*Qty*: {request.order_qty}\n"
            f"*Price*: EUR {request.order_price:.2f}\n"
            f"*Total Value*: EUR {request.order_value_eur:.2f}\n"
            f"*Mode*: {request.execution_mode}\n"
            f"*Agent*: {request.requester_agent}\n"
            f"*Tier*: 1 (Telegram)\n\n"
            f"ID: `{request.request_id}`"
        )

    async def send_challenge(self, request: ApprovalRequest) -> str:
        """Send Telegram message with Approve/Reject inline buttons."""
        challenge_id = str(uuid.uuid4())

        inline_keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ APPROVE",
                        "callback_data": f"approve:{challenge_id}",
                    },
                    {
                        "text": "❌ REJECT",
                        "callback_data": f"reject:{challenge_id}",
                    },
                ]
            ]
        }

        payload = {
            "chat_id": self._chat_id,
            "text": self._format_message(request),
            "parse_mode": "Markdown",
            "reply_markup": inline_keyboard,
        }

        try:
            resp = await self._http.post(
                self._api_url("sendMessage"),
                json=payload,
            )
            resp.raise_for_status()
            logger.info(
                "Telegram challenge sent: challenge_id=%s request_id=%s",
                challenge_id,
                request.request_id,
            )
        except httpx.HTTPError:
            logger.exception("Failed to send Telegram message for %s", request.request_id)
            raise

        # Create a future for the callback
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_challenges[challenge_id] = future

        return challenge_id

    async def await_response(
        self,
        request: ApprovalRequest,
        challenge_id: str,
        timeout_seconds: int,
    ) -> ApprovalResponse:
        """Wait for Telegram callback_query response."""
        future = _pending_challenges.get(challenge_id)
        if future is None:
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.REJECTED,
                tier=ApprovalTier.TIER_1,
                channel="telegram",
                rejected_at=datetime.utcnow(),
            )

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            now = datetime.utcnow()
            if result == "approve":
                return ApprovalResponse(
                    request_id=request.request_id,
                    status=ApprovalStatus.APPROVED,
                    tier=ApprovalTier.TIER_1,
                    channel="telegram",
                    approved_at=now,
                )
            else:
                return ApprovalResponse(
                    request_id=request.request_id,
                    status=ApprovalStatus.REJECTED,
                    tier=ApprovalTier.TIER_1,
                    channel="telegram",
                    rejected_at=now,
                )
        except asyncio.TimeoutError:
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.TIMED_OUT,
                tier=ApprovalTier.TIER_1,
                channel="telegram",
            )
        finally:
            _pending_challenges.pop(challenge_id, None)

    async def cancel(self, challenge_id: str) -> None:
        """Cancel a pending Telegram challenge."""
        future = _pending_challenges.pop(challenge_id, None)
        if future and not future.done():
            future.set_result("cancel")
        logger.info("Telegram challenge cancelled: %s", challenge_id)


def resolve_telegram_callback(challenge_id: str, action: str) -> bool:
    """Called by the webhook handler when a Telegram callback_query arrives.

    Args:
        challenge_id: Extracted from callback_data (e.g., "approve:<id>").
        action: "approve" or "reject".

    Returns:
        True if the challenge was found and resolved, False otherwise.
    """
    future = _pending_challenges.get(challenge_id)
    if future is None or future.done():
        return False
    future.set_result(action)
    return True
```

---

### `src/qitp_mcp_2fa/channels/mobile_push.py`

```python
"""Tier 2: Mobile Push + WebAuthn biometric approval channel.

Flow:
1. Send SNS push notification to the user's mobile device
2. Mobile app opens a WebAuthn biometric prompt (fingerprint / face)
3. WebAuthn assertion is POSTed to the webhook endpoint
4. Webhook validates the assertion and resolves the pending future
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime

import boto3

from qitp_mcp_2fa.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    ApprovalTier,
)

from .base import ApprovalChannel

logger = logging.getLogger(__name__)

# Pending challenges: challenge_id -> asyncio.Future
_pending_push_challenges: dict[str, asyncio.Future] = {}


class MobilePushChannel(ApprovalChannel):
    """Mobile push + WebAuthn biometric for Tier 2 (EUR 5K-25K orders)."""

    def __init__(
        self,
        sns_client=None,
        platform_arn: str | None = None,
        target_arn: str | None = None,
        webhook_base_url: str | None = None,
    ) -> None:
        self._sns = sns_client or boto3.client("sns")
        self._platform_arn = platform_arn or os.environ.get(
            "SNS_PLATFORM_ARN", ""
        )
        self._target_arn = target_arn or os.environ.get(
            "SNS_TARGET_ARN", ""
        )
        self._webhook_base_url = webhook_base_url or os.environ.get(
            "WEBHOOK_BASE_URL", "https://2fa.qitp.example.com"
        )

    @property
    def tier(self) -> ApprovalTier:
        return ApprovalTier.TIER_2

    @property
    def channel_name(self) -> str:
        return "mobile_push"

    def _build_push_payload(
        self, request: ApprovalRequest, challenge_id: str
    ) -> dict:
        """Build the SNS push notification payload.

        The mobile app receives this and presents a WebAuthn biometric prompt.
        On success, it POSTs the assertion to the callback URL.
        """
        callback_url = (
            f"{self._webhook_base_url}/api/v1/2fa/callback/webauthn"
        )

        return {
            "default": f"Order approval required: {request.order_symbol} {request.order_side} EUR {request.order_value_eur:.2f}",
            "GCM": json.dumps(
                {
                    "notification": {
                        "title": "QITP Order Approval",
                        "body": f"{request.order_side} {request.order_qty} {request.order_symbol} @ EUR {request.order_price:.2f}",
                    },
                    "data": {
                        "type": "order_approval",
                        "challenge_id": challenge_id,
                        "request_id": request.request_id,
                        "callback_url": callback_url,
                        "symbol": request.order_symbol,
                        "side": request.order_side,
                        "qty": str(request.order_qty),
                        "price": str(request.order_price),
                        "value_eur": str(request.order_value_eur),
                        "require_biometric": "true",
                    },
                }
            ),
            "APNS": json.dumps(
                {
                    "aps": {
                        "alert": {
                            "title": "QITP Order Approval",
                            "body": f"{request.order_side} {request.order_qty} {request.order_symbol} @ EUR {request.order_price:.2f}",
                        },
                        "sound": "default",
                        "category": "ORDER_APPROVAL",
                    },
                    "challenge_id": challenge_id,
                    "request_id": request.request_id,
                    "callback_url": callback_url,
                    "require_biometric": True,
                }
            ),
        }

    async def send_challenge(self, request: ApprovalRequest) -> str:
        """Send push notification via SNS and register pending challenge."""
        challenge_id = str(uuid.uuid4())

        payload = self._build_push_payload(request, challenge_id)

        try:
            self._sns.publish(
                TargetArn=self._target_arn,
                Message=json.dumps(payload),
                MessageStructure="json",
                Subject="QITP Order Approval",
            )
            logger.info(
                "Push notification sent: challenge_id=%s request_id=%s",
                challenge_id,
                request.request_id,
            )
        except Exception:
            logger.exception(
                "Failed to send push notification for %s", request.request_id
            )
            raise

        # Register pending future
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_push_challenges[challenge_id] = future

        return challenge_id

    async def await_response(
        self,
        request: ApprovalRequest,
        challenge_id: str,
        timeout_seconds: int,
    ) -> ApprovalResponse:
        """Wait for WebAuthn assertion callback from mobile app."""
        future = _pending_push_challenges.get(challenge_id)
        if future is None:
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.REJECTED,
                tier=ApprovalTier.TIER_2,
                channel="mobile_push",
                rejected_at=datetime.utcnow(),
            )

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            now = datetime.utcnow()
            if result.get("verified"):
                return ApprovalResponse(
                    request_id=request.request_id,
                    status=ApprovalStatus.APPROVED,
                    tier=ApprovalTier.TIER_2,
                    channel="mobile_push",
                    approved_at=now,
                    credential_id=result.get("credential_id"),
                    user_agent=result.get("user_agent"),
                )
            else:
                return ApprovalResponse(
                    request_id=request.request_id,
                    status=ApprovalStatus.REJECTED,
                    tier=ApprovalTier.TIER_2,
                    channel="mobile_push",
                    rejected_at=now,
                )
        except asyncio.TimeoutError:
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.TIMED_OUT,
                tier=ApprovalTier.TIER_2,
                channel="mobile_push",
            )
        finally:
            _pending_push_challenges.pop(challenge_id, None)

    async def cancel(self, challenge_id: str) -> None:
        """Cancel a pending push challenge."""
        future = _pending_push_challenges.pop(challenge_id, None)
        if future and not future.done():
            future.set_result({"verified": False, "cancelled": True})
        logger.info("Push challenge cancelled: %s", challenge_id)


def resolve_push_callback(
    challenge_id: str, verified: bool, credential_id: str | None = None, user_agent: str | None = None
) -> bool:
    """Called by the webhook handler when a WebAuthn assertion callback arrives.

    Args:
        challenge_id: The challenge being resolved.
        verified: Whether the WebAuthn assertion was valid.
        credential_id: The credential ID used for authentication.
        user_agent: Browser/device info.

    Returns:
        True if the challenge was found and resolved, False otherwise.
    """
    future = _pending_push_challenges.get(challenge_id)
    if future is None or future.done():
        return False
    future.set_result(
        {
            "verified": verified,
            "credential_id": credential_id,
            "user_agent": user_agent,
        }
    )
    return True
```

---

### `src/qitp_mcp_2fa/channels/webauthn.py`

```python
"""Tier 2 helper: WebAuthn/FIDO2 biometric registration and verification.

Uses py_webauthn for all WebAuthn operations. This module handles:
- Credential registration (new device enrollment)
- Authentication assertion generation and verification
- Integration with DynamoDB credential store
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime

from webauthn import generate_authentication_options, generate_registration_options
from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from qitp_mcp_2fa.schemas import WebAuthnCredential
from qitp_mcp_2fa.webauthn.credential_store import CredentialStore

logger = logging.getLogger(__name__)


def _get_rp_id() -> str:
    return os.environ.get("WEBAUTHN_RP_ID", "qitp.example.com")


def _get_rp_name() -> str:
    return os.environ.get("WEBAUTHN_RP_NAME", "QITP Trading Platform")


def _get_origin() -> str:
    return os.environ.get("WEBAUTHN_ORIGIN", "https://qitp.example.com")


class WebAuthnService:
    """Manages WebAuthn registration and authentication flows."""

    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store or CredentialStore()
        self._rp_id = _get_rp_id()
        self._rp_name = _get_rp_name()
        self._origin = _get_origin()

    def generate_registration_options_for_user(
        self, user_id: str, user_name: str
    ) -> dict:
        """Generate WebAuthn registration options for a new credential.

        Args:
            user_id: QITP user ID.
            user_name: Display name.

        Returns:
            Registration options dict to send to the client.
        """
        existing_creds = self._store.get_credentials_for_user(user_id)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(c.credential_id + "==")
            )
            for c in existing_creds
        ]

        options = generate_registration_options(
            rp_id=self._rp_id,
            rp_name=self._rp_name,
            user_id=user_id.encode(),
            user_name=user_name,
            exclude_credentials=exclude_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )

        logger.info("Registration options generated for user %s", user_id)
        return options

    def verify_registration(
        self,
        user_id: str,
        credential_json: dict,
        expected_challenge: bytes,
        device_name: str = "Unknown device",
    ) -> WebAuthnCredential:
        """Verify a registration response and store the credential.

        Args:
            user_id: QITP user ID.
            credential_json: The authenticatorAttestationResponse from the client.
            expected_challenge: The challenge bytes that were issued.
            device_name: Human-readable name for the device.

        Returns:
            The stored WebAuthnCredential.

        Raises:
            Exception: If verification fails.
        """
        verification = verify_registration_response(
            credential=credential_json,
            expected_challenge=expected_challenge,
            expected_rp_id=self._rp_id,
            expected_origin=self._origin,
        )

        credential_id_b64 = base64.urlsafe_b64encode(
            verification.credential_id
        ).rstrip(b"=").decode()

        public_key_b64 = base64.urlsafe_b64encode(
            verification.credential_public_key
        ).rstrip(b"=").decode()

        aaguid_str = str(verification.aaguid) if verification.aaguid else None

        cred = WebAuthnCredential(
            credential_id=credential_id_b64,
            user_id=user_id,
            public_key=public_key_b64,
            sign_count=verification.sign_count,
            aaguid=aaguid_str,
            device_name=device_name,
            registered_at=datetime.utcnow(),
        )

        self._store.save_credential(cred)
        logger.info(
            "WebAuthn credential registered: user=%s device=%s",
            user_id,
            device_name,
        )
        return cred

    def generate_authentication_options_for_user(self, user_id: str) -> dict:
        """Generate WebAuthn authentication options.

        Args:
            user_id: QITP user ID.

        Returns:
            Authentication options dict to send to the client.
        """
        creds = self._store.get_credentials_for_user(user_id)
        if not creds:
            raise ValueError(f"No registered WebAuthn credentials for user {user_id}")

        allow_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(c.credential_id + "==")
            )
            for c in creds
        ]

        options = generate_authentication_options(
            rp_id=self._rp_id,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        logger.info("Authentication options generated for user %s", user_id)
        return options

    def verify_authentication(
        self,
        user_id: str,
        credential_json: dict,
        expected_challenge: bytes,
    ) -> tuple[bool, str | None]:
        """Verify an authentication assertion.

        Args:
            user_id: QITP user ID.
            credential_json: The authenticatorAssertionResponse from the client.
            expected_challenge: The challenge bytes that were issued.

        Returns:
            Tuple of (verified: bool, credential_id: str | None).
        """
        # Find the matching credential
        creds = self._store.get_credentials_for_user(user_id)
        raw_id = credential_json.get("rawId") or credential_json.get("id", "")
        credential_id_b64 = raw_id.rstrip("=")

        matching_cred = next(
            (c for c in creds if c.credential_id == credential_id_b64),
            None,
        )

        if matching_cred is None:
            logger.warning(
                "No matching credential for user %s, credential_id=%s",
                user_id,
                credential_id_b64,
            )
            return False, None

        try:
            public_key_bytes = base64.urlsafe_b64decode(
                matching_cred.public_key + "=="
            )

            verification = verify_authentication_response(
                credential=credential_json,
                expected_challenge=expected_challenge,
                expected_rp_id=self._rp_id,
                expected_origin=self._origin,
                credential_public_key=public_key_bytes,
                credential_current_sign_count=matching_cred.sign_count,
            )

            # Update sign count to prevent cloned authenticator attacks
            self._store.update_sign_count(
                matching_cred.credential_id,
                verification.new_sign_count,
            )

            logger.info(
                "WebAuthn authentication verified: user=%s credential=%s",
                user_id,
                matching_cred.credential_id,
            )
            return True, matching_cred.credential_id

        except Exception:
            logger.exception(
                "WebAuthn authentication failed: user=%s", user_id
            )
            return False, None
```

---

### `src/qitp_mcp_2fa/channels/yubikey.py`

```python
"""Tier 3: YubiKey OTP approval channel.

Validates YubiKey OTP tokens against the Yubico cloud validation API
(or a self-hosted validation server). For orders > EUR 25K.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime

from qitp_mcp_2fa.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    ApprovalTier,
)
from qitp_mcp_2fa.yubikey.validator import YubiKeyValidator
from qitp_mcp_2fa.yubikey.key_registry import KeyRegistry

from .base import ApprovalChannel

logger = logging.getLogger(__name__)

# Pending challenges: challenge_id -> asyncio.Future
_pending_yubikey_challenges: dict[str, asyncio.Future] = {}


class YubiKeyChannel(ApprovalChannel):
    """YubiKey OTP approval for Tier 3 (orders > EUR 25K)."""

    def __init__(
        self,
        validator: YubiKeyValidator | None = None,
        registry: KeyRegistry | None = None,
        webhook_base_url: str | None = None,
    ) -> None:
        self._validator = validator or YubiKeyValidator()
        self._registry = registry or KeyRegistry()
        self._webhook_base_url = webhook_base_url or os.environ.get(
            "WEBHOOK_BASE_URL", "https://2fa.qitp.example.com"
        )

    @property
    def tier(self) -> ApprovalTier:
        return ApprovalTier.TIER_3

    @property
    def channel_name(self) -> str:
        return "yubikey"

    async def send_challenge(self, request: ApprovalRequest) -> str:
        """Register a YubiKey challenge and notify the user.

        The user must touch their YubiKey and submit the OTP via the
        webhook endpoint or Telegram bot within the timeout.
        """
        challenge_id = str(uuid.uuid4())

        # Register the pending future
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_yubikey_challenges[challenge_id] = future

        logger.info(
            "YubiKey challenge issued: challenge_id=%s request_id=%s value=EUR %.2f",
            challenge_id,
            request.request_id,
            request.order_value_eur,
        )

        return challenge_id

    async def await_response(
        self,
        request: ApprovalRequest,
        challenge_id: str,
        timeout_seconds: int,
    ) -> ApprovalResponse:
        """Wait for a YubiKey OTP submission."""
        future = _pending_yubikey_challenges.get(challenge_id)
        if future is None:
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.REJECTED,
                tier=ApprovalTier.TIER_3,
                channel="yubikey",
                rejected_at=datetime.utcnow(),
            )

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            now = datetime.utcnow()
            if result.get("verified"):
                return ApprovalResponse(
                    request_id=request.request_id,
                    status=ApprovalStatus.APPROVED,
                    tier=ApprovalTier.TIER_3,
                    channel="yubikey",
                    approved_at=now,
                    credential_id=result.get("device_id"),
                )
            else:
                return ApprovalResponse(
                    request_id=request.request_id,
                    status=ApprovalStatus.REJECTED,
                    tier=ApprovalTier.TIER_3,
                    channel="yubikey",
                    rejected_at=now,
                )
        except asyncio.TimeoutError:
            return ApprovalResponse(
                request_id=request.request_id,
                status=ApprovalStatus.TIMED_OUT,
                tier=ApprovalTier.TIER_3,
                channel="yubikey",
            )
        finally:
            _pending_yubikey_challenges.pop(challenge_id, None)

    async def cancel(self, challenge_id: str) -> None:
        """Cancel a pending YubiKey challenge."""
        future = _pending_yubikey_challenges.pop(challenge_id, None)
        if future and not future.done():
            future.set_result({"verified": False, "cancelled": True})
        logger.info("YubiKey challenge cancelled: %s", challenge_id)


def resolve_yubikey_callback(
    challenge_id: str, otp: str, user_id: str
) -> bool:
    """Called by the webhook when a YubiKey OTP is submitted.

    Performs synchronous validation — the webhook handler should call this
    and the validation happens inline before resolving the future.

    Args:
        challenge_id: The challenge being resolved.
        otp: The full YubiKey OTP string (44 chars).
        user_id: The QITP user submitting the OTP.

    Returns:
        True if validated and resolved, False otherwise.
    """
    future = _pending_yubikey_challenges.get(challenge_id)
    if future is None or future.done():
        return False

    # Extract device ID (first 12 chars of OTP)
    device_id = otp[:12] if len(otp) >= 12 else ""

    # Validate using the synchronous validator
    validator = YubiKeyValidator()
    registry = KeyRegistry()

    # Check device is registered to this user
    if not registry.is_device_registered(user_id, device_id):
        logger.warning(
            "YubiKey device %s not registered for user %s",
            device_id,
            user_id,
        )
        future.set_result({"verified": False, "reason": "unregistered_device"})
        return True

    # Validate OTP against Yubico API
    is_valid = validator.validate_otp(otp)

    if is_valid:
        registry.update_last_used(device_id)

    future.set_result({"verified": is_valid, "device_id": device_id})
    return True
```

---

### `src/qitp_mcp_2fa/webauthn/__init__.py`

```python
"""WebAuthn/FIDO2 credential management."""
```

---

### `src/qitp_mcp_2fa/webauthn/registration.py`

```python
"""WebAuthn credential registration flow.

Handles the two-step registration process:
1. Generate registration options (challenge) -> send to client
2. Receive and verify attestation response -> store credential
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta

import boto3

from qitp_mcp_2fa.schemas import WebAuthnChallenge, WebAuthnCredential
from qitp_mcp_2fa.channels.webauthn import WebAuthnService
from qitp_mcp_2fa.webauthn.credential_store import CredentialStore

logger = logging.getLogger(__name__)


class RegistrationFlow:
    """Manages the WebAuthn registration flow with transient challenges."""

    def __init__(
        self,
        webauthn_service: WebAuthnService | None = None,
        credential_store: CredentialStore | None = None,
        dynamodb_resource=None,
        challenges_table_name: str | None = None,
    ) -> None:
        self._credential_store = credential_store or CredentialStore()
        self._webauthn = webauthn_service or WebAuthnService(
            credential_store=self._credential_store
        )
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._challenges_table_name = challenges_table_name or os.environ.get(
            "DYNAMODB_CHALLENGES_TABLE", "qitp_2fa_challenges"
        )

    def _get_challenges_table(self):
        return self._dynamodb.Table(self._challenges_table_name)

    def initiate_registration(
        self, user_id: str, user_name: str
    ) -> tuple[dict, str]:
        """Start the registration process.

        Args:
            user_id: QITP user ID.
            user_name: Display name.

        Returns:
            Tuple of (registration_options_dict, challenge_id).
        """
        options = self._webauthn.generate_registration_options_for_user(
            user_id, user_name
        )

        challenge_id = str(uuid.uuid4())
        challenge_bytes = options.challenge if isinstance(options.challenge, bytes) else options.challenge.encode()

        # Store challenge in DynamoDB with TTL
        now = datetime.utcnow()
        expires = now + timedelta(minutes=5)

        challenge_record = WebAuthnChallenge(
            challenge_id=challenge_id,
            challenge=secrets.token_urlsafe(32),  # Placeholder — real challenge in options
            request_id="registration",
            purpose="registration",
            created_at=now,
            expires_at=expires,
        )

        table = self._get_challenges_table()
        table.put_item(
            Item={
                "challenge_id": challenge_id,
                "user_id": user_id,
                "challenge_bytes": challenge_bytes.hex(),
                "purpose": "registration",
                "created_at": now.isoformat(),
                "expires_at": int(expires.timestamp()),
                "consumed": False,
            }
        )

        logger.info(
            "Registration initiated: user=%s challenge_id=%s", user_id, challenge_id
        )
        return options, challenge_id

    def complete_registration(
        self,
        challenge_id: str,
        credential_json: dict,
        device_name: str = "Unknown device",
    ) -> WebAuthnCredential:
        """Complete registration by verifying the attestation response.

        Args:
            challenge_id: The challenge ID from initiate_registration.
            credential_json: The attestation response from the client.
            device_name: Human-readable device name.

        Returns:
            The stored WebAuthnCredential.

        Raises:
            ValueError: If challenge is expired, consumed, or not found.
        """
        table = self._get_challenges_table()
        resp = table.get_item(Key={"challenge_id": challenge_id})
        item = resp.get("Item")

        if not item:
            raise ValueError(f"Challenge not found: {challenge_id}")

        if item.get("consumed"):
            raise ValueError(f"Challenge already consumed: {challenge_id}")

        user_id = item["user_id"]
        challenge_bytes = bytes.fromhex(item["challenge_bytes"])

        # Mark as consumed
        table.update_item(
            Key={"challenge_id": challenge_id},
            UpdateExpression="SET consumed = :t",
            ExpressionAttributeValues={":t": True},
        )

        # Verify and store
        credential = self._webauthn.verify_registration(
            user_id=user_id,
            credential_json=credential_json,
            expected_challenge=challenge_bytes,
            device_name=device_name,
        )

        logger.info(
            "Registration completed: user=%s device=%s credential=%s",
            user_id,
            device_name,
            credential.credential_id,
        )
        return credential
```

---

### `src/qitp_mcp_2fa/webauthn/authentication.py`

```python
"""WebAuthn authentication (assertion) flow.

Used by the mobile push channel to verify biometric authentication
when the user responds to a push notification.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta

import boto3

from qitp_mcp_2fa.channels.webauthn import WebAuthnService
from qitp_mcp_2fa.webauthn.credential_store import CredentialStore

logger = logging.getLogger(__name__)


class AuthenticationFlow:
    """Manages the WebAuthn authentication (assertion) flow."""

    def __init__(
        self,
        webauthn_service: WebAuthnService | None = None,
        credential_store: CredentialStore | None = None,
        dynamodb_resource=None,
        challenges_table_name: str | None = None,
    ) -> None:
        self._credential_store = credential_store or CredentialStore()
        self._webauthn = webauthn_service or WebAuthnService(
            credential_store=self._credential_store
        )
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._challenges_table_name = challenges_table_name or os.environ.get(
            "DYNAMODB_CHALLENGES_TABLE", "qitp_2fa_challenges"
        )

    def _get_challenges_table(self):
        return self._dynamodb.Table(self._challenges_table_name)

    def initiate_authentication(
        self, user_id: str, request_id: str
    ) -> tuple[dict, str]:
        """Start the authentication process.

        Args:
            user_id: QITP user ID.
            request_id: The approval request ID this authentication is for.

        Returns:
            Tuple of (authentication_options_dict, challenge_id).
        """
        options = self._webauthn.generate_authentication_options_for_user(user_id)

        challenge_id = str(uuid.uuid4())
        challenge_bytes = options.challenge if isinstance(options.challenge, bytes) else options.challenge.encode()

        now = datetime.utcnow()
        expires = now + timedelta(minutes=3)

        table = self._get_challenges_table()
        table.put_item(
            Item={
                "challenge_id": challenge_id,
                "user_id": user_id,
                "request_id": request_id,
                "challenge_bytes": challenge_bytes.hex(),
                "purpose": "authentication",
                "created_at": now.isoformat(),
                "expires_at": int(expires.timestamp()),
                "consumed": False,
            }
        )

        logger.info(
            "Authentication initiated: user=%s request=%s challenge_id=%s",
            user_id,
            request_id,
            challenge_id,
        )
        return options, challenge_id

    def complete_authentication(
        self, challenge_id: str, credential_json: dict
    ) -> tuple[bool, str | None, str | None]:
        """Complete authentication by verifying the assertion response.

        Args:
            challenge_id: The challenge ID from initiate_authentication.
            credential_json: The assertion response from the client.

        Returns:
            Tuple of (verified: bool, credential_id: str | None, request_id: str | None).

        Raises:
            ValueError: If challenge not found or already consumed.
        """
        table = self._get_challenges_table()
        resp = table.get_item(Key={"challenge_id": challenge_id})
        item = resp.get("Item")

        if not item:
            raise ValueError(f"Challenge not found: {challenge_id}")

        if item.get("consumed"):
            raise ValueError(f"Challenge already consumed: {challenge_id}")

        user_id = item["user_id"]
        request_id = item.get("request_id")
        challenge_bytes = bytes.fromhex(item["challenge_bytes"])

        # Mark as consumed
        table.update_item(
            Key={"challenge_id": challenge_id},
            UpdateExpression="SET consumed = :t",
            ExpressionAttributeValues={":t": True},
        )

        verified, credential_id = self._webauthn.verify_authentication(
            user_id=user_id,
            credential_json=credential_json,
            expected_challenge=challenge_bytes,
        )

        logger.info(
            "Authentication %s: user=%s request=%s",
            "verified" if verified else "failed",
            user_id,
            request_id,
        )
        return verified, credential_id, request_id
```

---

### `src/qitp_mcp_2fa/webauthn/credential_store.py`

```python
"""DynamoDB storage for WebAuthn credentials."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import boto3

from qitp_mcp_2fa.schemas import WebAuthnCredential

logger = logging.getLogger(__name__)


class CredentialStore:
    """Stores and retrieves WebAuthn credentials from DynamoDB.

    Table schema (qitp_2fa_credentials):
        PK: credential_id (S)
        GSI: user_id-index on user_id (S)
    """

    def __init__(
        self,
        dynamodb_resource=None,
        table_name: str | None = None,
    ) -> None:
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table_name = table_name or os.environ.get(
            "DYNAMODB_CREDENTIALS_TABLE", "qitp_2fa_credentials"
        )

    def _get_table(self):
        return self._dynamodb.Table(self._table_name)

    def save_credential(self, credential: WebAuthnCredential) -> None:
        """Store a new WebAuthn credential."""
        table = self._get_table()
        table.put_item(
            Item={
                "credential_id": credential.credential_id,
                "user_id": credential.user_id,
                "public_key": credential.public_key,
                "sign_count": credential.sign_count,
                "aaguid": credential.aaguid or "",
                "device_name": credential.device_name,
                "registered_at": credential.registered_at.isoformat(),
                "last_used_at": credential.last_used_at.isoformat() if credential.last_used_at else "",
                "active": credential.active,
                "credential_type": "webauthn",
            }
        )
        logger.info(
            "Credential saved: credential_id=%s user=%s device=%s",
            credential.credential_id,
            credential.user_id,
            credential.device_name,
        )

    def get_credential(self, credential_id: str) -> WebAuthnCredential | None:
        """Get a single credential by ID."""
        table = self._get_table()
        resp = table.get_item(Key={"credential_id": credential_id})
        item = resp.get("Item")
        if not item:
            return None
        return self._item_to_credential(item)

    def get_credentials_for_user(self, user_id: str) -> list[WebAuthnCredential]:
        """Get all active credentials for a user."""
        table = self._get_table()
        resp = table.query(
            IndexName="user_id-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(user_id),
        )
        return [
            self._item_to_credential(item)
            for item in resp.get("Items", [])
            if item.get("active", True)
        ]

    def update_sign_count(self, credential_id: str, new_sign_count: int) -> None:
        """Update the sign count after a successful authentication."""
        table = self._get_table()
        table.update_item(
            Key={"credential_id": credential_id},
            UpdateExpression="SET sign_count = :sc, last_used_at = :ts",
            ExpressionAttributeValues={
                ":sc": new_sign_count,
                ":ts": datetime.utcnow().isoformat(),
            },
        )

    def deactivate_credential(self, credential_id: str) -> None:
        """Deactivate a credential (soft delete)."""
        table = self._get_table()
        table.update_item(
            Key={"credential_id": credential_id},
            UpdateExpression="SET active = :f",
            ExpressionAttributeValues={":f": False},
        )
        logger.info("Credential deactivated: %s", credential_id)

    @staticmethod
    def _item_to_credential(item: dict) -> WebAuthnCredential:
        """Convert a DynamoDB item to a WebAuthnCredential."""
        last_used = item.get("last_used_at")
        return WebAuthnCredential(
            credential_id=item["credential_id"],
            user_id=item["user_id"],
            public_key=item["public_key"],
            sign_count=int(item.get("sign_count", 0)),
            aaguid=item.get("aaguid") or None,
            device_name=item.get("device_name", "Unknown"),
            registered_at=datetime.fromisoformat(item["registered_at"]),
            last_used_at=datetime.fromisoformat(last_used) if last_used else None,
            active=item.get("active", True),
        )
```

---

### `src/qitp_mcp_2fa/yubikey/__init__.py`

```python
"""YubiKey OTP validation and device management."""
```

---

### `src/qitp_mcp_2fa/yubikey/validator.py`

```python
"""YubiKey OTP validation against Yubico cloud API.

Supports both:
- Yubico Cloud Validation (api.yubico.com) — default
- Self-hosted validation server — via YUBIKEY_VALIDATION_URL env var
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import logging
import os
import re
import time
import uuid

import httpx

logger = logging.getLogger(__name__)

# YubiKey OTP format: 12-char public ID prefix + 32-char encrypted token = 44 chars
_OTP_PATTERN = re.compile(r"^[cbdefghijklnrtuv]{44}$")

# Yubico API servers (round-robin)
_YUBICO_API_URLS = [
    "https://api.yubico.com/wsapi/2.0/verify",
    "https://api2.yubico.com/wsapi/2.0/verify",
    "https://api3.yubico.com/wsapi/2.0/verify",
    "https://api4.yubico.com/wsapi/2.0/verify",
    "https://api5.yubico.com/wsapi/2.0/verify",
]


class YubiKeyValidator:
    """Validates YubiKey OTP tokens against the Yubico cloud API."""

    def __init__(
        self,
        client_id: str | None = None,
        secret_key: str | None = None,
        validation_url: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("YUBIKEY_CLIENT_ID", "")
        self._secret_key = secret_key or os.environ.get("YUBIKEY_SECRET_KEY", "")
        self._validation_url = validation_url or os.environ.get(
            "YUBIKEY_VALIDATION_URL", ""
        )
        self._http = http_client or httpx.Client(timeout=10)

    def validate_otp(self, otp: str) -> bool:
        """Validate a YubiKey OTP string.

        Args:
            otp: The full 44-character YubiKey OTP.

        Returns:
            True if the OTP is valid, False otherwise.
        """
        if not self._is_valid_format(otp):
            logger.warning("Invalid OTP format: length=%d", len(otp))
            return False

        nonce = uuid.uuid4().hex
        params = {
            "id": self._client_id,
            "otp": otp,
            "nonce": nonce,
            "timestamp": "1",
        }

        # Sign the request if we have a secret key
        if self._secret_key:
            params["h"] = self._sign_params(params)

        # Try validation servers
        urls = (
            [self._validation_url]
            if self._validation_url
            else _YUBICO_API_URLS
        )

        for url in urls:
            try:
                resp = self._http.get(url, params=params)
                if resp.status_code == 200:
                    result = self._parse_response(resp.text)
                    if result.get("nonce") != nonce:
                        logger.warning("Nonce mismatch in YubiKey validation response")
                        continue
                    status = result.get("status", "")
                    if status == "OK":
                        logger.info("YubiKey OTP validated: device=%s", otp[:12])
                        return True
                    elif status == "REPLAYED_OTP":
                        logger.warning("Replayed YubiKey OTP detected: device=%s", otp[:12])
                        return False
                    else:
                        logger.warning("YubiKey validation status: %s", status)
                        return False
            except httpx.HTTPError:
                logger.debug("YubiKey API %s unreachable, trying next", url)
                continue

        logger.error("All YubiKey validation servers unreachable")
        return False

    def extract_device_id(self, otp: str) -> str:
        """Extract the public device ID from an OTP (first 12 characters)."""
        return otp[:12] if len(otp) >= 12 else ""

    @staticmethod
    def _is_valid_format(otp: str) -> bool:
        """Check if the OTP matches the expected YubiKey modhex format."""
        return bool(_OTP_PATTERN.match(otp))

    def _sign_params(self, params: dict) -> str:
        """HMAC-SHA1 sign the request parameters."""
        # Sort parameters alphabetically, exclude 'h'
        sorted_params = "&".join(
            f"{k}={v}" for k, v in sorted(params.items()) if k != "h"
        )
        secret_bytes = base64.b64decode(self._secret_key)
        signature = hmac.new(
            secret_bytes, sorted_params.encode(), hashlib.sha1
        ).digest()
        return base64.b64encode(signature).decode()

    @staticmethod
    def _parse_response(text: str) -> dict:
        """Parse the key=value response from the Yubico API."""
        result = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        return result
```

---

### `src/qitp_mcp_2fa/yubikey/key_registry.py`

```python
"""DynamoDB registry for registered YubiKey devices."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import boto3

from qitp_mcp_2fa.schemas import YubiKeyDevice

logger = logging.getLogger(__name__)


class KeyRegistry:
    """Manages registered YubiKey devices in DynamoDB.

    Table schema (qitp_2fa_yubikeys):
        PK: device_id (S) — first 12 chars of OTP
        GSI: user_id-index on user_id (S)
    """

    def __init__(
        self,
        dynamodb_resource=None,
        table_name: str | None = None,
    ) -> None:
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table_name = table_name or os.environ.get(
            "DYNAMODB_YUBIKEYS_TABLE", "qitp_2fa_yubikeys"
        )

    def _get_table(self):
        return self._dynamodb.Table(self._table_name)

    def register_device(
        self,
        user_id: str,
        device_id: str,
        serial_number: str | None = None,
        device_name: str = "YubiKey",
    ) -> YubiKeyDevice:
        """Register a new YubiKey device for a user.

        Args:
            user_id: QITP user ID.
            device_id: YubiKey public ID (first 12 chars of OTP).
            serial_number: Optional serial number.
            device_name: Human-readable name.

        Returns:
            The registered YubiKeyDevice.
        """
        device = YubiKeyDevice(
            device_id=device_id,
            user_id=user_id,
            serial_number=serial_number,
            device_name=device_name,
            registered_at=datetime.utcnow(),
        )

        table = self._get_table()
        table.put_item(
            Item={
                "device_id": device.device_id,
                "user_id": device.user_id,
                "serial_number": device.serial_number or "",
                "device_name": device.device_name,
                "registered_at": device.registered_at.isoformat(),
                "last_used_at": "",
                "active": True,
            },
            ConditionExpression="attribute_not_exists(device_id)",
        )

        logger.info(
            "YubiKey registered: device_id=%s user=%s name=%s",
            device_id,
            user_id,
            device_name,
        )
        return device

    def is_device_registered(self, user_id: str, device_id: str) -> bool:
        """Check if a device is registered and active for a user."""
        table = self._get_table()
        resp = table.get_item(Key={"device_id": device_id})
        item = resp.get("Item")
        if not item:
            return False
        return item.get("user_id") == user_id and item.get("active", False)

    def get_devices_for_user(self, user_id: str) -> list[YubiKeyDevice]:
        """Get all active YubiKey devices for a user."""
        table = self._get_table()
        resp = table.query(
            IndexName="user_id-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(user_id),
        )
        return [
            self._item_to_device(item)
            for item in resp.get("Items", [])
            if item.get("active", True)
        ]

    def update_last_used(self, device_id: str) -> None:
        """Update the last_used_at timestamp for a device."""
        table = self._get_table()
        table.update_item(
            Key={"device_id": device_id},
            UpdateExpression="SET last_used_at = :ts",
            ExpressionAttributeValues={":ts": datetime.utcnow().isoformat()},
        )

    def deactivate_device(self, device_id: str) -> None:
        """Deactivate a YubiKey device (soft delete)."""
        table = self._get_table()
        table.update_item(
            Key={"device_id": device_id},
            UpdateExpression="SET active = :f",
            ExpressionAttributeValues={":f": False},
        )
        logger.info("YubiKey deactivated: %s", device_id)

    @staticmethod
    def _item_to_device(item: dict) -> YubiKeyDevice:
        """Convert a DynamoDB item to a YubiKeyDevice."""
        last_used = item.get("last_used_at")
        return YubiKeyDevice(
            device_id=item["device_id"],
            user_id=item["user_id"],
            serial_number=item.get("serial_number") or None,
            device_name=item.get("device_name", "YubiKey"),
            registered_at=datetime.fromisoformat(item["registered_at"]),
            last_used_at=datetime.fromisoformat(last_used) if last_used else None,
            active=item.get("active", True),
        )
```

---

### `src/qitp_mcp_2fa/webhook/__init__.py`

```python
"""Webhook handlers for 2FA callbacks."""
```

---

### `src/qitp_mcp_2fa/webhook/handler.py`

```python
"""API Gateway webhook handler for WebAuthn and YubiKey callbacks.

Deployed as a Lambda function behind API Gateway. Receives:
- POST /api/v1/2fa/callback/webauthn — WebAuthn assertion from mobile app
- POST /api/v1/2fa/callback/yubikey  — YubiKey OTP submission
- POST /api/v1/2fa/register/webauthn/initiate — Start WebAuthn registration
- POST /api/v1/2fa/register/webauthn/complete — Complete WebAuthn registration
- POST /api/v1/2fa/register/yubikey — Register a new YubiKey
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

import boto3

from qitp_mcp_2fa.channels.mobile_push import resolve_push_callback
from qitp_mcp_2fa.channels.yubikey import resolve_yubikey_callback
from qitp_mcp_2fa.webauthn.authentication import AuthenticationFlow
from qitp_mcp_2fa.webauthn.registration import RegistrationFlow
from qitp_mcp_2fa.yubikey.key_registry import KeyRegistry

logger = logging.getLogger(__name__)


def _audit_event(
    request_id: str,
    event_type: str,
    channel: str,
    details: dict | None = None,
) -> None:
    """Write an audit event to qitp_2fa_events DynamoDB table."""
    table_name = os.environ.get("DYNAMODB_2FA_EVENTS_TABLE", "qitp_2fa_events")
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)
        table.put_item(
            Item={
                "event_id": str(uuid.uuid4()),
                "request_id": request_id,
                "event_type": event_type,
                "channel": channel,
                "details": details or {},
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    except Exception:
        logger.exception("Failed to write audit event: %s", event_type)


def lambda_handler(event: dict, context) -> dict:
    """API Gateway Lambda handler for 2FA webhooks.

    Routes based on the resource path.
    """
    path = event.get("path", "") or event.get("rawPath", "")
    method = event.get("httpMethod", "") or event.get("requestContext", {}).get("http", {}).get("method", "")
    body = event.get("body", "")

    if isinstance(body, str) and body:
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON body"})

    if not isinstance(body, dict):
        body = {}

    logger.info("Webhook request: %s %s", method, path)

    if path.endswith("/callback/webauthn") and method == "POST":
        return _handle_webauthn_callback(body)
    elif path.endswith("/callback/yubikey") and method == "POST":
        return _handle_yubikey_callback(body)
    elif path.endswith("/register/webauthn/initiate") and method == "POST":
        return _handle_webauthn_register_initiate(body)
    elif path.endswith("/register/webauthn/complete") and method == "POST":
        return _handle_webauthn_register_complete(body)
    elif path.endswith("/register/yubikey") and method == "POST":
        return _handle_yubikey_register(body)
    else:
        return _response(404, {"error": f"Not found: {method} {path}"})


def _handle_webauthn_callback(body: dict) -> dict:
    """Handle WebAuthn assertion callback from mobile app."""
    challenge_id = body.get("challenge_id")
    credential_json = body.get("credential")
    user_agent = body.get("user_agent")

    if not challenge_id or not credential_json:
        return _response(400, {"error": "Missing challenge_id or credential"})

    # Verify the assertion
    auth_flow = AuthenticationFlow()
    try:
        verified, credential_id, request_id = auth_flow.complete_authentication(
            challenge_id=challenge_id,
            credential_json=credential_json,
        )
    except ValueError as e:
        return _response(400, {"error": str(e)})

    # Resolve the pending push challenge
    resolved = resolve_push_callback(
        challenge_id=challenge_id,
        verified=verified,
        credential_id=credential_id,
        user_agent=user_agent,
    )

    _audit_event(
        request_id=request_id or challenge_id,
        event_type="webauthn_callback",
        channel="mobile_push",
        details={
            "verified": verified,
            "credential_id": credential_id,
            "resolved": resolved,
        },
    )

    return _response(200, {"verified": verified, "resolved": resolved})


def _handle_yubikey_callback(body: dict) -> dict:
    """Handle YubiKey OTP submission."""
    challenge_id = body.get("challenge_id")
    otp = body.get("otp")
    user_id = body.get("user_id")

    if not challenge_id or not otp or not user_id:
        return _response(400, {"error": "Missing challenge_id, otp, or user_id"})

    resolved = resolve_yubikey_callback(
        challenge_id=challenge_id,
        otp=otp,
        user_id=user_id,
    )

    _audit_event(
        request_id=challenge_id,
        event_type="yubikey_callback",
        channel="yubikey",
        details={
            "device_id": otp[:12] if len(otp) >= 12 else "",
            "resolved": resolved,
        },
    )

    return _response(200, {"resolved": resolved})


def _handle_webauthn_register_initiate(body: dict) -> dict:
    """Start WebAuthn credential registration."""
    user_id = body.get("user_id")
    user_name = body.get("user_name", user_id)

    if not user_id:
        return _response(400, {"error": "Missing user_id"})

    flow = RegistrationFlow()
    options, challenge_id = flow.initiate_registration(user_id, user_name)

    _audit_event(
        request_id=challenge_id,
        event_type="webauthn_registration_initiated",
        channel="webauthn",
        details={"user_id": user_id},
    )

    # Serialize options for JSON response
    # py_webauthn returns dataclass — convert to dict
    options_dict = options if isinstance(options, dict) else _serialize_webauthn_options(options)

    return _response(200, {"challenge_id": challenge_id, "options": options_dict})


def _handle_webauthn_register_complete(body: dict) -> dict:
    """Complete WebAuthn credential registration."""
    challenge_id = body.get("challenge_id")
    credential_json = body.get("credential")
    device_name = body.get("device_name", "Unknown device")

    if not challenge_id or not credential_json:
        return _response(400, {"error": "Missing challenge_id or credential"})

    flow = RegistrationFlow()
    try:
        credential = flow.complete_registration(
            challenge_id=challenge_id,
            credential_json=credential_json,
            device_name=device_name,
        )
    except ValueError as e:
        return _response(400, {"error": str(e)})

    _audit_event(
        request_id=challenge_id,
        event_type="webauthn_registration_completed",
        channel="webauthn",
        details={
            "user_id": credential.user_id,
            "credential_id": credential.credential_id,
            "device_name": device_name,
        },
    )

    return _response(200, {
        "credential_id": credential.credential_id,
        "device_name": credential.device_name,
        "registered_at": credential.registered_at.isoformat(),
    })


def _handle_yubikey_register(body: dict) -> dict:
    """Register a new YubiKey device."""
    user_id = body.get("user_id")
    otp = body.get("otp")
    device_name = body.get("device_name", "YubiKey")
    serial_number = body.get("serial_number")

    if not user_id or not otp:
        return _response(400, {"error": "Missing user_id or otp"})

    device_id = otp[:12] if len(otp) >= 12 else ""
    if not device_id:
        return _response(400, {"error": "Invalid OTP — cannot extract device ID"})

    registry = KeyRegistry()
    try:
        device = registry.register_device(
            user_id=user_id,
            device_id=device_id,
            serial_number=serial_number,
            device_name=device_name,
        )
    except Exception as e:
        return _response(400, {"error": str(e)})

    _audit_event(
        request_id=device_id,
        event_type="yubikey_registration",
        channel="yubikey",
        details={
            "user_id": user_id,
            "device_id": device_id,
            "device_name": device_name,
        },
    )

    return _response(200, {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "registered_at": device.registered_at.isoformat(),
    })


def _serialize_webauthn_options(options) -> dict:
    """Best-effort serialization of py_webauthn option objects."""
    if hasattr(options, "__dict__"):
        return {k: str(v) for k, v in options.__dict__.items()}
    return str(options)


def _response(status_code: int, body: dict) -> dict:
    """Build an API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
```

---

### `src/qitp_mcp_2fa/tools/__init__.py`

```python
"""MCP tools for the 2FA server."""
```

---

### `src/qitp_mcp_2fa/tools/approval.py`

```python
"""MCP tool: request_order_approval — tier-routed approval with escalation.

This is the primary tool invoked by Step Functions via the 2FA MCP server.
It determines the security tier, routes to the correct channel, handles
timeouts and escalation, and sends the callback to Step Functions.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

import boto3

from qitp_mcp_2fa.channels import get_channel
from qitp_mcp_2fa.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    ApprovalTier,
    TwoFAEvent,
)
from qitp_mcp_2fa.tier_router import (
    get_escalation_target,
    resolve_tier,
    tier_to_channel,
)

logger = logging.getLogger(__name__)


def _get_sfn_client():
    return boto3.client("stepfunctions")


def _get_events_table():
    table_name = os.environ.get("DYNAMODB_2FA_EVENTS_TABLE", "qitp_2fa_events")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def _log_event(
    request_id: str,
    event_type: str,
    tier: ApprovalTier,
    channel: str,
    details: dict | None = None,
) -> None:
    """Write an audit event to qitp_2fa_events."""
    try:
        table = _get_events_table()
        event = TwoFAEvent(
            event_id=str(uuid.uuid4()),
            request_id=request_id,
            event_type=event_type,
            tier=tier,
            channel=channel,
            details=details or {},
            timestamp=datetime.utcnow(),
        )
        table.put_item(Item=json.loads(event.model_dump_json()))
    except Exception:
        logger.exception("Failed to log 2FA event: %s", event_type)


async def request_order_approval(
    request_id: str,
    task_token: str,
    order_symbol: str,
    order_side: str,
    order_qty: int,
    order_price: float,
    order_value_eur: float,
    execution_mode: str = "live",
    requester_agent: str = "unknown",
) -> dict:
    """MCP tool: Request human approval for an order.

    Routes to the appropriate security tier based on order value,
    handles timeout and escalation, and sends the result back to
    Step Functions via SendTaskSuccess/SendTaskFailure.

    Args:
        request_id: Idempotency key.
        task_token: Step Functions waitForTaskToken callback token.
        order_symbol: Ticker symbol.
        order_side: BUY or SELL.
        order_qty: Quantity.
        order_price: Price per unit.
        order_value_eur: Total value in EUR for tier routing.
        execution_mode: paper or live.
        requester_agent: Agent ID that initiated the order.

    Returns:
        Dict with approval result and tier information.
    """
    request = ApprovalRequest(
        request_id=request_id,
        task_token=task_token,
        order_symbol=order_symbol,
        order_side=order_side,
        order_qty=order_qty,
        order_price=order_price,
        order_value_eur=order_value_eur,
        execution_mode=execution_mode,
        requester_agent=requester_agent,
    )

    # Determine tier
    tier_config = resolve_tier(order_value_eur)
    current_tier = tier_config.tier
    channel_name = tier_to_channel(current_tier)

    _log_event(
        request_id=request_id,
        event_type="approval_requested",
        tier=current_tier,
        channel=channel_name,
        details={
            "order_symbol": order_symbol,
            "order_side": order_side,
            "order_value_eur": order_value_eur,
        },
    )

    logger.info(
        "Approval request: id=%s symbol=%s value=EUR %.2f tier=%s channel=%s",
        request_id,
        order_symbol,
        order_value_eur,
        current_tier.value,
        channel_name,
    )

    # Execute approval with escalation support
    response = await _execute_with_escalation(request, tier_config)

    # Send result to Step Functions
    sfn = _get_sfn_client()
    result_payload = json.loads(response.model_dump_json())

    try:
        if response.status == ApprovalStatus.APPROVED:
            sfn.send_task_success(
                taskToken=task_token,
                output=json.dumps(result_payload),
            )
            logger.info("Task success sent for %s", request_id)
        else:
            sfn.send_task_failure(
                taskToken=task_token,
                error="OrderRejected",
                cause=json.dumps(result_payload),
            )
            logger.info("Task failure sent for %s: %s", request_id, response.status.value)
    except Exception:
        logger.exception("Failed to send SFN callback for %s", request_id)

    _log_event(
        request_id=request_id,
        event_type=response.status.value,
        tier=response.tier,
        channel=response.channel,
        details=result_payload,
    )

    return result_payload


async def _execute_with_escalation(
    request: ApprovalRequest,
    tier_config,
) -> ApprovalResponse:
    """Execute approval on the given tier, escalating on timeout if configured.

    Escalation flow:
    1. Try the primary tier channel
    2. If it times out and has a fallback_tier, cancel and escalate
    3. Escalation tier runs with its own timeout — no further escalation
    """
    channel = get_channel(tier_config.tier)

    _log_event(
        request_id=request.request_id,
        event_type="challenge_sent",
        tier=tier_config.tier,
        channel=channel.channel_name,
        details={"timeout_seconds": tier_config.timeout_seconds},
    )

    challenge_id = await channel.send_challenge(request)
    response = await channel.await_response(
        request, challenge_id, tier_config.timeout_seconds
    )

    # If timed out and there's an escalation target, escalate
    if response.status == ApprovalStatus.TIMED_OUT:
        escalation_target = get_escalation_target(tier_config.tier)

        if escalation_target is not None:
            logger.info(
                "Escalating %s from %s to %s (timeout)",
                request.request_id,
                tier_config.tier.value,
                escalation_target.tier.value,
            )

            await channel.cancel(challenge_id)

            _log_event(
                request_id=request.request_id,
                event_type="escalated",
                tier=escalation_target.tier,
                channel=tier_to_channel(escalation_target.tier),
                details={
                    "escalated_from": tier_config.tier.value,
                    "reason": "timeout",
                },
            )

            # Run escalated tier
            escalated_channel = get_channel(escalation_target.tier)
            escalated_challenge_id = await escalated_channel.send_challenge(request)
            escalated_response = await escalated_channel.await_response(
                request,
                escalated_challenge_id,
                escalation_target.timeout_seconds,
            )

            # Annotate response with escalation info
            escalated_response.escalated_from = tier_config.tier
            escalated_response.escalation_reason = "timeout"
            return escalated_response

    return response
```

---

### `tests/conftest.py`

```python
"""Shared test fixtures for the 2FA advanced tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_dynamodb, mock_sns


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("EXECUTION_MODE", "live")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.setenv("YUBIKEY_CLIENT_ID", "12345")
    monkeypatch.setenv("YUBIKEY_SECRET_KEY", "dGVzdHNlY3JldGtleQ==")  # base64("testsecretkey")
    monkeypatch.setenv("WEBAUTHN_RP_ID", "qitp.example.com")
    monkeypatch.setenv("WEBAUTHN_RP_NAME", "QITP Test")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://qitp.example.com")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://2fa.qitp.example.com")
    monkeypatch.setenv("SNS_TARGET_ARN", "arn:aws:sns:eu-west-1:835618032093:qitp-2fa-push")
    monkeypatch.setenv("DYNAMODB_CREDENTIALS_TABLE", "qitp_2fa_credentials")
    monkeypatch.setenv("DYNAMODB_YUBIKEYS_TABLE", "qitp_2fa_yubikeys")
    monkeypatch.setenv("DYNAMODB_CHALLENGES_TABLE", "qitp_2fa_challenges")
    monkeypatch.setenv("DYNAMODB_2FA_EVENTS_TABLE", "qitp_2fa_events")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def dynamodb_resource():
    """Create mocked DynamoDB resource with required tables."""
    with mock_dynamodb():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")

        # Credentials table
        dynamodb.create_table(
            TableName="qitp_2fa_credentials",
            KeySchema=[{"AttributeName": "credential_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "credential_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user_id-index",
                    "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # YubiKeys table
        dynamodb.create_table(
            TableName="qitp_2fa_yubikeys",
            KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "device_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user_id-index",
                    "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Challenges table
        dynamodb.create_table(
            TableName="qitp_2fa_challenges",
            KeySchema=[{"AttributeName": "challenge_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "challenge_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Events table
        dynamodb.create_table(
            TableName="qitp_2fa_events",
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "event_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield dynamodb


@pytest.fixture
def sns_client():
    """Create mocked SNS client."""
    with mock_sns():
        client = boto3.client("sns", region_name="eu-west-1")
        client.create_platform_application(
            Name="qitp-2fa-push",
            Platform="GCM",
            Attributes={"PlatformCredential": "test"},
        )
        yield client


@pytest.fixture
def sample_approval_request():
    """A sample approval request for testing."""
    from qitp_mcp_2fa.schemas import ApprovalRequest

    return ApprovalRequest(
        request_id="test-req-001",
        task_token="test-task-token-abc123",
        order_symbol="AAPL",
        order_side="BUY",
        order_qty=100,
        order_price=150.0,
        order_value_eur=15000.0,
        execution_mode="live",
        requester_agent="execution_agent",
    )
```

---

### `tests/test_tier_router.py`

```python
"""Tests for tier routing logic."""

from __future__ import annotations

import pytest

from qitp_mcp_2fa.schemas import ApprovalTier
from qitp_mcp_2fa.tier_router import (
    get_escalation_target,
    get_tier_configs,
    resolve_tier,
    tier_to_channel,
)


class TestResolveTier:
    def test_small_order_tier_1(self):
        config = resolve_tier(1000.0)
        assert config.tier == ApprovalTier.TIER_1

    def test_zero_value_tier_1(self):
        config = resolve_tier(0.0)
        assert config.tier == ApprovalTier.TIER_1

    def test_boundary_below_5k_tier_1(self):
        config = resolve_tier(4999.99)
        assert config.tier == ApprovalTier.TIER_1

    def test_exactly_5k_tier_2(self):
        config = resolve_tier(5000.0)
        assert config.tier == ApprovalTier.TIER_2

    def test_mid_range_tier_2(self):
        config = resolve_tier(15000.0)
        assert config.tier == ApprovalTier.TIER_2

    def test_boundary_below_25k_tier_2(self):
        config = resolve_tier(24999.99)
        assert config.tier == ApprovalTier.TIER_2

    def test_exactly_25k_tier_3(self):
        config = resolve_tier(25000.0)
        assert config.tier == ApprovalTier.TIER_3

    def test_large_order_tier_3(self):
        config = resolve_tier(100000.0)
        assert config.tier == ApprovalTier.TIER_3

    def test_very_large_order_tier_3(self):
        config = resolve_tier(1000000.0)
        assert config.tier == ApprovalTier.TIER_3

    def test_negative_value_raises(self):
        with pytest.raises(ValueError, match="negative"):
            resolve_tier(-100.0)


class TestTierTimeouts:
    def test_tier_1_timeout_5min(self):
        config = resolve_tier(1000.0)
        assert config.timeout_seconds == 300

    def test_tier_2_timeout_3min(self):
        config = resolve_tier(10000.0)
        assert config.timeout_seconds == 180

    def test_tier_3_timeout_2min(self):
        config = resolve_tier(50000.0)
        assert config.timeout_seconds == 120


class TestEscalation:
    def test_tier_1_no_escalation(self):
        target = get_escalation_target(ApprovalTier.TIER_1)
        assert target is None

    def test_tier_2_escalates_to_tier_3(self):
        target = get_escalation_target(ApprovalTier.TIER_2)
        assert target is not None
        assert target.tier == ApprovalTier.TIER_3

    def test_tier_3_no_escalation(self):
        target = get_escalation_target(ApprovalTier.TIER_3)
        assert target is None


class TestTierToChannel:
    def test_tier_1_telegram(self):
        assert tier_to_channel(ApprovalTier.TIER_1) == "telegram"

    def test_tier_2_mobile_push(self):
        assert tier_to_channel(ApprovalTier.TIER_2) == "mobile_push"

    def test_tier_3_yubikey(self):
        assert tier_to_channel(ApprovalTier.TIER_3) == "yubikey"


class TestCustomBoundaries:
    def test_custom_tier_1_max(self, monkeypatch):
        monkeypatch.setenv("TIER_1_MAX_EUR", "10000")
        monkeypatch.setenv("TIER_2_MAX_EUR", "50000")
        config = resolve_tier(8000.0)
        assert config.tier == ApprovalTier.TIER_1

    def test_custom_tier_2_max(self, monkeypatch):
        monkeypatch.setenv("TIER_1_MAX_EUR", "10000")
        monkeypatch.setenv("TIER_2_MAX_EUR", "50000")
        config = resolve_tier(30000.0)
        assert config.tier == ApprovalTier.TIER_2

    def test_custom_timeouts(self, monkeypatch):
        monkeypatch.setenv("TIER_1_TIMEOUT", "600")
        monkeypatch.setenv("TIER_2_TIMEOUT", "300")
        monkeypatch.setenv("TIER_3_TIMEOUT", "60")
        configs = get_tier_configs()
        assert configs[0].timeout_seconds == 600
        assert configs[1].timeout_seconds == 300
        assert configs[2].timeout_seconds == 60
```

---

### `tests/test_webauthn.py`

```python
"""Tests for WebAuthn credential store and registration/authentication flows."""

from __future__ import annotations

from datetime import datetime

import pytest

from qitp_mcp_2fa.schemas import WebAuthnCredential
from qitp_mcp_2fa.webauthn.credential_store import CredentialStore


class TestCredentialStore:
    def test_save_and_retrieve(self, dynamodb_resource):
        store = CredentialStore(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_credentials",
        )

        cred = WebAuthnCredential(
            credential_id="test-cred-id-123",
            user_id="user-001",
            public_key="test-public-key-base64",
            sign_count=0,
            aaguid="test-aaguid",
            device_name="Test MacBook",
            registered_at=datetime(2025, 1, 15, 12, 0, 0),
        )

        store.save_credential(cred)
        retrieved = store.get_credential("test-cred-id-123")

        assert retrieved is not None
        assert retrieved.credential_id == "test-cred-id-123"
        assert retrieved.user_id == "user-001"
        assert retrieved.public_key == "test-public-key-base64"
        assert retrieved.device_name == "Test MacBook"
        assert retrieved.sign_count == 0
        assert retrieved.active is True

    def test_get_credentials_for_user(self, dynamodb_resource):
        store = CredentialStore(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_credentials",
        )

        for i in range(3):
            cred = WebAuthnCredential(
                credential_id=f"cred-{i}",
                user_id="user-001",
                public_key=f"key-{i}",
                device_name=f"Device {i}",
                registered_at=datetime(2025, 1, 15, 12, 0, 0),
            )
            store.save_credential(cred)

        # Add one for a different user
        store.save_credential(
            WebAuthnCredential(
                credential_id="cred-other",
                user_id="user-002",
                public_key="key-other",
                device_name="Other Device",
                registered_at=datetime(2025, 1, 15, 12, 0, 0),
            )
        )

        creds = store.get_credentials_for_user("user-001")
        assert len(creds) == 3
        assert all(c.user_id == "user-001" for c in creds)

    def test_update_sign_count(self, dynamodb_resource):
        store = CredentialStore(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_credentials",
        )

        cred = WebAuthnCredential(
            credential_id="cred-sc",
            user_id="user-001",
            public_key="key-sc",
            sign_count=5,
            device_name="Test",
            registered_at=datetime(2025, 1, 15, 12, 0, 0),
        )
        store.save_credential(cred)
        store.update_sign_count("cred-sc", 10)

        updated = store.get_credential("cred-sc")
        assert updated is not None
        assert updated.sign_count == 10
        assert updated.last_used_at is not None

    def test_deactivate_credential(self, dynamodb_resource):
        store = CredentialStore(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_credentials",
        )

        cred = WebAuthnCredential(
            credential_id="cred-deactivate",
            user_id="user-001",
            public_key="key-deactivate",
            device_name="To Remove",
            registered_at=datetime(2025, 1, 15, 12, 0, 0),
        )
        store.save_credential(cred)
        store.deactivate_credential("cred-deactivate")

        # Direct get still returns it
        direct = store.get_credential("cred-deactivate")
        assert direct is not None
        assert direct.active is False

        # But get_credentials_for_user filters it out
        creds = store.get_credentials_for_user("user-001")
        assert len(creds) == 0

    def test_nonexistent_credential_returns_none(self, dynamodb_resource):
        store = CredentialStore(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_credentials",
        )
        assert store.get_credential("does-not-exist") is None
```

---

### `tests/test_yubikey.py`

```python
"""Tests for YubiKey validation and key registry."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from qitp_mcp_2fa.schemas import YubiKeyDevice
from qitp_mcp_2fa.yubikey.key_registry import KeyRegistry
from qitp_mcp_2fa.yubikey.validator import YubiKeyValidator


# A valid-format modhex OTP (44 chars of modhex alphabet)
SAMPLE_OTP = "ccccccbcgujhingjrdejhgfnuetrgigvejhhgbkugded"
SAMPLE_DEVICE_ID = "ccccccbcgujh"


class TestYubiKeyValidator:
    def test_valid_format(self):
        validator = YubiKeyValidator()
        assert validator._is_valid_format(SAMPLE_OTP) is True

    def test_invalid_format_too_short(self):
        validator = YubiKeyValidator()
        assert validator._is_valid_format("ccccccbcgujh") is False

    def test_invalid_format_wrong_chars(self):
        validator = YubiKeyValidator()
        assert validator._is_valid_format("a" * 44) is False  # 'a' not in modhex

    def test_extract_device_id(self):
        validator = YubiKeyValidator()
        assert validator.extract_device_id(SAMPLE_OTP) == SAMPLE_DEVICE_ID

    def test_extract_device_id_short_otp(self):
        validator = YubiKeyValidator()
        assert validator.extract_device_id("short") == ""

    def test_validate_otp_success(self):
        """Test successful OTP validation with mocked HTTP."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            "h=test\n"
            "t=2025-01-15T12:00:00\n"
            f"otp={SAMPLE_OTP}\n"
            "nonce=placeholder\n"
            "status=OK\n"
        )

        mock_http = MagicMock()
        mock_http.get.return_value = mock_response

        validator = YubiKeyValidator(
            client_id="12345",
            secret_key="",  # Skip signing for test
            validation_url="https://test.yubico.com/verify",
            http_client=mock_http,
        )

        # Patch the nonce to match
        with patch("qitp_mcp_2fa.yubikey.validator.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = MagicMock(hex="placeholder")
            result = validator.validate_otp(SAMPLE_OTP)

        assert result is True

    def test_validate_otp_replayed(self):
        """Test replayed OTP detection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            "h=test\n"
            f"otp={SAMPLE_OTP}\n"
            "nonce=placeholder\n"
            "status=REPLAYED_OTP\n"
        )

        mock_http = MagicMock()
        mock_http.get.return_value = mock_response

        validator = YubiKeyValidator(
            client_id="12345",
            secret_key="",
            validation_url="https://test.yubico.com/verify",
            http_client=mock_http,
        )

        with patch("qitp_mcp_2fa.yubikey.validator.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = MagicMock(hex="placeholder")
            result = validator.validate_otp(SAMPLE_OTP)

        assert result is False

    def test_validate_invalid_format_returns_false(self):
        validator = YubiKeyValidator()
        assert validator.validate_otp("tooshort") is False


class TestKeyRegistry:
    def test_register_device(self, dynamodb_resource):
        registry = KeyRegistry(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_yubikeys",
        )

        device = registry.register_device(
            user_id="user-001",
            device_id=SAMPLE_DEVICE_ID,
            device_name="My YubiKey 5",
            serial_number="12345678",
        )

        assert device.device_id == SAMPLE_DEVICE_ID
        assert device.user_id == "user-001"
        assert device.device_name == "My YubiKey 5"

    def test_is_device_registered(self, dynamodb_resource):
        registry = KeyRegistry(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_yubikeys",
        )

        registry.register_device(
            user_id="user-001",
            device_id=SAMPLE_DEVICE_ID,
        )

        assert registry.is_device_registered("user-001", SAMPLE_DEVICE_ID) is True
        assert registry.is_device_registered("user-002", SAMPLE_DEVICE_ID) is False
        assert registry.is_device_registered("user-001", "unknown") is False

    def test_get_devices_for_user(self, dynamodb_resource):
        registry = KeyRegistry(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_yubikeys",
        )

        registry.register_device(user_id="user-001", device_id="device-aaa")
        registry.register_device(user_id="user-001", device_id="device-bbb")
        registry.register_device(user_id="user-002", device_id="device-ccc")

        devices = registry.get_devices_for_user("user-001")
        assert len(devices) == 2
        assert all(d.user_id == "user-001" for d in devices)

    def test_deactivate_device(self, dynamodb_resource):
        registry = KeyRegistry(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_yubikeys",
        )

        registry.register_device(user_id="user-001", device_id=SAMPLE_DEVICE_ID)
        registry.deactivate_device(SAMPLE_DEVICE_ID)

        assert registry.is_device_registered("user-001", SAMPLE_DEVICE_ID) is False

    def test_update_last_used(self, dynamodb_resource):
        registry = KeyRegistry(
            dynamodb_resource=dynamodb_resource,
            table_name="qitp_2fa_yubikeys",
        )

        registry.register_device(user_id="user-001", device_id=SAMPLE_DEVICE_ID)
        registry.update_last_used(SAMPLE_DEVICE_ID)

        devices = registry.get_devices_for_user("user-001")
        assert len(devices) == 1
        assert devices[0].last_used_at is not None
```

---

### `tests/test_mobile_push.py`

```python
"""Tests for mobile push channel and approval flow."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qitp_mcp_2fa.channels.mobile_push import (
    MobilePushChannel,
    _pending_push_challenges,
    resolve_push_callback,
)
from qitp_mcp_2fa.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalTier,
)


@pytest.fixture
def mock_sns():
    return MagicMock()


@pytest.fixture
def push_channel(mock_sns):
    return MobilePushChannel(
        sns_client=mock_sns,
        target_arn="arn:aws:sns:eu-west-1:835618032093:test-push",
        webhook_base_url="https://test.example.com",
    )


@pytest.fixture
def tier_2_request():
    return ApprovalRequest(
        request_id="push-test-001",
        task_token="push-task-token",
        order_symbol="MSFT",
        order_side="BUY",
        order_qty=50,
        order_price=400.0,
        order_value_eur=20000.0,
        execution_mode="live",
        requester_agent="execution_agent",
    )


class TestMobilePushChannel:
    @pytest.mark.asyncio
    async def test_send_challenge(self, push_channel, tier_2_request, mock_sns):
        challenge_id = await push_channel.send_challenge(tier_2_request)

        assert challenge_id is not None
        assert len(challenge_id) > 0
        mock_sns.publish.assert_called_once()
        assert challenge_id in _pending_push_challenges

        # Clean up
        _pending_push_challenges.pop(challenge_id, None)

    @pytest.mark.asyncio
    async def test_approved_via_callback(self, push_channel, tier_2_request, mock_sns):
        challenge_id = await push_channel.send_challenge(tier_2_request)

        # Simulate async callback resolution
        async def resolve_later():
            await asyncio.sleep(0.05)
            resolve_push_callback(
                challenge_id=challenge_id,
                verified=True,
                credential_id="webauthn-cred-123",
                user_agent="QITP Mobile/1.0",
            )

        asyncio.create_task(resolve_later())

        response = await push_channel.await_response(
            tier_2_request, challenge_id, timeout_seconds=5
        )

        assert response.status == ApprovalStatus.APPROVED
        assert response.tier == ApprovalTier.TIER_2
        assert response.channel == "mobile_push"
        assert response.credential_id == "webauthn-cred-123"
        assert response.user_agent == "QITP Mobile/1.0"

    @pytest.mark.asyncio
    async def test_rejected_via_callback(self, push_channel, tier_2_request, mock_sns):
        challenge_id = await push_channel.send_challenge(tier_2_request)

        async def resolve_later():
            await asyncio.sleep(0.05)
            resolve_push_callback(
                challenge_id=challenge_id,
                verified=False,
            )

        asyncio.create_task(resolve_later())

        response = await push_channel.await_response(
            tier_2_request, challenge_id, timeout_seconds=5
        )

        assert response.status == ApprovalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_timeout(self, push_channel, tier_2_request, mock_sns):
        challenge_id = await push_channel.send_challenge(tier_2_request)

        response = await push_channel.await_response(
            tier_2_request, challenge_id, timeout_seconds=0.1
        )

        assert response.status == ApprovalStatus.TIMED_OUT
        assert response.tier == ApprovalTier.TIER_2

    @pytest.mark.asyncio
    async def test_cancel_challenge(self, push_channel, tier_2_request, mock_sns):
        challenge_id = await push_channel.send_challenge(tier_2_request)

        await push_channel.cancel(challenge_id)

        assert challenge_id not in _pending_push_challenges


class TestResolveCallback:
    @pytest.mark.asyncio
    async def test_resolve_nonexistent_challenge(self):
        result = resolve_push_callback(
            challenge_id="nonexistent",
            verified=True,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_resolve_already_done(self, push_channel, tier_2_request, mock_sns):
        challenge_id = await push_channel.send_challenge(tier_2_request)

        # Resolve once
        resolve_push_callback(challenge_id=challenge_id, verified=True)

        # Try to resolve again
        result = resolve_push_callback(challenge_id=challenge_id, verified=False)
        assert result is False
```

---

### `Dockerfile`

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080
ENV EXECUTION_MODE=live

EXPOSE 8080

ENTRYPOINT ["2fa-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  2fa-mcp:
    build: .
    container_name: qitp-2fa-mcp
    ports:
      - "8007:8080"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8080
      - EXECUTION_MODE=${EXECUTION_MODE:-live}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
      - YUBIKEY_CLIENT_ID=${YUBIKEY_CLIENT_ID:-}
      - YUBIKEY_SECRET_KEY=${YUBIKEY_SECRET_KEY:-}
      - WEBAUTHN_RP_ID=${WEBAUTHN_RP_ID:-qitp.example.com}
      - WEBAUTHN_RP_NAME=${WEBAUTHN_RP_NAME:-QITP Trading Platform}
      - WEBAUTHN_ORIGIN=${WEBAUTHN_ORIGIN:-https://qitp.example.com}
      - WEBHOOK_BASE_URL=${WEBHOOK_BASE_URL:-https://2fa.qitp.example.com}
      - SNS_TARGET_ARN=${SNS_TARGET_ARN:-}
      - DYNAMODB_CREDENTIALS_TABLE=${DYNAMODB_CREDENTIALS_TABLE:-qitp_2fa_credentials}
      - DYNAMODB_YUBIKEYS_TABLE=${DYNAMODB_YUBIKEYS_TABLE:-qitp_2fa_yubikeys}
      - DYNAMODB_CHALLENGES_TABLE=${DYNAMODB_CHALLENGES_TABLE:-qitp_2fa_challenges}
      - DYNAMODB_2FA_EVENTS_TABLE=${DYNAMODB_2FA_EVENTS_TABLE:-qitp_2fa_events}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
    restart: unless-stopped
    networks:
      - qitp

networks:
  qitp:
    driver: bridge
```

---

## DynamoDB Table Schemas

### `qitp_2fa_credentials`

| Attribute | Type | Key |
|---|---|---|
| `credential_id` | S | PK (HASH) |
| `user_id` | S | GSI: `user_id-index` |
| `public_key` | S | |
| `sign_count` | N | |
| `aaguid` | S | |
| `device_name` | S | |
| `registered_at` | S (ISO) | |
| `last_used_at` | S (ISO) | |
| `active` | BOOL | |
| `credential_type` | S | |

### `qitp_2fa_yubikeys`

| Attribute | Type | Key |
|---|---|---|
| `device_id` | S | PK (HASH) |
| `user_id` | S | GSI: `user_id-index` |
| `serial_number` | S | |
| `device_name` | S | |
| `registered_at` | S (ISO) | |
| `last_used_at` | S (ISO) | |
| `active` | BOOL | |

### `qitp_2fa_challenges`

| Attribute | Type | Key |
|---|---|---|
| `challenge_id` | S | PK (HASH) |
| `user_id` | S | |
| `request_id` | S | |
| `challenge_bytes` | S (hex) | |
| `purpose` | S | |
| `created_at` | S (ISO) | |
| `expires_at` | N (epoch) | TTL |
| `consumed` | BOOL | |

---

## Acceptance Criteria

- [ ] Tier routing correctly classifies orders: < EUR 5K -> Tier 1, EUR 5K-25K -> Tier 2, > EUR 25K -> Tier 3
- [ ] Tier boundaries are configurable via environment variables
- [ ] Tier 2 timeout escalates to Tier 3 automatically
- [ ] Tier 1 and Tier 3 timeouts result in rejection (no escalation)
- [ ] WebAuthn credential store supports CRUD operations with DynamoDB
- [ ] YubiKey registry validates device registration and ownership
- [ ] YubiKey OTP format validation rejects malformed tokens
- [ ] Mobile push sends SNS notification with correct payload structure
- [ ] Webhook handler routes to correct callback resolver (WebAuthn vs YubiKey)
- [ ] All approval outcomes (approved, rejected, timed_out, escalated) are audited in `qitp_2fa_events`
- [ ] Step Functions `SendTaskSuccess`/`SendTaskFailure` called on completion
- [ ] All credentials referenced via env vars — no hardcoded secrets
- [ ] Docker build succeeds
- [ ] All tests pass

## Test Plan

```bash
cd ~/dev/tccw-qitp-mcp-2fa
pip install -e ".[dev]"
pytest -v
docker build -t qitp-mcp-2fa .
```

## Agent Instructions

This plan extends the base 2FA gate (P15) with progressive security tiers. P15 must be implemented first — it provides the Telegram channel, DynamoDB event logging, and Step Functions callback patterns that this plan builds on.

Key implementation notes:

1. **Tier routing is the core logic**: The `resolve_tier()` function determines everything. Test boundary conditions exhaustively (exactly EUR 5000, exactly EUR 25000, zero, negative).

2. **Escalation path is Tier 2 -> Tier 3 only**: Tier 1 and Tier 3 have no escalation — they reject on timeout. The escalation logic in `_execute_with_escalation()` must cancel the original challenge before starting the escalated one.

3. **Channel abstraction**: All channels implement the `ApprovalChannel` ABC. This keeps the approval tool clean — it only knows about tiers, not channels. Adding a new channel (e.g., email, SMS) means implementing the ABC and registering in `channels/__init__.py`.

4. **WebAuthn uses py_webauthn**: Do not implement FIDO2 primitives from scratch. The `py_webauthn` library handles all the cryptographic verification. The credential store is the only custom piece.

5. **YubiKey uses Yubico Cloud API**: Validate OTPs via the standard Yubico verification protocol. The `YUBIKEY_CLIENT_ID` and `YUBIKEY_SECRET_KEY` env vars come from https://upgrade.yubico.com/getapikey/. Support self-hosted validation servers via `YUBIKEY_VALIDATION_URL`.

6. **Pending challenges use asyncio.Future**: Each channel maintains an in-memory dict of `challenge_id -> Future`. The webhook handler resolves the future when the user responds. This works in a single-process MCP server. For multi-process deployments, replace with Redis pub/sub or DynamoDB polling.

7. **Audit everything**: Every tier routing decision, challenge sent, timeout, escalation, approval, and rejection must be logged to `qitp_2fa_events`. This is a regulatory requirement (MiFID II).

8. **Credentials via env vars only**: `TELEGRAM_BOT_TOKEN`, `YUBIKEY_CLIENT_ID`, `YUBIKEY_SECRET_KEY`, `SNS_TARGET_ARN` — never hardcode these. In Phase 2, AgentCore Identity will manage these secrets.

9. **Idempotency**: The `request_id` on `ApprovalRequest` is the idempotency key. If the same `request_id` arrives twice (Lambda retry), the system should return the cached result rather than sending duplicate approval prompts.

10. **Refactor P15 Telegram channel**: The base Telegram implementation from P15 should be refactored into the `channels/telegram.py` module with the `ApprovalChannel` ABC. This is a breaking change to the P15 structure but necessary for the tier routing pattern.
