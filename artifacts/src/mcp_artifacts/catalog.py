"""DynamoDB catalog operations for artifact metadata."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table

logger = logging.getLogger(__name__)

TABLE_NAME = "mcp_artifacts"


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
    ) -> dict[str, Any]:
        """Insert a new catalog entry with status=processing."""
        now = datetime.now(timezone.utc).isoformat()
        item: dict[str, Any] = {
            "artifact_id": artifact_id,
            "type": artifact_type,
            "status": "processing",
            "s3_key": s3_key,
            "created_at": now,
            "metadata": json.dumps(metadata or {}),
        }
        if agent_id:
            item["agent_id"] = agent_id
        if execution_id:
            item["execution_id"] = execution_id
        if idempotency_key:
            item["idempotency_key"] = idempotency_key

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
    ) -> list[dict[str, Any]]:
        """Query/scan the catalog with optional filters.

        Filters:
        - artifact_type: use GSI1 (type-created_at-index)
        - agent_id: use GSI2 (agent_id-created_at-index)
        - date: filter created_at begins_with date string (YYYY-MM-DD)
        - If no type/agent_id provided, falls back to table scan with filters.
        """
        if artifact_type:
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

    # ------------------------------------------------------------------
    # Table bootstrap (for tests / local dev)
    # ------------------------------------------------------------------

    @classmethod
    def ensure_table(cls, dynamodb_resource=None, table_name: str = TABLE_NAME):
        """Create the DynamoDB table if it does not exist. Used in tests."""
        ddb = dynamodb_resource or boto3.resource("dynamodb")
        try:
            table = ddb.Table(table_name)
            table.load()
            return table
        except Exception:
            pass

        table = ddb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "artifact_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "artifact_id", "AttributeType": "S"},
                {"AttributeName": "type", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "agent_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "type-created_at-index",
                    "KeySchema": [
                        {"AttributeName": "type", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "agent_id-created_at-index",
                    "KeySchema": [
                        {"AttributeName": "agent_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        return table
