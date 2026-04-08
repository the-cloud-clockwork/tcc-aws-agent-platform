"""Tests for Block 9: Strands Integration — The Full Stack.

Validates:
- Observability hook auto-wiring from blueprint config
- Local tool mixing with Gateway + builtin tools
- AgentSession streaming methods
- Multi-turn conversation via session bridge
- build_entrypoint() method
- blueprints/__init__.py exports
- BEDROCK_REGION enforcement
- state= dict wiring for memory hooks
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agent_core.blueprints.session import AgentSession


def _write_blueprint(
    tmp: Path,
    agent_id: str = "test-agent",
    *,
    memory: dict | None = None,
    observability: dict | None = None,
) -> Path:
    agents_dir = tmp / "agents"
    agents_dir.mkdir(parents=True)
    bp: dict = {
        "id": agent_id,
        "version": "1.0.0",
        "name": "Test Agent",
        "model": {"provider": "bedrock", "model_id": "test-model-id", "temperature": 0.5, "max_tokens": 1024},
        "prompt_ref": "test_prompt",
    }
    if memory:
        bp["memory"] = memory
    if observability:
        bp["observability"] = observability
    bp_file = agents_dir / f"{agent_id}.yaml"
    bp_file.write_text(yaml.dump(bp))
    return tmp


class TestObservabilityAutoWiring:
    """Verify CompositeObservabilityHook is auto-created from blueprint config."""

    @patch("agent_core.blueprints.loader.Agent")
    @patch("agent_core.hooks.observability_hooks.LangfuseHook")
    @patch("agent_core.hooks.observability_hooks.AuditLogWriter")
    @patch("agent_core.hooks.observability_hooks.StructuredLogger")
    def test_observability_auto_wired(self, mock_sl, mock_alw, mock_lh, mock_agent_cls):
        mock_agent_cls.return_value = MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(
                Path(tmp),
                observability={"trace_attributes": {"team": "test"}},
            )
            from agent_core.blueprints.loader import BlueprintLoader

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="System prompt."):
                with patch.dict("os.environ", {"BEDROCK_REGION": "us-west-2"}):
                    session = loader.build_agent_session("test-agent")

            assert session.observability is not None

    @patch("agent_core.blueprints.loader.Agent")
    @patch("agent_core.hooks.observability_hooks.LangfuseHook")
    @patch("agent_core.hooks.observability_hooks.AuditLogWriter")
    @patch("agent_core.hooks.observability_hooks.StructuredLogger")
    def test_observability_hook_in_agent_hooks(
        self, mock_sl, mock_alw, mock_lh, mock_agent_cls
    ):
        mock_agent_cls.return_value = MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp))
            from agent_core.blueprints.loader import BlueprintLoader

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="System prompt."):
                with patch.dict("os.environ", {"BEDROCK_REGION": "us-west-2"}):
                    loader.build_agent_session("test-agent")

            call_kwargs = mock_agent_cls.call_args
            assert "hooks" in call_kwargs.kwargs or (
                call_kwargs.args and "hooks" in str(call_kwargs)
            )


class TestToolMixing:
    """Verify local @tool functions are merged with Gateway + builtin tools."""

    @patch("agent_core.blueprints.loader.Agent")
    @patch("agent_core.hooks.observability_hooks.LangfuseHook")
    @patch("agent_core.hooks.observability_hooks.AuditLogWriter")
    @patch("agent_core.hooks.observability_hooks.StructuredLogger")
    def test_local_tools_merged(self, mock_sl, mock_alw, mock_lh, mock_agent_cls):
        mock_agent_cls.return_value = MagicMock()

        def my_local_tool(x: str) -> str:
            return x

        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp))
            from agent_core.blueprints.loader import BlueprintLoader

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="System prompt."):
                with patch.object(loader, "_create_tool_providers", return_value=[]):
                    with patch.dict("os.environ", {"BEDROCK_REGION": "us-west-2"}):
                        loader.build_agent_session(
                            "test-agent", local_tools=[my_local_tool]
                        )

            call_kwargs = mock_agent_cls.call_args
            tools = call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")
            assert my_local_tool in tools


class TestSessionStreaming:
    """Verify AgentSession streaming methods."""

    def test_stream_async_delegates(self):
        mock_agent = MagicMock()

        async def fake_stream(prompt):
            yield {"data": "chunk1"}
            yield {"data": "chunk2"}

        mock_agent.stream_async = fake_stream
        session = AgentSession(agent=mock_agent, mcp_clients=[])

        results = []
        loop = asyncio.new_event_loop()

        async def collect():
            async for event in session.stream_async("test"):
                results.append(event)

        loop.run_until_complete(collect())
        loop.close()

        assert len(results) == 2
        assert results[0] == {"data": "chunk1"}

    def test_stream_sync_wrapper(self):
        mock_agent = MagicMock()

        async def fake_stream(prompt):
            yield "a"
            yield "b"

        mock_agent.stream_async = fake_stream
        session = AgentSession(agent=mock_agent, mcp_clients=[])

        results = list(session.stream("test"))
        assert results == ["a", "b"]

    def test_stream_fallback_no_stream_async(self):
        mock_agent = MagicMock()
        mock_agent.return_value = "result"
        del mock_agent.stream_async
        session = AgentSession(agent=mock_agent, mcp_clients=[])

        results = list(session.stream("test"))
        assert results == ["result"]


class TestMultiTurn:
    """Verify multi-turn conversation via session bridge."""

    def test_run_turn_syncs_bridge(self):
        mock_agent = MagicMock()
        mock_agent.return_value = "response"
        mock_bridge = MagicMock()
        session = AgentSession(
            agent=mock_agent, mcp_clients=[], session_bridge=mock_bridge
        )
        session.run_turn("hello")
        mock_bridge.sync_agent.assert_called_once_with(mock_agent)

    def test_session_bridge_lifecycle(self):
        mock_agent = MagicMock()
        mock_bridge = MagicMock()
        session = AgentSession(
            agent=mock_agent, mcp_clients=[], session_bridge=mock_bridge
        )
        with session:
            mock_bridge.initialize.assert_called_once_with(mock_agent)
        mock_bridge.flush.assert_called_once()

    def test_messages_property(self):
        mock_agent = MagicMock()
        mock_agent.messages = [{"role": "user", "content": "hi"}]
        session = AgentSession(agent=mock_agent, mcp_clients=[])
        assert len(session.messages) == 1

    def test_messages_empty_when_no_attr(self):
        mock_agent = MagicMock(spec=[])
        session = AgentSession(agent=mock_agent, mcp_clients=[])
        assert session.messages == []


class TestBuildEntrypoint:
    """Verify build_entrypoint() returns a configured app."""

    @patch("agent_core.blueprints.loader.Agent")
    @patch("agent_core.hooks.observability_hooks.LangfuseHook")
    @patch("agent_core.hooks.observability_hooks.AuditLogWriter")
    @patch("agent_core.hooks.observability_hooks.StructuredLogger")
    @patch("agent_core.runtime.entrypoint.BedrockAgentCoreApp")
    def test_build_entrypoint_returns_app(
        self, mock_sdk_app, mock_sl, mock_alw, mock_lh, mock_agent_cls
    ):
        mock_agent_cls.return_value = MagicMock()
        mock_sdk_app.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp))
            from agent_core.blueprints.loader import BlueprintLoader
            from agent_core.runtime.entrypoint import AgentCoreApp

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="System prompt."):
                with patch.dict("os.environ", {"BEDROCK_REGION": "us-west-2"}):
                    app = loader.build_entrypoint("test-agent")

            assert isinstance(app, AgentCoreApp)


class TestBlueprintsExports:
    """Verify all public classes are exported from blueprints/__init__.py."""

    def test_all_exports(self):
        from agent_core.blueprints import (
            AgentBlueprint,
            AgentSession,
            ArtifactConfig,
            BlueprintLoadError,
            BlueprintLoader,
            GraphEdgeConfig,
            GraphNodeConfig,
            MultiAgentConfig,
            ThinkingConfig,
            WorkflowBlueprint,
            WorkflowExecutor,
        )

        assert AgentBlueprint is not None
        assert AgentSession is not None
        assert BlueprintLoader is not None
        assert BlueprintLoadError is not None
        assert WorkflowBlueprint is not None
        assert WorkflowExecutor is not None
        assert GraphNodeConfig is not None
        assert GraphEdgeConfig is not None
        assert MultiAgentConfig is not None
        assert ThinkingConfig is not None
        assert ArtifactConfig is not None


class TestBedrockRegionEnforcement:
    """Verify BEDROCK_REGION env var is required."""

    def test_missing_region_raises(self):
        from agent_core.blueprints.loader import BlueprintLoadError, BlueprintLoader

        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp))
            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="System prompt."):
                with patch.dict("os.environ", {}, clear=True):
                    with pytest.raises(BlueprintLoadError, match="BEDROCK_REGION"):
                        loader.build_agent_session("test-agent")


class TestProviderDispatch:
    """Verify _build_model_config dispatches to the correct Strands provider."""

    def _make_model(self, provider: str = "bedrock", **overrides):
        from agent_core.schemas.model_config import ModelConfig

        defaults = {
            "provider": provider,
            "model_id": f"{provider}-test-model",
            "temperature": 0.5,
            "max_tokens": 1024,
        }
        defaults.update(overrides)
        return ModelConfig(**defaults)

    def test_bedrock_dispatches(self):
        from agent_core.blueprints.loader import BlueprintLoader

        with patch("strands.models.BedrockModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            with patch.dict("os.environ", {"BEDROCK_REGION": "us-east-1"}):
                result = BlueprintLoader._build_model_config(self._make_model("bedrock"))
            mock_cls.assert_called_once()
            kw = mock_cls.call_args
            assert kw.kwargs["model_id"] == "bedrock-test-model"
            assert kw.kwargs["region_name"] == "us-east-1"
            assert kw.kwargs["max_tokens"] == 1024
            assert "model" in result

    def test_anthropic_dispatches(self):
        from agent_core.blueprints.loader import BlueprintLoader

        with patch("strands.models.anthropic.AnthropicModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            model = self._make_model("anthropic", api_key_env="ANTHROPIC_API_KEY")
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                result = BlueprintLoader._build_model_config(model)
            mock_cls.assert_called_once()
            kw = mock_cls.call_args
            assert kw.kwargs["model_id"] == "anthropic-test-model"
            assert kw.kwargs["max_tokens"] == 1024
            assert kw.kwargs["client_args"]["api_key"] == "test-key"
            assert "model" in result

    def test_litellm_dispatches(self):
        from agent_core.blueprints.loader import BlueprintLoader

        with patch("strands.models.litellm.LiteLLMModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            model = self._make_model(
                "litellm",
                base_url="http://litellm.local",
                api_key_env="LITELLM_API_KEY",
            )
            with patch.dict("os.environ", {"LITELLM_API_KEY": "lk-test"}):
                result = BlueprintLoader._build_model_config(model)
            mock_cls.assert_called_once()
            kw = mock_cls.call_args
            assert kw.kwargs["model_id"] == "litellm-test-model"
            assert kw.kwargs["client_args"]["base_url"] == "http://litellm.local"
            assert kw.kwargs["client_args"]["api_key"] == "lk-test"
            assert kw.kwargs["params"] == {"max_tokens": 1024, "temperature": 0.5}
            assert "model" in result

    def test_non_bedrock_no_region_required(self):
        """Anthropic provider must work without BEDROCK_REGION."""
        from agent_core.blueprints.loader import BlueprintLoader

        with patch("strands.models.anthropic.AnthropicModel") as mock_cls:
            mock_cls.return_value = MagicMock()
            with patch.dict("os.environ", {}, clear=True):
                result = BlueprintLoader._build_model_config(self._make_model("anthropic"))
            assert "model" in result

    def test_unknown_provider_raises(self):
        from agent_core.blueprints.loader import BlueprintLoadError, BlueprintLoader

        model = MagicMock()
        model.provider = "unsupported"
        with pytest.raises(BlueprintLoadError, match="Unsupported model provider"):
            BlueprintLoader._build_model_config(model)


class TestStateDictWithMemory:
    """Verify state= dict is passed to Agent when memory is configured."""

    @patch("agent_core.blueprints.loader.Agent")
    @patch("agent_core.hooks.observability_hooks.LangfuseHook")
    @patch("agent_core.hooks.observability_hooks.AuditLogWriter")
    @patch("agent_core.hooks.observability_hooks.StructuredLogger")
    @patch("agent_core.memory.wiring.MemoryWiring")
    def test_state_dict_created(
        self, mock_mw, mock_sl, mock_alw, mock_lh, mock_agent_cls
    ):
        mock_agent_cls.return_value = MagicMock()
        mock_wiring = MagicMock()
        mock_wiring.hook_provider = MagicMock()
        mock_mw.return_value = mock_wiring

        memory_cfg = {
            "strategies": [
                {"type": "SEMANTIC", "name": "TestStrat", "namespace": "test/"}
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp), memory=memory_cfg)
            from agent_core.blueprints.loader import BlueprintLoader

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="System prompt."):
                with patch.object(loader, "_create_tool_providers", return_value=[]):
                    with patch.dict(
                        "os.environ",
                        {
                            "BEDROCK_REGION": "us-west-2",
                            "AGENTCORE_MEMORY_ID": "mem-123",
                        },
                    ):
                        loader.build_agent_session("test-agent")

            call_kwargs = mock_agent_cls.call_args
            agent_kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
            assert "state" in agent_kwargs
            assert isinstance(agent_kwargs["state"], dict)
