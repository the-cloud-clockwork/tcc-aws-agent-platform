"""PolicyClient — wrapper for AgentCore Policy Engine CRUD operations.

Provides a clean interface for creating policy engines, deploying Cedar
policies, attaching engines to Gateways, and generating policies from
natural language via the NL2Cedar API.

No hardcoded defaults — region must be provided or set via ``AWS_REGION``.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PolicyError(Exception):
    """Base exception for policy operations."""

    def __init__(self, message: str = "", code: str = "UNKNOWN") -> None:
        self.code = code
        super().__init__(f"Policy error [{code}]: {message}")


class PolicyConfigError(PolicyError):
    """Raised when policy configuration is missing or invalid."""


class PolicyEngineNotFoundError(PolicyError):
    """Raised when a referenced policy engine does not exist."""


class PolicyMode(str, Enum):
    """Enforcement mode for a policy engine on a Gateway."""

    ENFORCE = "ENFORCE"
    LOG_ONLY = "LOG_ONLY"


class PolicyClient:
    """Wrapper around AgentCore Policy Engine SDK.

    Combines ``boto3`` ``bedrock-agentcore-control`` client for engine
    lifecycle and ``bedrock_agentcore_starter_toolkit.operations.policy.client``
    for policy CRUD and NL2Cedar generation.

    No hardcoded defaults — region must be provided or set via ``AWS_REGION``.
    """

    def __init__(self, region: str | None = None) -> None:
        self._region = region or os.environ.get("AWS_REGION")
        if not self._region:
            raise PolicyConfigError(
                message="Region required — pass explicitly or set AWS_REGION env var.",
                code="MISSING_REGION",
            )

        import boto3
        from bedrock_agentcore_starter_toolkit.operations.policy.client import (
            PolicyClient as _SDKPolicyClient,
        )

        self._boto_client = boto3.client(
            "bedrock-agentcore-control", region_name=self._region
        )
        self._sdk_client = _SDKPolicyClient(region_name=self._region)
        logger.info("PolicyClient initialized (region=%s)", self._region)

    @property
    def sdk_client(self) -> Any:
        """Raw AgentCore Policy SDK client for advanced use cases."""
        return self._sdk_client

    # ------------------------------------------------------------------
    # Policy engine lifecycle
    # ------------------------------------------------------------------

    def create_engine(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new policy engine.

        Returns:
            Dict with ``policyEngineArn`` and ``policyEngineId``.
        """
        try:
            result = self._boto_client.create_policy_engine(
                name=name, description=description
            )
            logger.info(
                "Created policy engine '%s' -> %s", name, result.get("policyEngineArn")
            )
            return result
        except self._boto_client.exceptions.ConflictException:
            # Engine already exists — retrieve and return it
            logger.info("Policy engine '%s' already exists, retrieving", name)
            engines = self._boto_client.list_policy_engines()
            for eng in engines.get("policyEngines", []):
                if eng.get("name") == name:
                    return eng
            raise PolicyError(
                message=f"Policy engine '{name}' exists but not found in list",
                code="CREATE_ENGINE_FAILED",
            )
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to create policy engine '{name}': {exc}",
                code="CREATE_ENGINE_FAILED",
            ) from exc

    def get_engine(self, engine_id: str) -> dict[str, Any]:
        """Retrieve details of a policy engine."""
        try:
            return self._boto_client.get_policy_engine(policyEngineId=engine_id)
        except Exception as exc:
            raise PolicyEngineNotFoundError(
                message=f"Policy engine '{engine_id}' not found: {exc}",
                code="ENGINE_NOT_FOUND",
            ) from exc

    def delete_engine(self, engine_id: str) -> None:
        """Delete a policy engine."""
        try:
            self._boto_client.delete_policy_engine(policyEngineId=engine_id)
            logger.info("Deleted policy engine '%s'", engine_id)
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to delete policy engine '{engine_id}': {exc}",
                code="DELETE_ENGINE_FAILED",
            ) from exc

    # ------------------------------------------------------------------
    # Policy CRUD
    # ------------------------------------------------------------------

    def create_policy(
        self, engine_id: str, name: str, cedar_statement: str
    ) -> dict[str, Any]:
        """Create a Cedar policy in a policy engine.

        Uses the raw boto3 ``create_policy`` API with
        ``validationMode=IGNORE_ALL_FINDINGS`` (per AWS samples pattern)
        to skip Cedar schema validation while keeping the policy functional.

        Falls back to retrieving an existing policy on ``ConflictException``.

        Args:
            engine_id: Target policy engine ID.
            name: Policy name.
            cedar_statement: Raw Cedar policy statement string.

        Returns:
            Dict with policy details from the API.
        """
        try:
            result = self._boto_client.create_policy(
                policyEngineId=engine_id,
                name=name,
                definition={"cedar": {"statement": cedar_statement}},
                validationMode="IGNORE_ALL_FINDINGS",
            )
            policy_id = result.get("policyId", "")
            logger.info(
                "Created policy '%s' (id=%s) in engine '%s'",
                name,
                policy_id,
                engine_id,
            )
            return result
        except self._boto_client.exceptions.ConflictException:
            logger.info("Policy '%s' already exists in engine '%s'", name, engine_id)
            # Retrieve existing policies and find by name
            try:
                policies = self._sdk_client.list_policies(policy_engine_id=engine_id)
                for pol in policies:
                    if pol.get("name") == name:
                        return pol
            except Exception:
                pass
            return {"name": name, "policyEngineId": engine_id}
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to create policy '{name}': {exc}",
                code="CREATE_POLICY_FAILED",
            ) from exc

    def list_policies(self, engine_id: str) -> list[dict[str, Any]]:
        """List all policies in a policy engine."""
        try:
            return self._sdk_client.list_policies(policy_engine_id=engine_id)
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to list policies for engine '{engine_id}': {exc}",
                code="LIST_POLICIES_FAILED",
            ) from exc

    def delete_policy(self, engine_id: str, policy_id: str) -> None:
        """Delete a policy from a policy engine."""
        try:
            self._sdk_client.delete_policy(
                policy_engine_id=engine_id, policy_id=policy_id
            )
            logger.info("Deleted policy '%s' from engine '%s'", policy_id, engine_id)
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to delete policy '{policy_id}': {exc}",
                code="DELETE_POLICY_FAILED",
            ) from exc

    # ------------------------------------------------------------------
    # Gateway attachment
    # ------------------------------------------------------------------

    def attach_to_gateway(
        self,
        gateway_identifier: str,
        policy_engine_arn: str,
        mode: PolicyMode,
    ) -> None:
        """Attach a policy engine to a Gateway.

        Args:
            gateway_identifier: Gateway ID or ARN.
            policy_engine_arn: ARN of the policy engine to attach.
            mode: ``ENFORCE`` or ``LOG_ONLY``.
        """
        try:
            from bedrock_agentcore_starter_toolkit.operations.gateway.client import (
                GatewayClient as _SDKGatewayClient,
            )

            gw_client = _SDKGatewayClient(region_name=self._region)
            gw_client.update_gateway_policy_engine(
                gateway_identifier=gateway_identifier,
                policy_engine_arn=policy_engine_arn,
                mode=mode.value,
            )
            logger.info(
                "Attached policy engine to gateway (gateway=%s, mode=%s)",
                gateway_identifier,
                mode.value,
            )
        except Exception as exc:
            raise PolicyError(
                message=(
                    f"Failed to attach policy engine to gateway "
                    f"'{gateway_identifier}': {exc}"
                ),
                code="ATTACH_GATEWAY_FAILED",
            ) from exc

    def detach_from_gateway(self, gateway_identifier: str) -> None:
        """Detach any policy engine from a Gateway."""
        try:
            from bedrock_agentcore_starter_toolkit.operations.gateway.client import (
                GatewayClient as _SDKGatewayClient,
            )

            gw_client = _SDKGatewayClient(region_name=self._region)
            gw_client.update_gateway_policy_engine(
                gateway_identifier=gateway_identifier,
                policy_engine_arn="",
                mode="",
            )
            logger.info("Detached policy engine from gateway '%s'", gateway_identifier)
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to detach policy engine from gateway '{gateway_identifier}': {exc}",
                code="DETACH_GATEWAY_FAILED",
            ) from exc

    # ------------------------------------------------------------------
    # NL2Cedar
    # ------------------------------------------------------------------

    def generate_policy(
        self,
        engine_id: str,
        name: str,
        gateway_arn: str,
        natural_language: str,
        fetch_assets: bool = True,
    ) -> dict[str, Any]:
        """Generate a Cedar policy from natural language description.

        Uses the AgentCore NL2Cedar API to convert plain English into
        Cedar policy syntax.

        Args:
            engine_id: Target policy engine ID.
            name: Name for the generated policy.
            gateway_arn: Gateway ARN for resource context.
            natural_language: Plain English policy description.
            fetch_assets: Whether to fetch gateway target schemas for context.

        Returns:
            API response dict containing ``generatedPolicies``.
        """
        try:
            result = self._sdk_client.generate_policy(
                policy_engine_id=engine_id,
                name=name,
                resource={"arn": gateway_arn},
                content={"rawText": natural_language},
                fetch_assets=fetch_assets,
            )
            logger.info(
                "Generated NL2Cedar policy '%s' for engine '%s'", name, engine_id
            )
            return result
        except Exception as exc:
            raise PolicyError(
                message=f"Failed to generate NL2Cedar policy '{name}': {exc}",
                code="NL2CEDAR_FAILED",
            ) from exc
