"""Platform middleware for AgentCore runtimes.

Provides correlation ID propagation and structured error handling as
default middleware on every ``AgentCoreApp`` instance.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the in-flight correlation ID, or empty string outside a request."""
    return _correlation_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate ``x-request-id`` and propagate via contextvar."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = _correlation_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            _correlation_id_var.reset(token)


class StructuredErrorMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured JSON errors."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = get_correlation_id()
            logger.exception(
                "Unhandled error [request_id=%s]: %s", request_id, exc
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": str(exc),
                    "request_id": request_id,
                    "code": type(exc).__name__,
                },
                headers={"x-request-id": request_id} if request_id else {},
            )
