"""Tests for mcp_artifacts.tools — create, get, list_artifacts are sync (not async)."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.get import get_artifact
from mcp_artifacts.tools.list_artifacts import list_artifacts


class TestCreateArtifact:
    def test_is_not_coroutine(self) -> None:
        """create_artifact must be a regular function, not async."""
        assert not inspect.iscoroutinefunction(create_artifact)

    def test_creates_artifact(self) -> None:
        storage = MagicMock()
        catalog = MagicMock()
        catalog.get_by_idempotency_key.return_value = None

        result = create_artifact(
            type="report",
            content="hello world",
            agent_id="agent-1",
            execution_id="exec-1",
            storage=storage,
            catalog=catalog,
        )

        assert result["status"] == "ready"
        assert "artifact_id" in result
        catalog.create_entry.assert_called_once()
        storage.put_object.assert_called_once()

    def test_rejects_truncated_json_for_json_types(self) -> None:
        """Brace-short JSON for a JSON artifact type must raise — never be
        stored as 'ready' (the recommender truncation soft failure)."""
        import pytest

        storage = MagicMock()
        catalog = MagicMock()
        catalog.get_by_idempotency_key.return_value = None

        with pytest.raises(ValueError, match="not valid JSON"):
            create_artifact(
                type="recommendation",
                content='{"recommendations": [{"symbol": "AVGO"}',
                agent_id="portfolio-recommender",
                execution_id="exec-1",
                storage=storage,
                catalog=catalog,
            )

        catalog.create_entry.assert_not_called()
        storage.put_object.assert_not_called()

    def test_accepts_valid_json_for_json_types(self) -> None:
        storage = MagicMock()
        catalog = MagicMock()
        catalog.get_by_idempotency_key.return_value = None

        result = create_artifact(
            type="recommendation",
            content='{"recommendations": [{"symbol": "AVGO"}]}',
            agent_id="portfolio-recommender",
            execution_id="exec-1",
            storage=storage,
            catalog=catalog,
        )

        assert result["status"] == "ready"
        storage.put_object.assert_called_once()

    def test_idempotency_returns_existing(self) -> None:
        catalog = MagicMock()
        catalog.get_by_idempotency_key.return_value = {
            "artifact_id": "existing-id",
            "status": "ready",
            "s3_key": "tier/existing.json",
        }

        result = create_artifact(
            type="report",
            content="hello",
            idempotency_key="key-1",
            catalog=catalog,
        )

        assert result["artifact_id"] == "existing-id"
        catalog.create_entry.assert_not_called()


class TestGetArtifact:
    def test_is_not_coroutine(self) -> None:
        assert not inspect.iscoroutinefunction(get_artifact)

    def test_not_found(self) -> None:
        catalog = MagicMock()
        catalog.get_entry.return_value = None

        result = get_artifact("missing-id", catalog=catalog)
        assert result["status"] == "not_found"

    def test_found_ready(self) -> None:
        catalog = MagicMock()
        catalog.get_entry.return_value = {
            "status": "ready",
            "s3_key": "tier/abc/report.json",
            "type": "report",
            "metadata": {},
        }
        storage = MagicMock()
        storage.get_best_url.return_value = "https://signed-url"

        result = get_artifact("abc", storage=storage, catalog=catalog)
        assert result["status"] == "ready"
        assert result["signed_url"] == "https://signed-url"


class TestListArtifacts:
    def test_is_not_coroutine(self) -> None:
        assert not inspect.iscoroutinefunction(list_artifacts)

    def test_empty_list(self) -> None:
        catalog = MagicMock()
        catalog.list_entries.return_value = []

        result = list_artifacts(catalog=catalog)
        assert result == []

    def test_filters_by_execution_id(self) -> None:
        catalog = MagicMock()
        catalog.list_by_execution.return_value = [
            {
                "artifact_id": "a1",
                "type": "report",
                "status": "ready",
                "s3_key": "k",
                "created_at": "2026-01-01",
            }
        ]

        result = list_artifacts(execution_id="exec-1", catalog=catalog)
        assert len(result) == 1
        catalog.list_by_execution.assert_called_once_with("exec-1")
