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

            marshal_output(
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


def _make_strands_result(envelope: dict) -> MagicMock:
    """Build a mock object emulating a Strands AgentResult.to_dict()."""
    mock = MagicMock()
    mock.to_dict.return_value = envelope
    return mock


class TestExtractTypedPayload:
    """Direct tests for _extract_typed_payload pure-function behavior."""

    def test_enforcer_tooluse_returns_input(self) -> None:
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {"text": "## Result narrative"},
                    {
                        "toolUse": {
                            "toolUseId": "enforced_gapdetectionoutput",
                            "name": "GapDetectionOutput",
                            "input": {"ranked_gaps": [], "total_gaps_found": 0},
                        }
                    },
                ],
            },
            "stop_reason": "end_turn",
        }
        assert _extract_typed_payload(envelope) == {
            "ranked_gaps": [],
            "total_gaps_found": 0,
        }

    def test_create_artifact_tooluse_returns_content(self) -> None:
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tooluse_abc",
                            "name": "create_artifact",
                            "input": {
                                "artifact_type": "report",
                                "tier": "platform",
                                "content": {
                                    "per_symbol_sentiments": [],
                                    "aggregate_sentiment": 0.0,
                                },
                            },
                        }
                    }
                ],
            },
        }
        assert _extract_typed_payload(envelope) == {
            "per_symbol_sentiments": [],
            "aggregate_sentiment": 0.0,
        }

    def test_fenced_json_in_text_returns_parsed_dict(self) -> None:
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "text": (
                            "## Gap Detection Results\n\n"
                            "```json\n"
                            '{"analysis_date": "2026-05-19", '
                            '"total_gaps_found": 0, "ranked_gaps": []}\n'
                            "```\n"
                        )
                    }
                ],
            },
        }
        assert _extract_typed_payload(envelope) == {
            "analysis_date": "2026-05-19",
            "total_gaps_found": 0,
            "ranked_gaps": [],
        }

    def test_no_extractable_returns_none(self) -> None:
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [{"text": "Narrative-only response, no JSON, no tools."}],
            },
        }
        assert _extract_typed_payload(envelope) is None

    def test_multiagent_envelope_skipped(self) -> None:
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "multiagent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "GapDetectionOutput",
                            "input": {"would_have_been_returned": True},
                        }
                    }
                ],
            },
        }
        assert _extract_typed_payload(envelope) is None

    def test_malformed_content_returns_none(self) -> None:
        from agent_core.runtime.marshal import _extract_typed_payload

        # message.content is not a list
        assert _extract_typed_payload({"message": {"content": "not a list"}}) is None
        # message is not a dict
        assert _extract_typed_payload({"message": "not a dict"}) is None
        # block dicts missing fields are skipped, fall through
        assert (
            _extract_typed_payload({"message": {"content": [{"unrelated": 1}]}}) is None
        )

    def test_prefers_last_tooluse(self) -> None:
        """Reversed iteration finds the last toolUse first (enforcer over earlier create_artifact)."""
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "create_artifact",
                            "input": {"content": {"early": True}},
                        }
                    },
                    {
                        "toolUse": {
                            "name": "GapDetectionOutput",
                            "input": {"late": True},
                        }
                    },
                ],
            },
        }
        assert _extract_typed_payload(envelope) == {"late": True}

    def test_create_artifact_non_dict_content_falls_through(self) -> None:
        """When create_artifact.input.content is a string (markdown body), fall through."""
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "create_artifact",
                            "input": {"content": "# Markdown not dict"},
                        }
                    },
                    {"text": '```json\n{"fallback": "json"}\n```'},
                ],
            },
        }
        # The toolUse loop continues past the non-dict content; the text-pass
        # then finds the fenced JSON.
        assert _extract_typed_payload(envelope) == {"fallback": "json"}


class TestSerializeResultStrands:
    """Tests for _serialize_result against Strands AgentResult-like inputs."""

    def test_strands_envelope_with_enforcer_returns_typed_payload(self) -> None:
        from agent_core.runtime.marshal import _serialize_result

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "GapDetectionOutput",
                            "input": {"ranked_gaps": [], "total_gaps_found": 0},
                        }
                    }
                ],
            },
        }
        result = _make_strands_result(envelope)
        assert _serialize_result(result) == {
            "ranked_gaps": [],
            "total_gaps_found": 0,
        }

    def test_strands_envelope_no_extractable_returns_envelope(self) -> None:
        """Fallback: when no typed payload is found, return the envelope itself."""
        from agent_core.runtime.marshal import _serialize_result

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [{"text": "Just prose, no JSON, no tools."}],
            },
        }
        result = _make_strands_result(envelope)
        assert _serialize_result(result) == envelope

    def test_strands_multiagent_envelope_returns_envelope(self) -> None:
        """Multiagent envelopes are out of v1 scope — return as-is."""
        from agent_core.runtime.marshal import _serialize_result

        envelope = {
            "type": "multiagent_result",
            "message": {
                "role": "assistant",
                "content": [{"text": "sub-agent results"}],
            },
        }
        result = _make_strands_result(envelope)
        assert _serialize_result(result) == envelope

    def test_strands_envelope_with_create_artifact_returns_content(self) -> None:
        from agent_core.runtime.marshal import _serialize_result

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "create_artifact",
                            "input": {
                                "artifact_type": "recommendation",
                                "content": {"recommendations": [], "no_action_symbols": []},
                            },
                        }
                    }
                ],
            },
        }
        result = _make_strands_result(envelope)
        assert _serialize_result(result) == {
            "recommendations": [],
            "no_action_symbols": [],
        }


class TestParseFencedJson:
    """Direct tests for the fenced-JSON parser."""

    def test_simple_object(self) -> None:
        from agent_core.runtime.marshal import _parse_fenced_json

        text = '```json\n{"foo": 1}\n```'
        assert _parse_fenced_json(text) == {"foo": 1}

    def test_returns_first_parseable_block(self) -> None:
        from agent_core.runtime.marshal import _parse_fenced_json

        text = (
            "Intro\n```json\n{not valid json}\n```\n"
            'Middle\n```json\n{"valid": true}\n```'
        )
        assert _parse_fenced_json(text) == {"valid": True}

    def test_no_fence_returns_none(self) -> None:
        from agent_core.runtime.marshal import _parse_fenced_json

        assert _parse_fenced_json("Just text, no fences") is None

    def test_non_dict_json_returns_none(self) -> None:
        from agent_core.runtime.marshal import _parse_fenced_json

        # The regex requires a {...} body, so an array would not match anyway,
        # but defensive isinstance check is exercised by other tests.
        assert _parse_fenced_json("```json\nnot-an-object\n```") is None
