"""get_artifact tool implementation."""

from __future__ import annotations

from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactResult, ArtifactType
from mcp_artifacts.storage import ArtifactStorage


async def get_artifact(  # noqa: S7503 — async required by MCP server framework
    artifact_id: str,
    storage: ArtifactStorage | None = None,
    catalog: ArtifactCatalog | None = None,
) -> dict[str, Any]:
    """Retrieve artifact metadata and signed URL if ready.

    Parameters
    ----------
    artifact_id:
        The UUID of the artifact to retrieve.

    Returns
    -------
    dict with artifact_id, status, signed_url (if ready), type, metadata.
    """
    _storage = storage or ArtifactStorage()
    _catalog = catalog or ArtifactCatalog()

    entry = _catalog.get_entry(artifact_id)
    if entry is None:
        return ArtifactResult(
            artifact_id=artifact_id,
            status="not_found",
        ).model_dump()

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
