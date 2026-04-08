"""Tests for agent_core.blueprints.workflow_executor — in-process state machine."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_core.blueprints.workflow_executor import WorkflowExecutor, _resolve_path, _set_path


class TestResolvePath:
    def test_simple_key(self) -> None:
        assert _resolve_path({"a": 1}, "a") == 1

    def test_nested_key(self) -> None:
        assert _resolve_path({"a": {"b": 2}}, "a.b") == 2

    def test_jsonpath_prefix(self) -> None:
        assert _resolve_path({"x": 10}, "$.x") == 10

    def test_missing_key(self) -> None:
        assert _resolve_path({"a": 1}, "b") is None


class TestSetPath:
    def test_simple(self) -> None:
        assert _set_path({}, "a", 1) == {"a": 1}

    def test_nested(self) -> None:
        result = _set_path({}, "a.b.c", 42)
        assert result["a"]["b"]["c"] == 42

    def test_preserves_original(self) -> None:
        original = {"x": 1}
        _set_path(original, "y", 2)
        assert "y" not in original


def _make_blueprint(states: list[dict]) -> MagicMock:
    """Build a minimal WorkflowBlueprint mock from state dicts."""
    bp = MagicMock()
    mock_states = []
    for s in states:
        state = MagicMock()
        state.id = s["id"]
        state.type = s.get("type", "task")
        state.next = s.get("next")
        state.lambda_ref = s.get("lambda_ref")
        state.result_path = s.get("result_path")
        state.choices = s.get("choices")
        state.default = s.get("default")
        mock_states.append(state)
    bp.states = mock_states
    return bp


class TestWorkflowExecutor:
    def test_empty_workflow(self) -> None:
        bp = _make_blueprint([])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.states_visited == []

    def test_single_succeed_state(self) -> None:
        bp = _make_blueprint([{"id": "done", "type": "succeed"}])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.final_state_id == "done"

    def test_single_fail_state(self) -> None:
        bp = _make_blueprint([{"id": "err", "type": "fail"}])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "failed"

    def test_task_then_succeed(self) -> None:
        bp = _make_blueprint([
            {"id": "step1", "type": "task", "next": "done"},
            {"id": "done", "type": "succeed"},
        ])
        handler = MagicMock(return_value={"result": "ok"})
        result = WorkflowExecutor(task_handler=handler).execute(bp, {"input": 1})
        assert result.status == "succeeded"
        assert "step1" in result.outputs
        assert result.states_visited == ["step1", "done"]

    def test_task_with_result_path(self) -> None:
        bp = _make_blueprint([
            {"id": "s1", "type": "task", "result_path": "$.output", "next": "s2"},
            {"id": "s2", "type": "task"},
        ])
        handler = MagicMock(return_value={"val": 42})
        WorkflowExecutor(task_handler=handler).execute(bp, {"x": 1})
        # s2 should receive data with output.val = 42
        s2_call_data = handler.call_args_list[1][0][2]
        assert s2_call_data["output"]["val"] == 42

    def test_parallel_state_moves_to_next(self) -> None:
        bp = _make_blueprint([
            {"id": "p1", "type": "parallel", "next": "done"},
            {"id": "done", "type": "succeed"},
        ])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.states_visited == ["p1", "done"]

    def test_wait_state_moves_to_next(self) -> None:
        bp = _make_blueprint([
            {"id": "w1", "type": "wait", "next": "done"},
            {"id": "done", "type": "succeed"},
        ])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.states_visited == ["w1", "done"]

    def test_unknown_state_type_moves_to_next(self) -> None:
        bp = _make_blueprint([
            {"id": "u1", "type": "map", "next": "done"},
            {"id": "done", "type": "succeed"},
        ])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"

    def test_terminal_parallel_succeeds(self) -> None:
        """Parallel/wait/unknown with no next = terminal success."""
        bp = _make_blueprint([{"id": "p1", "type": "parallel"}])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.final_state_id == "p1"

    def test_terminal_wait_succeeds(self) -> None:
        bp = _make_blueprint([{"id": "w1", "type": "wait"}])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"

    def test_terminal_unknown_succeeds(self) -> None:
        bp = _make_blueprint([{"id": "x1", "type": "custom"}])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"

    def test_missing_state_fails(self) -> None:
        bp = _make_blueprint([
            {"id": "s1", "type": "task", "next": "nonexistent"},
        ])
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "failed"

    def test_choice_evaluates_condition(self) -> None:
        bp = _make_blueprint([
            {
                "id": "c1",
                "type": "choice",
                "choices": [
                    MagicMock(
                        condition={"path": "$.val", "op": "gt", "value": 5},
                        next="big",
                    ),
                ],
                "default": "small",
            },
            {"id": "big", "type": "succeed"},
            {"id": "small", "type": "succeed"},
        ])
        result = WorkflowExecutor().execute(bp, {"val": 10})
        assert result.final_state_id == "big"

    def test_choice_falls_to_default(self) -> None:
        bp = _make_blueprint([
            {
                "id": "c1",
                "type": "choice",
                "choices": [
                    MagicMock(
                        condition={"path": "$.val", "op": "gt", "value": 100},
                        next="big",
                    ),
                ],
                "default": "small",
            },
            {"id": "big", "type": "succeed"},
            {"id": "small", "type": "succeed"},
        ])
        result = WorkflowExecutor().execute(bp, {"val": 2})
        assert result.final_state_id == "small"

    def test_max_steps_safety(self) -> None:
        """Infinite loops hit the max_steps safety limit."""
        bp = _make_blueprint([
            {"id": "loop", "type": "task", "next": "loop"},
        ])
        handler = MagicMock(return_value={})
        result = WorkflowExecutor(task_handler=handler).execute(bp, {})
        assert result.status == "failed"
        assert len(result.states_visited) == 100
