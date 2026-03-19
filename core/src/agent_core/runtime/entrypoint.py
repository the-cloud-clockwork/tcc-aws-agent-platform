"""AgentCore Runtime entrypoint.

This module provides the @register_agent decorator and AgentCoreApp class
that registers agent handlers with the AgentCore Runtime. Each agent is
registered as a named entrypoint that AgentCore can invoke by agent_id.

In Lambda mode, this module is not imported — handlers use the standard
Lambda handler(event, context) signature directly.

Design rule:
  "Agent handlers must work with both Lambda event and AgentCore payload
   — use a thin adapter."
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from agent_core.runtime.adapter import (
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
    normalize_payload,
)
from agent_core.runtime.session import SessionManager

logger = logging.getLogger(__name__)

# Global registry of agent handler functions
_AGENT_REGISTRY: dict[str, Callable] = {}


def register_agent(agent_id: str) -> Callable:
    """Decorator to register an agent handler function.

    The decorated function must accept an AgentPayload and return an AgentResult.
    It will be callable from both Lambda and AgentCore contexts.

    Usage:
        @register_agent("my-agent")
        def handle_my_agent(payload: AgentPayload, session: SessionState) -> AgentResult:
            ...

    Args:
        agent_id: Unique agent identifier matching the blueprint YAML.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable) -> Callable:
        _AGENT_REGISTRY[agent_id] = func
        logger.info("Registered agent handler: %s", agent_id)
        return func

    return decorator


def get_registered_agents() -> dict[str, Callable]:
    """Return the registry of all registered agent handlers."""
    return dict(_AGENT_REGISTRY)


class AgentCoreApp:
    """AgentCore Runtime application wrapper.

    Manages the lifecycle of agent handlers in AgentCore Runtime.
    Provides the entrypoint that AgentCore invokes, routing to the
    correct agent handler based on agent_id in the payload.

    In Lambda mode, this class is not used — each handler has its
    own Lambda function. In AgentCore mode, all agents share one
    Runtime instance and this class routes between them.

    When a ``GenericHandler`` is provided, ``invoke()`` delegates to it
    instead of using the legacy registry-based dispatch.
    """

    def __init__(self, handler=None) -> None:
        self._handler = handler
        self.runtime_mode = get_runtime_mode()
        self.session_manager = SessionManager(
            runtime_mode=self.runtime_mode.value,
        )
        self._agentcore_runtime = None
        logger.info("AgentCoreApp initialized, mode=%s", self.runtime_mode.value)

    def start(self) -> None:
        """Start the AgentCore Runtime.

        In AgentCore mode: initializes the Runtime SDK and registers handlers.
        In Lambda mode: no-op (handlers are invoked directly by AWS Lambda).
        """
        if self.runtime_mode != RuntimeMode.AGENTCORE:
            logger.info("Lambda mode — skipping AgentCore Runtime start")
            return

        try:
            from bedrock_agentcore.runtime import AgentCoreRuntime

            self._agentcore_runtime = AgentCoreRuntime(
                agent_name=os.environ.get("AGENTCORE_AGENT_NAME", "agents"),
                region=os.environ.get("AWS_REGION", "eu-west-1"),
            )

            # Register all handlers as entrypoints
            for agent_id, handler_fn in _AGENT_REGISTRY.items():
                self._agentcore_runtime.register_entrypoint(
                    name=agent_id,
                    handler=self._wrap_handler(agent_id, handler_fn),
                )
                logger.info("Registered entrypoint: %s", agent_id)

            # Start the runtime event loop
            self._agentcore_runtime.start()
            logger.info("AgentCore Runtime started with %d agents", len(_AGENT_REGISTRY))

        except ImportError:
            logger.error("bedrock-agentcore-runtime not installed. Install with: pip install agent-core[agentcore]")
            raise
        except Exception:
            logger.exception("Failed to start AgentCore Runtime")
            raise

    def invoke(
        self,
        event_or_payload: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any]:
        """Invoke an agent handler — works in both Lambda and AgentCore mode.

        When a GenericHandler was provided at construction, delegates to it.
        Otherwise falls back to the legacy registry-based dispatch.

        Args:
            event_or_payload: Raw Lambda event or AgentCore payload.
            context: Lambda context (optional, unused in AgentCore).

        Returns:
            Response dict in the appropriate format for the runtime.
        """
        if self._handler is not None:
            return self._handler.handle(event_or_payload, context)
        return self._legacy_invoke(event_or_payload, context)

    def _legacy_invoke(
        self,
        event_or_payload: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any]:
        """Legacy invoke path using the global agent registry.

        This is the original invoke logic retained for backward compatibility
        with code that registers handlers via ``@register_agent`` and relies
        on the module-level ``app`` singleton.

        Args:
            event_or_payload: Raw Lambda event or AgentCore payload.
            context: Lambda context (optional, unused in AgentCore).

        Returns:
            Response dict in the appropriate format for the runtime.
        """
        payload = normalize_payload(event_or_payload)

        agent_id = payload.agent_id
        handler_fn = _AGENT_REGISTRY.get(agent_id)

        if handler_fn is None:
            error_msg = f"No handler registered for agent_id '{agent_id}'. Registered: {list(_AGENT_REGISTRY.keys())}"
            logger.error(error_msg)
            result = AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=payload.session_id,
                error=error_msg,
            )
            return self._format_response(result)

        # Create session
        session = self.session_manager.create_session(
            session_id=payload.session_id,
            agent_id=agent_id,
            execution_mode=payload.execution_mode,
            memory_context=payload.memory_context,
        )

        try:
            result = handler_fn(payload, session)

            # Persist session memory
            self.session_manager.persist_session(session)

            return self._format_response(result)

        except Exception as e:
            logger.exception("Agent %s failed", agent_id)
            result = AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=payload.session_id,
                error=str(e),
            )
            return self._format_response(result)

    def _wrap_handler(self, _agent_id: str, _handler_fn: Callable) -> Callable:
        """Wrap a handler function for AgentCore Runtime registration.

        AgentCore Runtime invokes handlers with a single payload dict.
        This wrapper normalizes the payload and routes to the handler.
        """

        def agentcore_handler(payload: dict[str, Any]) -> dict[str, Any]:
            return self.invoke(payload)

        return agentcore_handler

    def _format_response(self, result: AgentResult) -> dict[str, Any]:
        """Format response according to current runtime mode."""
        if self.runtime_mode == RuntimeMode.AGENTCORE:
            return result.to_agentcore_response()
        return result.to_lambda_response()
