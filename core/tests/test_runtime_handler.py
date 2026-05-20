"""Tests for agent_core.runtime.handler — GenericHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestGenericHandler:
    """Test GenericHandler dispatch and error handling."""

    @patch("agent_core.runtime.handler.SessionManager")
    @patch("agent_core.runtime.handler.AgentConfigRegistry")
    @patch("agent_core.runtime.handler.BlueprintLoader")
    def test_construction(
        self, mock_loader: MagicMock, mock_registry: MagicMock, mock_sm: MagicMock
    ) -> None:
        from agent_core.runtime.handler import GenericHandler

        handler = GenericHandler(
            loader=mock_loader,
            config_registry=mock_registry,
        )
        assert handler is not None

    @patch("agent_core.runtime.handler.SessionManager")
    @patch("agent_core.runtime.handler.AgentConfigRegistry")
    @patch("agent_core.runtime.handler.BlueprintLoader")
    def test_handle_returns_dict(
        self, mock_loader: MagicMock, mock_registry: MagicMock, mock_sm: MagicMock
    ) -> None:
        from agent_core.runtime.handler import GenericHandler

        mock_registry.resolve.return_value = MagicMock(
            agent_id="test-agent",
            blueprint_id="test-bp",
        )

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = "test output"
        mock_loader.build_agent_session.return_value = mock_session

        handler = GenericHandler(
            loader=mock_loader,
            config_registry=mock_registry,
        )
        result = handler.handle({"prompt": "hello", "agent_id": "test-agent"})
        assert isinstance(result, dict)

    @patch("agent_core.runtime.handler.SessionManager")
    @patch("agent_core.runtime.handler.AgentConfigRegistry")
    @patch("agent_core.runtime.handler.BlueprintLoader")
    def test_handle_missing_prompt(
        self, mock_loader: MagicMock, mock_registry: MagicMock, mock_sm: MagicMock
    ) -> None:
        from agent_core.runtime.handler import GenericHandler

        mock_registry.resolve.return_value = MagicMock(agent_id="a1")
        handler = GenericHandler(loader=mock_loader, config_registry=mock_registry)
        result = handler.handle({})
        assert isinstance(result, dict)

    def test_handler_threads_event_mode_into_session(self, monkeypatch) -> None:
        """payload.execution_mode must be forwarded to create_session, not env default."""
        from unittest.mock import MagicMock

        monkeypatch.setenv("EXECUTION_MODE", "simulation")

        mock_session_mgr = MagicMock()
        mock_session_mgr.create_session.return_value = MagicMock()
        mock_session_mgr.persist_session.return_value = None

        mock_agent_session = MagicMock()
        mock_agent_session.__enter__ = MagicMock(return_value=mock_agent_session)
        mock_agent_session.__exit__ = MagicMock(return_value=False)
        mock_agent_session.run.return_value = "ok"

        mock_loader = MagicMock()
        mock_loader.build_agent_session.return_value = mock_agent_session
        mock_loader.load_agent.return_value = MagicMock(
            artifacts=MagicMock(tier="platform", kms_key_alias=None)
        )

        mock_config = MagicMock()
        mock_config.defaults = {}
        mock_config.required_fields = []
        mock_config.operation_name = "op"
        mock_config.build_prompt.return_value = "prompt"

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_config

        from agent_core.runtime.handler import GenericHandler

        handler = GenericHandler(
            loader=mock_loader,
            config_registry=mock_registry,
            session_manager=mock_session_mgr,
        )
        handler.handle({
            "agent_id": "gap-detector",
            "execution_mode": "production",
            "input": {"prompt": "x"},
        })

        mock_session_mgr.create_session.assert_called_once()
        _, kwargs = mock_session_mgr.create_session.call_args
        assert kwargs.get("execution_mode") == "production", (
            f"Expected 'production' but got {kwargs.get('execution_mode')!r} — "
            "handler is not forwarding payload.execution_mode to create_session"
        )

    def test_handler_passes_conversation_history_to_marshal_output(
        self, monkeypatch
    ) -> None:
        """marshal v2: session.messages must be captured and threaded through."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("EXECUTION_MODE", "simulation")

        history = [
            {"role": "user", "content": [{"text": "go"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tu-1",
                            "name": "create_artifact",
                            "input": {"content": {"typed": "payload"}},
                        }
                    }
                ],
            },
        ]

        mock_agent_session = MagicMock()
        mock_agent_session.__enter__ = MagicMock(return_value=mock_agent_session)
        mock_agent_session.__exit__ = MagicMock(return_value=False)
        mock_agent_session.run.return_value = "ok"
        # AgentSession.messages is a property; patch the attribute directly on the mock
        type(mock_agent_session).messages = property(lambda self: history)

        mock_loader = MagicMock()
        mock_loader.build_agent_session.return_value = mock_agent_session
        mock_loader.load_agent.return_value = MagicMock(
            artifacts=MagicMock(tier="platform", kms_key_alias=None)
        )

        mock_config = MagicMock()
        mock_config.defaults = {}
        mock_config.required_fields = []
        mock_config.operation_name = "op"
        mock_config.build_prompt.return_value = "prompt"

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_config

        from agent_core.runtime.handler import GenericHandler

        handler = GenericHandler(loader=mock_loader, config_registry=mock_registry)

        with patch("agent_core.runtime.handler.marshal_output") as mock_marshal:
            mock_marshal.return_value = {
                "artifact_id": "a",
                "s3_key": "platform/a/x.json",
                "bucket": "b",
                "tier": "platform",
                "agent_id": "gap-detector",
                "success": True,
                "claim_check": True,
                "output": {"typed": "payload"},
            }
            handler.handle({
                "agent_id": "gap-detector",
                "execution_mode": "simulation",
                "input": {"prompt": "x"},
            })

        mock_marshal.assert_called_once()
        _, kwargs = mock_marshal.call_args
        assert kwargs.get("conversation_history") == history, (
            "handler did not capture session.messages and pass it as "
            "conversation_history to marshal_output"
        )


class TestHistoryHasTypedPayload:
    """Tests for _history_has_typed_payload — the forced-retry trigger."""

    def test_create_artifact_counts(self) -> None:
        from agent_core.runtime.handler import _history_has_typed_payload

        history = [
            {"role": "assistant", "content": [
                {"toolUse": {"name": "create_artifact", "input": {"content": {}}}}
            ]}
        ]
        assert _history_has_typed_payload(history) is True

    def test_camelcase_schema_tool_counts(self) -> None:
        from agent_core.runtime.handler import _history_has_typed_payload

        history = [
            {"role": "assistant", "content": [
                {"toolUse": {"name": "MLPredictionReport", "input": {"x": 1}}}
            ]}
        ]
        assert _history_has_typed_payload(history) is True

    def test_only_markdown_text_does_not_count(self) -> None:
        from agent_core.runtime.handler import _history_has_typed_payload

        history = [
            {"role": "user", "content": [{"text": "predict"}]},
            {"role": "assistant", "content": [
                {"text": "The MLPredictionReport has been created and stored."}
            ]},
        ]
        assert _history_has_typed_payload(history) is False

    def test_snake_case_tool_does_not_count(self) -> None:
        """get_ohlcv-style data fetches must not be mistaken for a typed artifact."""
        from agent_core.runtime.handler import _history_has_typed_payload

        history = [
            {"role": "assistant", "content": [
                {"toolUse": {"name": "get_ohlcv", "input": {"symbol": "NVDA"}}}
            ]}
        ]
        assert _history_has_typed_payload(history) is False

    def test_forced_retry_fires_when_first_run_is_markdown(self, monkeypatch) -> None:
        """Handler runs a second turn when the first ends without a typed payload."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("EXECUTION_MODE", "simulation")

        # First run → markdown only. After the forced turn → create_artifact.
        states = {"calls": 0}
        markdown_only = [
            {"role": "user", "content": [{"text": "go"}]},
            {"role": "assistant", "content": [{"text": "Here is a summary."}]},
        ]
        with_artifact = markdown_only + [
            {"role": "assistant", "content": [
                {"toolUse": {"name": "create_artifact", "input": {"content": {"ok": 1}}}}
            ]},
        ]

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        def _run(_prompt):
            states["calls"] += 1
            return "ok"

        mock_session.run.side_effect = _run
        # messages property reflects state: markdown after call 1, artifact after call 2
        type(mock_session).messages = property(
            lambda self: with_artifact if states["calls"] >= 2 else markdown_only
        )

        mock_loader = MagicMock()
        mock_loader.build_agent_session.return_value = mock_session
        mock_loader.load_agent.return_value = MagicMock(
            artifacts=MagicMock(tier="platform", kms_key_alias=None)
        )

        mock_config = MagicMock()
        mock_config.defaults = {}
        mock_config.required_fields = []
        mock_config.operation_name = "op"
        mock_config.build_prompt.return_value = "prompt"

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_config

        from agent_core.runtime.handler import GenericHandler

        handler = GenericHandler(loader=mock_loader, config_registry=mock_registry)

        with patch("agent_core.runtime.handler.marshal_output") as mock_marshal:
            mock_marshal.return_value = {
                "artifact_id": "a", "s3_key": "platform/a/x.json", "bucket": "b",
                "tier": "platform", "agent_id": "ml-predictor", "success": True,
                "claim_check": True, "output": {"ok": 1},
            }
            handler.handle({
                "agent_id": "ml-predictor",
                "execution_mode": "simulation",
                "input": {"prompt": "x"},
            })

        # session.run called twice — original + forced retry
        assert states["calls"] == 2, (
            f"expected 1 original + 1 forced-retry run, got {states['calls']}"
        )
        # marshal received the post-retry history (with the create_artifact toolUse)
        _, kwargs = mock_marshal.call_args
        assert kwargs.get("conversation_history") == with_artifact
