"""Tests for StructuredLogger."""
from __future__ import annotations

import json
import logging

import pytest

from agent_core.observability.structured_logger import LogSchema, StructuredLogger


class TestLogSchema:
    def test_to_dict(self) -> None:
        schema = LogSchema(
            timestamp="2025-01-01T00:00:00",
            level="INFO",
            message="test message",
            trace_id="trace-123",
            execution_id="exec-456",
            agent_id="test_detector",
            prompt_version="v1.2",
            execution_mode="simulation",
            extra={"target": "item-A"},
        )
        d = schema.to_dict()
        assert d["timestamp"] == "2025-01-01T00:00:00"
        assert d["level"] == "INFO"
        assert d["agent_id"] == "test_detector"
        assert d["extra"]["target"] == "item-A"

    def test_to_json(self) -> None:
        schema = LogSchema(
            timestamp="2025-01-01T00:00:00",
            level="ERROR",
            message="boom",
            trace_id="t",
            execution_id="e",
            agent_id="a",
            prompt_version="v",
            execution_mode="production",
        )
        parsed = json.loads(schema.to_json())
        assert parsed["level"] == "ERROR"
        assert "extra" not in parsed  # empty extra is omitted

    def test_empty_extra_not_in_dict(self) -> None:
        schema = LogSchema(
            timestamp="t", level="INFO", message="m",
            trace_id="t", execution_id="e", agent_id="a",
            prompt_version="v", execution_mode="simulation",
        )
        d = schema.to_dict()
        assert "extra" not in d


class TestStructuredLogger:
    def test_info_logs_json(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(
            agent_id="test_agent",
            execution_mode="simulation",
            prompt_version="v1.0",
            trace_id="trace-fixed",
            execution_id="exec-fixed",
        )
        with caplog.at_level(logging.INFO, logger="agent_core.structured"):
            record = logger.info("Gap found", target="ENTITY-1", gap_pct=2.3)

        assert record.agent_id == "test_agent"
        assert record.level == "INFO"
        assert record.extra["target"] == "ENTITY-1"
        assert record.extra["gap_pct"] == 2.3

        # Verify the log output is valid JSON
        assert len(caplog.records) == 1
        parsed = json.loads(caplog.records[0].message)
        assert parsed["agent_id"] == "test_agent"

    def test_error_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="err_agent")
        with caplog.at_level(logging.ERROR, logger="agent_core.structured"):
            record = logger.error("MCP timeout", tool="data-mcp")

        assert record.level == "ERROR"
        assert record.extra["tool"] == "data-mcp"

    def test_warning_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="warn_agent")
        with caplog.at_level(logging.WARNING, logger="agent_core.structured"):
            record = logger.warning("Slow response")

        assert record.level == "WARNING"

    def test_debug_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="dbg_agent")
        with caplog.at_level(logging.DEBUG, logger="agent_core.structured"):
            record = logger.debug("Internal state", step=3)

        assert record.level == "DEBUG"
        assert record.extra["step"] == 3

    def test_critical_level(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = StructuredLogger(agent_id="crit_agent")
        with caplog.at_level(logging.CRITICAL, logger="agent_core.structured"):
            record = logger.critical("System down")

        assert record.level == "CRITICAL"

    def test_defaults_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "staging")
        monkeypatch.setenv("_X_AMZN_TRACE_ID", "xray-trace-id")
        monkeypatch.setenv("SFN_EXECUTION_ID", "sfn-exec-id")
        logger = StructuredLogger(agent_id="env_agent")

        assert logger.execution_mode == "staging"
        assert logger.trace_id == "xray-trace-id"
        assert logger.execution_id == "sfn-exec-id"

    def test_auto_generated_ids(self) -> None:
        logger = StructuredLogger()
        assert len(logger.trace_id) > 0
        assert len(logger.execution_id) > 0
