"""A2A Task handler — receive, execute, and respond to A2A tasks.

Implements the A2A task lifecycle:
  1. tasks/send — receive task, invoke appropriate agent handler
  2. tasks/get — return task status/result
  3. tasks/cancel — cancel a running task

Ref: https://google.github.io/A2A/specification/
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agent_core.a2a.models import Task, TaskMessage, TaskState, TaskStatus

logger = logging.getLogger(__name__)


class A2ATaskHandler:
    """Handles A2A task lifecycle by routing to agent handlers.

    Maps A2A task messages to agent invocations and converts
    agent outputs back to A2A response format.

    Accepts an optional blueprint_loader for prompt registry compliance.
    """

    def __init__(
        self,
        agent_handlers: dict[str, Any],
        blueprint_loader: Any | None = None,
    ) -> None:
        """Initialize with a map of agent_id -> handler function.

        Args:
            agent_handlers: Map of agent_id to handler callable.
                Each handler has signature: handler(event) -> dict
            blueprint_loader: Optional BlueprintLoader instance for
                prompt/blueprint resolution. Callers should inject
                their own loader rather than relying on a default.
        """
        self._handlers = agent_handlers
        self._tasks: dict[str, Task] = {}  # In-memory store (DynamoDB in production)
        self._loader = blueprint_loader

    def send_task(self, agent_id: str, request: dict[str, Any]) -> Task:
        """Handle tasks/send — create and execute a task.

        Args:
            agent_id: Target agent ID.
            request: A2A task send request body.

        Returns:
            Task with result or error status.
        """
        task_id = request.get("id", str(uuid.uuid4()))
        session_id = request.get("sessionId")

        # Extract user message
        message_data = request.get("message", {})
        user_message = TaskMessage(
            role="user",
            parts=message_data.get("parts", []),
        )

        task = Task(
            id=task_id,
            session_id=session_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            messages=[user_message],
        )
        self._tasks[task_id] = task

        # Route to agent handler
        handler_fn = self._handlers.get(agent_id)
        if not handler_fn:
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message=TaskMessage(
                    role="agent",
                    parts=[{"type": "text", "text": f"Unknown agent: {agent_id}"}],
                ),
            )
            return task

        # Convert A2A message parts to agent event
        event = self._a2a_to_agent_event(user_message, agent_id)

        task.status = TaskStatus(state=TaskState.WORKING)

        try:
            result = handler_fn(event)

            # Convert agent response to A2A format
            response_parts = self._agent_result_to_parts(result)

            agent_message = TaskMessage(role="agent", parts=response_parts)
            task.messages.append(agent_message)

            # Store artifacts if present
            body = result.get("body")
            if body:
                import json

                body_data = json.loads(body) if isinstance(body, str) else body
                if "artifact_id" in body_data:
                    task.artifacts.append(
                        {
                            "name": f"{agent_id}_output",
                            "parts": [{"type": "data", "data": body_data}],
                        }
                    )

            task.status = TaskStatus(
                state=TaskState.COMPLETED,
                message=agent_message,
            )

        except Exception as e:
            logger.exception("A2A task execution failed: %s", task_id)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message=TaskMessage(
                    role="agent",
                    parts=[{"type": "text", "text": f"Execution failed: {e}"}],
                ),
            )

        return task

    def get_task(self, task_id: str) -> Task | None:
        """Handle tasks/get — retrieve task status."""
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> Task | None:
        """Handle tasks/cancel — cancel a running task."""
        task = self._tasks.get(task_id)
        if task and task.status.state in (TaskState.SUBMITTED, TaskState.WORKING):
            task.status = TaskStatus(state=TaskState.CANCELED)
        return task

    def _a2a_to_agent_event(self, message: TaskMessage, agent_id: str) -> dict[str, Any]:
        """Convert A2A message parts to Lambda event format."""
        event: dict[str, Any] = {"agent_id": agent_id}

        for part in message.parts:
            if part.get("type") == "data":
                # Structured data — merge into event
                event.update(part.get("data", {}))
            elif part.get("type") == "text":
                # Free text — add as query
                event["query"] = part.get("text", "")

        return event

    def _agent_result_to_parts(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert agent result to A2A message parts."""
        import json

        parts: list[dict[str, Any]] = []
        status_code = result.get("statusCode", 500)
        body = result.get("body", "{}")

        if isinstance(body, str):
            body_data = json.loads(body)
        else:
            body_data = body

        if status_code == 200:
            parts.append({"type": "data", "data": body_data})
            # Add human-readable summary
            summary = body_data.get("summary", body_data.get("message", "Task completed."))
            parts.append({"type": "text", "text": str(summary)})
        else:
            error_msg = body_data.get("error", "Unknown error")
            parts.append({"type": "text", "text": f"Error: {error_msg}"})

        return parts
