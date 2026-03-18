"""Tests for AlertPublisher."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agent_core.observability.alerts import AlertLevel, AlertPublisher


class MockSnsClient:
    """Mock SNS client for testing."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self._fail_next = False

    def publish(self, **kwargs) -> dict:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("SNS error")
        self.messages.append(kwargs)
        return {"MessageId": f"msg-{len(self.messages)}"}


@pytest.fixture
def mock_sns() -> MockSnsClient:
    return MockSnsClient()


@pytest.fixture
def publisher(mock_sns: MockSnsClient) -> AlertPublisher:
    return AlertPublisher(
        topic_arn="arn:aws:sns:eu-west-1:123456789012:test-alerts",
        sns_client=mock_sns,
    )


class TestAlertPublisher:
    def test_publish(self, publisher: AlertPublisher, mock_sns: MockSnsClient) -> None:
        msg_id = publisher.publish(
            alert_type="test",
            level=AlertLevel.INFO,
            title="Test Alert",
            message="This is a test",
        )
        assert msg_id == "msg-1"
        assert len(mock_sns.messages) == 1
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "test"
        assert payload["title"] == "Test Alert"

    def test_no_topic_arn_returns_none(self) -> None:
        publisher = AlertPublisher(topic_arn="")
        result = publisher.publish(
            alert_type="test",
            level=AlertLevel.INFO,
            title="No Topic",
            message="No topic ARN configured",
        )
        assert result is None

    def test_sns_error_returns_none(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        mock_sns._fail_next = True
        result = publisher.publish(
            alert_type="test",
            level=AlertLevel.CRITICAL,
            title="Error Test",
            message="Should handle gracefully",
        )
        assert result is None

    def test_circuit_breaker_tripped(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.circuit_breaker_tripped(
            rule="daily_loss_breaker",
            details="Service degraded",
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "circuit_breaker"
        assert payload["level"] == "CRITICAL"
        assert payload["details"]["rule"] == "daily_loss_breaker"

    def test_circuit_breaker_reset(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.circuit_breaker_reset(rule="daily_loss_breaker")
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "circuit_breaker_reset"
        assert payload["level"] == "INFO"

    def test_pipeline_failed(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.pipeline_failed(
            execution_id="arn:aws:states:exec-123",
            error="Gap Detection Agent timed out",
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "pipeline_failure"
        assert payload["level"] == "CRITICAL"

    def test_pipeline_completed(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        msg_id = publisher.pipeline_completed(
            execution_id="exec-456",
            duration_s=123.4,
        )
        assert msg_id is not None
        payload = json.loads(mock_sns.messages[0]["Message"])
        assert payload["alert_type"] == "pipeline_completed"
        assert payload["level"] == "INFO"

    def test_message_attributes(
        self, publisher: AlertPublisher, mock_sns: MockSnsClient
    ) -> None:
        publisher.publish(
            alert_type="test_type",
            level=AlertLevel.WARNING,
            title="Attr Test",
            message="Check attributes",
        )
        attrs = mock_sns.messages[0]["MessageAttributes"]
        assert attrs["alert_type"]["StringValue"] == "test_type"
        assert attrs["level"]["StringValue"] == "WARNING"
