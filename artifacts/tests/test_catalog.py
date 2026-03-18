"""Tests for DynamoDB catalog operations."""

from __future__ import annotations

import pytest

from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.list_artifacts import list_artifacts


@pytest.mark.asyncio
async def test_list_by_type(mock_aws_all):
    """list_artifacts filters by artifact type."""
    storage, catalog = mock_aws_all

    await create_artifact(type="report", content="# R1", storage=storage, catalog=catalog)
    await create_artifact(type="report", content="# R2", storage=storage, catalog=catalog)
    await create_artifact(type="chart", content="<Chart/>", storage=storage, catalog=catalog)

    results = await list_artifacts(type="report", catalog=catalog)
    assert len(results) == 2
    assert all(r["type"] == "report" for r in results)


@pytest.mark.asyncio
async def test_list_by_agent_id(mock_aws_all):
    """list_artifacts filters by agent_id."""
    storage, catalog = mock_aws_all

    await create_artifact(
        type="report", content="# R1", agent_id="agent-a", storage=storage, catalog=catalog
    )
    await create_artifact(
        type="chart", content="<C/>", agent_id="agent-b", storage=storage, catalog=catalog
    )
    await create_artifact(
        type="report", content="# R2", agent_id="agent-a", storage=storage, catalog=catalog
    )

    results = await list_artifacts(agent_id="agent-a", catalog=catalog)
    assert len(results) == 2
    assert all(r["agent_id"] == "agent-a" for r in results)


@pytest.mark.asyncio
async def test_list_with_limit(mock_aws_all):
    """list_artifacts respects the limit parameter."""
    storage, catalog = mock_aws_all

    for i in range(5):
        await create_artifact(type="report", content=f"# R{i}", storage=storage, catalog=catalog)

    results = await list_artifacts(type="report", limit=3, catalog=catalog)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_list_no_filters(mock_aws_all):
    """list_artifacts with no filters returns all (scan)."""
    storage, catalog = mock_aws_all

    await create_artifact(type="report", content="# R", storage=storage, catalog=catalog)
    await create_artifact(type="chart", content="<C/>", storage=storage, catalog=catalog)

    results = await list_artifacts(catalog=catalog)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_catalog_create_and_get(mock_aws_all):
    """Direct catalog create + get roundtrip."""
    _, catalog = mock_aws_all

    catalog.create_entry(
        artifact_id="test-123",
        artifact_type="report",
        s3_key="test-123/artifact.md",
        agent_id="agent-x",
        metadata={"key": "value"},
    )

    entry = catalog.get_entry("test-123")
    assert entry is not None
    assert entry["artifact_id"] == "test-123"
    assert entry["type"] == "report"
    assert entry["status"] == "processing"
    assert entry["agent_id"] == "agent-x"
    assert entry["metadata"] == {"key": "value"}


@pytest.mark.asyncio
async def test_catalog_update_status(mock_aws_all):
    """Catalog status update works."""
    _, catalog = mock_aws_all

    catalog.create_entry(
        artifact_id="test-456",
        artifact_type="chart",
        s3_key="test-456/artifact.jsx",
    )

    catalog.update_status("test-456", "ready")
    entry = catalog.get_entry("test-456")
    assert entry["status"] == "ready"

    catalog.update_status("test-456", "error")
    entry = catalog.get_entry("test-456")
    assert entry["status"] == "error"
