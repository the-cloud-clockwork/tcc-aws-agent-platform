"""Tests for agent_cli.graph — ASCII graph rendering."""

from __future__ import annotations

from agent_cli.graph import (
    _build_adjacency,
    _build_ascii_diagram,
    _build_circuit_breaker_section,
    _build_edge_table,
    _build_node_table,
    _get_node_id,
    _render_node_box,
    _topological_sort,
)


class TestBuildAdjacency:
    def test_basic(self) -> None:
        edges = [{"from": "a", "to": "b"}, {"from": "a", "to": "c"}]
        adj = _build_adjacency(edges)
        assert len(adj["a"]) == 2

    def test_with_label(self) -> None:
        edges = [{"from": "a", "to": "b", "label": "yes"}]
        adj = _build_adjacency(edges)
        assert adj["a"][0] == ("b", "yes")

    def test_source_target_keys(self) -> None:
        edges = [{"source": "x", "target": "y"}]
        adj = _build_adjacency(edges)
        assert adj["x"][0][0] == "y"


class TestGetNodeId:
    def test_id_field(self) -> None:
        assert _get_node_id({"id": "abc"}) == "abc"

    def test_node_id_field(self) -> None:
        assert _get_node_id({"node_id": "xyz"}) == "xyz"

    def test_fallback(self) -> None:
        assert _get_node_id({}) == "?"


class TestTopologicalSort:
    def test_linear_chain(self) -> None:
        node_ids = ["a", "b", "c"]
        edges = [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
        adj = _build_adjacency(edges)
        result = _topological_sort(node_ids, edges, adj)
        assert result == ["a", "b", "c"]

    def test_diamond(self) -> None:
        node_ids = ["a", "b", "c", "d"]
        edges = [
            {"from": "a", "to": "b"},
            {"from": "a", "to": "c"},
            {"from": "b", "to": "d"},
            {"from": "c", "to": "d"},
        ]
        adj = _build_adjacency(edges)
        result = _topological_sort(node_ids, edges, adj)
        assert result[0] == "a"
        assert result[-1] == "d"

    def test_isolated_node(self) -> None:
        node_ids = ["a", "b"]
        edges: list[dict] = []
        adj = _build_adjacency(edges)
        result = _topological_sort(node_ids, edges, adj)
        assert set(result) == {"a", "b"}

    def test_single_node(self) -> None:
        result = _topological_sort(["only"], [], {})
        assert result == ["only"]


class TestRenderNodeBox:
    def test_basic_box(self) -> None:
        lines = _render_node_box("mynode", {"agent_ref": "my-agent"})
        assert any("mynode" in line for line in lines)
        assert any("my-agent" in line for line in lines)
        assert lines[0].startswith("+")

    def test_gate_node(self) -> None:
        lines = _render_node_box("g1", {"type": "gate"})
        assert any("[GATE]" in line for line in lines)


class TestBuildAsciiDiagram:
    def test_no_nodes(self) -> None:
        assert _build_ascii_diagram([], []) == "(no nodes defined)"

    def test_single_node(self) -> None:
        result = _build_ascii_diagram([{"id": "n1"}], [])
        assert "n1" in result

    def test_with_edges(self) -> None:
        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"from": "a", "to": "b"}]
        result = _build_ascii_diagram(nodes, edges)
        assert "--> b" in result


class TestBuildNodeTable:
    def test_header_and_rows(self) -> None:
        result = _build_node_table([{"id": "n1", "agent_ref": "ref1"}])
        assert "| n1 |" in result
        assert "| ID |" in result


class TestBuildEdgeTable:
    def test_header_and_rows(self) -> None:
        result = _build_edge_table([{"from": "a", "to": "b"}])
        assert "| a |" in result


class TestCircuitBreakerSection:
    def test_no_gates(self) -> None:
        assert _build_circuit_breaker_section([{"id": "n1"}]) is None

    def test_with_gate(self) -> None:
        result = _build_circuit_breaker_section([
            {"id": "g1", "type": "gate", "trip_condition": "err > 5", "fallback": "stop"},
        ])
        assert result is not None
        assert "g1" in result
        assert "err > 5" in result
