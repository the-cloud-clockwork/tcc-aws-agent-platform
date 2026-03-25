"""DynamoDB operations for prompt metadata CRUD."""

from __future__ import annotations

from datetime import UTC, datetime

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from prompt_registry.models import PromptStatus, PromptVersion

DEFAULT_TABLE = "prompt_registry"


class PromptRegistry:
    """DynamoDB-backed prompt metadata store."""

    def __init__(
        self,
        table_name: str = DEFAULT_TABLE,
        dynamodb_resource=None,
    ) -> None:
        self.table_name = table_name
        dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self.table = dynamodb.Table(table_name)

    def put_version(self, prompt: PromptVersion) -> None:
        """Write a prompt version record to DynamoDB."""
        self.table.put_item(Item=prompt.model_dump())

    def get_version(
        self, prompt_id: str, version: str
    ) -> PromptVersion | None:
        """Get a specific prompt version."""
        resp = self.table.get_item(
            Key={"prompt_key": prompt_id, "version": version}
        )
        item = resp.get("Item")
        if not item:
            return None
        return PromptVersion(**item)

    def list_versions(self, prompt_id: str) -> list[PromptVersion]:
        """List all versions for a prompt_id, sorted by version."""
        resp = self.table.query(
            KeyConditionExpression=Key("prompt_key").eq(prompt_id)
        )
        items = resp.get("Items", [])
        versions = [PromptVersion(**item) for item in items]
        versions.sort(key=lambda v: _version_sort_key(v.version))
        return versions

    def get_latest_stable(self, prompt_id: str) -> PromptVersion | None:
        """Get the latest stable version for a prompt_id."""
        versions = self.list_versions(prompt_id)
        stable = [v for v in versions if v.status == PromptStatus.STABLE]
        if not stable:
            return None
        return stable[-1]

    def get_latest_draft(self, prompt_id: str) -> PromptVersion | None:
        """Get the latest draft version for a prompt_id."""
        versions = self.list_versions(prompt_id)
        drafts = [v for v in versions if v.status == PromptStatus.DRAFT]
        if not drafts:
            return None
        return drafts[-1]

    def update_status(
        self, prompt_id: str, version: str, new_status: PromptStatus
    ) -> PromptVersion | None:
        """Update the status of a prompt version."""
        now = datetime.now(UTC).isoformat()
        try:
            resp = self.table.update_item(
                Key={"prompt_key": prompt_id, "version": version},
                UpdateExpression="SET #s = :status, updated_at = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":status": new_status.value,
                    ":now": now,
                },
                ReturnValues="ALL_NEW",
                ConditionExpression="attribute_exists(prompt_id)",
            )
            return PromptVersion(**resp["Attributes"])
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

    def promote(self, prompt_id: str, version: str) -> PromptVersion | None:
        """
        Promote a version to stable.
        Deprecates the current stable version first.
        """
        # Deprecate current stable
        current_stable = self.get_latest_stable(prompt_id)
        if current_stable and current_stable.version != version:
            self.update_status(
                prompt_id,
                current_stable.version,
                PromptStatus.DEPRECATED,
            )

        return self.update_status(prompt_id, version, PromptStatus.STABLE)

    def rollback(self, prompt_id: str, version: str) -> PromptVersion | None:
        """
        Rollback to a specific version.
        Deprecates the current stable and promotes the target version.
        """
        target = self.get_version(prompt_id, version)
        if not target:
            return None

        # Deprecate current stable
        current_stable = self.get_latest_stable(prompt_id)
        if current_stable and current_stable.version != version:
            self.update_status(
                prompt_id,
                current_stable.version,
                PromptStatus.DEPRECATED,
            )

        return self.update_status(prompt_id, version, PromptStatus.STABLE)


def _version_sort_key(version: str) -> tuple[int, ...]:
    """Convert semver string to tuple for sorting."""
    parts = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    # Pad to 3 components
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)
