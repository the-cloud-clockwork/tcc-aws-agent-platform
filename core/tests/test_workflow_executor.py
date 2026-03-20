"""Tests for WorkflowExecutor."""

from __future__ import annotations

from agent_core.blueprints.workflow import (
    ChoiceRule,
    TriggerConfig,
    WorkflowBlueprint,
    WorkflowState,
)
from agent_core.blueprints.workflow_executor import (
    WorkflowExecutor,
    _resolve_path,
    _set_path,
)


def _make_trigger() -> TriggerConfig:
    return TriggerConfig(type="schedule", schedule="rate(1 day)")


class TestResolvePath:
    def test_simple_key(self):
        assert _resolve_path({"status": "ok"}, "status") == "ok"

    def test_nested_key(self):
        assert _resolve_path({"a": {"b": "c"}}, "a.b") == "c"

    def test_jsonpath_prefix(self):
        assert _resolve_path({"status": "ok"}, "$.status") == "ok"

    def test_missing_key(self):
        assert _resolve_path({"a": 1}, "b") is None

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert _resolve_path(data, "a.b.c.d") == 42


class TestSetPath:
    def test_simple_set(self):
        result = _set_path({}, "result", {"key": "val"})
        assert result == {"result": {"key": "val"}}

    def test_nested_set(self):
        result = _set_path({"existing": 1}, "a.b", "value")
        assert result["a"]["b"] == "value"
        assert result["existing"] == 1

    def test_does_not_mutate_original(self):
        original = {"key": "original"}
        _set_path(original, "key", "modified")
        assert original["key"] == "original"


class TestWorkflowExecutor:
    def test_empty_workflow(self):
        bp = WorkflowBlueprint(
            id="empty",
            version="1.0.0",
            name="Empty",
            description="Empty workflow",
            trigger=_make_trigger(),
            states=[],
        )
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.states_visited == []

    def test_single_task_state(self):
        bp = WorkflowBlueprint(
            id="single",
            version="1.0.0",
            name="Single Task",
            description="One task",
            trigger=_make_trigger(),
            states=[
                WorkflowState(id="task1", type="task", lambda_ref="my_lambda"),
            ],
        )
        handler_calls = []

        def mock_handler(state_id, lambda_ref, input_data):
            handler_calls.append((state_id, lambda_ref))
            return {"result": "done"}

        result = WorkflowExecutor(task_handler=mock_handler).execute(bp, {"input": "data"})
        assert result.status == "succeeded"
        assert result.states_visited == ["task1"]
        assert result.outputs["task1"] == {"result": "done"}
        assert handler_calls == [("task1", "my_lambda")]

    def test_task_chain(self):
        bp = WorkflowBlueprint(
            id="chain",
            version="1.0.0",
            name="Chain",
            description="Task chain",
            trigger=_make_trigger(),
            states=[
                WorkflowState(id="step1", type="task", next="step2"),
                WorkflowState(id="step2", type="task", next="done"),
                WorkflowState(id="done", type="succeed"),
            ],
        )
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.states_visited == ["step1", "step2", "done"]

    def test_choice_state_routing(self):
        bp = WorkflowBlueprint(
            id="choice_test",
            version="1.0.0",
            name="Choice",
            description="Choice routing",
            trigger=_make_trigger(),
            states=[
                WorkflowState(
                    id="check_risk",
                    type="choice",
                    choices=[
                        ChoiceRule(
                            condition={"path": "$.risk.status", "op": "eq", "value": "PASS"},
                            next="execute_order",
                        ),
                        ChoiceRule(
                            condition={"path": "$.risk.status", "op": "eq", "value": "FAIL"},
                            next="reject",
                        ),
                    ],
                    default="reject",
                ),
                WorkflowState(id="execute_order", type="succeed"),
                WorkflowState(id="reject", type="fail"),
            ],
        )
        # Test PASS path
        result = WorkflowExecutor().execute(bp, {"risk": {"status": "PASS"}})
        assert result.status == "succeeded"
        assert "execute_order" in result.states_visited

        # Test FAIL path
        result = WorkflowExecutor().execute(bp, {"risk": {"status": "FAIL"}})
        assert result.status == "failed"
        assert "reject" in result.states_visited

    def test_result_path_merging(self):
        bp = WorkflowBlueprint(
            id="result_path",
            version="1.0.0",
            name="ResultPath",
            description="Result path test",
            trigger=_make_trigger(),
            states=[
                WorkflowState(
                    id="analyze",
                    type="task",
                    result_path="$.analysis",
                    next="check",
                ),
                WorkflowState(id="check", type="succeed"),
            ],
        )

        def handler(state_id, lambda_ref, input_data):
            return {"score": 0.85}

        result = WorkflowExecutor(task_handler=handler).execute(bp, {"target": "item-A"})
        assert result.status == "succeeded"
        assert result.outputs["analyze"] == {"score": 0.85}

    def test_fail_state(self):
        bp = WorkflowBlueprint(
            id="fail_test",
            version="1.0.0",
            name="Fail",
            description="Fail test",
            trigger=_make_trigger(),
            states=[
                WorkflowState(id="start", type="task", next="error"),
                WorkflowState(id="error", type="fail"),
            ],
        )
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "failed"
        assert result.final_state_id == "error"

    def test_missing_state_reference(self):
        bp = WorkflowBlueprint(
            id="missing",
            version="1.0.0",
            name="Missing",
            description="Missing state ref",
            trigger=_make_trigger(),
            states=[
                WorkflowState(id="start", type="task", next="nonexistent"),
            ],
        )
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "failed"

    def test_succeed_state(self):
        bp = WorkflowBlueprint(
            id="succeed",
            version="1.0.0",
            name="Succeed",
            description="Immediate succeed",
            trigger=_make_trigger(),
            states=[
                WorkflowState(id="done", type="succeed"),
            ],
        )
        result = WorkflowExecutor().execute(bp, {})
        assert result.status == "succeeded"
        assert result.final_state_id == "done"
