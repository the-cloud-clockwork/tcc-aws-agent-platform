"""Tests for XRayTracer.

Tests run without aws-xray-sdk installed -- they verify the no-op fallback
behavior and the decorator pattern.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.observability.xray_tracing import (
    XRayTracer,
    _NoOpSubsegment,
    reset_recorder,
)


@pytest.fixture(autouse=True)
def _reset_xray():
    """Reset the global recorder before each test."""
    reset_recorder()
    yield
    reset_recorder()


class TestNoOpSubsegment:
    def test_context_manager(self) -> None:
        sub = _NoOpSubsegment()
        with sub as s:
            assert s is sub
            s.put_annotation("key", "value")
            s.put_metadata("key", "value")

    def test_add_exception(self) -> None:
        sub = _NoOpSubsegment()
        sub.add_exception(ValueError("test"))


class TestXRayTracer:
    def test_subsegment_without_sdk(self) -> None:
        """Without aws-xray-sdk, subsegment returns a no-op."""
        tracer = XRayTracer(service_name="test")
        with tracer.subsegment("test_op", target="ENTITY-1") as sub:
            assert isinstance(sub, _NoOpSubsegment)
            sub.put_annotation("rows", 100)

    def test_capture_decorator_without_sdk(self) -> None:
        """Decorator works without X-Ray -- just runs the function."""
        tracer = XRayTracer(service_name="test")

        @tracer.capture("compute_gap")
        def compute_gap(a: float, b: float) -> float:
            return (a - b) / b

        result = compute_gap(105.0, 100.0)
        assert abs(result - 0.05) < 1e-6

    def test_add_annotation_without_sdk(self) -> None:
        """add_annotation is safe to call without X-Ray."""
        tracer = XRayTracer(service_name="test")
        tracer.add_annotation("key", "value")  # should not raise

    def test_add_metadata_without_sdk(self) -> None:
        """add_metadata is safe to call without X-Ray."""
        tracer = XRayTracer(service_name="test")
        tracer.add_metadata("key", {"data": 123})  # should not raise

    @patch("agent_core.observability.xray_tracing._get_recorder")
    def test_subsegment_with_mock_recorder(self, mock_get_recorder: MagicMock) -> None:
        """Verify X-Ray recorder methods are called when available."""
        mock_recorder = MagicMock()
        mock_subseg = MagicMock()
        mock_recorder.begin_subsegment.return_value = mock_subseg
        mock_get_recorder.return_value = mock_recorder

        tracer = XRayTracer(service_name="gap_detector")
        with tracer.subsegment("fetch_data", target="ENTITY-1") as sub:
            assert sub is mock_subseg

        mock_recorder.begin_subsegment.assert_called_once_with("fetch_data")
        mock_subseg.put_annotation.assert_any_call("service", "gap_detector")
        mock_subseg.put_annotation.assert_any_call("target", "ENTITY-1")
        mock_recorder.end_subsegment.assert_called_once()

    @patch("agent_core.observability.xray_tracing._get_recorder")
    def test_subsegment_exception_handling(self, mock_get_recorder: MagicMock) -> None:
        """Verify exceptions inside subsegments are recorded and re-raised."""
        mock_recorder = MagicMock()
        mock_subseg = MagicMock()
        mock_recorder.begin_subsegment.return_value = mock_subseg
        mock_get_recorder.return_value = mock_recorder

        tracer = XRayTracer(service_name="test")
        with pytest.raises(ValueError, match="boom"):
            with tracer.subsegment("fail_op"):
                raise ValueError("boom")

        mock_subseg.add_exception.assert_called_once()
        mock_recorder.end_subsegment.assert_called_once()
