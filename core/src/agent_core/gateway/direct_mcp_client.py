"""Direct MCP client — bypasses Gateway for MCP runtime tool calls.

WORKAROUND for AWS Issue #809: Gateway tools/call returns "internal error"
for MCP runtime targets. This module connects agents directly to MCP runtimes
using Cognito JWT tokens (client_credentials grant).

Enabled by GATEWAY_DIRECT_MCP=true env var. Remove when AWS fixes the Gateway.
See KNOWN_ISSUES.md KI-001.
"""

from __future__ import annotations

import base64
import functools
import json
import logging
import os
import time
from typing import Any
from urllib.parse import quote

import httpx
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)
# Force our logger to WARNING+ for visibility in OTEL-instrumented runtimes
logger.setLevel(logging.DEBUG)

# Token cache — shared across DirectMCPClient instances
_token_cache: dict[str, tuple[str, float]] = {}


def _get_cognito_token(token_url: str, client_id: str, client_secret: str, scopes: str) -> str:
    """Get M2M token via client_credentials grant. Cached for 50 minutes."""
    cache_key = f"{token_url}:{client_id}"
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > time.time():
        return cached[0]

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = httpx.post(
        token_url,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=f"grant_type=client_credentials&scope={scopes}",
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]

    # Cache for 50 minutes (Cognito tokens last 60 min)
    _token_cache[cache_key] = (token, time.time() + 3000)
    logger.warning("DIAG Cognito M2M token obtained for direct MCP access")
    return token


class DirectMCPClient:
    """Connects directly to an MCP runtime with JWT Bearer auth.

    Bypasses the AgentCore Gateway — workaround for AWS Issue #809.
    """

    def __init__(
        self,
        runtime_url: str,
        mcp_name: str,
        token_url: str = "",
        client_id: str = "",
        client_secret: str = "",
        scopes: str = "",
    ) -> None:
        self._runtime_url = runtime_url
        self._mcp_name = mcp_name
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes
        self._mcp_client: MCPClient | None = None

    def _get_token(self) -> str:
        if not self._token_url or not self._client_id:
            return ""
        return _get_cognito_token(
            self._token_url, self._client_id, self._client_secret, self._scopes
        )

    def _build_mcp_client(self) -> MCPClient:
        import uuid
        from datetime import timedelta

        # --- DIAGNOSTIC: Step 1 — Token acquisition ---
        t0 = time.time()
        try:
            token = self._get_token()
            logger.warning(
                "DIAG[%s] Token acquired in %.1fs (has_token=%s)",
                self._mcp_name, time.time() - t0, bool(token),
            )
        except Exception as exc:
            logger.error(
                "DIAG[%s] Token FAILED after %.1fs: %s",
                self._mcp_name, time.time() - t0, exc,
            )
            token = ""

        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        session_id = f"direct-{self._mcp_name}-{uuid.uuid4().hex[:12]}"
        headers["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"] = session_id

        logger.warning(
            "DIAG[%s] Building MCPClient -> %s (auth=%s, session=%s)",
            self._mcp_name,
            self._runtime_url,
            "jwt" if token else "none",
            session_id,
        )

        _url = self._runtime_url
        _headers = dict(headers)
        _timeout = timedelta(seconds=120)

        # --- DIAGNOSTIC: Step 2 — MCPClient construction ---
        t1 = time.time()
        try:
            client = MCPClient(
                lambda: streamablehttp_client(
                    url=_url,
                    headers=_headers,
                    timeout=_timeout,
                ),
                startup_timeout=30,
            )
            logger.warning(
                "DIAG[%s] MCPClient created in %.1fs",
                self._mcp_name, time.time() - t1,
            )
            return client
        except Exception as exc:
            logger.error(
                "DIAG[%s] MCPClient FAILED after %.1fs: %s",
                self._mcp_name, time.time() - t1, exc,
            )
            raise

    @property
    def mcp_client(self) -> MCPClient:
        if self._mcp_client is None:
            self._mcp_client = self._build_mcp_client()
        return self._mcp_client

    def as_tool_provider(self) -> MCPClient:
        return self.mcp_client

    def close(self) -> None:
        if self._mcp_client is not None:
            try:
                self._mcp_client.__exit__(None, None, None)
            except Exception:
                pass
            self._mcp_client = None


def create_direct_providers(blueprint: Any) -> list[MCPClient]:
    """Create DirectMCPClient instances for each MCP tool in the blueprint.

    Reads config from env vars:
      GATEWAY_DIRECT_MCP=true
      MCP_DIRECT_URLS={"market-data-mcp": "https://...", ...}
      COGNITO_TOKEN_URL=https://{domain}.auth.{region}.amazoncognito.com/oauth2/token
      COGNITO_MCP_CLIENT_ID=...
      COGNITO_MCP_CLIENT_SECRET=...
      COGNITO_MCP_SCOPES=scope1,scope2

    Returns list of MCPClient instances (one per MCP server).
    """
    from agent_core.schemas.tool_config import McpToolConfig

    urls_json = os.environ.get("MCP_DIRECT_URLS", "{}")
    try:
        mcp_urls: dict[str, str] = json.loads(urls_json)
    except json.JSONDecodeError:
        logger.error("Invalid MCP_DIRECT_URLS JSON: %s", urls_json[:100])
        return []

    if not mcp_urls:
        logger.warning("GATEWAY_DIRECT_MCP=true but MCP_DIRECT_URLS is empty")
        return []

    token_url = os.environ.get("COGNITO_TOKEN_URL", "")
    client_id = os.environ.get("COGNITO_MCP_CLIENT_ID", "")
    client_secret = os.environ.get("COGNITO_MCP_CLIENT_SECRET", "")
    scopes = os.environ.get("COGNITO_MCP_SCOPES", "")

    # --- DIAGNOSTIC: Network reachability check ---
    if token_url:
        t_net = time.time()
        try:
            # Just check if we can reach Cognito (HEAD on the OIDC well-known)
            wellknown = token_url.rsplit("/oauth2/token", 1)[0] + "/.well-known/openid-configuration"
            r = httpx.get(wellknown, timeout=5, follow_redirects=True)
            logger.warning(
                "DIAG Cognito reachable: %s -> %d (%.1fs)",
                wellknown, r.status_code, time.time() - t_net,
            )
        except Exception as exc:
            logger.error(
                "DIAG Cognito UNREACHABLE after %.1fs: %s",
                time.time() - t_net, exc,
            )

    # Deduplicate: one client per MCP server, not per tool
    seen_mcps: set[str] = set()
    providers: list[MCPClient] = []

    for tool_cfg in blueprint.tools:
        if not isinstance(tool_cfg, McpToolConfig):
            continue
        mcp_name = tool_cfg.mcp
        if mcp_name in seen_mcps:
            continue
        seen_mcps.add(mcp_name)

        url = mcp_urls.get(mcp_name)
        if not url:
            logger.warning("No direct URL for MCP '%s' — skipping", mcp_name)
            continue

        client = DirectMCPClient(
            runtime_url=url,
            mcp_name=mcp_name,
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )
        t_start = time.time()
        try:
            provider = client.as_tool_provider()
            providers.append(provider)
            logger.warning(
                "DIAG Direct MCP bypass OK: '%s' -> %s (%.1fs)",
                mcp_name, url, time.time() - t_start,
            )
        except Exception as exc:
            logger.error(
                "DIAG Direct MCP bypass FAILED: '%s' after %.1fs: %s",
                mcp_name, time.time() - t_start, exc,
            )

    return providers
