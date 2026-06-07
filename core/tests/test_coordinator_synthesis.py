"""Tests for coordinator synthesis turn in multi-agent graph sessions."""

from __future__ import annotations

from unittest.mock import MagicMock

from strands.multiagent.base import Status

from agent_core.blueprints.session import AgentSession, _build_synthesis_prompt


def _make_agent_result(text: str) -> MagicMock:
    ar = MagicMock()
    ar.__str__ = lambda self: text
    return ar


def _make_graph_result(
    status: Status = Status.COMPLETED,
    node_outputs: dict[str, str] | None = None,
) -> MagicMock:
    gr = MagicMock()
    gr.status = status

    results: dict[str, MagicMock] = {}
    for node_id, text in (node_outputs or {}).items():
        nr = MagicMock()
        nr.get_agent_results.return_value = [_make_agent_result(text)]
        results[node_id] = nr
    gr.results = results
    return gr


class TestCoordinatorSynthesisTurn:
    def test_coordinator_runs_agent_after_graph(self):
        agent = MagicMock()
        agent.return_value = "coordinator_result"

        graph = MagicMock()
        graph.return_value = _make_graph_result(
            node_outputs={"gap_analysis": "gaps found", "sentiment": "bullish"}
        )

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=graph,
            pattern="graph",
            role="coordinator",
        )

        result = session.run("analyze 2026-03-24")

        assert result == "coordinator_result"
        agent.assert_called_once()
        synthesis_prompt = agent.call_args[0][0]
        assert "gap_analysis" in synthesis_prompt
        assert "gaps found" in synthesis_prompt
        assert "analyze 2026-03-24" in synthesis_prompt

    def test_synthesis_skipped_on_failed_graph(self):
        agent = MagicMock()
        graph = MagicMock()
        failed_result = _make_graph_result(status=Status.FAILED)
        graph.return_value = failed_result

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=graph,
            pattern="graph",
            role="coordinator",
        )

        result = session.run("prompt")

        assert result is failed_result
        agent.assert_not_called()

    def test_synthesis_skipped_on_interrupted_graph(self):
        agent = MagicMock()
        graph = MagicMock()
        interrupted_result = _make_graph_result(status=Status.INTERRUPTED)
        graph.return_value = interrupted_result

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=graph,
            pattern="graph",
            role="coordinator",
        )

        result = session.run("prompt")

        assert result is interrupted_result
        agent.assert_not_called()

    def test_standalone_role_no_synthesis(self):
        agent = MagicMock()
        graph = MagicMock()
        graph_result = _make_graph_result()
        graph.return_value = graph_result

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=graph,
            pattern="graph",
            role="standalone",
        )

        result = session.run("prompt")
        assert result is graph_result
        agent.assert_not_called()

    def test_specialist_role_no_synthesis(self):
        agent = MagicMock()
        graph = MagicMock()
        graph_result = _make_graph_result()
        graph.return_value = graph_result

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=graph,
            pattern="graph",
            role="specialist",
        )

        result = session.run("prompt")
        assert result is graph_result
        agent.assert_not_called()

    def test_swarm_coordinator_no_synthesis(self):
        agent = MagicMock()
        swarm = MagicMock()
        swarm_result = MagicMock()
        swarm.return_value = swarm_result

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=swarm,
            pattern="swarm",
            role="coordinator",
        )

        result = session.run("prompt")
        assert result is swarm_result
        agent.assert_not_called()

    def test_synthesis_exception_returns_graph_result(self):
        agent = MagicMock(side_effect=RuntimeError("LLM error"))
        graph = MagicMock()
        graph_result = _make_graph_result(node_outputs={"n1": "output"})
        graph.return_value = graph_result

        session = AgentSession(
            agent=agent,
            mcp_clients=[],
            multi_agent=graph,
            pattern="graph",
            role="coordinator",
        )

        result = session.run("prompt")

        assert result is graph_result

    def test_default_role_is_standalone(self):
        session = AgentSession(agent=MagicMock(), mcp_clients=[])
        assert session.role == "standalone"

    def test_role_stored(self):
        session = AgentSession(
            agent=MagicMock(), mcp_clients=[], role="coordinator"
        )
        assert session.role == "coordinator"


class TestBuildSynthesisPrompt:
    def test_contains_node_outputs(self):
        gr = _make_graph_result(
            node_outputs={
                "gap_analysis": "CRM gaps detected",
                "sentiment": "bullish signal",
            }
        )
        prompt = _build_synthesis_prompt("analyze AAPL", gr)

        assert "analyze AAPL" in prompt
        assert "[gap_analysis]" in prompt
        assert "CRM gaps detected" in prompt
        assert "[sentiment]" in prompt
        assert "bullish signal" in prompt
        assert "create_artifact" in prompt

    def test_truncates_long_node_text(self):
        gr = _make_graph_result(node_outputs={"n1": "x" * 20000})
        prompt = _build_synthesis_prompt("prompt", gr)

        assert "... (truncated)" in prompt
        assert len(prompt) < 25000

    def test_empty_graph_results(self):
        gr = MagicMock()
        gr.results = {}
        prompt = _build_synthesis_prompt("prompt", gr)

        assert "(no node outputs)" in prompt
        assert "prompt" in prompt

    def test_missing_results_attr(self):
        gr = MagicMock(spec=[])
        prompt = _build_synthesis_prompt("prompt", gr)

        assert "(no node outputs)" in prompt
