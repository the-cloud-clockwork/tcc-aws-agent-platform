"""A2A client — agent discovery and cross-runtime invocation.

Two call patterns:
  - ``call_a2a()``: Discover agent card, send message via A2A protocol.
  - ``call_direct()``: invoke_agent_runtime() via boto3 bedrock-agentcore.
"""

from __future__ import annotations

import json
import logging
import os
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
        return "\n".join(texts) if texts else json.dumps(result)

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

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http_client is not None and not self._http_client.is_closed:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> A2AClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False
