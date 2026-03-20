"""AgentCore Runtime entrypoint.

Provides AgentCoreApp — a thin wrapper over BedrockAgentCoreApp from the
bedrock_agentcore SDK. All agents run on AgentCore Runtime (microVM per
session). The @app.entrypoint decorator registers the handler function.

Contract:
  - POST /invocations on port 8080
  - GET /ping on port 8080
  - context.session_id and context.request_headers available in handler
  - Streaming via async def + yield (SSE)
  - Starlette middleware stack support
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from starlette.middleware import Middleware

from agent_core.runtime.adapter import InvocationContext

logger = logging.getLogger(__name__)


class AgentCoreApp:
    """AgentCore Runtime application.

    Wraps BedrockAgentCoreApp and exposes the @app.entrypoint decorator
    pattern. Handles all HTTP serving, streaming, and session routing
    via the SDK.

    Usage::

        from agent_core.runtime.entrypoint import AgentCoreApp

        app = AgentCoreApp()

        @app.entrypoint
        def handler(payload, context):
            session_id = context.session_id
            headers = context.request_headers
            return agent(payload.get("prompt")).message

        # Streaming:
        @app.entrypoint
        async def handler(payload, context):
            async for event in agent.stream_async(payload.get("prompt")):
                if "data" in event:
                    yield event["data"]

        if __name__ == "__main__":
            app.run()
    """

    def __init__(
        self,
        *,
        middleware: list[Middleware] | None = None,
    ) -> None:
        self._sdk_app = BedrockAgentCoreApp(
            middleware=middleware or [],
        )
        self._entrypoint_fn: Callable | None = None
        logger.info("AgentCoreApp initialized")

    def entrypoint(self, fn: Callable) -> Callable:
        """Decorator to register the agent entrypoint handler.

        The decorated function receives (payload, context) where:
          - payload: dict with the invocation data (prompt, parameters, etc.)
          - context: SDK context with session_id and request_headers

        For streaming, use async def + yield.

        Args:
            fn: Handler function or async generator.

        Returns:
            The original function, unmodified.
        """
        self._entrypoint_fn = fn
        self._sdk_app.entrypoint(fn)
        logger.info("Registered entrypoint: %s", fn.__name__)
        return fn

    def run(self) -> None:
        """Start the AgentCore Runtime server.

        Starts the HTTP server on port 8080, serving POST /invocations
        and GET /ping. Blocks until the server is stopped.
        """
        if self._entrypoint_fn is None:
            raise RuntimeError(
                "No entrypoint registered. Use @app.entrypoint to register a handler."
            )
        logger.info("Starting AgentCore Runtime server")
        self._sdk_app.run()

    def invoke(
        self,
        payload: dict[str, Any],
        *,
        session_id: str = "",
        request_headers: dict[str, str] | None = None,
    ) -> Any:
        """Invoke the registered entrypoint directly (for testing).

        Args:
            payload: Invocation payload dict.
            session_id: Optional session ID override.
            request_headers: Optional request headers.

        Returns:
            Handler result.
        """
        if self._entrypoint_fn is None:
            raise RuntimeError("No entrypoint registered.")

        context = InvocationContext(
            session_id=session_id,
            request_headers=request_headers or {},
        )
        return self._entrypoint_fn(payload, context)
