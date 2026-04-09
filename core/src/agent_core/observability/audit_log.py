"""DynamoDB audit log writer.

Writes structured audit events to DynamoDB with configurable retention,
idempotency via conditional expressions, and query support by execution ID
or event type.

Usage::

    writer = AuditLogWriter(table_name="my_audit_log")
    writer.log(
        event_type="TASK_SUBMITTED",
        agent_id="execution_agent",
        execution_mode="production",
        payload={
            "target": "ENTITY-1",
            "action": "invoke",
            "result_count": 10,
        },
    )

Environment variables:
- ``AUDIT_TABLE`` -- DynamoDB table name override
- ``EXECUTION_MODE`` -- default execution mode if not provided per call
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from decimal import Decimal
from typing import Any

logger = logging.getLogger("agent_core.audit")

# Default 5-year retention in seconds
DEFAULT_RETENTION_SECONDS = 157_680_000  # ~5 years


def _to_dynamodb_safe(obj: Any) -> Any:
    """Convert a dict/list tree to DynamoDB-safe types.

    boto3's DynamoDB resource rejects raw ``float`` values with
    ``TypeError: Float types are not supported. Use Decimal types instead.``
    Agents routinely emit floats (gap percentages, volume ratios, confidence
    scores, latency metrics) through audit_log payloads, so the writer has to
    normalise the whole item before ``put_item``.

    Strategy: JSON round-trip with ``parse_float=Decimal``. This walks the
    entire nested structure once, converts floats → Decimal, leaves ints/
    strings/bools alone, and coerces non-JSON-serialisable leaves (datetime,
    UUID, Pydantic models) to strings via ``default=str``.
    """
    return json.loads(json.dumps(obj, default=str), parse_float=Decimal)


class AuditLogError(Exception):
    """Raised when an audit log write fails."""


class AuditLogWriter:
    """Writes audit events to DynamoDB with idempotency and TTL.

    Parameters
    ----------
    table_name:
        DynamoDB table name. Defaults to ``AUDIT_TABLE`` env var.
    dynamodb_client:
        Optional boto3 DynamoDB client (injected for testing).
    retention_seconds:
        TTL duration in seconds. Default: 5 years.
    """

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_client: Any = None,
        retention_seconds: int = DEFAULT_RETENTION_SECONDS,
    ) -> None:
        self.table_name = table_name or os.getenv("AUDIT_TABLE", "audit_log")
        self._client = dynamodb_client
        self._retention_seconds = retention_seconds

    def _get_client(self) -> Any:
        """Lazily initialize the DynamoDB client."""
        if self._client is None:
            import boto3  # type: ignore[import-untyped]

            self._client = boto3.resource("dynamodb").Table(self.table_name)
        return self._client

    def log(
        self,
        event_type: str,
        agent_id: str = "",
        execution_mode: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        """Write an audit event to DynamoDB.

        Parameters
        ----------
        event_type:
            Event type string (e.g. ``PIPELINE_STARTED``, ``TASK_SUBMITTED``).
        agent_id:
            Agent that generated the event.
        execution_mode:
            ``simulation``, ``staging``, or ``production``.
        payload:
            Event-specific data dict.
        idempotency_key:
            Unique key for deduplication. Auto-generated if not provided.
        execution_id:
            Pipeline execution ID for correlation.

        Returns
        -------
        The complete item dict that was written.
        """
        mode = execution_mode or os.getenv("EXECUTION_MODE", "")
        payload = payload or {}

        now_ms = int(time.time() * 1000)
        event_id = idempotency_key or str(uuid.uuid4())
        ttl = int(time.time()) + self._retention_seconds

        item: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event_type
            if isinstance(event_type, str)
            else event_type.value,
            "timestamp_ms": now_ms,
            "timestamp_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now_ms / 1000)
            ),
            "agent_id": agent_id,
            "execution_mode": mode,
            "execution_id": execution_id or os.getenv("SFN_EXECUTION_ID", "unknown"),
            "payload": payload,
            "ttl": ttl,
        }

        event_type_str = event_type if isinstance(event_type, str) else event_type.value
        logger.info(
            "Audit event: type=%s agent=%s mode=%s event_id=%s",
            event_type_str,
            agent_id,
            mode,
            event_id,
        )

        try:
            table = self._get_client()
            # Normalise floats → Decimal (DynamoDB requirement) and coerce
            # non-JSON-serialisable leaves to strings before PutItem.
            safe_item = _to_dynamodb_safe(item)
            # Condition expression ensures idempotency -- no overwrite if event_id exists
            table.put_item(
                Item=safe_item,
                ConditionExpression="attribute_not_exists(event_id)",
            )
        except Exception as exc:
            # ClientError for ConditionalCheckFailedException means duplicate -- that's OK
            exc_name = type(exc).__name__
            if (
                "ConditionalCheckFailed" in str(exc)
                or "ConditionalCheckFailed" in exc_name
            ):
                logger.warning("Duplicate audit event ignored: %s", event_id)
            else:
                logger.error("Failed to write audit event: %s", exc)
                raise AuditLogError(f"Failed to write audit event: {exc}") from exc

        return item

    def query_by_execution(self, execution_id: str) -> list[dict[str, Any]]:
        """Query all audit events for a given execution ID.

        Requires a GSI ``execution_id-index`` on the audit log table.

        Parameters
        ----------
        execution_id:
            The execution ID or pipeline run ID.

        Returns
        -------
        List of audit event dicts sorted by timestamp.
        """
        table = self._get_client()
        try:
            response = table.query(
                IndexName="execution_id-index",
                KeyConditionExpression="execution_id = :eid",
                ExpressionAttributeValues={":eid": execution_id},
            )
            items = response.get("Items", [])
            return sorted(items, key=lambda x: x.get("timestamp_ms", 0))
        except Exception as exc:
            logger.error("Failed to query audit log: %s", exc)
            raise AuditLogError(f"Failed to query audit log: {exc}") from exc

    def query_by_type(
        self,
        event_type: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query recent audit events of a given type.

        Requires a GSI ``event_type-index`` on the audit log table.

        Parameters
        ----------
        event_type:
            The event type to query.
        limit:
            Maximum number of results.

        Returns
        -------
        List of audit event dicts sorted by timestamp descending.
        """
        table = self._get_client()
        event_type_str = event_type if isinstance(event_type, str) else event_type.value
        try:
            response = table.query(
                IndexName="event_type-index",
                KeyConditionExpression="event_type = :et",
                ExpressionAttributeValues={":et": event_type_str},
                ScanIndexForward=False,
                Limit=limit,
            )
            return response.get("Items", [])
        except Exception as exc:
            logger.error("Failed to query audit log: %s", exc)
            raise AuditLogError(f"Failed to query audit log: {exc}") from exc
