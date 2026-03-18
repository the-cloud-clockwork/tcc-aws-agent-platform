# P15 — 2FA Gate MCP Server

## Objective
Build `2fa-mcp`: an MCP server implementing the 2FA approval gateway for live order execution. Integrates with Step Functions `waitForTaskToken` pattern. Phase 1: Telegram bot with inline approve/reject buttons. Auto-approval in backtest/paper modes. 4 tools covering the full approval lifecycle.

## Plane Tickets
ROOT-51

## Target Repo
`~/dev/tccw-qitp-mcp-2fa`

## Dependencies
P01 (repo scaffold), P12 (orchestration — defines `TwoFactorGate` state with `waitForTaskToken`)

## Repo Structure
```
tccw-qitp-mcp-2fa/
├── src/
│   └── qitp_mcp_2fa/
│       ├── __init__.py
│       ├── server.py           # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   └── approval.py     # request_approval, verify_token, get_approval_status, reject_pending
│       ├── telegram/
│       │   ├── __init__.py
│       │   ├── bot.py          # Telegram bot (python-telegram-bot)
│       │   └── handlers.py     # Inline keyboard callback handlers
│       ├── sfn_integration.py  # Step Functions task token send_task_success/failure
│       ├── token_store.py      # DynamoDB: single-use approval tokens with TTL
│       ├── schemas.py          # ApprovalRequest, ApprovalStatus, ApprovalEvent
│       └── audit.py            # DynamoDB audit logging for every gate event
├── tests/
│   ├── conftest.py
│   ├── test_approval.py
│   ├── test_telegram.py
│   ├── test_sfn_integration.py
│   └── test_token_store.py
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
version = "0.1.0"
description = "QITP 2FA Gate MCP Server — Telegram-based approval gateway for order execution with Step Functions waitForTaskToken integration"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0",
    "boto3>=1.34",
    "python-telegram-bot>=21.0",
    "uvicorn>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "moto[dynamodb,stepfunctions]>=5.0",
]

[project.scripts]
2fa-mcp = "qitp_mcp_2fa.server:main"
```

---

### `src/qitp_mcp_2fa/__init__.py`

```python
"""QITP 2FA Gate MCP Server."""

__version__ = "0.1.0"
```

---

### `src/qitp_mcp_2fa/schemas.py`

```python
"""Shared data schemas for the 2FA gate MCP server."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Possible states of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


class OrderDetails(BaseModel):
    """Order details included in the approval request for display in Telegram."""

    symbol: str
    action: Literal["BUY", "SELL", "SSHORT"]
    quantity: int
    order_type: Literal["MKT", "LMT", "STP", "STP_LMT"]
    limit_price: float | None = None
    stop_price: float | None = None
    trailing_stop_pct: float | None = None
    estimated_cost_usd: float | None = None
    strategy: str | None = None
    rationale: str | None = None


class ApprovalRequest(BaseModel):
    """A 2FA approval request created by the request_approval tool."""

    approval_id: str = Field(description="Unique ID for this approval request (UUID)")
    task_token: str = Field(description="Step Functions task token for callback")
    execution_mode: str = Field(description="Current execution mode: backtest|paper|live")
    order_details: OrderDetails
    status: ApprovalStatus = ApprovalStatus.PENDING
    token: str | None = Field(default=None, description="Single-use approval token")
    telegram_message_id: int | None = Field(default=None, description="Telegram message ID for button callback")
    telegram_chat_id: int | None = Field(default=None, description="Telegram chat ID where approval was sent")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = Field(default=None, description="Auto-reject after this time")
    resolved_at: datetime | None = Field(default=None, description="When approval was approved/rejected")
    resolved_by: str | None = Field(default=None, description="Who approved/rejected (Telegram user ID or 'system')")


class ApprovalEvent(BaseModel):
    """An audit event for the 2FA gate. Every state change is logged."""

    approval_id: str
    event_type: Literal[
        "request_created",
        "telegram_sent",
        "approved",
        "rejected",
        "expired",
        "auto_approved",
        "force_rejected",
        "token_verified",
        "token_invalid",
        "sfn_callback_sent",
        "sfn_callback_failed",
    ]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="system", description="Who triggered this event")


class ApprovalResult(BaseModel):
    """Result returned by request_approval tool."""

    approval_id: str
    status: ApprovalStatus
    auto_approved: bool = False
    message: str = ""
    expires_at: datetime | None = None


class TokenVerifyResult(BaseModel):
    """Result returned by verify_token tool."""

    approval_id: str
    status: ApprovalStatus
    valid: bool
    message: str = ""


class StatusResult(BaseModel):
    """Result returned by get_approval_status tool."""

    approval_id: str
    status: ApprovalStatus
    order_details: OrderDetails
    created_at: datetime
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
```

---

### `src/qitp_mcp_2fa/token_store.py`

```python
"""DynamoDB-backed token store for single-use approval tokens.

Tables:
- qitp_2fa_events: PK=approval_id, SK=event_type#timestamp — audit log
- qitp_2fa_tokens: PK=token_id — single-use tokens with TTL

Approval requests are stored in qitp_2fa_tokens with:
- PK: approval_id
- token: single-use approval token (UUID)
- task_token: Step Functions callback token
- order_details: JSON of OrderDetails
- status: pending|approved|rejected|expired|auto_approved
- ttl: Unix timestamp for DynamoDB TTL auto-cleanup
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from qitp_mcp_2fa.schemas import ApprovalRequest, ApprovalStatus, OrderDetails

logger = logging.getLogger(__name__)

# Table names from environment
TOKENS_TABLE = os.environ.get("DYNAMODB_TOKENS_TABLE", "qitp_2fa_tokens")
EVENTS_TABLE = os.environ.get("DYNAMODB_EVENTS_TABLE", "qitp_2fa_events")

# Approval timeout in seconds (5 minutes default)
APPROVAL_TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "300"))

_dynamodb = None


def _get_dynamodb():
    """Lazy-init DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        endpoint_url = os.environ.get("DYNAMODB_ENDPOINT_URL")
        _dynamodb = boto3.resource("dynamodb", region_name=region, endpoint_url=endpoint_url)
    return _dynamodb


def _override_dynamodb(resource):
    """Override the DynamoDB resource (for testing with moto)."""
    global _dynamodb
    _dynamodb = resource


def _tokens_table():
    return _get_dynamodb().Table(TOKENS_TABLE)


def _events_table():
    return _get_dynamodb().Table(EVENTS_TABLE)


def create_approval_request(
    task_token: str,
    order_details: OrderDetails,
    execution_mode: str,
) -> ApprovalRequest:
    """Create a new approval request in DynamoDB.

    Generates a unique approval_id and single-use token.
    Sets TTL for auto-expiry after APPROVAL_TIMEOUT_SECONDS.

    Returns:
        ApprovalRequest with all fields populated.
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=APPROVAL_TIMEOUT_SECONDS)
    approval_id = str(uuid.uuid4())
    token = str(uuid.uuid4())

    # Determine initial status based on execution mode
    if execution_mode in ("backtest", "paper"):
        status = ApprovalStatus.AUTO_APPROVED
        resolved_at = now
        resolved_by = "system"
    else:
        status = ApprovalStatus.PENDING
        resolved_at = None
        resolved_by = None

    request = ApprovalRequest(
        approval_id=approval_id,
        task_token=task_token,
        execution_mode=execution_mode,
        order_details=order_details,
        status=status,
        token=token,
        created_at=now,
        expires_at=expires_at,
        resolved_at=resolved_at,
        resolved_by=resolved_by,
    )

    # Store in DynamoDB
    item = {
        "approval_id": approval_id,
        "token": token,
        "task_token": task_token,
        "execution_mode": execution_mode,
        "order_details": json.loads(order_details.model_dump_json()),
        "status": status.value,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl": int(expires_at.timestamp()) + 86400,  # Keep record 24h after expiry for audit
        "token_consumed": False,
    }

    if resolved_at is not None:
        item["resolved_at"] = resolved_at.isoformat()
        item["resolved_by"] = resolved_by

    _tokens_table().put_item(Item=item)

    logger.info(
        "Created approval request %s (status=%s, mode=%s, symbol=%s)",
        approval_id,
        status.value,
        execution_mode,
        order_details.symbol,
    )

    return request


def get_approval_request(approval_id: str) -> ApprovalRequest | None:
    """Retrieve an approval request by ID.

    Returns:
        ApprovalRequest if found, None otherwise.
    """
    try:
        resp = _tokens_table().get_item(Key={"approval_id": approval_id})
        item = resp.get("Item")
        if item is None:
            return None
        return _item_to_request(item)
    except ClientError:
        logger.exception("Failed to get approval request %s", approval_id)
        return None


def _item_to_request(item: dict[str, Any]) -> ApprovalRequest:
    """Convert a DynamoDB item to an ApprovalRequest."""
    order_details = OrderDetails(**item["order_details"])

    return ApprovalRequest(
        approval_id=item["approval_id"],
        task_token=item["task_token"],
        execution_mode=item["execution_mode"],
        order_details=order_details,
        status=ApprovalStatus(item["status"]),
        token=item.get("token"),
        telegram_message_id=item.get("telegram_message_id"),
        telegram_chat_id=item.get("telegram_chat_id"),
        created_at=datetime.fromisoformat(item["created_at"]),
        expires_at=datetime.fromisoformat(item["expires_at"]) if item.get("expires_at") else None,
        resolved_at=datetime.fromisoformat(item["resolved_at"]) if item.get("resolved_at") else None,
        resolved_by=item.get("resolved_by"),
    )


def update_approval_status(
    approval_id: str,
    new_status: ApprovalStatus,
    resolved_by: str = "system",
) -> ApprovalRequest | None:
    """Update the status of an approval request.

    Uses a conditional expression to prevent overwriting already-resolved requests.

    Returns:
        Updated ApprovalRequest if successful, None if request not found or already resolved.
    """
    now = datetime.utcnow()

    try:
        resp = _tokens_table().update_item(
            Key={"approval_id": approval_id},
            UpdateExpression="SET #status = :new_status, resolved_at = :resolved_at, resolved_by = :resolved_by",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":new_status": new_status.value,
                ":resolved_at": now.isoformat(),
                ":resolved_by": resolved_by,
                ":pending": ApprovalStatus.PENDING.value,
            },
            ConditionExpression="#status = :pending",
            ReturnValues="ALL_NEW",
        )
        return _item_to_request(resp["Attributes"])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning(
                "Approval %s is not pending — cannot update to %s",
                approval_id,
                new_status.value,
            )
            return None
        logger.exception("Failed to update approval %s", approval_id)
        return None


def update_telegram_ids(
    approval_id: str,
    message_id: int,
    chat_id: int,
) -> None:
    """Store the Telegram message and chat IDs for callback routing."""
    try:
        _tokens_table().update_item(
            Key={"approval_id": approval_id},
            UpdateExpression="SET telegram_message_id = :mid, telegram_chat_id = :cid",
            ExpressionAttributeValues={
                ":mid": message_id,
                ":cid": chat_id,
            },
        )
    except ClientError:
        logger.exception("Failed to update Telegram IDs for %s", approval_id)


def consume_token(approval_id: str, token: str) -> bool:
    """Consume a single-use approval token.

    Uses a conditional expression to ensure the token:
    1. Matches the stored token
    2. Has not already been consumed
    3. The request is still pending

    Returns:
        True if token was valid and consumed, False otherwise.
    """
    try:
        _tokens_table().update_item(
            Key={"approval_id": approval_id},
            UpdateExpression="SET token_consumed = :true",
            ExpressionAttributeValues={
                ":true": True,
                ":false": False,
                ":token": token,
                ":pending": ApprovalStatus.PENDING.value,
            },
            ConditionExpression=(
                "token = :token AND token_consumed = :false AND #status = :pending"
            ),
            ExpressionAttributeNames={"#status": "status"},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning("Token consumption failed for %s — invalid, consumed, or not pending", approval_id)
            return False
        logger.exception("Failed to consume token for %s", approval_id)
        return False


def check_and_expire_request(approval_id: str) -> bool:
    """Check if a pending request has expired and mark it as expired if so.

    Returns:
        True if the request was expired, False otherwise.
    """
    request = get_approval_request(approval_id)
    if request is None or request.status != ApprovalStatus.PENDING:
        return False

    if request.expires_at and datetime.utcnow() > request.expires_at:
        result = update_approval_status(approval_id, ApprovalStatus.EXPIRED, resolved_by="system")
        return result is not None

    return False
```

---

### `src/qitp_mcp_2fa/audit.py`

```python
"""DynamoDB audit logging for the 2FA gate.

Every gate event is logged to the qitp_2fa_events table for MiFID II
compliance (5-year retention). Events include: request creation, Telegram
delivery, approval, rejection, expiry, and Step Functions callback results.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from qitp_mcp_2fa.schemas import ApprovalEvent

logger = logging.getLogger(__name__)

EVENTS_TABLE = os.environ.get("DYNAMODB_EVENTS_TABLE", "qitp_2fa_events")

_dynamodb = None


def _get_dynamodb():
    """Lazy-init DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        endpoint_url = os.environ.get("DYNAMODB_ENDPOINT_URL")
        _dynamodb = boto3.resource("dynamodb", region_name=region, endpoint_url=endpoint_url)
    return _dynamodb


def _override_dynamodb(resource):
    """Override the DynamoDB resource (for testing with moto)."""
    global _dynamodb
    _dynamodb = resource


def _events_table():
    return _get_dynamodb().Table(EVENTS_TABLE)


def log_event(
    approval_id: str,
    event_type: str,
    actor: str = "system",
    details: dict[str, Any] | None = None,
) -> ApprovalEvent:
    """Log an audit event for a 2FA gate action.

    Args:
        approval_id: The approval request ID.
        event_type: One of the ApprovalEvent.event_type literals.
        actor: Who triggered this event (Telegram user ID, 'system', etc.).
        details: Additional context for the event.

    Returns:
        The created ApprovalEvent.
    """
    now = datetime.utcnow()
    event = ApprovalEvent(
        approval_id=approval_id,
        event_type=event_type,
        timestamp=now,
        details=details or {},
        actor=actor,
    )

    # DynamoDB item — PK=approval_id, SK=event_type#timestamp
    item = {
        "approval_id": approval_id,
        "sort_key": f"{event_type}#{now.isoformat()}",
        "event_type": event_type,
        "timestamp": now.isoformat(),
        "actor": actor,
        "details": json.loads(json.dumps(details or {}, default=str)),
        # 5-year TTL for MiFID II compliance (157,680,000 seconds)
        "ttl": int(now.timestamp()) + 157_680_000,
    }

    try:
        _events_table().put_item(Item=item)
        logger.info("Audit event: %s/%s by %s", approval_id, event_type, actor)
    except ClientError:
        logger.exception(
            "CRITICAL: Failed to write audit event %s/%s — MiFID II compliance risk",
            approval_id,
            event_type,
        )

    return event


def get_events(approval_id: str) -> list[ApprovalEvent]:
    """Get all audit events for an approval request, ordered by timestamp.

    Args:
        approval_id: The approval request ID.

    Returns:
        List of ApprovalEvent objects sorted by timestamp ascending.
    """
    try:
        resp = _events_table().query(
            KeyConditionExpression="approval_id = :aid",
            ExpressionAttributeValues={":aid": approval_id},
            ScanIndexForward=True,  # Ascending by sort key
        )

        events = []
        for item in resp.get("Items", []):
            events.append(
                ApprovalEvent(
                    approval_id=item["approval_id"],
                    event_type=item["event_type"],
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    details=item.get("details", {}),
                    actor=item.get("actor", "system"),
                )
            )
        return events
    except ClientError:
        logger.exception("Failed to query events for %s", approval_id)
        return []
```

---

### `src/qitp_mcp_2fa/sfn_integration.py`

```python
"""Step Functions integration — send_task_success / send_task_failure callbacks.

When the 2FA gate approves or rejects an order, it must call back to
Step Functions to resume the workflow. The TwoFactorGate state in the
orchestration pipeline uses IntegrationPattern.WAIT_FOR_TASK_TOKEN,
meaning it pauses until we call send_task_success or send_task_failure
with the original task_token.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from qitp_mcp_2fa.audit import log_event

logger = logging.getLogger(__name__)

_sfn_client = None


def _get_sfn_client():
    """Lazy-init Step Functions client."""
    global _sfn_client
    if _sfn_client is None:
        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        endpoint_url = os.environ.get("SFN_ENDPOINT_URL")
        _sfn_client = boto3.client("stepfunctions", region_name=region, endpoint_url=endpoint_url)
    return _sfn_client


def _override_sfn_client(client):
    """Override the SFN client (for testing)."""
    global _sfn_client
    _sfn_client = client


def send_approval_callback(
    task_token: str,
    approval_id: str,
    approved: bool,
    approver: str,
) -> bool:
    """Send task success or failure to Step Functions.

    When approved: sends send_task_success with approval details.
    When rejected: sends send_task_failure with rejection reason.

    The output payload matches what P12's TwoFactorGate expects:
        {"approved": bool, "approver": str, "timestamp": str}

    Args:
        task_token: The Step Functions task token from the waitForTaskToken state.
        approval_id: The approval request ID (for audit logging).
        approved: Whether the order was approved.
        approver: Who approved/rejected (Telegram user ID or 'system').

    Returns:
        True if the callback was sent successfully, False otherwise.
    """
    client = _get_sfn_client()
    now = datetime.utcnow().isoformat()

    try:
        if approved:
            output = json.dumps({
                "approved": True,
                "approver": approver,
                "timestamp": now,
                "approval_id": approval_id,
            })
            client.send_task_success(
                taskToken=task_token,
                output=output,
            )
            logger.info("SFN task_success sent for %s by %s", approval_id, approver)
            log_event(
                approval_id,
                "sfn_callback_sent",
                actor=approver,
                details={"callback_type": "success", "output": output},
            )
        else:
            client.send_task_failure(
                taskToken=task_token,
                error="OrderRejected",
                cause=f"2FA approval rejected by {approver} at {now}",
            )
            logger.info("SFN task_failure sent for %s by %s", approval_id, approver)
            log_event(
                approval_id,
                "sfn_callback_sent",
                actor=approver,
                details={"callback_type": "failure", "error": "OrderRejected"},
            )
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error(
            "SFN callback failed for %s: %s — %s",
            approval_id,
            error_code,
            e.response["Error"]["Message"],
        )
        log_event(
            approval_id,
            "sfn_callback_failed",
            actor="system",
            details={"error_code": error_code, "message": str(e)},
        )
        return False
```

---

### `src/qitp_mcp_2fa/telegram/__init__.py`

```python
"""Telegram bot integration for 2FA approval."""
```

---

### `src/qitp_mcp_2fa/telegram/bot.py`

```python
"""Telegram bot for sending approval requests with inline keyboard buttons.

Uses python-telegram-bot (v21+, async). The bot sends a formatted message
with order details and Approve/Reject inline buttons. When the user taps
a button, the callback handler in handlers.py processes the response.

Configuration via environment variables:
- TELEGRAM_BOT_TOKEN: Bot API token from @BotFather
- TELEGRAM_CHAT_ID: Chat ID of the authorized approver (owner only)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from qitp_mcp_2fa.audit import log_event
from qitp_mcp_2fa.token_store import update_telegram_ids

if TYPE_CHECKING:
    from qitp_mcp_2fa.schemas import ApprovalRequest

logger = logging.getLogger(__name__)

_bot: Bot | None = None


def _get_bot() -> Bot:
    """Lazy-init Telegram bot."""
    global _bot
    if _bot is None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN not set — cannot send approval requests. "
                "Configure it as an environment variable."
            )
        _bot = Bot(token=token)
    return _bot


def _override_bot(bot: Bot) -> None:
    """Override the Telegram bot instance (for testing)."""
    global _bot
    _bot = bot


def _get_chat_id() -> int:
    """Get the authorized approver's Telegram chat ID."""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID not set — cannot route approval requests. "
            "Configure it as an environment variable."
        )
    return int(chat_id)


def _format_order_message(request: ApprovalRequest) -> str:
    """Format the approval request as a Telegram message."""
    od = request.order_details
    lines = [
        "--- QITP ORDER APPROVAL ---",
        "",
        f"Action:   {od.action} {od.quantity}x {od.symbol}",
        f"Type:     {od.order_type}",
    ]

    if od.limit_price is not None:
        lines.append(f"Limit:    ${od.limit_price:,.2f}")
    if od.stop_price is not None:
        lines.append(f"Stop:     ${od.stop_price:,.2f}")
    if od.trailing_stop_pct is not None:
        lines.append(f"Trail:    {od.trailing_stop_pct}%")
    if od.estimated_cost_usd is not None:
        lines.append(f"Est Cost: ${od.estimated_cost_usd:,.2f}")
    if od.strategy:
        lines.append(f"Strategy: {od.strategy}")

    lines.append("")
    if od.rationale:
        lines.append(f"Rationale: {od.rationale}")
        lines.append("")

    lines.append(f"Approval ID: {request.approval_id[:8]}...")
    lines.append(f"Expires: {request.expires_at.strftime('%H:%M:%S UTC') if request.expires_at else 'N/A'}")
    lines.append("")
    lines.append("Tap below to approve or reject:")

    return "\n".join(lines)


def _build_keyboard(approval_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with Approve and Reject buttons.

    The callback_data format is: approve:{approval_id} or reject:{approval_id}
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Approve",
                    callback_data=f"approve:{approval_id}",
                ),
                InlineKeyboardButton(
                    "Reject",
                    callback_data=f"reject:{approval_id}",
                ),
            ]
        ]
    )


async def send_approval_message(request: ApprovalRequest) -> bool:
    """Send the approval request to Telegram with inline keyboard buttons.

    Args:
        request: The ApprovalRequest to send.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    try:
        bot = _get_bot()
        chat_id = _get_chat_id()
        text = _format_order_message(request)
        keyboard = _build_keyboard(request.approval_id)

        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=None,  # Plain text for reliability
        )

        # Store Telegram message/chat IDs for later reference
        update_telegram_ids(
            approval_id=request.approval_id,
            message_id=message.message_id,
            chat_id=chat_id,
        )

        log_event(
            request.approval_id,
            "telegram_sent",
            actor="system",
            details={
                "chat_id": chat_id,
                "message_id": message.message_id,
            },
        )

        logger.info(
            "Telegram approval message sent for %s (msg_id=%d)",
            request.approval_id,
            message.message_id,
        )
        return True

    except TelegramError as e:
        logger.error("Failed to send Telegram message for %s: %s", request.approval_id, e)
        log_event(
            request.approval_id,
            "telegram_sent",
            actor="system",
            details={"error": str(e), "success": False},
        )
        return False

    except RuntimeError as e:
        # Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID
        logger.error("Telegram configuration error: %s", e)
        return False
```

---

### `src/qitp_mcp_2fa/telegram/handlers.py`

```python
"""Telegram inline keyboard callback handlers.

When a user taps Approve or Reject on the inline keyboard, Telegram sends
a callback query. This module processes those callbacks, updates the approval
status, and sends the Step Functions callback.

The bot is run in webhook or polling mode depending on deployment:
- Dev: polling via Application.run_polling()
- Production: webhook via Application.run_webhook() behind API Gateway

The callback_data format is: {action}:{approval_id}
where action is "approve" or "reject".
"""

from __future__ import annotations

import logging
import os

from telegram import Bot, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from qitp_mcp_2fa.audit import log_event
from qitp_mcp_2fa.schemas import ApprovalStatus
from qitp_mcp_2fa.sfn_integration import send_approval_callback
from qitp_mcp_2fa.token_store import (
    consume_token,
    get_approval_request,
    update_approval_status,
)

logger = logging.getLogger(__name__)


async def handle_approval_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle Approve/Reject button presses from the Telegram inline keyboard.

    Extracts the action and approval_id from callback_data, validates the
    request, updates status, and sends the Step Functions callback.
    """
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()  # Acknowledge the button press

    # Parse callback data
    parts = query.data.split(":", 1)
    if len(parts) != 2 or parts[0] not in ("approve", "reject"):
        await query.edit_message_text("Invalid callback data.")
        return

    action, approval_id = parts
    user = query.from_user
    actor = str(user.id) if user else "unknown"
    actor_name = user.full_name if user else "Unknown"

    # Validate the authorized chat
    authorized_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if authorized_chat_id and str(query.message.chat_id) != authorized_chat_id:
        logger.warning(
            "Unauthorized approval attempt from chat %s (authorized: %s)",
            query.message.chat_id,
            authorized_chat_id,
        )
        await query.edit_message_text("Unauthorized. This approval is restricted.")
        return

    # Retrieve the approval request
    request = get_approval_request(approval_id)
    if request is None:
        await query.edit_message_text(f"Approval {approval_id[:8]}... not found.")
        return

    if request.status != ApprovalStatus.PENDING:
        await query.edit_message_text(
            f"Approval {approval_id[:8]}... already {request.status.value}."
        )
        return

    # Process the action
    approved = action == "approve"
    new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED

    # Consume the single-use token
    if request.token:
        token_ok = consume_token(approval_id, request.token)
        if not token_ok:
            await query.edit_message_text(
                f"Token already consumed for {approval_id[:8]}... — cannot process."
            )
            log_event(approval_id, "token_invalid", actor=actor)
            return
        log_event(approval_id, "token_verified", actor=actor)

    # Update approval status
    updated = update_approval_status(approval_id, new_status, resolved_by=actor)
    if updated is None:
        await query.edit_message_text(
            f"Failed to update {approval_id[:8]}... — it may have already been resolved."
        )
        return

    # Log the approval/rejection event
    log_event(
        approval_id,
        "approved" if approved else "rejected",
        actor=actor,
        details={"actor_name": actor_name},
    )

    # Send Step Functions callback
    sfn_ok = send_approval_callback(
        task_token=request.task_token,
        approval_id=approval_id,
        approved=approved,
        approver=actor,
    )

    # Update the Telegram message to reflect the result
    status_emoji = "APPROVED" if approved else "REJECTED"
    status_text = (
        f"--- {status_emoji} ---\n\n"
        f"{request.order_details.action} {request.order_details.quantity}x "
        f"{request.order_details.symbol}\n\n"
        f"By: {actor_name}\n"
        f"SFN callback: {'sent' if sfn_ok else 'FAILED'}"
    )
    await query.edit_message_text(status_text)


def create_bot_application() -> Application:
    """Create the Telegram bot Application with callback handlers registered.

    Returns:
        Configured Application ready to run_polling() or run_webhook().
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = Application.builder().token(token).build()
    app.add_handler(CallbackQueryHandler(handle_approval_callback))

    return app


async def start_polling() -> None:
    """Start the Telegram bot in polling mode (for development)."""
    app = create_bot_application()
    logger.info("Starting Telegram bot in polling mode...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()


async def stop_polling(app: Application) -> None:
    """Stop the Telegram bot polling."""
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
```

---

### `src/qitp_mcp_2fa/tools/__init__.py`

```python
"""MCP tool implementations for 2FA gate server."""
```

---

### `src/qitp_mcp_2fa/tools/approval.py`

```python
"""2FA approval tools — the core business logic of the 2FA gate MCP server.

4 tools:
1. request_approval — Create approval request, send Telegram message (or auto-approve)
2. verify_token — Validate a single-use approval token
3. get_approval_status — Check current status of a pending approval
4. reject_pending — Admin force-reject a pending approval
"""

from __future__ import annotations

import logging
import os

from qitp_mcp_2fa.audit import log_event
from qitp_mcp_2fa.schemas import (
    ApprovalResult,
    ApprovalStatus,
    OrderDetails,
    StatusResult,
    TokenVerifyResult,
)
from qitp_mcp_2fa.sfn_integration import send_approval_callback
from qitp_mcp_2fa.token_store import (
    check_and_expire_request,
    consume_token,
    create_approval_request,
    get_approval_request,
    update_approval_status,
)

logger = logging.getLogger(__name__)


async def request_approval(
    task_token: str,
    symbol: str,
    action: str,
    quantity: int,
    order_type: str,
    limit_price: float | None = None,
    stop_price: float | None = None,
    trailing_stop_pct: float | None = None,
    estimated_cost_usd: float | None = None,
    strategy: str | None = None,
    rationale: str | None = None,
) -> dict:
    """Create a 2FA approval request for an order.

    In backtest/paper mode: returns auto_approved=True immediately without
    sending a Telegram message or waiting for human approval.

    In live mode: creates the approval request, sends a Telegram message
    with Approve/Reject buttons, and returns the approval_id. The caller
    (Step Functions) blocks on waitForTaskToken until the callback arrives.

    Args:
        task_token: Step Functions task token for the waitForTaskToken callback.
        symbol: Ticker symbol (e.g. "AAPL").
        action: Order action — BUY, SELL, or SSHORT.
        quantity: Number of shares.
        order_type: Order type — MKT, LMT, STP, or STP_LMT.
        limit_price: Limit price (for LMT/STP_LMT orders).
        stop_price: Stop price (for STP/STP_LMT orders).
        trailing_stop_pct: Trailing stop percentage.
        estimated_cost_usd: Estimated total cost in USD.
        strategy: Strategy name that generated this order.
        rationale: AI-generated rationale for the order.

    Returns:
        ApprovalResult as dictionary.
    """
    execution_mode = os.environ.get("EXECUTION_MODE", "backtest").lower()

    order_details = OrderDetails(
        symbol=symbol,
        action=action,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
        stop_price=stop_price,
        trailing_stop_pct=trailing_stop_pct,
        estimated_cost_usd=estimated_cost_usd,
        strategy=strategy,
        rationale=rationale,
    )

    # Create the approval request in DynamoDB
    request = create_approval_request(
        task_token=task_token,
        order_details=order_details,
        execution_mode=execution_mode,
    )

    # Audit: request created
    log_event(
        request.approval_id,
        "request_created",
        actor="system",
        details={
            "execution_mode": execution_mode,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "order_type": order_type,
        },
    )

    # Auto-approve in backtest/paper mode
    if execution_mode in ("backtest", "paper"):
        log_event(request.approval_id, "auto_approved", actor="system")

        # Send immediate SFN callback for auto-approval
        send_approval_callback(
            task_token=task_token,
            approval_id=request.approval_id,
            approved=True,
            approver="system",
        )

        result = ApprovalResult(
            approval_id=request.approval_id,
            status=ApprovalStatus.AUTO_APPROVED,
            auto_approved=True,
            message=f"Auto-approved in {execution_mode} mode — no 2FA required.",
            expires_at=request.expires_at,
        )
        return result.model_dump(mode="json")

    # Live mode: send Telegram message
    from qitp_mcp_2fa.telegram.bot import send_approval_message

    telegram_ok = await send_approval_message(request)

    if not telegram_ok:
        logger.error(
            "Failed to send Telegram approval for %s — order will time out",
            request.approval_id,
        )

    result = ApprovalResult(
        approval_id=request.approval_id,
        status=ApprovalStatus.PENDING,
        auto_approved=False,
        message="Approval request sent to Telegram. Waiting for response."
        if telegram_ok
        else "Telegram delivery failed. Approval will expire in 5 minutes.",
        expires_at=request.expires_at,
    )
    return result.model_dump(mode="json")


async def verify_token(
    approval_id: str,
    token: str,
) -> dict:
    """Validate a single-use approval token.

    Checks that the token matches, hasn't been consumed, and the request
    is still pending. If valid, the token is consumed (single-use).

    Args:
        approval_id: The approval request ID.
        token: The single-use token to verify.

    Returns:
        TokenVerifyResult as dictionary.
    """
    request = get_approval_request(approval_id)

    if request is None:
        log_event(approval_id, "token_invalid", details={"reason": "request_not_found"})
        result = TokenVerifyResult(
            approval_id=approval_id,
            status=ApprovalStatus.EXPIRED,
            valid=False,
            message="Approval request not found.",
        )
        return result.model_dump(mode="json")

    # Check for expiry first
    check_and_expire_request(approval_id)
    request = get_approval_request(approval_id)
    if request is None or request.status == ApprovalStatus.EXPIRED:
        log_event(approval_id, "token_invalid", details={"reason": "expired"})
        result = TokenVerifyResult(
            approval_id=approval_id,
            status=ApprovalStatus.EXPIRED,
            valid=False,
            message="Approval request has expired.",
        )
        return result.model_dump(mode="json")

    if request.status != ApprovalStatus.PENDING:
        log_event(
            approval_id,
            "token_invalid",
            details={"reason": f"already_{request.status.value}"},
        )
        result = TokenVerifyResult(
            approval_id=approval_id,
            status=request.status,
            valid=False,
            message=f"Approval is already {request.status.value}.",
        )
        return result.model_dump(mode="json")

    # Attempt to consume the token
    consumed = consume_token(approval_id, token)

    if consumed:
        log_event(approval_id, "token_verified")
        result = TokenVerifyResult(
            approval_id=approval_id,
            status=ApprovalStatus.PENDING,
            valid=True,
            message="Token is valid and has been consumed.",
        )
    else:
        log_event(approval_id, "token_invalid", details={"reason": "consume_failed"})
        result = TokenVerifyResult(
            approval_id=approval_id,
            status=request.status,
            valid=False,
            message="Token is invalid or has already been consumed.",
        )

    return result.model_dump(mode="json")


async def get_approval_status(approval_id: str) -> dict:
    """Check the current status of an approval request.

    Also checks for expiry — if the request is pending and past its
    expiry time, it will be marked as expired.

    Args:
        approval_id: The approval request ID.

    Returns:
        StatusResult as dictionary.
    """
    # Check and expire if needed
    check_and_expire_request(approval_id)

    request = get_approval_request(approval_id)
    if request is None:
        return {
            "error": "NotFound",
            "message": f"Approval request {approval_id} not found.",
        }

    result = StatusResult(
        approval_id=request.approval_id,
        status=request.status,
        order_details=request.order_details,
        created_at=request.created_at,
        expires_at=request.expires_at,
        resolved_at=request.resolved_at,
        resolved_by=request.resolved_by,
    )
    return result.model_dump(mode="json")


async def reject_pending(
    approval_id: str,
    reason: str = "Admin force-reject",
) -> dict:
    """Force-reject a pending approval request.

    Used by admins to reject an order without waiting for the Telegram
    button press. Also sends the Step Functions failure callback.

    Args:
        approval_id: The approval request ID.
        reason: Reason for the force-rejection.

    Returns:
        StatusResult as dictionary with updated status.
    """
    request = get_approval_request(approval_id)
    if request is None:
        return {
            "error": "NotFound",
            "message": f"Approval request {approval_id} not found.",
        }

    if request.status != ApprovalStatus.PENDING:
        return {
            "error": "AlreadyResolved",
            "message": f"Approval is already {request.status.value} — cannot reject.",
            "approval_id": approval_id,
            "status": request.status.value,
        }

    # Update status to rejected
    updated = update_approval_status(
        approval_id,
        ApprovalStatus.REJECTED,
        resolved_by="admin",
    )

    if updated is None:
        return {
            "error": "UpdateFailed",
            "message": "Failed to update approval status — it may have been resolved concurrently.",
        }

    # Audit log
    log_event(
        approval_id,
        "force_rejected",
        actor="admin",
        details={"reason": reason},
    )

    # Send Step Functions failure callback
    send_approval_callback(
        task_token=request.task_token,
        approval_id=approval_id,
        approved=False,
        approver="admin",
    )

    result = StatusResult(
        approval_id=updated.approval_id,
        status=updated.status,
        order_details=updated.order_details,
        created_at=updated.created_at,
        expires_at=updated.expires_at,
        resolved_at=updated.resolved_at,
        resolved_by=updated.resolved_by,
    )
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_2fa/server.py`

```python
"""MCP server entrypoint — registers all 4 tools and runs the server."""

from __future__ import annotations

import asyncio
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
logger = logging.getLogger("qitp_mcp_2fa")

# ---------------------------------------------------------------------------
# Build the MCP server
# ---------------------------------------------------------------------------

server = Server("2fa-mcp")


# ---------------------------------------------------------------------------
# Tool definitions (list_tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="request_approval",
        description=(
            "Create a 2FA approval request for an order. In backtest/paper mode, "
            "returns auto_approved=True immediately. In live mode, sends a Telegram "
            "message with Approve/Reject buttons and blocks via waitForTaskToken."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_token": {
                    "type": "string",
                    "description": "Step Functions task token for waitForTaskToken callback",
                },
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL)"},
                "action": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "SSHORT"],
                    "description": "Order action",
                },
                "quantity": {"type": "integer", "description": "Number of shares"},
                "order_type": {
                    "type": "string",
                    "enum": ["MKT", "LMT", "STP", "STP_LMT"],
                    "description": "Order type",
                },
                "limit_price": {
                    "type": "number",
                    "description": "Limit price for LMT/STP_LMT orders",
                },
                "stop_price": {
                    "type": "number",
                    "description": "Stop price for STP/STP_LMT orders",
                },
                "trailing_stop_pct": {
                    "type": "number",
                    "description": "Trailing stop percentage",
                },
                "estimated_cost_usd": {
                    "type": "number",
                    "description": "Estimated total cost in USD",
                },
                "strategy": {
                    "type": "string",
                    "description": "Strategy name that generated this order",
                },
                "rationale": {
                    "type": "string",
                    "description": "AI-generated rationale for the order",
                },
            },
            "required": ["task_token", "symbol", "action", "quantity", "order_type"],
        },
    ),
    Tool(
        name="verify_token",
        description=(
            "Validate a single-use approval token. Returns approved/rejected/expired. "
            "The token is consumed on successful verification and cannot be reused."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string", "description": "The approval request ID"},
                "token": {"type": "string", "description": "The single-use approval token to verify"},
            },
            "required": ["approval_id", "token"],
        },
    ),
    Tool(
        name="get_approval_status",
        description=(
            "Check the current status of a pending approval request. "
            "Returns pending, approved, rejected, expired, or auto_approved."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string", "description": "The approval request ID"},
            },
            "required": ["approval_id"],
        },
    ),
    Tool(
        name="reject_pending",
        description=(
            "Admin force-reject a pending approval. Sends Step Functions failure "
            "callback immediately. Cannot reject already-resolved approvals."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string", "description": "The approval request ID"},
                "reason": {
                    "type": "string",
                    "description": "Reason for the force-rejection",
                    "default": "Admin force-reject",
                },
            },
            "required": ["approval_id"],
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
    if name == "request_approval":
        from qitp_mcp_2fa.tools.approval import request_approval

        return await request_approval(
            task_token=arguments["task_token"],
            symbol=arguments["symbol"],
            action=arguments["action"],
            quantity=arguments["quantity"],
            order_type=arguments["order_type"],
            limit_price=arguments.get("limit_price"),
            stop_price=arguments.get("stop_price"),
            trailing_stop_pct=arguments.get("trailing_stop_pct"),
            estimated_cost_usd=arguments.get("estimated_cost_usd"),
            strategy=arguments.get("strategy"),
            rationale=arguments.get("rationale"),
        )

    elif name == "verify_token":
        from qitp_mcp_2fa.tools.approval import verify_token

        return await verify_token(
            approval_id=arguments["approval_id"],
            token=arguments["token"],
        )

    elif name == "get_approval_status":
        from qitp_mcp_2fa.tools.approval import get_approval_status

        return await get_approval_status(
            approval_id=arguments["approval_id"],
        )

    elif name == "reject_pending":
        from qitp_mcp_2fa.tools.approval import reject_pending

        return await reject_pending(
            approval_id=arguments["approval_id"],
            reason=arguments.get("reason", "Admin force-reject"),
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Telegram bot background task
# ---------------------------------------------------------------------------

async def _run_telegram_bot():
    """Start the Telegram bot polling in the background (dev mode only)."""
    try:
        from qitp_mcp_2fa.telegram.handlers import start_polling

        await start_polling()
    except Exception:
        logger.exception("Telegram bot failed to start — approval buttons will not work")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def run_stdio():
    """Run MCP server over stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_with_telegram():
    """Run MCP server with Telegram bot polling in the background."""
    # Start Telegram bot as a background task
    telegram_task = asyncio.create_task(_run_telegram_bot())

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        telegram_task.cancel()


def main():
    """Main entrypoint — select transport based on env."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    enable_telegram = os.environ.get("ENABLE_TELEGRAM_BOT", "false").lower() == "true"

    if transport == "stdio":
        if enable_telegram:
            asyncio.run(run_with_telegram())
        else:
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
"""Shared test fixtures for 2FA gate MCP server tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Set default environment for all tests."""
    monkeypatch.setenv("EXECUTION_MODE", "live")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DYNAMODB_TOKENS_TABLE", "qitp_2fa_tokens")
    monkeypatch.setenv("DYNAMODB_EVENTS_TABLE", "qitp_2fa_events")
    monkeypatch.setenv("APPROVAL_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-bot-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")


@pytest.fixture
def dynamodb_tables():
    """Create DynamoDB tables using moto and inject them into token_store and audit modules."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")

        # Create tokens table
        dynamodb.create_table(
            TableName="qitp_2fa_tokens",
            KeySchema=[
                {"AttributeName": "approval_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "approval_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create events table
        dynamodb.create_table(
            TableName="qitp_2fa_events",
            KeySchema=[
                {"AttributeName": "approval_id", "KeyType": "HASH"},
                {"AttributeName": "sort_key", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "approval_id", "AttributeType": "S"},
                {"AttributeName": "sort_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Inject the moto DynamoDB resource into both modules
        from qitp_mcp_2fa import audit, token_store

        token_store._override_dynamodb(dynamodb)
        audit._override_dynamodb(dynamodb)

        yield dynamodb

        # Reset after test
        token_store._override_dynamodb(None)
        audit._override_dynamodb(None)


@pytest.fixture
def mock_sfn_client():
    """Mock Step Functions client."""
    client = MagicMock()
    client.send_task_success = MagicMock(return_value={})
    client.send_task_failure = MagicMock(return_value={})

    from qitp_mcp_2fa import sfn_integration

    sfn_integration._override_sfn_client(client)

    yield client

    sfn_integration._override_sfn_client(None)


@pytest.fixture
def sample_order_details():
    """Sample order details for testing."""
    from qitp_mcp_2fa.schemas import OrderDetails

    return OrderDetails(
        symbol="AAPL",
        action="BUY",
        quantity=100,
        order_type="LMT",
        limit_price=185.50,
        trailing_stop_pct=2.5,
        estimated_cost_usd=18550.00,
        strategy="gap_momentum_up",
        rationale="Gap up 3.2% with high volume confirmation. Analyst sentiment bullish.",
    )


@pytest.fixture
def mock_telegram_bot():
    """Mock Telegram bot that captures sent messages."""
    bot = AsyncMock()
    message = MagicMock()
    message.message_id = 42
    bot.send_message = AsyncMock(return_value=message)

    from qitp_mcp_2fa.telegram import bot as bot_module

    bot_module._override_bot(bot)

    yield bot

    bot_module._override_bot(None)
```

---

### `tests/test_approval.py`

```python
"""Tests for the approval tools — the core business logic."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from qitp_mcp_2fa.schemas import ApprovalStatus, OrderDetails
from qitp_mcp_2fa.token_store import (
    create_approval_request,
    get_approval_request,
    update_approval_status,
)
from qitp_mcp_2fa.tools.approval import (
    get_approval_status as get_status_tool,
    reject_pending,
    request_approval,
    verify_token,
)


# ---------------------------------------------------------------------------
# Auto-approval in backtest/paper mode
# ---------------------------------------------------------------------------


class TestAutoApproval:
    @pytest.mark.asyncio
    async def test_backtest_auto_approves(self, monkeypatch, dynamodb_tables, mock_sfn_client):
        """In backtest mode, request_approval returns auto_approved=True immediately."""
        monkeypatch.setenv("EXECUTION_MODE", "backtest")

        result = await request_approval(
            task_token="fake-task-token-123",
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT",
        )

        assert result["auto_approved"] is True
        assert result["status"] == "auto_approved"
        assert "backtest" in result["message"].lower()

        # Verify SFN callback was sent
        mock_sfn_client.send_task_success.assert_called_once()
        call_args = mock_sfn_client.send_task_success.call_args
        assert call_args.kwargs["taskToken"] == "fake-task-token-123"

    @pytest.mark.asyncio
    async def test_paper_auto_approves(self, monkeypatch, dynamodb_tables, mock_sfn_client):
        """In paper mode, request_approval returns auto_approved=True immediately."""
        monkeypatch.setenv("EXECUTION_MODE", "paper")

        result = await request_approval(
            task_token="fake-task-token-456",
            symbol="SPY",
            action="SELL",
            quantity=50,
            order_type="LMT",
            limit_price=450.00,
        )

        assert result["auto_approved"] is True
        assert result["status"] == "auto_approved"
        mock_sfn_client.send_task_success.assert_called_once()


# ---------------------------------------------------------------------------
# Live mode: Telegram approval flow
# ---------------------------------------------------------------------------


class TestLiveApproval:
    @pytest.mark.asyncio
    async def test_live_sends_telegram(
        self, monkeypatch, dynamodb_tables, mock_sfn_client, mock_telegram_bot
    ):
        """In live mode, request_approval sends a Telegram message and returns pending."""
        monkeypatch.setenv("EXECUTION_MODE", "live")

        result = await request_approval(
            task_token="live-task-token-789",
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="LMT",
            limit_price=185.50,
            strategy="gap_momentum_up",
            rationale="Gap up 3.2%",
        )

        assert result["auto_approved"] is False
        assert result["status"] == "pending"
        assert "Telegram" in result["message"]

        # Verify Telegram message was sent
        mock_telegram_bot.send_message.assert_called_once()
        call_kwargs = mock_telegram_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 12345678
        assert "AAPL" in call_kwargs["text"]
        assert "BUY" in call_kwargs["text"]

        # SFN callback should NOT be sent yet (waiting for approval)
        mock_sfn_client.send_task_success.assert_not_called()
        mock_sfn_client.send_task_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_creates_dynamo_record(
        self, monkeypatch, dynamodb_tables, mock_sfn_client, mock_telegram_bot
    ):
        """Live mode should store the approval request in DynamoDB."""
        monkeypatch.setenv("EXECUTION_MODE", "live")

        result = await request_approval(
            task_token="live-token-abc",
            symbol="TSLA",
            action="BUY",
            quantity=50,
            order_type="MKT",
        )

        approval_id = result["approval_id"]
        stored = get_approval_request(approval_id)
        assert stored is not None
        assert stored.status == ApprovalStatus.PENDING
        assert stored.order_details.symbol == "TSLA"
        assert stored.task_token == "live-token-abc"


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------


class TestVerifyToken:
    @pytest.mark.asyncio
    async def test_valid_token(self, dynamodb_tables, mock_sfn_client, sample_order_details):
        """A valid, unconsumed token should be verified and consumed."""
        request = create_approval_request(
            task_token="token-verify-test",
            order_details=sample_order_details,
            execution_mode="live",
        )
        # Force status to pending for live mode test
        # (create_approval_request already sets PENDING for live)

        result = await verify_token(request.approval_id, request.token)

        assert result["valid"] is True
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_invalid_token(self, dynamodb_tables, mock_sfn_client, sample_order_details):
        """An incorrect token should fail verification."""
        request = create_approval_request(
            task_token="token-invalid-test",
            order_details=sample_order_details,
            execution_mode="live",
        )

        result = await verify_token(request.approval_id, "wrong-token-value")

        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_consumed_token_cannot_be_reused(
        self, dynamodb_tables, mock_sfn_client, sample_order_details
    ):
        """A token that has already been consumed cannot be verified again."""
        request = create_approval_request(
            task_token="token-reuse-test",
            order_details=sample_order_details,
            execution_mode="live",
        )

        # First verification succeeds
        result1 = await verify_token(request.approval_id, request.token)
        assert result1["valid"] is True

        # Second verification fails (token consumed)
        result2 = await verify_token(request.approval_id, request.token)
        assert result2["valid"] is False

    @pytest.mark.asyncio
    async def test_nonexistent_approval(self, dynamodb_tables, mock_sfn_client):
        """Verifying a token for a nonexistent approval should fail."""
        result = await verify_token("nonexistent-id", "any-token")

        assert result["valid"] is False
        assert result["status"] == "expired"


# ---------------------------------------------------------------------------
# get_approval_status
# ---------------------------------------------------------------------------


class TestGetApprovalStatus:
    @pytest.mark.asyncio
    async def test_pending_status(self, dynamodb_tables, mock_sfn_client, sample_order_details):
        """A newly created live approval should be pending."""
        request = create_approval_request(
            task_token="status-pending-test",
            order_details=sample_order_details,
            execution_mode="live",
        )

        result = await get_status_tool(request.approval_id)

        assert result["status"] == "pending"
        assert result["order_details"]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_approved_status(self, dynamodb_tables, mock_sfn_client, sample_order_details):
        """After approval, status should reflect approved."""
        request = create_approval_request(
            task_token="status-approved-test",
            order_details=sample_order_details,
            execution_mode="live",
        )
        update_approval_status(request.approval_id, ApprovalStatus.APPROVED, "user123")

        result = await get_status_tool(request.approval_id)

        assert result["status"] == "approved"
        assert result["resolved_by"] == "user123"

    @pytest.mark.asyncio
    async def test_not_found(self, dynamodb_tables, mock_sfn_client):
        """Nonexistent approval should return error."""
        result = await get_status_tool("nonexistent-id")

        assert "error" in result
        assert result["error"] == "NotFound"


# ---------------------------------------------------------------------------
# reject_pending
# ---------------------------------------------------------------------------


class TestRejectPending:
    @pytest.mark.asyncio
    async def test_force_reject_pending(
        self, dynamodb_tables, mock_sfn_client, sample_order_details
    ):
        """Admin force-reject should update status and send SFN failure callback."""
        request = create_approval_request(
            task_token="reject-pending-test",
            order_details=sample_order_details,
            execution_mode="live",
        )

        result = await reject_pending(request.approval_id, reason="Market volatility too high")

        assert result["status"] == "rejected"
        assert result["resolved_by"] == "admin"

        # Verify SFN failure callback was sent
        mock_sfn_client.send_task_failure.assert_called_once()
        call_kwargs = mock_sfn_client.send_task_failure.call_args.kwargs
        assert call_kwargs["taskToken"] == "reject-pending-test"
        assert call_kwargs["error"] == "OrderRejected"

    @pytest.mark.asyncio
    async def test_cannot_reject_already_approved(
        self, dynamodb_tables, mock_sfn_client, sample_order_details
    ):
        """Cannot force-reject an already approved request."""
        request = create_approval_request(
            task_token="already-approved-test",
            order_details=sample_order_details,
            execution_mode="live",
        )
        update_approval_status(request.approval_id, ApprovalStatus.APPROVED, "user123")

        result = await reject_pending(request.approval_id)

        assert "error" in result
        assert result["error"] == "AlreadyResolved"

    @pytest.mark.asyncio
    async def test_reject_nonexistent(self, dynamodb_tables, mock_sfn_client):
        """Rejecting a nonexistent approval should return error."""
        result = await reject_pending("nonexistent-id")

        assert "error" in result
        assert result["error"] == "NotFound"
```

---

### `tests/test_telegram.py`

```python
"""Tests for Telegram bot message formatting and sending."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from qitp_mcp_2fa.schemas import ApprovalRequest, ApprovalStatus, OrderDetails
from qitp_mcp_2fa.telegram.bot import (
    _build_keyboard,
    _format_order_message,
    send_approval_message,
)


@pytest.fixture
def sample_approval_request():
    """A sample approval request for message formatting tests."""
    return ApprovalRequest(
        approval_id="test-approval-id-12345678",
        task_token="fake-task-token",
        execution_mode="live",
        order_details=OrderDetails(
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="LMT",
            limit_price=185.50,
            trailing_stop_pct=2.5,
            estimated_cost_usd=18550.00,
            strategy="gap_momentum_up",
            rationale="Gap up 3.2% with high volume confirmation.",
        ),
        status=ApprovalStatus.PENDING,
        token="fake-token",
        created_at=datetime(2025, 3, 15, 10, 0, 0),
        expires_at=datetime(2025, 3, 15, 10, 5, 0),
    )


class TestMessageFormatting:
    def test_format_includes_order_details(self, sample_approval_request):
        """Message should include all order details."""
        text = _format_order_message(sample_approval_request)

        assert "AAPL" in text
        assert "BUY" in text
        assert "100" in text
        assert "LMT" in text
        assert "185.50" in text
        assert "2.5%" in text
        assert "18,550.00" in text
        assert "gap_momentum_up" in text
        assert "Gap up 3.2%" in text

    def test_format_includes_approval_id_prefix(self, sample_approval_request):
        """Message should include a truncated approval ID."""
        text = _format_order_message(sample_approval_request)

        assert "test-app" in text  # First 8 chars of approval_id

    def test_format_includes_expiry(self, sample_approval_request):
        """Message should include the expiry time."""
        text = _format_order_message(sample_approval_request)

        assert "10:05:00" in text

    def test_format_minimal_order(self):
        """Message should work with minimal order details (no optional fields)."""
        request = ApprovalRequest(
            approval_id="minimal-test-id-123456",
            task_token="token",
            execution_mode="live",
            order_details=OrderDetails(
                symbol="SPY",
                action="SELL",
                quantity=50,
                order_type="MKT",
            ),
            status=ApprovalStatus.PENDING,
        )
        text = _format_order_message(request)

        assert "SPY" in text
        assert "SELL" in text
        assert "50" in text
        assert "MKT" in text


class TestKeyboard:
    def test_keyboard_has_two_buttons(self):
        """Keyboard should have Approve and Reject buttons."""
        keyboard = _build_keyboard("test-approval-id")

        buttons = keyboard.inline_keyboard[0]
        assert len(buttons) == 2
        assert buttons[0].text == "Approve"
        assert buttons[1].text == "Reject"

    def test_keyboard_callback_data(self):
        """Callback data should include action and approval_id."""
        keyboard = _build_keyboard("my-approval-123")

        buttons = keyboard.inline_keyboard[0]
        assert buttons[0].callback_data == "approve:my-approval-123"
        assert buttons[1].callback_data == "reject:my-approval-123"


class TestSendApprovalMessage:
    @pytest.mark.asyncio
    async def test_sends_message_to_configured_chat(
        self, dynamodb_tables, mock_telegram_bot, sample_approval_request
    ):
        """send_approval_message should call bot.send_message with correct chat_id."""
        result = await send_approval_message(sample_approval_request)

        assert result is True
        mock_telegram_bot.send_message.assert_called_once()
        call_kwargs = mock_telegram_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 12345678

    @pytest.mark.asyncio
    async def test_returns_false_on_telegram_error(
        self, dynamodb_tables, sample_approval_request
    ):
        """send_approval_message should return False if Telegram fails."""
        from telegram.error import TelegramError

        from qitp_mcp_2fa.telegram import bot as bot_module

        failing_bot = AsyncMock()
        failing_bot.send_message = AsyncMock(side_effect=TelegramError("Network error"))
        bot_module._override_bot(failing_bot)

        result = await send_approval_message(sample_approval_request)

        assert result is False
        bot_module._override_bot(None)

    @pytest.mark.asyncio
    async def test_returns_false_without_bot_token(
        self, monkeypatch, dynamodb_tables, sample_approval_request
    ):
        """send_approval_message should return False if TELEGRAM_BOT_TOKEN is not set."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")

        from qitp_mcp_2fa.telegram import bot as bot_module

        bot_module._override_bot(None)  # Force re-initialization

        result = await send_approval_message(sample_approval_request)

        assert result is False
```

---

### `tests/test_sfn_integration.py`

```python
"""Tests for Step Functions integration — send_task_success / send_task_failure."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from qitp_mcp_2fa.sfn_integration import send_approval_callback


class TestSendApprovalCallback:
    def test_approved_sends_task_success(self, dynamodb_tables, mock_sfn_client):
        """Approved callback should call send_task_success with correct payload."""
        result = send_approval_callback(
            task_token="test-task-token",
            approval_id="test-approval-id",
            approved=True,
            approver="user123",
        )

        assert result is True
        mock_sfn_client.send_task_success.assert_called_once()

        call_kwargs = mock_sfn_client.send_task_success.call_args.kwargs
        assert call_kwargs["taskToken"] == "test-task-token"

        output = json.loads(call_kwargs["output"])
        assert output["approved"] is True
        assert output["approver"] == "user123"
        assert output["approval_id"] == "test-approval-id"
        assert "timestamp" in output

    def test_rejected_sends_task_failure(self, dynamodb_tables, mock_sfn_client):
        """Rejected callback should call send_task_failure with OrderRejected error."""
        result = send_approval_callback(
            task_token="test-task-token",
            approval_id="test-approval-id",
            approved=False,
            approver="admin",
        )

        assert result is True
        mock_sfn_client.send_task_failure.assert_called_once()

        call_kwargs = mock_sfn_client.send_task_failure.call_args.kwargs
        assert call_kwargs["taskToken"] == "test-task-token"
        assert call_kwargs["error"] == "OrderRejected"
        assert "admin" in call_kwargs["cause"]

    def test_handles_sfn_client_error(self, dynamodb_tables, mock_sfn_client):
        """Should return False and log on SFN client error."""
        mock_sfn_client.send_task_success.side_effect = ClientError(
            {"Error": {"Code": "TaskTimedOut", "Message": "Task timed out"}},
            "SendTaskSuccess",
        )

        result = send_approval_callback(
            task_token="expired-token",
            approval_id="test-id",
            approved=True,
            approver="user",
        )

        assert result is False

    def test_output_matches_p12_result_selector(self, dynamodb_tables, mock_sfn_client):
        """Output payload must match what P12 TwoFactorGate ResultSelector expects.

        P12 expects: {"approved.$": "$.approved", "approver.$": "$.approver", "timestamp.$": "$.timestamp"}
        """
        send_approval_callback(
            task_token="test-token",
            approval_id="test-id",
            approved=True,
            approver="telegram_user_42",
        )

        call_kwargs = mock_sfn_client.send_task_success.call_args.kwargs
        output = json.loads(call_kwargs["output"])

        # These three fields are required by P12's ResultSelector
        assert "approved" in output
        assert "approver" in output
        assert "timestamp" in output

        assert isinstance(output["approved"], bool)
        assert isinstance(output["approver"], str)
        assert isinstance(output["timestamp"], str)
```

---

### `tests/test_token_store.py`

```python
"""Tests for the DynamoDB token store — approval request CRUD and token lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from qitp_mcp_2fa.schemas import ApprovalStatus, OrderDetails
from qitp_mcp_2fa.token_store import (
    check_and_expire_request,
    consume_token,
    create_approval_request,
    get_approval_request,
    update_approval_status,
    update_telegram_ids,
)


@pytest.fixture
def order_details():
    return OrderDetails(
        symbol="AAPL",
        action="BUY",
        quantity=100,
        order_type="LMT",
        limit_price=185.50,
    )


class TestCreateApprovalRequest:
    def test_creates_pending_for_live(self, dynamodb_tables, order_details):
        """Live mode creates a PENDING approval request."""
        request = create_approval_request(
            task_token="test-token-live",
            order_details=order_details,
            execution_mode="live",
        )

        assert request.status == ApprovalStatus.PENDING
        assert request.approval_id is not None
        assert request.token is not None
        assert request.task_token == "test-token-live"
        assert request.order_details.symbol == "AAPL"
        assert request.expires_at is not None

    def test_creates_auto_approved_for_backtest(self, dynamodb_tables, order_details):
        """Backtest mode creates an AUTO_APPROVED request."""
        request = create_approval_request(
            task_token="test-token-bt",
            order_details=order_details,
            execution_mode="backtest",
        )

        assert request.status == ApprovalStatus.AUTO_APPROVED
        assert request.resolved_by == "system"
        assert request.resolved_at is not None

    def test_creates_auto_approved_for_paper(self, dynamodb_tables, order_details):
        """Paper mode creates an AUTO_APPROVED request."""
        request = create_approval_request(
            task_token="test-token-paper",
            order_details=order_details,
            execution_mode="paper",
        )

        assert request.status == ApprovalStatus.AUTO_APPROVED

    def test_unique_approval_ids(self, dynamodb_tables, order_details):
        """Each request should get a unique approval_id."""
        r1 = create_approval_request("t1", order_details, "live")
        r2 = create_approval_request("t2", order_details, "live")

        assert r1.approval_id != r2.approval_id
        assert r1.token != r2.token


class TestGetApprovalRequest:
    def test_retrieves_stored_request(self, dynamodb_tables, order_details):
        """Should retrieve a previously stored request."""
        created = create_approval_request("token-get", order_details, "live")
        retrieved = get_approval_request(created.approval_id)

        assert retrieved is not None
        assert retrieved.approval_id == created.approval_id
        assert retrieved.order_details.symbol == "AAPL"
        assert retrieved.status == ApprovalStatus.PENDING

    def test_returns_none_for_nonexistent(self, dynamodb_tables):
        """Should return None for nonexistent approval_id."""
        result = get_approval_request("nonexistent-id")
        assert result is None


class TestUpdateApprovalStatus:
    def test_updates_pending_to_approved(self, dynamodb_tables, order_details):
        """Should update a pending request to approved."""
        request = create_approval_request("token-update", order_details, "live")
        updated = update_approval_status(request.approval_id, ApprovalStatus.APPROVED, "user42")

        assert updated is not None
        assert updated.status == ApprovalStatus.APPROVED
        assert updated.resolved_by == "user42"
        assert updated.resolved_at is not None

    def test_cannot_update_already_resolved(self, dynamodb_tables, order_details):
        """Should not update an already approved/rejected request."""
        request = create_approval_request("token-resolved", order_details, "live")
        update_approval_status(request.approval_id, ApprovalStatus.APPROVED, "user1")

        # Try to reject an already-approved request
        result = update_approval_status(request.approval_id, ApprovalStatus.REJECTED, "user2")
        assert result is None

        # Confirm it's still approved
        current = get_approval_request(request.approval_id)
        assert current.status == ApprovalStatus.APPROVED


class TestConsumeToken:
    def test_consumes_valid_token(self, dynamodb_tables, order_details):
        """Should consume a valid, unused token."""
        request = create_approval_request("token-consume", order_details, "live")
        consumed = consume_token(request.approval_id, request.token)
        assert consumed is True

    def test_rejects_wrong_token(self, dynamodb_tables, order_details):
        """Should reject an incorrect token."""
        request = create_approval_request("token-wrong", order_details, "live")
        consumed = consume_token(request.approval_id, "wrong-token")
        assert consumed is False

    def test_single_use_enforcement(self, dynamodb_tables, order_details):
        """Token should only be consumable once."""
        request = create_approval_request("token-single", order_details, "live")

        first = consume_token(request.approval_id, request.token)
        assert first is True

        second = consume_token(request.approval_id, request.token)
        assert second is False

    def test_rejects_non_pending(self, dynamodb_tables, order_details):
        """Should reject token consumption if request is not pending."""
        request = create_approval_request("token-non-pending", order_details, "live")
        update_approval_status(request.approval_id, ApprovalStatus.APPROVED, "user")

        consumed = consume_token(request.approval_id, request.token)
        assert consumed is False


class TestUpdateTelegramIds:
    def test_stores_telegram_ids(self, dynamodb_tables, order_details):
        """Should store Telegram message and chat IDs."""
        request = create_approval_request("token-tg", order_details, "live")
        update_telegram_ids(request.approval_id, message_id=42, chat_id=12345678)

        retrieved = get_approval_request(request.approval_id)
        assert retrieved.telegram_message_id == 42
        assert retrieved.telegram_chat_id == 12345678


class TestCheckAndExpire:
    def test_expires_past_due_request(self, dynamodb_tables, order_details):
        """Should expire a request past its expiry time."""
        request = create_approval_request("token-expire", order_details, "live")

        # Manually set expires_at to the past
        from qitp_mcp_2fa.token_store import _tokens_table

        _tokens_table().update_item(
            Key={"approval_id": request.approval_id},
            UpdateExpression="SET expires_at = :exp",
            ExpressionAttributeValues={
                ":exp": (datetime.utcnow() - timedelta(minutes=1)).isoformat()
            },
        )

        expired = check_and_expire_request(request.approval_id)
        assert expired is True

        retrieved = get_approval_request(request.approval_id)
        assert retrieved.status == ApprovalStatus.EXPIRED

    def test_does_not_expire_active_request(self, dynamodb_tables, order_details):
        """Should not expire a request that hasn't reached its expiry."""
        request = create_approval_request("token-active", order_details, "live")

        expired = check_and_expire_request(request.approval_id)
        assert expired is False

        retrieved = get_approval_request(request.approval_id)
        assert retrieved.status == ApprovalStatus.PENDING
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
ENV EXECUTION_MODE=live
ENV ENABLE_TELEGRAM_BOT=true

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
      - ENABLE_TELEGRAM_BOT=true
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
      - DYNAMODB_TOKENS_TABLE=${DYNAMODB_TOKENS_TABLE:-qitp_2fa_tokens}
      - DYNAMODB_EVENTS_TABLE=${DYNAMODB_EVENTS_TABLE:-qitp_2fa_events}
      - APPROVAL_TIMEOUT_SECONDS=${APPROVAL_TIMEOUT_SECONDS:-300}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
    restart: unless-stopped
    networks:
      - qitp

  # Local DynamoDB for development
  dynamodb-local:
    image: amazon/dynamodb-local:latest
    container_name: qitp-2fa-dynamodb
    ports:
      - "8000:8000"
    command: "-jar DynamoDBLocal.jar -sharedDb -inMemory"
    networks:
      - qitp

networks:
  qitp:
    driver: bridge
```

---

## Acceptance Criteria

- [ ] MCP server starts and lists 4 tools (`request_approval`, `verify_token`, `get_approval_status`, `reject_pending`)
- [ ] `request_approval` returns `auto_approved=True` immediately in backtest and paper modes
- [ ] `request_approval` sends Telegram message with inline Approve/Reject buttons in live mode
- [ ] Telegram callback handler processes Approve/Reject, updates DynamoDB, sends SFN callback
- [ ] `send_task_success` output matches P12's `TwoFactorGate` ResultSelector: `{approved, approver, timestamp}`
- [ ] Single-use token enforcement: token consumed on first `verify_token`, rejected on second
- [ ] `reject_pending` force-rejects a pending approval and sends SFN `send_task_failure`
- [ ] Cannot update already-resolved approvals (conditional expression on DynamoDB)
- [ ] Every gate event logged to `qitp_2fa_events` table with 5-year TTL (MiFID II)
- [ ] Expired requests auto-detected and marked via `check_and_expire_request`
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

This MCP server is a hard security boundary — no order reaches the broker without passing through it in live mode. The architecture is simple but the correctness guarantees are critical.

Key implementation notes:
1. **Auto-approval is a no-op in backtest/paper.** The `request_approval` tool detects `EXECUTION_MODE` and returns immediately. No Telegram message, no DynamoDB wait. But it still creates an audit record and sends the SFN callback so the workflow continues.
2. **Single-use tokens are enforced at DynamoDB level.** Use conditional expressions (`token = :token AND token_consumed = :false AND #status = :pending`) to prevent double-consumption. Never check-then-update — always use atomic conditional writes.
3. **SFN callback payload must match P12.** The `TwoFactorGate` state in P12 has a `ResultSelector` expecting `{approved, approver, timestamp}`. If the output shape changes, the workflow breaks.
4. **Concurrent approval defense.** Two Telegram taps on the same approval must not both succeed. The `update_approval_status` uses `ConditionExpression="#status = :pending"` to ensure only the first update wins.
5. **Audit everything.** Every state change goes to `qitp_2fa_events`. This is MiFID II mandated. If the audit write fails, log CRITICAL but do not block the approval flow — the order still needs to process.
6. **Credentials via env vars only.** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, AWS credentials — never hardcoded, never logged, never in error messages.
7. **Telegram bot lifecycle.** In dev/stdio mode, the bot runs in polling mode as a background asyncio task. In production HTTP mode, use webhook via API Gateway (not implemented in Phase 1 — polling is sufficient for single-user).
8. **5-minute timeout.** Default `APPROVAL_TIMEOUT_SECONDS=300`. After expiry, `check_and_expire_request` marks it expired and any subsequent actions are rejected. Phase 2 adds EventBridge scheduled rule for proactive expiry.
