"""In-process workflow executor for testing.

Simulates AWS Step Functions state machine execution from
WorkflowBlueprint definitions. For testing only --- production
workflows run on Step Functions via CDK.
"""

from __future__ import annotations

import copy
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_core.blueprints.workflow import WorkflowBlueprint

CHOICE_OPS: dict[str, Any] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    """Resolve a dot-delimited or JSONPath-like path in data.

    Supports: "$.field.subfield" or "field.subfield"
    """
    if path.startswith("$."):
        path = path[2:]
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _set_path(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Set a value at a dot-delimited path, creating intermediate dicts."""
    if path.startswith("$."):
        path = path[2:]
    parts = path.split(".")
    result = copy.deepcopy(data)
    current = result
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return result


@dataclass
class WorkflowExecutionResult:
    final_state_id: str
    states_visited: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    status: Literal["succeeded", "failed"] = "succeeded"


class WorkflowExecutor:
    """Executes WorkflowBlueprint state machines in-process for testing."""

    def __init__(
        self, task_handler: Callable[..., dict[str, Any]] | None = None
    ) -> None:
        self._task_handler = task_handler or (
            lambda state_id, lambda_ref, input_data: {}
        )

    def execute(
        self, blueprint: WorkflowBlueprint, initial_input: dict[str, Any]
    ) -> WorkflowExecutionResult:
        """Execute a workflow blueprint with given input."""
        if not blueprint.states:
            return WorkflowExecutionResult(
                final_state_id="",
                states_visited=[],
                status="succeeded",
            )

        states_by_id = {s.id: s for s in blueprint.states}
        current_id = blueprint.states[0].id
        data = copy.deepcopy(initial_input)
        visited: list[str] = []
        outputs: dict[str, Any] = {}
        max_steps = 100  # safety limit

        for _ in range(max_steps):
            if current_id not in states_by_id:
                return WorkflowExecutionResult(
                    final_state_id=current_id,
                    states_visited=visited,
                    outputs=outputs,
                    status="failed",
                )

            state = states_by_id[current_id]
            visited.append(current_id)

            if state.type == "succeed":
                return WorkflowExecutionResult(
                    final_state_id=current_id,
                    states_visited=visited,
                    outputs=outputs,
                    status="succeeded",
                )

            if state.type == "fail":
                return WorkflowExecutionResult(
                    final_state_id=current_id,
                    states_visited=visited,
                    outputs=outputs,
                    status="failed",
                )

            if state.type == "task":
                lambda_ref = state.lambda_ref or state.id
                task_output = self._task_handler(
                    current_id, lambda_ref, copy.deepcopy(data)
                )
                outputs[current_id] = task_output

                # Apply result_path if specified
                if state.result_path:
                    data = _set_path(data, state.result_path, task_output)
                else:
                    data.update(task_output)

                # Move to next state
                if state.next:
                    current_id = state.next
                else:
                    return WorkflowExecutionResult(
                        final_state_id=current_id,
                        states_visited=visited,
                        outputs=outputs,
                        status="succeeded",
                    )

            elif state.type == "choice":
                next_state = self._evaluate_choice(state, data)
                if next_state is None:
                    return WorkflowExecutionResult(
                        final_state_id=current_id,
                        states_visited=visited,
                        outputs=outputs,
                        status="failed",
                    )
                current_id = next_state

            elif state.type == "parallel":
                # Simplified: just move to next
                if state.next:
                    current_id = state.next
                else:
                    return WorkflowExecutionResult(
                        final_state_id=current_id,
                        states_visited=visited,
                        outputs=outputs,
                        status="succeeded",
                    )

            elif state.type == "wait":
                # Skip wait in test executor
                if state.next:
                    current_id = state.next
                else:
                    return WorkflowExecutionResult(
                        final_state_id=current_id,
                        states_visited=visited,
                        outputs=outputs,
                        status="succeeded",
                    )

            else:
                # Unknown state type, move to next if available
                if state.next:
                    current_id = state.next
                else:
                    return WorkflowExecutionResult(
                        final_state_id=current_id,
                        states_visited=visited,
                        outputs=outputs,
                        status="succeeded",
                    )

        return WorkflowExecutionResult(
            final_state_id=current_id,
            states_visited=visited,
            outputs=outputs,
            status="failed",
        )

    def _evaluate_choice(self, state: Any, data: dict[str, Any]) -> str | None:
        """Evaluate choice state rules against current data."""
        if not state.choices:
            return state.next

        for rule in state.choices:
            condition = rule.condition
            path = condition.get("path", "")
            op = condition.get("op", "eq")
            expected = condition.get("value")

            actual = _resolve_path(data, path)
            op_fn = CHOICE_OPS.get(op)

            if op_fn is not None and actual is not None:
                try:
                    if op_fn(actual, expected):
                        return rule.next
                except (TypeError, ValueError):
                    continue

        # Default fallback
        if state.default:
            return state.default
        return state.next
