"""SQS artifact notification publisher.

Publishes status-change events to the artifact-notifications queue so downstream
consumers (Step Functions, agents) can react without polling DynamoDB.

The queue URL is read from ARTIFACT_QUEUE_URL. If unset, notifications are silently
skipped — this allows local development without SQS.
"""

from __future__ import annotations

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)


def publish_artifact_notification(
    artifact_id: str,
    status: str,
    artifact_type: str,
    agent_id: str = "",
    execution_id: str = "",
    *,
    sqs_client=None,
) -> None:
    """Publish an artifact status-change event to SQS.

    Args:
        artifact_id: UUID of the artifact.
        status: New status (``ready`` or ``error``).
        artifact_type: Artifact type enum value.
        agent_id: Agent that created the artifact.
        execution_id: Pipeline execution ID.
        sqs_client: Optional boto3 SQS client (for testing).
    """
    queue_url = os.environ.get("ARTIFACT_QUEUE_URL", "")
    if not queue_url:
        return

    client = sqs_client or boto3.client("sqs")
    message = {
        "artifact_id": artifact_id,
        "status": status,
        "type": artifact_type,
        "agent_id": agent_id,
        "execution_id": execution_id,
    }

    try:
        client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
        )
        logger.debug("Published artifact notification: %s -> %s", artifact_id, status)
    except Exception:
        logger.warning(
            "Failed to publish artifact notification for %s",
            artifact_id,
            exc_info=True,
        )
