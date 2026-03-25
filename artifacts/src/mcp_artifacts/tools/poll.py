"""poll_artifact tool implementation.

.. deprecated::
    With the synchronous ``create_artifact`` changes, artifacts are returned
    with ``status=ready`` and a ``signed_url`` immediately on creation.
    For async workflows, subscribe to the ``artifact-notifications`` SQS queue
    instead of polling DynamoDB. This tool is retained for backward
    compatibility only.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactResult, ArtifactType
from mcp_artifacts.storage import ArtifactStorage

logger = logging.getLogger(__name__)


async def poll_artifact(
    artifact_id: str,
    timeout_s: int = 30,
    storage: ArtifactStorage | None = None,
    catalog: ArtifactCatalog | None = None,
) -> dict[str, Any]:
    """Poll DynamoDB every 2s until the artifact is ready or timeout.

    .. deprecated::
        Prefer consuming the ``artifact-notifications`` SQS queue for
        event-driven artifact readiness checks. ``create_artifact`` now
        returns ``signed_url`` directly on success.

    Parameters
    ----------
    artifact_id:
        The UUID of the artifact to poll.
    timeout_s:
        Maximum seconds to wait (default 30).

    Returns
    -------
    dict with artifact_id, status, signed_url (if ready), type, metadata.
    """
    _storage = storage or ArtifactStorage()
    _catalog = catalog or ArtifactCatalog()

    logger.info(
        "poll_artifact called for %s — consider using SQS notifications instead",
        artifact_id,
    )

    elapsed = 0.0
    poll_interval = 2.0

    while elapsed < timeout_s:
        entry = _catalog.get_entry(artifact_id)

        if entry is None:
            return ArtifactResult(
                artifact_id=artifact_id,
                status="not_found",
            ).model_dump()

        if entry["status"] in ("ready", "error"):
            signed_url = None
            if entry["status"] == "ready":
                signed_url = _storage.generate_signed_url(entry["s3_key"])

            artifact_type = ArtifactType(entry["type"]) if "type" in entry else None
            meta = entry.get("metadata", {})

            return ArtifactResult(
                artifact_id=artifact_id,
                status=entry["status"],
                signed_url=signed_url,
                type=artifact_type,
                metadata=meta,
            ).model_dump()

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout reached
    return ArtifactResult(
        artifact_id=artifact_id,
        status="timeout",
    ).model_dump()
