"""DynamoDB catalog operations for artifact metadata."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger(__name__)

TABLE_NAME = os.environ.get("ARTIFACTS_TABLE", "mcp_artifacts")


class ArtifactCatalog:
    """DynamoDB CRUD for the artifact catalog table."""

    def __init__(self, dynamodb_resource=None, table_name: str = TABLE_NAME) -> None:
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table_name = table_name
        self._table = self._dynamodb.Table(table_name)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_entry(
        self,
        artifact_id: str,
        artifact_type: str,
        s3_key: str,
        agent_id: str | None = None,
        execution_id: str | None = None,
        metadata: dict | None = None,
        idempotency_key: str | None = None,
        tier: str = "platform",
        kms_key_alias: str | None = None,
        pipeline_date: str = "",
    ) -> dict[str, Any]:
        """Insert a new catalog entry with status=processing."""
        now = datetime.now(UTC).isoformat()
        item: dict[str, Any] = {
            "artifact_id": artifact_id,
            "type": artifact_type,
            "status": "processing",
            "s3_key": s3_key,
            "created_at": now,
            "metadata": json.dumps(metadata or {}),
            "tier": tier,
        }
        if agent_id:
            item["agent_id"] = agent_id
        if execution_id:
            item["execution_id"] = execution_id
        if idempotency_key:
            item["idempotency_key"] = idempotency_key
        if kms_key_alias:
            item["kms_key_alias"] = kms_key_alias
        if pipeline_date:
            item["pipeline_date"] = pipeline_date

        self._table.put_item(Item=item)
        logger.info("Created catalog entry %s (type=%s)", artifact_id, artifact_type)
        return item

    def update_status(self, artifact_id: str, status: str) -> None:
        """Update the status field of an artifact."""
        self._table.update_item(
            Key={"artifact_id": artifact_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status},
        )
        logger.info("Updated %s status to %s", artifact_id, status)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        """Look up an artifact by its idempotency_key.

        Uses a scan with filter (POC). Production should use a GSI.
        """
        resp = self._table.scan(
            FilterExpression=Attr("idempotency_key").eq(key),
            Limit=1,
        )
        items = resp.get("Items", [])
        if items:
            item = items[0]
            if "metadata" in item and isinstance(item["metadata"], str):
                item["metadata"] = json.loads(item["metadata"])
            return item
        return None

    def get_entry(self, artifact_id: str) -> dict[str, Any] | None:
        """Fetch a single catalog entry by artifact_id (PK)."""
        resp = self._table.get_item(Key={"artifact_id": artifact_id})
        item = resp.get("Item")
        if item and "metadata" in item and isinstance(item["metadata"], str):
            item["metadata"] = json.loads(item["metadata"])
        return item

    def list_entries(
        self,
        artifact_type: str | None = None,
        agent_id: str | None = None,
        date: str | None = None,
        limit: int = 50,
        execution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query/scan the catalog with optional filters.

        Filters:
        - artifact_type: use GSI1 (type-created_at-index)
        - agent_id: use GSI2 (agent_id-created_at-index)
        - date: filter created_at begins_with date string (YYYY-MM-DD)
        - If no type/agent_id provided, falls back to table scan with filters.
        """
        if execution_id:
            resp = self._scan_with_execution_id(execution_id, artifact_type, agent_id, date, limit)
        elif artifact_type:
            resp = self._query_by_type(artifact_type, agent_id, date, limit)
        elif agent_id:
            resp = self._query_by_agent(agent_id, date, limit)
        else:
            resp = self._scan_with_filters(date, limit)

        items = resp.get("Items", [])
        for item in items:
            if "metadata" in item and isinstance(item["metadata"], str):
                item["metadata"] = json.loads(item["metadata"])
        return items

    def list_by_execution(self, execution_id: str) -> list[dict[str, Any]]:
        """List all artifacts for a given execution_id."""
        return self.list_entries(execution_id=execution_id, limit=200)

    def _scan_with_execution_id(
        self,
        execution_id: str,
        artifact_type: str | None,
        agent_id: str | None,
        date: str | None,
        limit: int,
    ) -> dict[str, Any]:
        filter_expr = Attr("execution_id").eq(execution_id)
        if artifact_type:
            filter_expr &= Attr("type").eq(artifact_type)
        if agent_id:
            filter_expr &= Attr("agent_id").eq(agent_id)
        if date:
            filter_expr &= Attr("created_at").begins_with(date)
        return self._table.scan(FilterExpression=filter_expr, Limit=limit)

    def _query_by_type(
        self, artifact_type: str, agent_id: str | None, date: str | None, limit: int
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "IndexName": "type-created_at-index",
            "KeyConditionExpression": Key("type").eq(artifact_type),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if date:
            kwargs["KeyConditionExpression"] &= Key("created_at").begins_with(date)
        if agent_id:
            kwargs["FilterExpression"] = Attr("agent_id").eq(agent_id)
        return self._table.query(**kwargs)

    def _query_by_agent(self, agent_id: str, date: str | None, limit: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "IndexName": "agent_id-created_at-index",
            "KeyConditionExpression": Key("agent_id").eq(agent_id),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if date:
            kwargs["KeyConditionExpression"] &= Key("created_at").begins_with(date)
        return self._table.query(**kwargs)

    def _scan_with_filters(self, date: str | None, limit: int) -> dict[str, Any]:
        scan_kwargs: dict[str, Any] = {"Limit": limit}
        if date:
            scan_kwargs["FilterExpression"] = Attr("created_at").begins_with(date)
        return self._table.scan(**scan_kwargs)

