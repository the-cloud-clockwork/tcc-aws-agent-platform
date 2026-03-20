"""SNS alert publisher for notifications.

Publishes structured alert messages to an SNS topic. A downstream Lambda
(``telegram_alert/handler.py``) subscribes to the topic and forwards
messages to Telegram.

Usage::

    publisher = AlertPublisher(topic_arn="arn:aws:sns:eu-west-1:123456789012:my-alerts")

    publisher.circuit_breaker_tripped(
        rule="daily_loss_breaker",
        details="Service degraded. All operations halted for 24h.",
    )

    publisher.pipeline_failed(
        execution_id="arn:aws:states:...",
        error="Gap Detection Agent timed out after 15min",
    )

    publisher.send_alert(
        alert_type="threshold_breach",
        message="Agent exceeded latency threshold",
        severity="warning",
    )

Environment variables:
- ``ALERT_TOPIC_ARN`` -- SNS topic ARN
- ``EXECUTION_MODE`` -- current execution mode
"""
from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from typing import Any

logger = logging.getLogger("agent_core.alerts")


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertPublisher:
    """Publishes alert messages to SNS for Telegram delivery.

    Parameters
    ----------
    topic_arn:
        SNS topic ARN. Defaults to ``ALERT_TOPIC_ARN`` env var.
    sns_client:
        Optional boto3 SNS client (injected for testing).
    """

    def __init__(
        self,
        topic_arn: str | None = None,
        sns_client: Any = None,
        platform_name: str = "",
    ) -> None:
        self.topic_arn = topic_arn or os.getenv("ALERT_TOPIC_ARN", "")
        self.platform_name = platform_name or os.getenv("PLATFORM_NAME", "AGENT")
        self._client = sns_client

    def _get_client(self) -> Any:
        """Lazily initialize the SNS client."""
        if self._client is None:
            import boto3  # type: ignore[import-untyped]

            self._client = boto3.client("sns")
        return self._client

    def publish(
        self,
        alert_type: str,
        level: AlertLevel,
        title: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        """Publish a structured alert to SNS.

        Parameters
        ----------
        alert_type:
            Category string (e.g. ``circuit_breaker``, ``pipeline_failure``).
        level:
            Severity level.
        title:
            Short title for the alert (used as Telegram header).
        message:
            Human-readable message body.
        details:
            Optional structured data for the alert.

        Returns
        -------
        SNS MessageId on success, None on failure.
        """
        if not self.topic_arn:
            logger.warning("No SNS topic ARN configured -- alert not sent: %s", title)
            return None

        mode = os.getenv("EXECUTION_MODE", "simulation")
        payload = {
            "alert_type": alert_type,
            "level": level.value,
            "title": title,
            "message": message,
            "execution_mode": mode,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "details": details or {},
        }

        try:
            client = self._get_client()
            response = client.publish(
                TopicArn=self.topic_arn,
                Subject=f"[{self.platform_name} {mode.upper()}] {level.value}: {title}",
                Message=json.dumps(payload, default=str),
                MessageAttributes={
                    "alert_type": {
                        "DataType": "String",
                        "StringValue": alert_type,
                    },
                    "level": {
                        "DataType": "String",
                        "StringValue": level.value,
                    },
                },
            )
            msg_id = response.get("MessageId", "unknown")
            logger.info("Alert published: type=%s level=%s msg_id=%s", alert_type, level.value, msg_id)
            return msg_id
        except Exception:
            logger.exception("Failed to publish alert: %s", title)
            return None

    # ---- Convenience Methods ----

    def circuit_breaker_tripped(self, rule: str, details: str) -> str | None:
        """Alert: circuit breaker tripped."""
        return self.publish(
            alert_type="circuit_breaker",
            level=AlertLevel.CRITICAL,
            title=f"Circuit Breaker: {rule}",
            message=details,
            details={"rule": rule},
        )

    def circuit_breaker_reset(self, rule: str) -> str | None:
        """Alert: circuit breaker reset."""
        return self.publish(
            alert_type="circuit_breaker_reset",
            level=AlertLevel.INFO,
            title=f"Circuit Breaker Reset: {rule}",
            message=f"Circuit breaker '{rule}' has been manually reset.",
            details={"rule": rule},
        )

    def pipeline_failed(self, execution_id: str, error: str) -> str | None:
        """Alert: pipeline execution failed."""
        return self.publish(
            alert_type="pipeline_failure",
            level=AlertLevel.CRITICAL,
            title="Pipeline Failed",
            message=f"Execution {execution_id} failed: {error}",
            details={"execution_id": execution_id, "error": error},
        )

    def pipeline_completed(self, execution_id: str, duration_s: float) -> str | None:
        """Alert: pipeline execution completed successfully."""
        return self.publish(
            alert_type="pipeline_completed",
            level=AlertLevel.INFO,
            title="Pipeline Completed",
            message=f"Execution {execution_id} completed in {duration_s:.1f}s",
            details={"execution_id": execution_id, "duration_s": duration_s},
        )
