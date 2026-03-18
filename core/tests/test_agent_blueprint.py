"""Tests for AgentBlueprint model."""
from __future__ import annotations

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.schemas.model_config import ModelConfig


class TestAgentBlueprint:
    def test_parse_sample_yaml(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.id == "gap_detector"
        assert bp.version == "1.2.0"
        assert bp.name == "Gap Detection Agent"
        assert bp.prompt_ref == "gap_detector_v1.2"

    def test_model_config(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.model.provider == "bedrock"
        assert bp.model.model_id == "us.anthropic.claude-sonnet-4-20250514-v1:0"
        assert bp.model.temperature == 0.2
        assert bp.model.max_tokens == 4096

    def test_tools_parsed(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert len(bp.tools) == 2
        assert bp.tools[0].mcp == "data-mcp"
        assert "get_watchlist_gaps" in bp.tools[0].tools
        assert bp.tools[1].mcp == "artifacts-mcp"

    def test_execution_modes(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.execution_modes.simulation is True
        assert bp.execution_modes.staging is True
        assert bp.execution_modes.production is True

    def test_runtime(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.runtime.type == "agentcore"
        assert bp.runtime.max_iterations == 5
        assert bp.runtime.max_execution_time == 120

    def test_multi_agent(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.multi_agent is not None
        assert bp.multi_agent.pattern == "swarm"
        assert bp.multi_agent.execution_timeout == 90
        assert bp.multi_agent.max_handoffs == 20

    def test_hooks(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert "ObservabilityHook" in bp.hooks

    def test_output_schema(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.output_schema == "gap_detection_output_v1"

    def test_minimal_agent(self) -> None:
        """An agent with only required fields should work."""
        bp = AgentBlueprint(
            id="minimal",
            version="0.1.0",
            name="Minimal Agent",
            model=ModelConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
            prompt_ref="minimal_v1",
        )
        assert bp.id == "minimal"
        assert bp.execution_modes.simulation is True
        assert bp.execution_modes.staging is False
