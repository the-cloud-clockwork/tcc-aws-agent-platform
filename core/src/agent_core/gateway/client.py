"""AgentCore Gateway client — Strands MCPClient wrapper.

Agents consume the Gateway as a single MCP endpoint.  All tools registered
as Gateway targets appear as MCP tools via one ``streamablehttp_client``
connection.

Two auth modes:
  - **AWS_IAM** — SigV4 signing via ``streamable_http_sigv4``
  - **CUSTOM_JWT** — Bearer token in ``Authorization`` header
  - **NONE** — No auth (local development only)
"""

from __future__ import annotations

import functools
import logging
import os
from typing import TYPE_CHECKING, Any

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

if TYPE_CHECKING:
    from agent_core.schemas.gateway_config import GatewayConfig

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """Base exception for Gateway failures."""

    def __init__(
        self,
        tool_name: str = "",
        message: str = "",
        code: str = "UNKNOWN",
    ) -> None:
        self.tool_name = tool_name
        self.code = code
        super().__init__(f"Gateway error [{code}] on '{tool_name}': {message}")


class GatewayPolicyDeniedError(GatewayError):
    """Raised when Cedar policy denies a tool invocation (HTTP 403)."""

    def __init__(self, tool_name: str = "", agent_id: str = "") -> None:
        super().__init__(
            tool_name=tool_name,
            message=f"Policy denied tool access for agent '{agent_id}'",
            code="POLICY_DENIED",
        )
        self.agent_id = agent_id


class GatewayConfigError(Exception):
    """Raised when Gateway configuration is missing or invalid."""


class GatewayClient:
    """Strands MCPClient-based gateway client.

    Creates a single ``MCPClient`` pointed at the Gateway URL.  The Gateway
    proxies tool calls to registered targets (Lambda, MCP servers, OpenAPI,
    Smithy, API Gateway).

    Usage::

        client = GatewayClient(gateway_url="https://gw.example.com/mcp")
        with client:
            tools = client.list_tools_sync()
            agent = Agent(tools=[local_tool] + tools)
            result = agent("What orders are pending?")

    Or via blueprint config::

        client = GatewayClient.from_config(blueprint.gateway)
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        auth_type: str = "aws_iam",
        jwt_env_var: str | None = None,
        region: str | None = None,
        service_name: str = "bedrock-agentcore",
    ) -> None:
        self._gateway_url = gateway_url
        self._auth_type = auth_type
        self._jwt_env_var = jwt_env_var
        self._region = (
            region
            or os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
        )
        if not self._region:
            raise GatewayConfigError(
                "No AWS region configured.  Set gateway.region in blueprint YAML "
                "or export AWS_DEFAULT_REGION."
            )
        self._service_name = service_name
        self._mcp_client: MCPClient | None = None

    @classmethod
    def from_config(cls, config: GatewayConfig) -> GatewayClient:
        """Create a ``GatewayClient`` from a :class:`GatewayConfig` schema."""
        return cls(
            gateway_url=config.url,
            auth_type=config.auth_type.value,
            jwt_env_var=config.jwt_env_var,
            region=config.region,
            service_name=config.service_name,
        )

    def _resolve_url(self) -> str:
        """Resolve the Gateway URL from config or environment."""
        url = self._gateway_url or os.environ.get("AGENTCORE_GATEWAY_URL")
        if not url:
            raise GatewayConfigError(
                "No Gateway URL configured.  Set gateway.url in blueprint YAML "
                "or export AGENTCORE_GATEWAY_URL."
            )
        if not url.endswith("/mcp"):
            url = url.rstrip("/") + "/mcp"
        return url

    def _build_mcp_client(self) -> MCPClient:
        """Build the underlying Strands MCPClient with auth-aware transport."""
        url = self._resolve_url()

        if self._auth_type == "custom_jwt":
            return self._build_jwt_client(url)
        if self._auth_type == "aws_iam":
            return self._build_sigv4_client(url)
        return self._build_anonymous_client(url)

    def _build_jwt_client(self, url: str) -> MCPClient:
        """Build MCPClient with JWT Bearer auth header."""
        if not self._jwt_env_var:
            raise GatewayConfigError(
                "CUSTOM_JWT auth requires jwt_env_var to be set in gateway config."
            )
        token = os.environ.get(self._jwt_env_var, "")
        if not token:
            raise GatewayConfigError(
                f"JWT env var '{self._jwt_env_var}' is empty or not set."
            )
        logger.info("Building Gateway MCPClient with JWT auth -> %s", url)
        return MCPClient(
            functools.partial(
                streamablehttp_client,
                url=url,
                headers={"Authorization": f"Bearer {token}"},
            )
        )

    def _build_sigv4_client(self, url: str) -> MCPClient:
        """Build MCPClient with SigV4 auth transport."""
        import boto3 as _boto3

        try:
            from agent_core.gateway.streamable_http_sigv4 import (
                streamablehttp_client_with_sigv4,
            )
        except ImportError as exc:
            logger.error(
                "Cannot import streamable_http_sigv4: %s. "
                "Ensure mcp>=1.10.0 is installed.",
                exc,
            )
            raise GatewayConfigError(
                f"SigV4 transport not available: {exc}"
            ) from exc

        session = _boto3.Session()
        # Use get_credentials() WITHOUT freeze — per AWS samples pattern.
        # Frozen credentials may not work with RefreshableCredentials in
        # AgentCore Runtime (IMDS-based credential provider).
        credentials = session.get_credentials()
        if credentials is None:
            raise GatewayConfigError(
                "No AWS credentials available for SigV4 signing. "
                "Check IAM role attachment on the AgentCore Runtime."
            )
        logger.info("Building Gateway MCPClient with SigV4 auth -> %s", url)
        return MCPClient(
            lambda: streamablehttp_client_with_sigv4(
                url=url,
                credentials=credentials,
                service=self._service_name,
                region=self._region,
            )
        )

    def _build_anonymous_client(self, url: str) -> MCPClient:
        """Build MCPClient without auth (local development)."""
        logger.info("Building Gateway MCPClient without auth -> %s", url)
        return MCPClient(functools.partial(streamablehttp_client, url=url))

    @property
    def mcp_client(self) -> MCPClient:
        """Lazy-built underlying Strands MCPClient."""
        if self._mcp_client is None:
            self._mcp_client = self._build_mcp_client()
        return self._mcp_client

    def list_tools_sync(self) -> list[Any]:
        """List all tools available through the Gateway."""
        return self.mcp_client.list_tools_sync()

    def as_tool_provider(self) -> MCPClient:
        """Return the MCPClient for direct use as a Strands tool provider.

        Pass this to ``Agent(tools=[...])`` or use in a context manager::

            with client.as_tool_provider() as provider:
                tools = provider.list_tools_sync()
        """
        return self.mcp_client

    def __enter__(self) -> GatewayClient:
        self.mcp_client.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if self._mcp_client is not None:
            self._mcp_client.__exit__(exc_type, exc_val, exc_tb)

    def close(self) -> None:
        """Close the underlying MCPClient transport."""
        if self._mcp_client is not None:
            self._mcp_client.__exit__(None, None, None)
            self._mcp_client = None
