"""AgentCore Gateway target registry.

Registers and manages MCP servers and OpenAPI endpoints as Gateway targets.
Each target is an MCP server, REST API, or OpenAPI spec that the Gateway
can route tool calls to.

Targets can be loaded from a YAML file or registered programmatically.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TargetType(str, Enum):
    """Type of Gateway target."""

    MCP_SERVER = "mcp_server"
    OPENAPI = "openapi"
    REST_API = "rest_api"


class AuthType(str, Enum):
    """Authentication type for the target."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    IAM = "iam"


@dataclass
class GatewayTarget:
    """Definition of a Gateway target -- an MCP server or API endpoint.

    Attributes:
        name: Unique target name (used as namespace prefix).
        target_type: MCP server, OpenAPI spec, or REST API.
        endpoint: URL or Cloud Map service name.
        auth_type: How to authenticate to this target.
        auth_config: Auth-specific configuration (references env vars, not secrets).
        description: Human-readable description for semantic search.
        tags: Metadata tags for filtering.
        health_check_path: Health check endpoint path.
        max_tools: Maximum tools this target can expose (default 10000).
    """

    name: str
    target_type: TargetType
    endpoint: str
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, str] = field(default_factory=dict)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    health_check_path: str = "/health"
    max_tools: int = 10000


class TargetRegistry:
    """Manages registration and synchronization of Gateway targets.

    Usage:
        registry = TargetRegistry(gateway_url="https://gateway.example.com")
        targets = TargetRegistry.load_targets_from_file("targets.yaml")
        registry.synchronize_all(targets)
        registry.get_target_health("my-mcp-server")
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.gateway_url = (
            gateway_url
            or os.environ.get("AGENTCORE_GATEWAY_URL")
            or "http://localhost:9000"
        )
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.gateway_url,
                timeout=self.timeout,
            )
        return self._client

    def register_target(self, target: GatewayTarget) -> dict[str, Any]:
        """Register a single target with the Gateway.

        Args:
            target: Target definition.

        Returns:
            Registration response with tool count.
        """
        payload = {
            "name": target.name,
            "type": target.target_type.value,
            "endpoint": target.endpoint,
            "auth": {
                "type": target.auth_type.value,
                **target.auth_config,
            },
            "description": target.description,
            "tags": target.tags,
            "health_check_path": target.health_check_path,
            "max_tools": target.max_tools,
        }

        response = self.client.post("/targets/register", json=payload)
        response.raise_for_status()
        result = response.json()

        logger.info(
            "Registered target '%s': %d tools discovered",
            target.name,
            result.get("tool_count", 0),
        )
        return result

    def synchronize_all(
        self,
        targets: list[GatewayTarget],
    ) -> dict[str, Any]:
        """Register all provided targets with the Gateway.

        Call this after MCP redeployment to refresh tool definitions.

        Args:
            targets: List of GatewayTarget definitions to register.

        Returns:
            Summary dict with per-target registration results.
        """
        results = {}

        for target in targets:
            try:
                result = self.register_target(target)
                results[target.name] = {
                    "status": "registered",
                    "tool_count": result.get("tool_count", 0),
                }
            except Exception as e:
                logger.error("Failed to register target '%s': %s", target.name, e)
                results[target.name] = {
                    "status": "failed",
                    "error": str(e),
                }

        total_tools = sum(
            r.get("tool_count", 0)
            for r in results.values()
            if r["status"] == "registered"
        )
        logger.info(
            "Synchronized %d targets, %d total tools",
            len([r for r in results.values() if r["status"] == "registered"]),
            total_tools,
        )
        return {"targets": results, "total_tools": total_tools}

    @classmethod
    def load_targets_from_file(cls, path: str) -> list[GatewayTarget]:
        """Load target definitions from a YAML file.

        Args:
            path: Path to YAML file containing target definitions.

        Returns:
            List of GatewayTarget objects.
        """
        import yaml  # type: ignore[import-untyped]

        with open(path) as f:
            data = yaml.safe_load(f)

        targets = []
        for entry in data.get("targets", []):
            targets.append(
                GatewayTarget(
                    name=entry["name"],
                    target_type=TargetType(entry.get("type", "mcp_server")),
                    endpoint=entry["endpoint"],
                    auth_type=AuthType(entry.get("auth_type", "none")),
                    auth_config=entry.get("auth_config", {}),
                    description=entry.get("description", ""),
                    tags=entry.get("tags", []),
                    health_check_path=entry.get("health_check_path", "/health"),
                    max_tools=entry.get("max_tools", 10000),
                )
            )
        return targets

    def get_target_health(self, target_name: str) -> dict[str, Any]:
        """Check health of a specific target.

        Args:
            target_name: Target name.

        Returns:
            Health status dict.
        """
        response = self.client.get(f"/targets/{target_name}/health")
        response.raise_for_status()
        return response.json()

    def deregister_target(self, target_name: str) -> None:
        """Remove a target from the Gateway.

        Args:
            target_name: Target name to deregister.
        """
        response = self.client.delete(f"/targets/{target_name}")
        response.raise_for_status()
        logger.info("Deregistered target: %s", target_name)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
