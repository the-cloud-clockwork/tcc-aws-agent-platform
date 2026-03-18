"""Tests for get_artifact and poll_artifact tools."""

from __future__ import annotations

import pytest

from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.get import get_artifact
from mcp_artifacts.tools.poll import poll_artifact


@pytest.mark.asyncio
async def test_get_ready_artifact(mock_aws_all):
    """get_artifact returns signed URL for a ready artifact."""
    storage, catalog = mock_aws_all

    created = await create_artifact(
        type="report",
        content="# Report",
        storage=storage,
        catalog=catalog,
    )

    result = await get_artifact(
        artifact_id=created["artifact_id"],
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["signed_url"] is not None
    assert "mcp-artifacts" in result["signed_url"]
    assert result["type"] == "report"


@pytest.mark.asyncio
async def test_get_not_found(mock_aws_all):
    """get_artifact returns not_found for missing artifact."""
    storage, catalog = mock_aws_all

    result = await get_artifact(
        artifact_id="nonexistent-id",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "not_found"
    assert result["signed_url"] is None


@pytest.mark.asyncio
async def test_get_processing_artifact(mock_aws_all):
    """get_artifact returns processing status without URL."""
    storage, catalog = mock_aws_all

    # Manually create a processing entry (no S3 upload)
    catalog.create_entry(
        artifact_id="test-processing-id",
        artifact_type="chart",
        s3_key="test-processing-id/artifact.jsx",
    )

    result = await get_artifact(
        artifact_id="test-processing-id",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "processing"
    assert result["signed_url"] is None


@pytest.mark.asyncio
async def test_poll_ready_artifact(mock_aws_all):
    """poll_artifact returns immediately if artifact is already ready."""
    storage, catalog = mock_aws_all

    created = await create_artifact(
        type="report",
        content="# Report",
        storage=storage,
        catalog=catalog,
    )

    result = await poll_artifact(
        artifact_id=created["artifact_id"],
        timeout_s=5,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["signed_url"] is not None


@pytest.mark.asyncio
async def test_poll_not_found(mock_aws_all):
    """poll_artifact returns not_found immediately."""
    storage, catalog = mock_aws_all

    result = await poll_artifact(
        artifact_id="nonexistent",
        timeout_s=2,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_poll_error_artifact(mock_aws_all):
    """poll_artifact returns error status immediately."""
    storage, catalog = mock_aws_all

    catalog.create_entry(
        artifact_id="error-artifact",
        artifact_type="report",
        s3_key="error-artifact/artifact.md",
    )
    catalog.update_status("error-artifact", "error")

    result = await poll_artifact(
        artifact_id="error-artifact",
        timeout_s=5,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "error"
    assert result["signed_url"] is None
