"""DynamoDB-backed idempotency enforcement."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def generate_idempotency_key(
    agent_id: str,
    operation: str,
    params: dict[str, Any] | None = None,
    execution_id: str | None = None,
) -> str:
    """Generate idempotency key: {agent_id}:{execution_id}:{operation}:{param_hash}."""
    if execution_id is None:
        execution_id = (
            os.environ.get("SFN_EXECUTION_ID")
            or os.environ.get("AWS_REQUEST_ID")
            or str(uuid.uuid4())
        )
    param_hash = hashlib.sha256(
        json.dumps(params or {}, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"{agent_id}:{execution_id}:{operation}:{param_hash}"


class IdempotencyStore:
    """DynamoDB-backed idempotency check/store.

    Graceful degradation: if table missing or DynamoDB unavailable,
    logs warning and proceeds without caching.
    """

    def __init__(self, table_name: str | None = None) -> None:
        self._table_name = table_name or os.environ["IDEMPOTENCY_TABLE"]
        self._table = None

    def _get_table(self) -> Any:
        if self._table is None:
            try:
                import boto3

                self._table = boto3.resource("dynamodb").Table(self._table_name)
            except Exception:
                logger.warning(
                    "Cannot connect to DynamoDB table '%s'", self._table_name
                )
        return self._table

    def check(self, key: str) -> dict[str, Any] | None:
        """Return cached result if idempotency key exists, else None."""
        table = self._get_table()
        if table is None:
            return None
        try:
            resp = table.get_item(Key={"idempotency_key": key})
            item = resp.get("Item")
            if item:
                logger.info("Idempotency cache hit: %s", key)
                result_json = item.get("result")
                if isinstance(result_json, str):
                    return json.loads(result_json)
                return result_json
            return None
        except Exception:
            logger.warning(
                "Idempotency check failed for '%s', proceeding", key, exc_info=True
            )
            return None

    def store(self, key: str, result: dict[str, Any], ttl_hours: int = 24) -> None:
        """Store result with TTL. Idempotent (no-op if key exists)."""
        table = self._get_table()
        if table is None:
            return
        try:
            table.put_item(
                Item={
                    "idempotency_key": key,
                    "result": json.dumps(result, default=str),
                    "ttl": int(time.time()) + ttl_hours * 3600,
                },
                ConditionExpression="attribute_not_exists(idempotency_key)",
            )
            logger.info("Idempotency stored: %s (ttl=%dh)", key, ttl_hours)
        except Exception as exc:
            if "ConditionalCheckFailedException" in str(exc):
                logger.info("Idempotency key already exists: %s", key)
            else:
                logger.warning("Idempotency store failed for '%s'", key, exc_info=True)
