"""AgentCore Gateway client.

Provides a single entry point for all MCP tool calls. The Gateway fronts
every MCP server and OpenAPI endpoint, exposing them as a unified tool registry.

Agents call tools through the Gateway URL instead of connecting to individual
MCP servers. The Gateway handles:
- Routing to the correct target MCP
- Outbound auth injection (API keys, OAuth tokens)
- Tool namespace prefixing (e.g., "data-mcp::get_data")
- Caching of tool definitions

Design rule from CLAUDE.md:
  "Gateway becomes the MCP control plane."
  "MCP tool lists come from blueprint YAML, not hardcoded — Gateway will
   replace the loader."
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Tool definition cache TTL in seconds
TOOL_CACHE_TTL = int(os.environ.get("GATEWAY_TOOL_CACHE_TTL", "300"))


class GatewayClient:
    """Client for AgentCore Gateway — routes tool calls to MCP targets.

    Usage:
        client = GatewayClient(gateway_url="https://gateway.agentcore.example.com")
        result = client.invoke_tool("data-mcp::get_data", {"target": "ENTITY-1"})
        tools = client.list_tools()
        tools = client.search_tools("retrieve metrics for analysis")
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """Initialize Gateway client.

        Args:
            gateway_url: AgentCore Gateway HTTPS endpoint.
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum retry attempts for transient failures.
        """
        self.gateway_url = (
            gateway_url
            or os.environ.get("AGENTCORE_GATEWAY_URL")
            or "http://localhost:9000"
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self._tool_cache: dict[str, Any] | None = None
        self._cache_timestamp: float = 0.0
        self._http_client: httpx.Client | None = None

    @property
    def http_client(self) -> httpx.Client:
        """Lazy-initialized HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self.gateway_url,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "agent-core-gateway/0.2.0",
                },
            )
        return self._http_client

    def _handle_http_error(
        self,
        exc: httpx.HTTPStatusError,
        tool_name: str,
        agent_id: str | None,
        attempt: int,
    ) -> None:
        """Handle HTTP status errors from Gateway calls.

        Raises immediately for 403 (policy denied) and non-retryable errors.
        Returns normally for retryable server errors to let the retry loop continue.
        """
        if exc.response.status_code == 403:
            raise GatewayPolicyDeniedError(
                tool_name=tool_name,
                agent_id=agent_id or "unknown",
            ) from exc
        if exc.response.status_code >= 500 and attempt < self.max_retries - 1:
            logger.warning(
                "Gateway error (attempt %d/%d): %s",
                attempt + 1,
                self.max_retries,
                str(exc),
            )
            return
        raise exc

    @staticmethod
    def _parse_tool_response(result: dict[str, Any], tool_name: str) -> dict[str, Any]:
        """Validate a Gateway response and extract the output payload."""
        if result.get("error"):
            raise GatewayError(
                tool_name=tool_name,
                message=result["error"],
                code=result.get("error_code", "UNKNOWN"),
            )
        return result.get("output", result)

    def invoke_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a tool through the Gateway.

        The Gateway routes the call to the correct MCP target based on
        the namespace prefix (e.g., "data-mcp::get_data").

        Args:
            tool_name: Fully qualified tool name with namespace prefix.
            arguments: Tool input arguments.
            agent_id: Calling agent ID (for Cedar policy evaluation).
            session_id: Session ID (for audit logging).

        Returns:
            Tool output dict.

        Raises:
            GatewayError: If the Gateway returns an error response.
            httpx.HTTPStatusError: On HTTP errors.
        """
        request_body = {
            "tool_name": tool_name,
            "arguments": arguments,
            "context": {
                "agent_id": agent_id,
                "session_id": session_id,
                "execution_mode": os.environ.get("EXECUTION_MODE", "simulation"),
            },
        }

        for attempt in range(self.max_retries):
            try:
                response = self.http_client.post(
                    "/tools/invoke",
                    json=request_body,
                )
                response.raise_for_status()
                return self._parse_tool_response(response.json(), tool_name)

            except httpx.HTTPStatusError as e:
                self._handle_http_error(e, tool_name, agent_id, attempt)
            except httpx.ConnectError:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "Gateway connection failed (attempt %d/%d)",
                        attempt + 1,
                        self.max_retries,
                    )
                    continue
                raise

        raise GatewayError(
            tool_name=tool_name,
            message=f"Failed after {self.max_retries} attempts",
        )

    def list_tools(
        self,
        target: str | None = None,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """List all available tools from the Gateway.

        Args:
            target: Optional filter by MCP target name.
            refresh: Force cache refresh.

        Returns:
            List of tool definition dicts.
        """
        import time

        now = time.time()
        if (
            not refresh
            and self._tool_cache is not None
            and (now - self._cache_timestamp) < TOOL_CACHE_TTL
        ):
            tools = self._tool_cache.get("tools", [])
            if target:
                tools = [t for t in tools if t.get("target") == target]
            return tools

        response = self.http_client.get(
            "/tools/list",
            params={"target": target} if target else None,
        )
        response.raise_for_status()
        data = response.json()

        self._tool_cache = data
        self._cache_timestamp = now

        return data.get("tools", [])

    def search_tools(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search for tools across all Gateway targets.

        Uses AgentCore Gateway's built-in semantic search to find
        relevant tools by natural language description.

        Args:
            query: Natural language search query.
            max_results: Maximum number of results.

        Returns:
            List of matching tool definitions, ranked by relevance.
        """
        response = self.http_client.post(
            "/tools/search",
            json={
                "query": query,
                "max_results": max_results,
            },
        )
        response.raise_for_status()
        return response.json().get("tools", [])

    def health_check(self) -> dict[str, Any]:
        """Check Gateway health and target connectivity.

        Returns:
            Health status dict with target connectivity info.
        """
        response = self.http_client.get("/health")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the HTTP client connection."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> GatewayClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class GatewayError(Exception):
    """Error from AgentCore Gateway."""

    def __init__(
        self,
        tool_name: str,
        message: str,
        code: str = "UNKNOWN",
    ) -> None:
        self.tool_name = tool_name
        self.code = code
        super().__init__(f"Gateway error for {tool_name} [{code}]: {message}")


class GatewayPolicyDeniedError(GatewayError):
    """Cedar policy denied the tool invocation."""

    def __init__(self, tool_name: str, agent_id: str) -> None:
        super().__init__(
            tool_name=tool_name,
            message=f"Cedar policy denied access for agent '{agent_id}'",
            code="POLICY_DENIED",
        )
