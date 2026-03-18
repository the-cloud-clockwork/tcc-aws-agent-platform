"""poll_artifact tool implementation."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactResult, ArtifactType
from mcp_artifacts.storage import ArtifactStorage


async def poll_artifact(
    artifact_id: str,
    timeout_s: int = 60,
    storage: ArtifactStorage | None = None,
    catalog: ArtifactCatalog | None = None,
) -> dict[str, Any]:
    """Poll DynamoDB every 2s until the artifact is ready or timeout.

    Parameters
    ----------
    artifact_id:
        The UUID of the artifact to poll.
    timeout_s:
        Maximum seconds to wait (default 60).

    Returns
    -------
    dict with artifact_id, status, signed_url (if ready), type, metadata.
    """
    _storage = storage or ArtifactStorage()
    _catalog = catalog or ArtifactCatalog()

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
