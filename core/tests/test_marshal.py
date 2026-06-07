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

    def test_multiagent_envelope_with_no_results_returns_none(self) -> None:
        """v3: empty multiagent envelope (no sub-agent results) — caller falls back."""
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "multiagent_result",
            "results": {},
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

    def test_history_walk_finds_create_artifact_when_last_message_is_markdown(self) -> None:
        """v2 — earlier create_artifact toolUse wins when last message is plain markdown."""
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [{"text": "## Gap detection results\n\nNo gaps found today."}],
            },
        }
        conversation_history = [
            {"role": "user", "content": [{"text": "Run gap detection."}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {
                                "artifact_type": "report",
                                "content": {
                                    "analysis_date": "2026-05-19",
                                    "total_gaps_found": 0,
                                    "ranked_gaps": [],
                                },
                            },
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            "status": "success",
                            "content": [{"json": {"artifact_id": "u", "s3_key": "platform/u/x.json"}}],
                        }
                    }
                ],
            },
            {"role": "assistant", "content": envelope["message"]["content"]},
        ]
        assert _extract_typed_payload(envelope, conversation_history) == {
            "analysis_date": "2026-05-19",
            "total_gaps_found": 0,
            "ranked_gaps": [],
        }

    def test_non_schema_toolname_does_not_leak_input_as_payload(self) -> None:
        """v3: lowercase get_*/set_*-style tools must not be treated as schema toolUses.

        Reproduces smoke v6/v7 sentiment-analyzer bug where the sub-agent's final
        toolUse was an arbitrary fetch with input={config: {...}} and the walker
        returned that whole input dict, leaking the request config as the artifact.
        """
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "get_pipeline_config",
                            "input": {"config": {"body": {"pipeline": {}}}},
                        }
                    }
                ],
            },
        }
        # Walker must skip the non-schema toolUse entirely → fall through to
        # text/fenced scan (no text) → return None → caller serializes envelope.
        assert _extract_typed_payload(envelope) is None

    def test_history_walk_picks_latest_create_artifact_in_reverse(self) -> None:
        """v2 — when multiple create_artifact calls, the latest (most recent) wins."""
        from agent_core.runtime.marshal import _extract_typed_payload

        envelope = {
            "type": "agent_result",
            "message": {"role": "assistant", "content": [{"text": "summary"}]},
        }
        conversation_history = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"call": "first"}},
                        }
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-2",
                            "name": "create_artifact",
                            "input": {"content": {"call": "second"}},
                        }
                    }
                ],
            },
        ]
        assert _extract_typed_payload(envelope, conversation_history) == {
            "call": "second"
        }


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

    def test_strands_multiagent_envelope_with_no_typed_subagents_returns_envelope(self) -> None:
        """v3: multiagent envelope where no sub-agent has a typed payload — return envelope."""
        from agent_core.runtime.marshal import _serialize_result

        envelope = {
            "type": "multiagent_result",
            "results": {
                "specialist_a": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [{"text": "plain text only"}],
                        },
                    }
                }
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

    def test_strands_multiagent_envelope_with_typed_subagent_returns_payload(self) -> None:
        """v3: multiagent envelope where a sub-agent's last message has a create_artifact
        toolUse — extract and return that typed payload."""
        from agent_core.runtime.marshal import _serialize_result

        envelope = {
            "type": "multiagent_result",
            "results": {
                "sentiment_specialist": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "toolUse": {
                                        "name": "create_artifact",
                                        "input": {
                                            "artifact_type": "sentiment-report",
                                            "content": {
                                                "per_symbol_sentiments": [
                                                    {"symbol": "NVDA", "composite_score": 0.6}
                                                ]
                                            },
                                        },
                                    }
                                }
                            ],
                        },
                    }
                }
            },
        }
        result = _make_strands_result(envelope)
        assert _serialize_result(result) == {
            "per_symbol_sentiments": [{"symbol": "NVDA", "composite_score": 0.6}]
        }

    def test_threads_conversation_history_into_extractor(self) -> None:
        """v2 — conversation_history passed to _serialize_result reaches extractor."""
        from agent_core.runtime.marshal import _serialize_result

        # Envelope has no typed payload; history does.
        envelope = {
            "type": "agent_result",
            "message": {"role": "assistant", "content": [{"text": "narrative only"}]},
        }
        history = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "create_artifact",
                            "input": {"content": {"from_history": True}},
                        }
                    }
                ],
            },
        ]
        result = _make_strands_result(envelope)
        assert _serialize_result(result, conversation_history=history) == {
            "from_history": True,
        }

    def test_history_last_message_beats_stale_envelope(self) -> None:
        """v3.1 — when the envelope's message is a stale pre-hook copy (plain
        markdown) but conversation_history's last assistant message carries the
        StructuredOutputEnforcer's synthetic schema toolUse, prefer history."""
        from agent_core.runtime.marshal import _serialize_result

        # Stale envelope — captured before AfterInvocationEvent mutated messages.
        envelope = {
            "type": "agent_result",
            "message": {
                "role": "assistant",
                "content": [{"text": "The MLPredictionReport has been created."}],
            },
        }
        # Live history — enforcer injected the synthetic toolUse post-hook.
        history = [
            {"role": "user", "content": [{"text": "predict"}]},
            {
                "role": "assistant",
                "content": [
                    {"text": "The MLPredictionReport has been created."},
                    {
                        "toolUse": {
                            "toolUseId": "enforced_mlpredictionreport",
                            "name": "MLPredictionReport",
                            "input": {"per_symbol_predictions": [{"symbol": "NVDA"}]},
                        }
                    },
                ],
            },
        ]
        result = _make_strands_result(envelope)
        assert _serialize_result(result, conversation_history=history) == {
            "per_symbol_predictions": [{"symbol": "NVDA"}]
        }


class TestMultiAgentExtraction:
    """Tests for _extract_from_multiagent_envelope walker (v3 scope)."""

    def test_single_node_graph_unwraps_to_inner_payload(self) -> None:
        from agent_core.runtime.marshal import _extract_from_multiagent_envelope

        envelope = {
            "type": "multiagent_result",
            "results": {
                "only_specialist": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "toolUse": {
                                        "name": "create_artifact",
                                        "input": {"content": {"x": 1, "y": 2}},
                                    }
                                }
                            ],
                        },
                    }
                }
            },
        }
        assert _extract_from_multiagent_envelope(envelope) == {"x": 1, "y": 2}

    def test_multi_node_graph_returns_aggregate_by_name(self) -> None:
        from agent_core.runtime.marshal import _extract_from_multiagent_envelope

        envelope = {
            "type": "multiagent_result",
            "results": {
                "gap_analysis": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "toolUse": {
                                        "name": "create_artifact",
                                        "input": {"content": {"gaps": []}},
                                    }
                                }
                            ],
                        },
                    }
                },
                "sentiment_analysis": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "toolUse": {
                                        "name": "create_artifact",
                                        "input": {"content": {"sentiment": 0.0}},
                                    }
                                }
                            ],
                        },
                    }
                },
            },
        }
        result = _extract_from_multiagent_envelope(envelope)
        assert result == {
            "gap_analysis": {"gaps": []},
            "sentiment_analysis": {"sentiment": 0.0},
        }

    def test_no_typed_subagent_returns_none(self) -> None:
        from agent_core.runtime.marshal import _extract_from_multiagent_envelope

        envelope = {
            "type": "multiagent_result",
            "results": {
                "a": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [{"text": "narrative only"}],
                        },
                    }
                },
                "b": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [{"text": "also narrative"}],
                        },
                    }
                },
            },
        }
        assert _extract_from_multiagent_envelope(envelope) is None

    def test_nested_multiagent_recurses(self) -> None:
        from agent_core.runtime.marshal import _extract_from_multiagent_envelope

        envelope = {
            "type": "multiagent_result",
            "results": {
                "outer_node": {
                    "result": {
                        "type": "multiagent_result",
                        "results": {
                            "inner_specialist": {
                                "result": {
                                    "type": "agent_result",
                                    "message": {
                                        "role": "assistant",
                                        "content": [
                                            {
                                                "toolUse": {
                                                    "name": "create_artifact",
                                                    "input": {"content": {"deep": True}},
                                                }
                                            }
                                        ],
                                    },
                                }
                            }
                        },
                    }
                }
            },
        }
        # Single outer node containing a single-node nested multiagent — outer
        # unwraps, inner unwraps, final dict is the payload.
        assert _extract_from_multiagent_envelope(envelope) == {"deep": True}

    def test_subagent_with_fenced_json_text_falls_back(self) -> None:
        """Sub-agent didn't call create_artifact but emitted fenced JSON in text."""
        from agent_core.runtime.marshal import _extract_from_multiagent_envelope

        envelope = {
            "type": "multiagent_result",
            "results": {
                "only_specialist": {
                    "result": {
                        "type": "agent_result",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"text": "## Result\n\n```json\n{\"score\": 0.42}\n```\n"}
                            ],
                        },
                    }
                }
            },
        }
        assert _extract_from_multiagent_envelope(envelope) == {"score": 0.42}


class TestFindCreateArtifactResult:
    """Tests for _find_create_artifact_result history walker (Option B entry)."""

    def test_returns_latest_when_multiple_create_artifact_calls(self) -> None:
        from agent_core.runtime.marshal import _find_create_artifact_result

        messages = [
            {"role": "user", "content": [{"text": "go"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"first": True}},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            "status": "success",
                            "content": [
                                {
                                    "json": {
                                        "artifact_id": "uuid-first",
                                        "s3_key": "platform/uuid-first/artifact.json",
                                    }
                                }
                            ],
                        }
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-2",
                            "name": "create_artifact",
                            "input": {"content": {"second": True}},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-2",
                            "status": "success",
                            "content": [
                                {
                                    "json": {
                                        "artifact_id": "uuid-second",
                                        "s3_key": "platform/uuid-second/artifact.json",
                                    }
                                }
                            ],
                        }
                    }
                ],
            },
        ]
        assert _find_create_artifact_result(messages) == {
            "artifact_id": "uuid-second",
            "s3_key": "platform/uuid-second/artifact.json",
        }

    def test_returns_none_when_no_create_artifact_in_history(self) -> None:
        from agent_core.runtime.marshal import _find_create_artifact_result

        messages = [
            {"role": "user", "content": [{"text": "go"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "get_ohlcv",
                            "input": {"symbol": "NVDA"},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            "status": "success",
                            "content": [{"json": {"bars": []}}],
                        }
                    }
                ],
            },
            {"role": "assistant", "content": [{"text": "Summary"}]},
        ]
        assert _find_create_artifact_result(messages) is None

    def test_skips_failed_status_results(self) -> None:
        from agent_core.runtime.marshal import _find_create_artifact_result

        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"x": 1}},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            "status": "error",
                            "content": [
                                {
                                    "json": {
                                        "artifact_id": "should-be-ignored",
                                        "s3_key": "platform/should-be-ignored/artifact.json",
                                    }
                                }
                            ],
                        }
                    }
                ],
            },
        ]
        assert _find_create_artifact_result(messages) is None

    def test_handles_json_string_text_content_shape(self) -> None:
        from agent_core.runtime.marshal import _find_create_artifact_result

        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"y": 2}},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            "status": "success",
                            "content": [
                                {
                                    "text": (
                                        '{"artifact_id": "uuid-text", '
                                        '"s3_key": "platform/uuid-text/artifact.json", '
                                        '"status": "ready"}'
                                    )
                                }
                            ],
                        }
                    }
                ],
            },
        ]
        assert _find_create_artifact_result(messages) == {
            "artifact_id": "uuid-text",
            "s3_key": "platform/uuid-text/artifact.json",
        }

    def test_empty_or_none_messages_returns_none(self) -> None:
        from agent_core.runtime.marshal import _find_create_artifact_result

        assert _find_create_artifact_result(None) is None
        assert _find_create_artifact_result([]) is None

    def test_accepts_missing_status_field(self) -> None:
        """Some Strands transports omit `status` on success — treat absent as ok."""
        from agent_core.runtime.marshal import _find_create_artifact_result

        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"x": 1}},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            # status field intentionally absent
                            "content": [
                                {
                                    "json": {
                                        "artifact_id": "uuid-nostatus",
                                        "s3_key": "platform/uuid-nostatus/artifact.json",
                                    }
                                }
                            ],
                        }
                    }
                ],
            },
        ]
        assert _find_create_artifact_result(messages) == {
            "artifact_id": "uuid-nostatus",
            "s3_key": "platform/uuid-nostatus/artifact.json",
        }

    def test_accepts_bare_dict_content(self) -> None:
        """Some MCP transports surface toolResult.content as a bare dict."""
        from agent_core.runtime.marshal import _find_create_artifact_result

        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"x": 1}},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tu-1",
                            "status": "success",
                            "content": {
                                "artifact_id": "uuid-bare",
                                "s3_key": "platform/uuid-bare/artifact.json",
                            },
                        }
                    }
                ],
            },
        ]
        assert _find_create_artifact_result(messages) == {
            "artifact_id": "uuid-bare",
            "s3_key": "platform/uuid-bare/artifact.json",
        }


class TestAliasPlatformArtifact:
    """Tests for _alias_platform_artifact — Option B cross-tier alias write."""

    def test_writes_domain_ddb_row_pointing_at_platform_s3_key(self) -> None:
        from unittest.mock import call

        mock_boto3, mock_s3, _ = _make_boto3_mock("123456789012")
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b'{"typed": "payload"}'))
        }
        mock_ddb_table = MagicMock()
        mock_ddb_resource = MagicMock()
        mock_ddb_resource.Table.return_value = mock_ddb_table
        mock_boto3.resource.return_value = mock_ddb_resource

        env = {
            "ARTIFACTS_BUCKET": "test-bucket",
            "ARTIFACTS_TABLE": "test-artifacts",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.dict(sys.modules, {"boto3": mock_boto3}):
                from agent_core.runtime.marshal import _alias_platform_artifact

                result = _alias_platform_artifact(
                    platform_ref={
                        "artifact_id": "platform-uuid",
                        "s3_key": "platform/platform-uuid/artifact.json",
                    },
                    agent_id="gap-detector",
                    execution_id="exec-abc",
                    tier="domain",
                    kms_key_alias=None,
                    date="2026-05-19",
                )

        assert result["success"] is True
        assert result["s3_key"] == "platform/platform-uuid/artifact.json"
        assert result["tier"] == "domain"
        assert result["agent_id"] == "gap-detector"
        assert result["claim_check"] is True
        assert result["output"] == {"typed": "payload"}
        # The new domain artifact_id is a fresh UUID, not the platform one
        assert result["artifact_id"] != "platform-uuid"
        assert len(result["artifact_id"]) == 36

        mock_ddb_table.put_item.assert_called_once()
        put_kwargs = mock_ddb_table.put_item.call_args[1]
        item = put_kwargs["Item"]
        assert item["agent_id"] == "gap-detector"
        assert item["execution_id"] == "exec-abc"
        assert item["s3_key"] == "platform/platform-uuid/artifact.json"
        assert item["tier"] == "domain"
        assert item["claim_check"] is True

        # No S3 PUT — the whole point of aliasing
        mock_s3.put_object.assert_not_called()
        # But we DO read the platform body once to inline output
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="platform/platform-uuid/artifact.json",
            ExpectedBucketOwner="123456789012",
        )
        del call  # silence unused-import warning

    def test_continues_when_platform_body_load_fails(self) -> None:
        """S3 GET error is best-effort — catalog row still written with empty output."""
        mock_boto3, mock_s3, _ = _make_boto3_mock("123")
        mock_s3.get_object.side_effect = Exception("NoSuchKey")
        mock_ddb_table = MagicMock()
        mock_ddb_resource = MagicMock()
        mock_ddb_resource.Table.return_value = mock_ddb_table
        mock_boto3.resource.return_value = mock_ddb_resource

        env = {
            "ARTIFACTS_BUCKET": "test-bucket",
            "ARTIFACTS_TABLE": "test-artifacts",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.dict(sys.modules, {"boto3": mock_boto3}):
                from agent_core.runtime.marshal import _alias_platform_artifact

                result = _alias_platform_artifact(
                    platform_ref={
                        "artifact_id": "platform-uuid",
                        "s3_key": "platform/platform-uuid/artifact.json",
                    },
                    agent_id="a",
                    execution_id="e",
                    tier="domain",
                    kms_key_alias=None,
                    date="2026-05-19",
                )

        assert result["success"] is True
        assert result["output"] == {}
        mock_ddb_table.put_item.assert_called_once()

    def test_no_bucket_returns_error(self) -> None:
        from agent_core.runtime.marshal import _alias_platform_artifact

        with patch.dict("os.environ", {}, clear=True):
            result = _alias_platform_artifact(
                platform_ref={
                    "artifact_id": "u",
                    "s3_key": "platform/u/artifact.json",
                },
                agent_id="a",
                execution_id="e",
                tier="domain",
                kms_key_alias=None,
                date="2026-05-19",
            )

        assert result["success"] is False
        assert result["error"] == "no_bucket"


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
