"""AgentCore Gateway target registry.

Manages registration of Gateway targets via the ``bedrock-agentcore-control``
boto3 API.  Supports all 5 target types: Lambda, MCP Server, OpenAPI, Smithy,
and API Gateway.

Targets can be loaded from a ``gateway-targets.yaml`` file (lives in domain
repos) or registered programmatically at deploy time.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TargetType(str, Enum):
    """Type of Gateway target — matches AgentCore Gateway target types."""

    LAMBDA = "lambda"
    MCP_SERVER = "mcp_server"
    OPENAPI = "openapi"
    SMITHY = "smithy"
    API_GATEWAY = "api_gateway"


class OutboundAuthType(str, Enum):
    """Outbound credential provider for Gateway -> target auth."""

    GATEWAY_IAM_ROLE = "gateway_iam_role"
    OAUTH2_CREDENTIAL = "oauth2_credential"
    NONE = "none"


@dataclass
class GatewayTarget:
    """Definition of a Gateway target.

    Attributes:
        name: Unique target name (used as namespace prefix in tool FQNs).
        target_type: One of the 5 supported target types.
        lambda_arn: Lambda function ARN (required for LAMBDA type).
        endpoint_url: URL for MCP_SERVER, OPENAPI, SMITHY, API_GATEWAY targets.
        tool_schema_path: Path to inline tool schema file (for OpenAPI/Smithy).
        outbound_auth: How Gateway authenticates to this target.
        oauth2_credential_provider_id: Credential provider ID for OAuth2.
        description: Human-readable description.
        tags: Metadata tags for filtering.
    """

    name: str
    target_type: TargetType
    lambda_arn: str | None = None
    endpoint_url: str | None = None
    tool_schema_path: str | None = None
    outbound_auth: OutboundAuthType = OutboundAuthType.GATEWAY_IAM_ROLE
    oauth2_credential_provider_id: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)


class TargetRegistry:
    """Manages registration of Gateway targets via boto3 control plane.

    Usage at deploy time (not runtime)::

        registry = TargetRegistry(gateway_id="gw-12345")
        targets = TargetRegistry.load_targets_from_file("gateway-targets.yaml")
        registry.synchronize_all(targets)
    """

    def __init__(
        self,
        gateway_id: str | None = None,
        region: str = "eu-west-1",
    ) -> None:
        self._gateway_id = gateway_id or os.environ.get("AGENTCORE_GATEWAY_ID", "")
        self._region = region
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy-initialized boto3 bedrock-agentcore-control client."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "bedrock-agentcore-control",
                region_name=self._region,
            )
        return self._client

    def _build_target_config(self, target: GatewayTarget) -> dict[str, Any]:
        """Build the ``targetConfiguration`` dict for ``create_gateway_target``."""
        if target.target_type == TargetType.LAMBDA:
            config: dict[str, Any] = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": target.lambda_arn,
                    }
                }
            }
            if target.tool_schema_path:
                config["mcp"]["lambda"]["toolSchema"] = self._load_tool_schema(
                    target.tool_schema_path
                )
            return config

        if target.target_type == TargetType.MCP_SERVER:
            return {"mcp": {"mcpServer": {"url": target.endpoint_url}}}

        if target.target_type == TargetType.OPENAPI:
            config = {"mcp": {"openApi": {"url": target.endpoint_url}}}
            if target.tool_schema_path:
                config["mcp"]["openApi"]["spec"] = self._load_tool_schema(
                    target.tool_schema_path
                )
            return config

        if target.target_type == TargetType.SMITHY:
            return {"mcp": {"smithyApi": {"url": target.endpoint_url}}}

        if target.target_type == TargetType.API_GATEWAY:
            return {"mcp": {"apiGateway": {"url": target.endpoint_url}}}

        raise ValueError(f"Unknown target type: {target.target_type}")

    def _build_credential_providers(
        self, target: GatewayTarget
    ) -> list[dict[str, Any]]:
        """Build credential provider configurations for a target."""
        if target.outbound_auth == OutboundAuthType.GATEWAY_IAM_ROLE:
            return [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
        if target.outbound_auth == OutboundAuthType.OAUTH2_CREDENTIAL:
            return [
                {
                    "credentialProviderType": "OAUTH2",
                    "oAuth2CredentialProvider": {
                        "credentialProviderArn": target.oauth2_credential_provider_id,
                    },
                }
            ]
        return []

    @staticmethod
    def _load_tool_schema(path: str) -> dict[str, Any]:
        """Load a tool schema from a JSON file."""
        import json

        with open(path) as f:
            return json.load(f)

    def register_target(self, target: GatewayTarget) -> dict[str, Any]:
        """Register a single target with the Gateway.

        Returns:
            Response dict from ``create_gateway_target``.
        """
        target_config = self._build_target_config(target)
        credential_providers = self._build_credential_providers(target)

        response = self.client.create_gateway_target(
            gatewayIdentifier=self._gateway_id,
            name=target.name,
            targetConfiguration=target_config,
            credentialProviderConfigurations=credential_providers,
        )

        logger.info("Registered Gateway target '%s' (type=%s)", target.name, target.target_type.value)
        return response

    def synchronize_all(self, targets: list[GatewayTarget]) -> dict[str, Any]:
        """Register all provided targets with the Gateway.

        Returns:
            Summary dict with per-target registration results.
        """
        results: dict[str, Any] = {}

        for target in targets:
            try:
                result = self.register_target(target)
                results[target.name] = {"status": "registered", "response": result}
            except Exception as e:
                logger.error("Failed to register target '%s': %s", target.name, e)
                results[target.name] = {"status": "failed", "error": str(e)}

        registered = sum(1 for r in results.values() if r["status"] == "registered")
        logger.info("Synchronized %d/%d targets", registered, len(targets))
        return {"targets": results, "registered_count": registered}

    @classmethod
    def load_targets_from_file(cls, path: str) -> list[GatewayTarget]:
        """Load target definitions from a ``gateway-targets.yaml`` file.

        Expected format::

            gateway_id: "${AGENTCORE_GATEWAY_ID}"
            targets:
              - name: "order-tools"
                type: lambda
                lambda_arn: "${ORDER_TOOLS_LAMBDA_ARN}"
                outbound_auth: gateway_iam_role
              - name: "analytics-mcp"
                type: mcp_server
                endpoint_url: "${ANALYTICS_MCP_URL}"
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
                    lambda_arn=entry.get("lambda_arn"),
                    endpoint_url=entry.get("endpoint_url"),
                    tool_schema_path=entry.get("tool_schema_path"),
                    outbound_auth=OutboundAuthType(
                        entry.get("outbound_auth", "gateway_iam_role")
                    ),
                    oauth2_credential_provider_id=entry.get(
                        "oauth2_credential_provider_id"
                    ),
                    description=entry.get("description", ""),
                    tags=entry.get("tags", []),
                )
            )
        return targets

    def deregister_target(self, target_name: str) -> None:
        """Remove a target from the Gateway."""
        self.client.delete_gateway_target(
            gatewayIdentifier=self._gateway_id,
            targetIdentifier=target_name,
        )
        logger.info("Deregistered Gateway target: %s", target_name)
