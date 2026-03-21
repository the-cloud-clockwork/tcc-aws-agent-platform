"""A2A client — agent discovery and cross-runtime invocation.

Three call patterns:
  - ``call_a2a()``: Discover agent card, send message via A2A protocol.
  - ``stream_a2a()``: Streaming variant using A2A ``message/stream`` + SSE.
  - ``call_direct()``: invoke_agent_runtime() via boto3 bedrock-agentcore.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator, Iterator
from functools import lru_cache
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


class A2AClient:
    """Client for calling remote agents via A2A protocol or direct invoke."""

    def __init__(
        self,
        *,
        auth_provider: Callable[[], str] | None = None,
        region: str = "",
    ) -> None:
        self._auth_provider = auth_provider
        self._region = region or os.environ.get("AWS_REGION", "")
        self._http_client: httpx.Client | None = None
        self._async_http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None or self._http_client.is_closed:
            headers: dict[str, str] = {}
            if self._auth_provider is not None:
                token = self._auth_provider()
                headers["Authorization"] = f"Bearer {token}"
            self._http_client = httpx.Client(
                headers=headers,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._http_client

    def _get_async_http_client(self) -> httpx.AsyncClient:
        if self._async_http_client is None or self._async_http_client.is_closed:
            headers: dict[str, str] = {}
            if self._auth_provider is not None:
                token = self._auth_provider()
                headers["Authorization"] = f"Bearer {token}"
            self._async_http_client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._async_http_client

    @lru_cache(maxsize=32)  # noqa: B019
    def resolve_agent_card(self, base_url: str) -> dict[str, Any]:
        """Fetch /.well-known/agent.json from a remote agent."""
        url = base_url.rstrip("/") + "/.well-known/agent.json"
        logger.debug("Resolving agent card from %s", url)
        client = self._get_http_client()
        resp = client.get(url)
        resp.raise_for_status()
        card: dict[str, Any] = resp.json()
        logger.info(
            "Resolved agent card: %s (version %s)",
            card.get("name", "?"),
            card.get("version", "?"),
        )
        return card

    # ------------------------------------------------------------------
    # Synchronous request/response
    # ------------------------------------------------------------------

    def call_a2a(self, a2a_url: str, message: str) -> str:
        """Send message to a remote agent via A2A protocol.

        1. Resolve agent card from a2a_url.
        2. POST a JSON-RPC message to the agent's endpoint.
        3. Extract and return response text.
        """
        card = self.resolve_agent_card(a2a_url)
        endpoint = card.get("url", a2a_url.rstrip("/"))
        client = self._get_http_client()

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }
        logger.debug("Sending A2A message to %s", endpoint)
        resp = client.post(endpoint, json=payload)
        resp.raise_for_status()
        result = resp.json()

        return self._extract_response_text(result)

    # ------------------------------------------------------------------
    # Streaming via SSE (Server-Sent Events)
    # ------------------------------------------------------------------

    def stream_a2a(self, a2a_url: str, message: str) -> Iterator[str]:
        """Stream response from a remote agent via A2A protocol.

        Uses JSON-RPC method ``message/stream`` with SSE. Yields text
        chunks as they arrive from the remote agent.

        Parameters
        ----------
        a2a_url:
            Base URL of the remote agent.
        message:
            User message to send.

        Yields
        ------
        Text chunks from the streaming response.
        """
        card = self.resolve_agent_card(a2a_url)
        endpoint = card.get("url", a2a_url.rstrip("/"))
        client = self._get_http_client()

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }
        logger.debug("Starting A2A stream to %s", endpoint)

        with client.stream("POST", endpoint, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                text = self._parse_sse_line(line)
                if text:
                    yield text

    async def stream_a2a_async(self, a2a_url: str, message: str) -> AsyncIterator[str]:
        """Async streaming variant of :meth:`stream_a2a`.

        Uses ``httpx.AsyncClient`` for non-blocking SSE consumption.

        Parameters
        ----------
        a2a_url:
            Base URL of the remote agent.
        message:
            User message to send.

        Yields
        ------
        Text chunks from the streaming response.
        """
        card = self.resolve_agent_card(a2a_url)
        endpoint = card.get("url", a2a_url.rstrip("/"))
        client = self._get_async_http_client()

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }
        logger.debug("Starting async A2A stream to %s", endpoint)

        async with client.stream("POST", endpoint, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                text = self._parse_sse_line(line)
                if text:
                    yield text

    # ------------------------------------------------------------------
    # Direct invoke (AWS API)
    # ------------------------------------------------------------------

    def call_direct(self, runtime_arn: str, payload: dict[str, Any]) -> str:
        """Invoke a remote agent runtime directly via AWS API.

        Uses boto3 bedrock-agentcore client with invoke_agent_runtime().
        """
        import boto3

        client = boto3.client("bedrock-agentcore", region_name=self._region or None)
        logger.debug("Direct invoke: %s", runtime_arn)
        response = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            qualifier="DEFAULT",
            payload=json.dumps(payload),
        )
        body = response.get("body", b"")
        if hasattr(body, "read"):
            body = body.read()
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return str(body)

    # ------------------------------------------------------------------
    # SSE parsing + response extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sse_line(line: str) -> str:
        """Parse a single SSE line and extract text content.

        SSE lines are formatted as ``data: <json>``. Each JSON payload
        is a JSON-RPC notification with artifacts or status updates.
        Returns extracted text or empty string if not a data line.
        """
        line = line.strip()
        if not line.startswith("data:"):
            return ""
        data_str = line[5:].strip()
        if not data_str or data_str == "[DONE]":
            return ""
        try:
            event = json.loads(data_str)
        except json.JSONDecodeError:
            return ""
        return A2AClient._extract_response_text(event)

    @staticmethod
    def _extract_response_text(result: dict[str, Any]) -> str:
        """Extract text from an A2A JSON-RPC response."""
        rpc_result = result.get("result", {})
        artifacts = rpc_result.get("artifacts", [])
        texts: list[str] = []
        for artifact in artifacts:
            for part in artifact.get("parts", []):
                if part.get("type") == "text":
                    texts.append(part["text"])
        if texts:
            return "\n".join(texts)
        status = rpc_result.get("status", {})
        status_msg = status.get("message", {})
        for part in status_msg.get("parts", []):
            if part.get("type") == "text":
                texts.append(part["text"])
        return "\n".join(texts) if texts else ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP clients."""
        if self._http_client is not None and not self._http_client.is_closed:
            self._http_client.close()
            self._http_client = None
        if (
            self._async_http_client is not None
            and not self._async_http_client.is_closed
        ):
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_http_client.aclose())
            except RuntimeError:
                asyncio.run(self._async_http_client.aclose())
            self._async_http_client = None

    def __enter__(self) -> A2AClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False
