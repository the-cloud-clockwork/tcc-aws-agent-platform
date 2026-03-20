"""Tests for extended MultiAgentConfig with nodes, edges, validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.blueprints.agent import GraphEdgeConfig, GraphNodeConfig, MultiAgentConfig


class TestMultiAgentConfigBackwardCompat:
    def test_empty_nodes_default(self):
        ma = MultiAgentConfig(pattern="swarm")
        assert ma.nodes == []
        assert ma.edges == []
        assert ma.entry_point is None

    def test_existing_fields_preserved(self):
        ma = MultiAgentConfig(
            pattern="graph",
            execution_timeout=120,
            node_timeout=45,
            max_handoffs=15,
        )
        assert ma.execution_timeout == 120
        assert ma.node_timeout == 45
        assert ma.max_handoffs == 15


class TestGraphNodeEdgeConfig:
    def test_node_config(self):
        node = GraphNodeConfig(agent_ref="test_detector", node_id="detect")
        assert node.agent_ref == "test_detector"
        assert node.node_id == "detect"

    def test_edge_config_unconditional(self):
        edge = GraphEdgeConfig(from_node="a", to_node="b")
        assert edge.condition is None

    def test_edge_config_conditional(self):
        edge = GraphEdgeConfig(from_node="a", to_node="b", condition="score >= 0.7")
        assert edge.condition == "score >= 0.7"


class TestMultiAgentConfigValidation:
    def test_valid_graph_with_nodes(self):
        ma = MultiAgentConfig(
            pattern="graph",
            nodes=[
                GraphNodeConfig(agent_ref="agent_a", node_id="detect"),
                GraphNodeConfig(agent_ref="agent_b", node_id="evaluate"),
            ],
            edges=[
                GraphEdgeConfig(from_node="detect", to_node="evaluate"),
            ],
            entry_point="detect",
        )
        assert len(ma.nodes) == 2
        assert len(ma.edges) == 1

    def test_invalid_edge_from_node(self):
        with pytest.raises(ValidationError, match="from_node"):
            MultiAgentConfig(
                pattern="graph",
                nodes=[GraphNodeConfig(agent_ref="a", node_id="detect")],
                edges=[GraphEdgeConfig(from_node="bad", to_node="detect")],
            )

    def test_invalid_edge_to_node(self):
        with pytest.raises(ValidationError, match="to_node"):
            MultiAgentConfig(
                pattern="graph",
                nodes=[GraphNodeConfig(agent_ref="a", node_id="detect")],
                edges=[GraphEdgeConfig(from_node="detect", to_node="bad")],
            )

    def test_invalid_entry_point(self):
        with pytest.raises(ValidationError, match="entry_point"):
            MultiAgentConfig(
                pattern="graph",
                nodes=[GraphNodeConfig(agent_ref="a", node_id="detect")],
                entry_point="nonexistent",
            )

    def test_empty_nodes_skips_validation(self):
        ma = MultiAgentConfig(
            pattern="graph",
            edges=[GraphEdgeConfig(from_node="a", to_node="b")],
        )
        assert len(ma.edges) == 1

    def test_max_iterations_field(self):
        ma = MultiAgentConfig(pattern="swarm", max_iterations=50)
        assert ma.max_iterations == 50

    def test_max_node_executions_field(self):
        ma = MultiAgentConfig(pattern="graph", max_node_executions=10)
        assert ma.max_node_executions == 10
