"""CloudWatch GenAI-specific metrics publisher.

Publishes per-model-invocation metrics to CloudWatch custom metrics:
  - ``ModelInferenceTime`` — latency in milliseconds, dimensioned by model ID
  - ``InputTokenCount`` — input tokens per invocation
  - ``OutputTokenCount`` — output tokens per invocation

Reads ``metric_namespace`` from :class:`DashboardConfig`.  Region is
resolved from environment variables (no hardcoded defaults).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class GenAIMetricsPublisher:
    """Publishes GenAI-specific metrics to CloudWatch.

    Parameters
    ----------
    metric_namespace:
        CloudWatch metric namespace (from ``DashboardConfig.metric_namespace``).
    region:
        AWS region.  Resolved from env if not provided.
    """

    def __init__(
        self,
        metric_namespace: str,
        region: str | None = None,
    ) -> None:
        self._namespace = metric_namespace
        self._region = (
            region
            or os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
        )
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy-initialized CloudWatch client."""
        if self._client is None:
            import boto3

            self._client = boto3.client("cloudwatch", region_name=self._region)
        return self._client

    def publish_invocation(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> None:
        """Publish metrics for a single model invocation.

        Args:
            model_id: Bedrock model identifier (used as dimension).
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            latency_ms: Model inference latency in milliseconds.
        """
        dimensions = [{"Name": "ModelId", "Value": model_id}]

        metric_data = [
            {
                "MetricName": "ModelInferenceTime",
                "Dimensions": dimensions,
                "Value": latency_ms,
                "Unit": "Milliseconds",
            },
            {
                "MetricName": "InputTokenCount",
                "Dimensions": dimensions,
                "Value": float(input_tokens),
                "Unit": "Count",
            },
            {
                "MetricName": "OutputTokenCount",
                "Dimensions": dimensions,
                "Value": float(output_tokens),
                "Unit": "Count",
            },
        ]

        try:
            self.client.put_metric_data(
                Namespace=self._namespace,
                MetricData=metric_data,
            )
            logger.debug(
                "Published GenAI metrics: model=%s latency=%.1fms tokens=%d/%d",
                model_id,
                latency_ms,
                input_tokens,
                output_tokens,
            )
        except Exception:
            logger.exception("Failed to publish GenAI metrics to CloudWatch")
