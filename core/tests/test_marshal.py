"""Tests for agent_core.runtime.marshal — output marshalling with S3 storage."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


def _make_boto3_mock(account_id: str = "123456789012") -> MagicMock:
    """Create a mock boto3 module with STS + S3 clients."""
    mock_boto3 = MagicMock()
    mock_s3 = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": account_id}
    mock_boto3.client.side_effect = lambda svc, **kw: mock_sts if svc == "sts" else mock_s3
    return mock_boto3, mock_s3, mock_sts


class TestMarshalOutput:
    """Tests for marshal_output S3 upload behavior."""

    def test_put_object_includes_expected_bucket_owner(self) -> None:
        """S3 put_object must include ExpectedBucketOwner to prevent bucket confusion."""
        mock_boto3, mock_s3, _ = _make_boto3_mock("123456789012")

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            from agent_core.runtime.marshal import marshal_output

            result = marshal_output(
                result={"key": "value"},
                agent_id="test-agent",
                execution_id="exec-123",
                s3_bucket="test-bucket",
            )

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert "ExpectedBucketOwner" in call_kwargs
        assert call_kwargs["ExpectedBucketOwner"] == "123456789012"
        assert result["success"] is True

    def test_put_object_with_kms_includes_expected_bucket_owner(self) -> None:
        """KMS-encrypted uploads must also include ExpectedBucketOwner."""
        mock_boto3, mock_s3, _ = _make_boto3_mock("999888777666")

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            from agent_core.runtime.marshal import marshal_output

            result = marshal_output(
                result="test output",
                agent_id="agent-1",
                execution_id="exec-1",
                s3_bucket="bucket",
                kms_key_alias="alias/my-key",
            )

        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ExpectedBucketOwner"] == "999888777666"
        assert call_kwargs["ServerSideEncryption"] == "aws:kms"
        assert call_kwargs["SSEKMSKeyId"] == "alias/my-key"

    @patch.dict("os.environ", {"ARTIFACTS_BUCKET": "env-bucket"})
    def test_falls_back_to_env_bucket(self) -> None:
        """Falls back to ARTIFACTS_BUCKET env var when s3_bucket not provided."""
        mock_boto3, mock_s3, _ = _make_boto3_mock("111222333444")

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            from agent_core.runtime.marshal import marshal_output

            result = marshal_output(
                result={"data": 1},
                agent_id="a",
                execution_id="e",
            )

        assert result["bucket"] == "env-bucket"
        assert result["success"] is True

    def test_no_bucket_returns_error(self) -> None:
        """Returns error dict when no bucket is configured."""
        from agent_core.runtime.marshal import marshal_output

        with patch.dict("os.environ", {}, clear=True):
            result = marshal_output(
                result="test",
                agent_id="a",
                execution_id="e",
                s3_bucket=None,
            )
            assert result["success"] is False
            assert result["error"] == "no_bucket"

    def test_s3_exception_returns_error(self) -> None:
        """S3 failures return error dict, don't raise."""
        mock_boto3, mock_s3, _ = _make_boto3_mock("123")
        mock_s3.put_object.side_effect = Exception("Access denied")

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            from agent_core.runtime.marshal import marshal_output

            result = marshal_output(
                result="test",
                agent_id="a",
                execution_id="e",
                s3_bucket="bucket",
            )

        assert result["success"] is False
        assert "Access denied" in result["error"]

    def test_pydantic_model_serialization(self) -> None:
        """Pydantic models are serialized via model_dump."""
        mock_boto3, mock_s3, _ = _make_boto3_mock("123")

        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"field": "value"}
        del mock_model.to_dict

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            from agent_core.runtime.marshal import marshal_output

            result = marshal_output(
                result=mock_model,
                agent_id="a",
                execution_id="e",
                s3_bucket="bucket",
            )

        assert result["output"] == {"field": "value"}
