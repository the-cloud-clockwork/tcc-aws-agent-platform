"""Bi-directional streaming for real-time UI updates.

Provides server-sent events (SSE) and WebSocket adapters for
streaming agent progress to the UI layer. Used by:
- Coordinator (streaming reasoning)
- Long-running agents (progress updates as items are processed)
- Report generators (progress as records are processed)

In POC: SSE via Lambda response streaming.
In Production: AgentCore Runtime native streaming.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StreamEventType(str, Enum):
    """Types of streaming events."""

    PROGRESS = "progress"
    PARTIAL_RESULT = "partial_result"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    COMPLETE = "complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    """A single streaming event."""

    event_type: StreamEventType
    agent_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)
    sequence: int = 0


class StreamBuffer:
    """Buffer for collecting and distributing stream events.

    Thread-safe event buffer that allows agents to push events
    and UI clients to consume them via async iteration.
    """

    def __init__(self, session_id: str, agent_id: str) -> None:
        self._session_id = session_id
        self._agent_id = agent_id
        self._events: list[StreamEvent] = []
        self._sequence = 0
        self._complete = False
        self._subscribers: list[asyncio.Queue[StreamEvent | None]] = []

    async def push(self, event_type: StreamEventType, data: dict[str, Any]) -> None:
        """Push an event to the buffer and notify subscribers."""
        self._sequence += 1
        event = StreamEvent(
            event_type=event_type,
            agent_id=self._agent_id,
            session_id=self._session_id,
            data=data,
            sequence=self._sequence,
        )
        self._events.append(event)

        for queue in self._subscribers:
            await queue.put(event)

        if event_type in (StreamEventType.COMPLETE, StreamEventType.ERROR):
            self._complete = True
            for queue in self._subscribers:
                await queue.put(None)  # Sentinel

    async def subscribe(self) -> AsyncIterator[StreamEvent]:
        """Subscribe to stream events. Yields events as they arrive."""
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        self._subscribers.append(queue)

        # Replay existing events
        for event in self._events:
            yield event

        if self._complete:
            return

        # Wait for new events
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

        self._subscribers.remove(queue)

    def get_events(self, after_sequence: int = 0) -> list[StreamEvent]:
        """Get events after a given sequence number (for polling clients)."""
        return [e for e in self._events if e.sequence > after_sequence]

    @property
    def is_complete(self) -> bool:
        return self._complete


def format_sse(event: StreamEvent) -> str:
    """Format a StreamEvent as Server-Sent Events (SSE) text.

    Returns:
        SSE-formatted string ready to write to HTTP response.
    """
    data = event.model_dump_json()
    return f"event: {event.event_type.value}\ndata: {data}\n\n"
