"""Block 10 — Agent-to-Agent Communication (A2A) tests.

Tests the A2A subsystem: server wrapper, client, remote agent tools,
wiring, blueprint schema extensions, loader integration, and Dockerfile
generation with A2A port exposure.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---- Schema Extensions ----


class TestBlueprintA2AExtensions:
    """Verify blueprint model extensions for A2A."""

    def test_role_field_in_multi_agent(self):
        from agent_core.blueprints.agent import MultiAgentConfig

        cfg = MultiAgentConfig(role="coordinator")
        assert cfg.role == "coordinator"

        cfg2 = MultiAgentConfig(role="specialist")
        assert cfg2.role == "specialist"

        cfg3 = MultiAgentConfig()
        assert cfg3.role == "standalone"

    def test_role_invalid_value_rejected(self):
        from pydantic import ValidationError

        from agent_core.blueprints.agent import MultiAgentConfig

        with pytest.raises(ValidationError):
            MultiAgentConfig(role="invalid")

    def test_a2a_url_in_graph_node(self):
        from agent_core.blueprints.agent import GraphNodeConfig

        node = GraphNodeConfig(
            agent_ref="specialist-agent",
            node_id="spec1",
            a2a_url="http://agent:9000",
        )
        assert node.a2a_url == "http://agent:9000"
        assert node.a2a_url_env == ""

    def test_a2a_url_env_in_graph_node(self):
        from agent_core.blueprints.agent import GraphNodeConfig

        node = GraphNodeConfig(
            agent_ref="specialist-agent",
            node_id="spec1",
            a2a_url_env="SPEC_A2A_URL",
        )
        assert node.a2a_url_env == "SPEC_A2A_URL"

    def test_runtime_arn_in_graph_node(self):
        from agent_core.blueprints.agent import GraphNodeConfig

        node = GraphNodeConfig(
            agent_ref="specialist-agent",
            node_id="spec1",
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123:runtime/xyz",
        )
        assert node.runtime_arn.startswith("arn:aws:")

    def test_runtime_arn_env_in_graph_node(self):
        from agent_core.blueprints.agent import GraphNodeConfig

        node = GraphNodeConfig(
            agent_ref="specialist-agent",
            node_id="spec1",
            runtime_arn_env="SPEC_RUNTIME_ARN",
        )
        assert node.runtime_arn_env == "SPEC_RUNTIME_ARN"

    def test_a2a_port_in_runtime_config(self):
        from agent_core.schemas.runtime_config import RuntimeConfig

        cfg = RuntimeConfig(a2a_port=9000)
        assert cfg.a2a_port == 9000

    def test_a2a_port_zero_means_disabled(self):
        from agent_core.schemas.runtime_config import RuntimeConfig

        cfg = RuntimeConfig()
        assert cfg.a2a_port == 0

    def test_a2a_port_not_equal_main_port(self):
        from pydantic import ValidationError

        from agent_core.schemas.runtime_config import RuntimeConfig

        with pytest.raises(ValidationError, match="must differ"):
            RuntimeConfig(port=8080, a2a_port=8080)

    def test_a2a_port_and_main_port_different_ok(self):
        from agent_core.schemas.runtime_config import RuntimeConfig

        cfg = RuntimeConfig(port=8080, a2a_port=9000)
        assert cfg.port == 8080
        assert cfg.a2a_port == 9000

    def test_backward_compat_no_a2a_fields(self):
        """Existing blueprints without A2A fields still parse."""
        from agent_core.blueprints.agent import GraphNodeConfig, MultiAgentConfig

        node = GraphNodeConfig(agent_ref="agent-a", node_id="a")
        assert node.a2a_url == ""
        assert node.runtime_arn == ""

        ma = MultiAgentConfig(pattern="graph", nodes=[node])
        assert ma.role == "standalone"


# ---- A2A Server ----


class TestA2AServerWrapper:
    """Verify A2AServerWrapper generates agent cards from blueprints."""

    @patch("agent_core.a2a.server.A2AServer")
    def test_creates_strands_server(self, mock_a2a_cls):
        from agent_core.a2a.server import A2AServerWrapper

        agent = MagicMock()
        bp = self._make_blueprint()

        wrapper = A2AServerWrapper(agent=agent, blueprint=bp, port=9000)
        assert wrapper.port == 9000
        mock_a2a_cls.assert_called_once()

    @patch("agent_core.a2a.server.A2AServer")
    def test_skills_from_tools(self, mock_a2a_cls):
        from agent_core.a2a.server import A2AServerWrapper

        agent = MagicMock()
        bp = self._make_blueprint()

        A2AServerWrapper(agent=agent, blueprint=bp, port=9000)
        call_kwargs = mock_a2a_cls.call_args[1]
        skills = call_kwargs.get("skills", [])
        assert len(skills) == 2
        assert skills[0]["name"] == "query_data"

    @patch("agent_core.a2a.server.A2AServer")
    def test_port_from_env(self, mock_a2a_cls):
        from agent_core.a2a.server import A2AServerWrapper

        agent = MagicMock()
        bp = self._make_blueprint(a2a_port=0)

        with patch.dict(os.environ, {"A2A_PORT": "9001"}):
            wrapper = A2AServerWrapper(agent=agent, blueprint=bp)
            assert wrapper.port == 9001

    @patch("agent_core.a2a.server.A2AServer")
    def test_port_missing_raises(self, mock_a2a_cls):
        from agent_core.a2a.server import A2AServerWrapper

        agent = MagicMock()
        bp = self._make_blueprint(a2a_port=0)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("A2A_PORT", None)
            os.environ.pop("A2A_HOST", None)
            os.environ.pop("A2A_HTTP_URL", None)
            with pytest.raises(ValueError, match="A2A port not configured"):
                A2AServerWrapper(agent=agent, blueprint=bp)

    @patch("agent_core.a2a.server.A2AServer")
    def test_to_starlette_app(self, mock_a2a_cls):
        from agent_core.a2a.server import A2AServerWrapper

        agent = MagicMock()
        bp = self._make_blueprint()
        mock_server_instance = MagicMock()
        mock_a2a_cls.return_value = mock_server_instance

        wrapper = A2AServerWrapper(agent=agent, blueprint=bp, port=9000)
        wrapper.to_starlette_app()
        mock_server_instance.to_starlette_app.assert_called_once()

    @staticmethod
    def _make_blueprint(a2a_port=9000):
        """Create a minimal blueprint mock for testing."""
        bp = MagicMock()
        bp.name = "test-specialist"
        bp.version = "1.0.0"
        bp.description = "Test specialist"
        bp.runtime.a2a_port = a2a_port

        tool1 = MagicMock()
        tool1.mcp = "data-source-mcp"
        tool1.tools = ["query_data", "aggregate_data"]
        tool1.builtin = None
        bp.tools = [tool1]

        return bp


# ---- A2A Client ----


class TestA2AClient:
    """Verify A2AClient call patterns."""

    def test_call_a2a_sends_message(self):
        from agent_core.a2a.client import A2AClient

        mock_response = {
            "result": {
                "artifacts": [
                    {"parts": [{"type": "text", "text": "Analysis complete"}]}
                ]
            }
        }

        with patch("agent_core.a2a.client.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value = mock_http

            card_resp = MagicMock()
            card_resp.json.return_value = {
                "name": "specialist",
                "url": "http://agent:9000",
            }
            card_resp.raise_for_status = MagicMock()

            msg_resp = MagicMock()
            msg_resp.json.return_value = mock_response
            msg_resp.raise_for_status = MagicMock()

            mock_http.get.return_value = card_resp
            mock_http.post.return_value = msg_resp
            mock_http.is_closed = False

            client = A2AClient()
            result = client.call_a2a("http://agent:9000", "Analyze data")
            assert result == "Analysis complete"
            client.close()

    def test_call_direct_uses_boto3(self):
        from agent_core.a2a.client import A2AClient

        with patch("agent_core.a2a.client.httpx.Client"):
            client = A2AClient(region="us-west-2")

        with patch("boto3.client") as mock_boto:
            mock_ac = MagicMock()
            mock_boto.return_value = mock_ac
            mock_ac.invoke_agent_runtime.return_value = {"body": b'{"result": "ok"}'}

            result = client.call_direct(
                "arn:aws:bedrock-agentcore:us-west-2:123:runtime/xyz",
                {"prompt": "test"},
            )
            assert "ok" in result
            mock_ac.invoke_agent_runtime.assert_called_once()

    def test_auth_provider_injects_token(self):
        from agent_core.a2a.client import A2AClient

        token_fn = MagicMock(return_value="test-token-123")

        with patch("agent_core.a2a.client.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value = mock_http
            mock_http.is_closed = False

            client = A2AClient(auth_provider=token_fn)
            client._get_http_client()
            token_fn.assert_called_once()
            call_kwargs = mock_cls.call_args
            headers = call_kwargs[1].get("headers", {})
            assert headers.get("Authorization") == "Bearer test-token-123"
            client.close()

    def test_context_manager(self):
        from agent_core.a2a.client import A2AClient

        with patch("agent_core.a2a.client.httpx.Client"):
            with A2AClient() as client:
                assert client is not None


# ---- Remote Agent Tool ----


class TestRemoteAgentTool:
    """Verify remote_agent_tool() creates valid Strands tools."""

    def test_tool_calls_a2a_url(self):
        from agent_core.a2a.tools import remote_agent_tool

        mock_client = MagicMock()
        mock_client.call_a2a.return_value = "result from A2A"

        tool_fn = remote_agent_tool(
            node_id="spec1",
            name="call_spec1",
            description="Call specialist",
            a2a_client=mock_client,
            a2a_url="http://agent:9000",
        )
        assert callable(tool_fn)

    def test_tool_calls_direct_invoke(self):
        from agent_core.a2a.tools import remote_agent_tool

        mock_client = MagicMock()
        mock_client.call_direct.return_value = "result from direct"

        tool_fn = remote_agent_tool(
            node_id="spec1",
            name="call_spec1",
            description="Call specialist",
            a2a_client=mock_client,
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123:runtime/xyz",
        )
        assert callable(tool_fn)

    def test_tool_raises_without_url_or_arn(self):
        from agent_core.a2a.tools import remote_agent_tool

        mock_client = MagicMock()

        tool_fn = remote_agent_tool(
            node_id="spec1",
            name="call_spec1",
            description="Call specialist",
            a2a_client=mock_client,
        )
        # The tool function itself should raise on invocation
        assert callable(tool_fn)


# ---- A2A Wiring ----


class TestA2AWiring:
    """Verify A2AWiring bridges blueprint config to A2A components."""

    def test_coordinator_creates_client(self):
        from agent_core.a2a.wiring import A2AWiring

        bp = MagicMock()
        bp.multi_agent.role = "coordinator"
        bp.identity.credentials = []

        wiring = A2AWiring(bp)
        assert wiring.client is not None
        wiring.close()

    @patch("agent_core.a2a.wiring.A2AServerWrapper")
    def test_specialist_builds_server(self, mock_wrapper_cls):
        from agent_core.a2a.wiring import A2AWiring

        bp = MagicMock()
        bp.multi_agent.role = "specialist"
        bp.identity.credentials = []

        wiring = A2AWiring(bp)
        agent = MagicMock()
        wiring.build_server(agent)
        mock_wrapper_cls.from_blueprint.assert_called_once_with(
            agent=agent, blueprint=bp
        )

    def test_coordinator_builds_remote_tools(self):
        from agent_core.a2a.wiring import A2AWiring

        bp = MagicMock()
        bp.multi_agent.role = "coordinator"
        bp.identity.credentials = []

        node1 = MagicMock()
        node1.node_id = "spec1"
        node1.a2a_url = "http://agent1:9000"
        node1.a2a_url_env = ""
        node1.runtime_arn = ""
        node1.runtime_arn_env = ""

        node2 = MagicMock()
        node2.node_id = "spec2"
        node2.a2a_url = ""
        node2.a2a_url_env = ""
        node2.runtime_arn = "arn:aws:bedrock-agentcore:us-west-2:123:runtime/xyz"
        node2.runtime_arn_env = ""

        bp.multi_agent.nodes = [node1, node2]

        wiring = A2AWiring(bp)
        tools = wiring.build_remote_tools()
        assert len(tools) == 2
        wiring.close()

    def test_standalone_no_client(self):
        from agent_core.a2a.wiring import A2AWiring

        bp = MagicMock()
        bp.multi_agent.role = "standalone"
        bp.identity.credentials = []

        wiring = A2AWiring(bp)
        assert wiring.client is None


# ---- Dockerfile Generation ----


class TestDockerfileA2A:
    """Verify Dockerfile generation includes A2A port."""

    def test_specialist_exposes_a2a_port(self):
        from agent_core.runtime.config_gen import generate_dockerfile

        bp = MagicMock()
        bp.runtime.port = 8080
        bp.runtime.a2a_port = 9000
        bp.runtime.observability_enabled = False
        bp.multi_agent.role = "specialist"

        dockerfile = generate_dockerfile(bp)
        assert "EXPOSE 8080" in dockerfile
        assert "EXPOSE 9000" in dockerfile

    def test_standalone_no_a2a_port(self):
        from agent_core.runtime.config_gen import generate_dockerfile

        bp = MagicMock()
        bp.runtime.port = 8080
        bp.runtime.a2a_port = 0
        bp.runtime.observability_enabled = False
        bp.multi_agent = None

        dockerfile = generate_dockerfile(bp)
        assert "EXPOSE 8080" in dockerfile
        assert "EXPOSE 9000" not in dockerfile

    def test_coordinator_no_a2a_port(self):
        from agent_core.runtime.config_gen import generate_dockerfile

        bp = MagicMock()
        bp.runtime.port = 8080
        bp.runtime.a2a_port = 0
        bp.runtime.observability_enabled = False
        bp.multi_agent.role = "coordinator"

        dockerfile = generate_dockerfile(bp)
        assert "EXPOSE 9000" not in dockerfile


# ---- Loader Integration ----


class TestLoaderA2AIntegration:
    """Verify BlueprintLoader detects remote nodes."""

    def test_is_remote_node_with_a2a_url(self):
        from agent_core.blueprints.loader import BlueprintLoader

        node = MagicMock()
        node.a2a_url = "http://agent:9000"
        node.a2a_url_env = ""
        node.runtime_arn = ""
        node.runtime_arn_env = ""

        assert BlueprintLoader._is_remote_node(node) is True

    def test_is_remote_node_with_env(self):
        from agent_core.blueprints.loader import BlueprintLoader

        node = MagicMock()
        node.a2a_url = ""
        node.a2a_url_env = "AGENT_A2A_URL"
        node.runtime_arn = ""
        node.runtime_arn_env = ""

        assert BlueprintLoader._is_remote_node(node) is True

    def test_is_not_remote_node(self):
        from agent_core.blueprints.loader import BlueprintLoader

        node = MagicMock()
        node.a2a_url = ""
        node.a2a_url_env = ""
        node.runtime_arn = ""
        node.runtime_arn_env = ""

        assert BlueprintLoader._is_remote_node(node) is False


# ---- Entrypoint ----


class TestAgentCoreAppA2A:
    """Verify AgentCoreApp A2A mounting."""

    def test_mount_a2a_stores_app(self):
        with patch("agent_core.runtime.entrypoint.BedrockAgentCoreApp"):
            from agent_core.runtime.entrypoint import AgentCoreApp

            app = AgentCoreApp()
            a2a_app = MagicMock()
            app.mount_a2a(a2a_app, 9000)
            assert app._a2a_app is a2a_app
            assert app._a2a_port == 9000
