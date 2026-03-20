"""Tests for BlueprintLoader."""
from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from agent_core.blueprints.agent import MultiAgentConfig
from agent_core.blueprints.loader import BlueprintLoader, BlueprintLoadError
from agent_core.blueprints.session import AgentSession
from agent_core.execution.mode import ExecutionMode

if TYPE_CHECKING:
    from pathlib import Path


class _DummyOutput(BaseModel):
    """Dummy output schema for tests that need a schema_registry."""

    data: str = ""


# Default registries used by session tests to satisfy the sample blueprint's
# hooks and output_schema declarations.
_DEFAULT_HOOK_REG: dict[str, type] = {"ObservabilityHook": MagicMock}
_DEFAULT_SCHEMA_REG: dict[str, type[BaseModel]] = {"test_detection_output_v1": _DummyOutput}


class TestBlueprintLoader:
    def test_load_agent(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_agent("test_detector")
        assert bp.id == "test_detector"
        assert bp.version == "1.2.0"

    def test_load_strategy(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_strategy("multi_signal_entry")
        assert bp.id == "multi_signal_entry"

    def test_load_workflow(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_workflow("weekly_analysis")
        assert bp.id == "weekly_analysis"
        assert len(bp.states) == 2
        assert bp.states[0].id == "ValidateSchedule"

    def test_load_agent_not_found(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        with pytest.raises(BlueprintLoadError, match="not found"):
            loader.load_agent("nonexistent_agent")

    def test_load_agent_from_path(self, tmp_blueprints: Path) -> None:
        path = tmp_blueprints / "agents" / "test_detector.yaml"
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_agent_from_path(path)
        assert bp.id == "test_detector"

    def test_load_strategy_from_path(self, tmp_blueprints: Path) -> None:
        path = tmp_blueprints / "strategies" / "multi_signal_entry.yaml"
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_strategy_from_path(path)
        assert bp.id == "multi_signal_entry"


class TestBuildStrandsAgent:
    """Tests for build_strands_agent prompt and mode features."""

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_strands_agent_resolves_prompt(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path
    ) -> None:
        loader = BlueprintLoader(blueprints_dir=tmp_blueprints, prompt_dir=tmp_prompts)
        mock_agent_cls.return_value = MagicMock()

        mcp_client = MagicMock()
        loader.build_strands_agent("test_detector", mcp_clients={"data-mcp": mcp_client})

        # Verify Agent was called with resolved prompt text
        call_kwargs = mock_agent_cls.call_args
        assert "system_prompt" in call_kwargs.kwargs or len(call_kwargs.args) > 0

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_strands_agent_prompt_failure_raises(
        self, mock_agent_cls, tmp_blueprints: Path
    ) -> None:
        # No prompt_dir and no prompt_client → should fail on prompt resolution
        loader = BlueprintLoader(blueprints_dir=tmp_blueprints)
        mcp_client = MagicMock()

        with pytest.raises(BlueprintLoadError):
            loader.build_strands_agent("test_detector", mcp_clients={"data-mcp": mcp_client})

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_strands_agent_mode_gating(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path
    ) -> None:
        # Modify blueprint to disable production mode for this test
        bp_path = tmp_blueprints / "agents" / "test_detector.yaml"
        with open(bp_path) as f:
            data = yaml.safe_load(f)
        data["execution_modes"]["production"] = False
        with open(bp_path, "w") as f:
            yaml.dump(data, f)

        loader = BlueprintLoader(blueprints_dir=tmp_blueprints, prompt_dir=tmp_prompts)
        mock_agent_cls.return_value = MagicMock()
        mcp_client = MagicMock()

        # simulation is enabled in the sample blueprint
        agent = loader.build_strands_agent(
            "test_detector",
            mcp_clients={"data-mcp": mcp_client},
            mode=ExecutionMode.SIMULATION,
        )
        assert agent is not None

        # production is NOT enabled → should raise
        with pytest.raises(BlueprintLoadError):
            loader.build_strands_agent(
                "test_detector",
                mcp_clients={"data-mcp": mcp_client},
                mode=ExecutionMode.PRODUCTION,
            )


class TestBuildAgentSession:
    """Tests for build_agent_session lifecycle management."""

    def _make_loader(self, tmp_blueprints, tmp_prompts, mock_mcp_factory, **overrides):
        """Helper to create a loader with default registries for the sample blueprint."""
        kwargs = {
            "blueprints_dir": tmp_blueprints,
            "prompt_dir": tmp_prompts,
            "mcp_factory": mock_mcp_factory,
            "hook_registry": {"ObservabilityHook": MagicMock},
            "schema_registry": _DEFAULT_SCHEMA_REG,
        }
        kwargs.update(overrides)
        return BlueprintLoader(**kwargs)

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_enters_mcp_clients(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path, mock_mcp_factory
    ) -> None:
        loader = self._make_loader(tmp_blueprints, tmp_prompts, mock_mcp_factory)
        mock_agent_cls.return_value = MagicMock()

        with loader.build_agent_session("test_detector") as session:
            assert isinstance(session, AgentSession)
            # MCP clients should have __enter__ called
            for client in session._mcp_clients:
                client.__enter__.assert_called_once()

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_exits_mcp_clients(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path, mock_mcp_factory
    ) -> None:
        loader = self._make_loader(tmp_blueprints, tmp_prompts, mock_mcp_factory)
        mock_agent_cls.return_value = MagicMock()

        session = loader.build_agent_session("test_detector")
        with session:
            pass
        # After exit, all MCP clients should have __exit__ called
        for client in session._mcp_clients:
            client.__exit__.assert_called_once()

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_exits_on_error(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path, mock_mcp_factory
    ) -> None:
        loader = self._make_loader(tmp_blueprints, tmp_prompts, mock_mcp_factory)
        mock_agent_cls.return_value = MagicMock()

        with pytest.raises(RuntimeError), loader.build_agent_session("test_detector") as session:
            raise RuntimeError("test error")
        # Even on error, MCP clients should be cleaned up
        for client in session._mcp_clients:
            client.__exit__.assert_called_once()

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_hooks_wired(
        self,
        mock_agent_cls,
        tmp_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
        sample_hook_registry,
    ) -> None:
        loader = self._make_loader(
            tmp_blueprints,
            tmp_prompts,
            mock_mcp_factory,
            hook_registry=sample_hook_registry,
        )
        mock_agent_cls.return_value = MagicMock()

        with loader.build_agent_session("test_detector"):
            pass

        # Verify hook class was instantiated
        # (The sample blueprint has hooks: ["ObservabilityHook"])
        sample_hook_registry["ObservabilityHook"].assert_called()

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_unknown_hook_raises(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path, mock_mcp_factory
    ) -> None:
        loader = self._make_loader(
            tmp_blueprints,
            tmp_prompts,
            mock_mcp_factory,
            hook_registry={"something_else": MagicMock()},
        )

        with pytest.raises(BlueprintLoadError, match="Unknown hook"):
            loader.build_agent_session("test_detector")

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_output_schema(
        self,
        mock_agent_cls,
        tmp_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
        sample_schema_registry,
    ) -> None:
        # Modify the sample test_detector blueprint to use a known test schema
        bp_path = tmp_blueprints / "agents" / "test_detector.yaml"
        with open(bp_path) as f:
            data = yaml.safe_load(f)
        data["output_schema"] = "TestOutput"
        # Remove hooks to avoid needing the hook registry for this test
        data["hooks"] = []
        with open(bp_path, "w") as f:
            yaml.dump(data, f)

        loader = BlueprintLoader(
            blueprints_dir=tmp_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
            schema_registry=sample_schema_registry,
        )
        mock_agent_cls.return_value = MagicMock()

        with loader.build_agent_session("test_detector"):
            pass

        # Verify structured_output_model was passed to Agent
        call_kwargs = mock_agent_cls.call_args.kwargs
        assert call_kwargs.get("structured_output_model") == sample_schema_registry["TestOutput"]

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_no_factory_fallback(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path
    ) -> None:
        loader = BlueprintLoader(blueprints_dir=tmp_blueprints, prompt_dir=tmp_prompts)

        with pytest.raises(BlueprintLoadError, match="no mcp_factory"):
            loader.build_agent_session("test_detector")

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_tool_filter_passed(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path, mock_mcp_factory
    ) -> None:
        """Verify that blueprint-declared tool names are passed to the factory as tool_filter."""
        loader = self._make_loader(tmp_blueprints, tmp_prompts, mock_mcp_factory)
        mock_agent_cls.return_value = MagicMock()

        with loader.build_agent_session("test_detector") as session:
            # Sample blueprint has two tool entries:
            #   data-mcp: [get_watchlist_gaps, get_data, get_volume_profile]
            #   artifacts-mcp: [create_artifact]
            data_client = session._mcp_clients[0]
            artifacts_client = session._mcp_clients[1]
            assert data_client.tool_filter == ["get_watchlist_gaps", "get_data", "get_volume_profile"]
            assert artifacts_client.tool_filter == ["create_artifact"]

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_agent_session_multiple_hooks_uses_composite(
        self, mock_agent_cls, tmp_blueprints: Path, tmp_prompts: Path, mock_mcp_factory
    ) -> None:
        """Verify that multiple hooks are wrapped in CompositeCallbackHandler."""
        # Modify blueprint to have two hooks
        bp_path = tmp_blueprints / "agents" / "test_detector.yaml"
        with open(bp_path) as f:
            data = yaml.safe_load(f)
        data["hooks"] = ["HookA", "HookB"]
        with open(bp_path, "w") as f:
            yaml.dump(data, f)

        mock_hook_a = MagicMock()
        mock_hook_a.return_value = MagicMock()
        mock_hook_b = MagicMock()
        mock_hook_b.return_value = MagicMock()

        loader = BlueprintLoader(
            blueprints_dir=tmp_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
            hook_registry={"HookA": mock_hook_a, "HookB": mock_hook_b},
            schema_registry=_DEFAULT_SCHEMA_REG,
        )
        mock_agent_cls.return_value = MagicMock()

        with loader.build_agent_session("test_detector"):
            pass

        call_kwargs = mock_agent_cls.call_args.kwargs
        handler = call_kwargs.get("callback_handler")
        assert handler is not None
        # Should be a CompositeCallbackHandler, not a raw list
        assert not isinstance(handler, list), "Multiple hooks must be wrapped, not passed as list"
        assert callable(handler), "Handler must be callable"


class TestMultiAgentSession:
    """Tests for multi-agent orchestration in build_agent_session."""

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_swarm_session(
        self,
        mock_agent_cls,
        tmp_multi_agent_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
    ) -> None:
        """Blueprint with multi_agent: {pattern: swarm} builds a Swarm session."""
        mock_agent_cls.return_value = MagicMock()
        mock_swarm = MagicMock()

        loader = BlueprintLoader(
            blueprints_dir=tmp_multi_agent_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
        )

        with (
            patch("agent_core.blueprints.loader.Swarm", create=True),
            patch("strands.multiagent.swarm.Swarm", mock_swarm, create=True),
        ):
            session = loader.build_agent_session("swarm_agent")

        assert isinstance(session, AgentSession)
        assert session.pattern == "swarm"
        assert session.multi_agent is not None

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_graph_session(
        self,
        mock_agent_cls,
        tmp_multi_agent_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
    ) -> None:
        """Blueprint with multi_agent: {pattern: graph} builds a Graph session."""
        mock_agent_cls.return_value = MagicMock()
        mock_graph_builder = MagicMock()
        mock_graph = MagicMock()
        mock_graph_builder.return_value = mock_graph_builder
        mock_graph_builder.add_node.return_value = MagicMock()
        mock_graph_builder.build.return_value = mock_graph

        loader = BlueprintLoader(
            blueprints_dir=tmp_multi_agent_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
        )

        with patch("strands.multiagent.graph.GraphBuilder", mock_graph_builder, create=True):
            session = loader.build_agent_session("graph_agent")

        assert isinstance(session, AgentSession)
        assert session.pattern == "graph"
        assert session.multi_agent is mock_graph

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_single_session_no_multi_agent(
        self,
        mock_agent_cls,
        tmp_multi_agent_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
    ) -> None:
        """Blueprint with multi_agent: null returns pattern='single' (backward compat)."""
        mock_agent_cls.return_value = MagicMock()

        loader = BlueprintLoader(
            blueprints_dir=tmp_multi_agent_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
        )

        session = loader.build_agent_session("single_agent")

        assert isinstance(session, AgentSession)
        assert session.pattern == "single"
        assert session.multi_agent is None

    def test_session_run_delegates_to_agent(self) -> None:
        """session.run(prompt) calls session.agent(prompt) when pattern is single."""
        mock_agent = MagicMock()
        mock_agent.return_value = {"result": "ok"}

        session = AgentSession(agent=mock_agent, mcp_clients=[])
        result = session.run("test prompt")

        mock_agent.assert_called_once_with("test prompt")
        assert result == {"result": "ok"}

    def test_session_run_delegates_to_multi_agent(self) -> None:
        """session.run(prompt) calls multi_agent(prompt) when pattern is swarm."""
        mock_agent = MagicMock()
        mock_multi = MagicMock()
        mock_multi.return_value = {"swarm_result": "done"}

        session = AgentSession(
            agent=mock_agent, mcp_clients=[],
            multi_agent=mock_multi, pattern="swarm",
        )
        result = session.run("test prompt")

        mock_multi.assert_called_once_with("test prompt")
        mock_agent.assert_not_called()
        assert result == {"swarm_result": "done"}

    def test_multi_agent_config_rejects_invalid_pattern(self) -> None:
        """MultiAgentConfig rejects patterns other than 'swarm' or 'graph'."""
        with pytest.raises(ValidationError):
            MultiAgentConfig(pattern="invalid")


class TestMultiNodeSession:
    """Tests for multi-node graph/swarm orchestration in build_agent_session."""

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_multi_node_graph(
        self,
        mock_agent_cls,
        tmp_multi_node_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
    ) -> None:
        """Multi-node graph: loads multiple blueprints and builds Graph."""
        mock_agent_cls.return_value = MagicMock()
        mock_graph_builder = MagicMock()
        mock_graph = MagicMock()
        mock_graph_builder.return_value = mock_graph_builder
        mock_graph_builder.add_node.return_value = MagicMock()
        mock_graph_builder.build.return_value = mock_graph

        loader = BlueprintLoader(
            blueprints_dir=tmp_multi_node_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
        )

        with patch("strands.multiagent.graph.GraphBuilder", mock_graph_builder, create=True):
            session = loader.build_agent_session("multi_graph_agent")

        assert isinstance(session, AgentSession)
        assert session.pattern == "graph"
        assert session.multi_agent is mock_graph
        # 2 node agents + 1 primary = 3 Agent() calls
        assert mock_agent_cls.call_count == 3
        # GraphBuilder.add_node called for each node
        assert mock_graph_builder.add_node.call_count == 2

    @patch("agent_core.blueprints.loader.Agent")
    def test_build_multi_node_swarm(
        self,
        mock_agent_cls,
        tmp_multi_node_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
    ) -> None:
        """Multi-node swarm: loads multiple blueprints and builds Swarm."""
        mock_agent_cls.return_value = MagicMock()
        mock_swarm_cls = MagicMock()
        mock_swarm = MagicMock()
        mock_swarm_cls.return_value = mock_swarm

        loader = BlueprintLoader(
            blueprints_dir=tmp_multi_node_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
        )

        with patch("strands.multiagent.swarm.Swarm", mock_swarm_cls, create=True):
            session = loader.build_agent_session("multi_swarm_agent")

        assert isinstance(session, AgentSession)
        assert session.pattern == "swarm"
        # Swarm called with list of node agents
        mock_swarm_cls.assert_called_once()
        call_kwargs = mock_swarm_cls.call_args
        assert len(call_kwargs.kwargs.get("nodes", call_kwargs.args[0] if call_kwargs.args else [])) == 2

    @patch("agent_core.blueprints.loader.Agent")
    def test_multi_node_mcp_clients_collected(
        self,
        mock_agent_cls,
        tmp_multi_node_blueprints: Path,
        tmp_prompts: Path,
        mock_mcp_factory,
    ) -> None:
        """All MCP clients from all nodes are collected into the session."""
        mock_agent_cls.return_value = MagicMock()
        mock_graph_builder = MagicMock()
        mock_graph = MagicMock()
        mock_graph_builder.return_value = mock_graph_builder
        mock_graph_builder.add_node.return_value = MagicMock()
        mock_graph_builder.build.return_value = mock_graph

        loader = BlueprintLoader(
            blueprints_dir=tmp_multi_node_blueprints,
            prompt_dir=tmp_prompts,
            mcp_factory=mock_mcp_factory,
        )

        with patch("strands.multiagent.graph.GraphBuilder", mock_graph_builder, create=True):
            session = loader.build_agent_session("multi_graph_agent")

        # Primary agent + 2 node agents = 3 MCP client sets
        assert len(session._mcp_clients) == 3
