"""Tests for create_artifact tool."""

from __future__ import annotations

import json

import pytest

from mcp_artifacts.tools.create import create_artifact


@pytest.mark.asyncio
async def test_create_report(mock_aws_all):
    """Create a report artifact and verify S3 + DynamoDB state."""
    storage, catalog = mock_aws_all

    result = await create_artifact(
        type="report",
        content="# My Report\n\nSome analysis here.",
        metadata={"title": "Q1 Analysis"},
        agent_id="research-agent",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["artifact_id"]
    assert result["s3_key"].endswith("/artifact.md")

    # Verify DynamoDB entry
    entry = catalog.get_entry(result["artifact_id"])
    assert entry is not None
    assert entry["status"] == "ready"
    assert entry["type"] == "report"
    assert entry["agent_id"] == "research-agent"


@pytest.mark.asyncio
async def test_create_chart(mock_aws_all):
    """Create a chart artifact (JSX content)."""
    storage, catalog = mock_aws_all

    jsx_content = "<BarChart data={data}><Bar dataKey='value' /></BarChart>"
    result = await create_artifact(
        type="chart",
        content=jsx_content,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.jsx")


@pytest.mark.asyncio
async def test_create_simulation_result(mock_aws_all):
    """Create a simulation_result artifact (JSON content)."""
    storage, catalog = mock_aws_all

    content = json.dumps({"sharpe_ratio": 1.5, "max_drawdown": -0.12})
    result = await create_artifact(
        type="simulation_result",
        content=content,
        metadata={"strategy": "momentum"},
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.json")


@pytest.mark.asyncio
async def test_create_image(mock_aws_all):
    """Create an image artifact (base64 content)."""
    import base64

    storage, catalog = mock_aws_all

    # Minimal 1x1 PNG
    fake_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()
    result = await create_artifact(
        type="image",
        content=fake_png,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.png")


@pytest.mark.asyncio
async def test_create_data_export(mock_aws_all):
    """Create a data_export artifact (CSV content)."""
    storage, catalog = mock_aws_all

    csv_content = "date,target,close\n2025-01-01,ITEM-A,100.50\n2025-01-02,ITEM-A,101.10"
    result = await create_artifact(
        type="data_export",
        content=csv_content,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.csv")


@pytest.mark.asyncio
async def test_create_recommendation(mock_aws_all):
    """Create a recommendation artifact."""
    storage, catalog = mock_aws_all

    content = json.dumps({
        "action": "BUY",
        "target": "ENTITY-1",
        "confidence": 0.85,
        "rationale": "Strong momentum signals",
    })
    result = await create_artifact(
        type="recommendation",
        content=content,
        agent_id="signal-agent",
        execution_id="exec-001",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.json")

    entry = catalog.get_entry(result["artifact_id"])
    assert entry["agent_id"] == "signal-agent"
    assert entry["execution_id"] == "exec-001"


@pytest.mark.asyncio
async def test_create_invalid_type(mock_aws_all):
    """Invalid artifact type raises ValueError."""
    storage, catalog = mock_aws_all

    with pytest.raises(ValueError):
        await create_artifact(
            type="invalid_type",
            content="stuff",
            storage=storage,
            catalog=catalog,
        )
