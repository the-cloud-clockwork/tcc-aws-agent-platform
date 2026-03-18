"""Tests for AuditLogWriter.

Uses a mock DynamoDB table to verify write behavior, idempotency,
and validation logic.
"""
from __future__ import annotations

import pytest

from agent_core.observability.audit_log import (
    DEFAULT_RETENTION_SECONDS,
    AuditLogError,
    AuditLogWriter,
)


class MockTable:
    """Mock DynamoDB table for testing."""

    def __init__(self) -> None:
        self.items: list[dict] = []
        self._fail_next = False
        self._duplicate_next = False

    def put_item(self, Item: dict, **kwargs) -> None:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("DynamoDB error")
        if self._duplicate_next:
            self._duplicate_next = False

            class ConditionalCheckFailedException(Exception):
                pass

            raise ConditionalCheckFailedException("ConditionalCheckFailedException")
        self.items.append(Item)

    def query(self, **kwargs) -> dict:
        return {"Items": self.items}


@pytest.fixture
def mock_table() -> MockTable:
    return MockTable()


@pytest.fixture
def writer(mock_table: MockTable) -> AuditLogWriter:
    return AuditLogWriter(
        table_name="test_audit_log",
        dynamodb_client=mock_table,
    )


class TestAuditLogWriter:
    def test_write_event(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        item = writer.log(
            event_type="PIPELINE_STARTED",
            agent_id="gap_detector",
            execution_mode="simulation",
            payload={"target": "AAPL"},
        )
        assert len(mock_table.items) == 1
        assert item["event_type"] == "PIPELINE_STARTED"
        assert item["agent_id"] == "gap_detector"
        assert item["execution_mode"] == "simulation"
        assert item["payload"]["target"] == "AAPL"
        assert "event_id" in item
        assert "timestamp_ms" in item
        assert "ttl" in item

    def test_ttl_default(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        import time

        now = int(time.time())
        item = writer.log(
            event_type="PIPELINE_COMPLETED",
            agent_id="test",
        )
        # TTL should be ~5 years from now
        assert item["ttl"] >= now + DEFAULT_RETENTION_SECONDS - 10

    def test_idempotency_key(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        item = writer.log(
            event_type="ORDER_REQUESTED",
            idempotency_key="idem-123",
            payload={"target": "AAPL"},
        )
        assert item["event_id"] == "idem-123"

    def test_duplicate_event_ignored(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        mock_table._duplicate_next = True
        # Should not raise -- duplicates are silently ignored
        item = writer.log(
            event_type="PROMPT_LOADED",
            payload={"prompt_id": "test"},
        )
        assert item["event_type"] == "PROMPT_LOADED"

    def test_dynamodb_error_raises(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        mock_table._fail_next = True
        with pytest.raises(AuditLogError, match="Failed to write"):
            writer.log(
                event_type="PIPELINE_FAILED",
                payload={"error": "timeout"},
            )

    def test_default_execution_mode_from_env(
        self, mock_table: MockTable, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "production")
        writer = AuditLogWriter(table_name="test", dynamodb_client=mock_table)
        item = writer.log(event_type="RISK_CHECK_PASS")
        assert item["execution_mode"] == "production"

    def test_query_by_execution(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        writer.log(
            event_type="PIPELINE_STARTED",
            execution_id="exec-001",
        )
        writer.log(
            event_type="PIPELINE_COMPLETED",
            execution_id="exec-001",
        )
        results = writer.query_by_execution("exec-001")
        assert len(results) == 2

    def test_query_by_type(self, writer: AuditLogWriter, mock_table: MockTable) -> None:
        writer.log(event_type="RISK_CHECK_PASS")
        results = writer.query_by_type("RISK_CHECK_PASS")
        assert len(results) >= 1

    def test_default_table_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUDIT_TABLE", "my_custom_table")
        writer = AuditLogWriter()
        assert writer.table_name == "my_custom_table"

    def test_default_table_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUDIT_TABLE", raising=False)
        writer = AuditLogWriter()
        assert writer.table_name == "audit_log"
