"""list_artifacts tool implementation."""

from __future__ import annotations

from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactMeta, ArtifactType


async def list_artifacts(
    type: str | None = None,
    agent_id: str | None = None,
    date: str | None = None,
    limit: int = 50,
    execution_id: str | None = None,
    catalog: ArtifactCatalog | None = None,
) -> list[dict[str, Any]]:
    """List artifacts with optional filters. Returns metadata only, no URLs.

    Parameters
    ----------
    type:
        Filter by ArtifactType value (e.g. "chart", "report").
    agent_id:
        Filter by the agent that created the artifact.
    date:
        Filter by date prefix (YYYY-MM-DD).
    limit:
        Max results to return (default 50).

    Returns
    -------
    list of ArtifactMeta dicts (no signed_url).
    """
    _catalog = catalog or ArtifactCatalog()

    if execution_id:
        entries = _catalog.list_by_execution(execution_id)
    else:
        entries = _catalog.list_entries(
            artifact_type=type,
            agent_id=agent_id,
            date=date,
            limit=limit,
        )

    results: list[dict[str, Any]] = []
    for entry in entries:
        meta = ArtifactMeta(
            artifact_id=entry["artifact_id"],
            type=ArtifactType(entry["type"]),
            status=entry["status"],
            s3_key=entry["s3_key"],
            signed_url=None,
            agent_id=entry.get("agent_id"),
            execution_id=entry.get("execution_id"),
            created_at=entry["created_at"],
            expires_at=None,
            metadata=entry.get("metadata", {}),
        )
        results.append(meta.model_dump(mode="json"))

    return results
