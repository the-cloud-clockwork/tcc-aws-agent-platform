"""Multi-tenant isolation primitives.

Provides tenant-scoped resource access for future SaaS expansion.
In development: single tenant. In production: tenant isolation
at DynamoDB, S3, and AgentCore session level.

Design principle: every data access path includes tenant_id, even in
single-tenant mode. This makes multi-tenant migration a config change,
not a code change.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default tenant for single-tenant POC
DEFAULT_TENANT_ID = os.environ.get("TENANT_ID", "default")


class TenantContext(BaseModel):
    """Tenant context passed through all operations."""

    tenant_id: str = DEFAULT_TENANT_ID
    display_name: str = ""
    tier: str = "standard"  # "standard", "professional", "enterprise"
    config: dict[str, Any] = Field(default_factory=dict)

    # Resource limits per tier
    max_entities: int = 100
    max_collections: int = 4
    max_concurrent_agents: int = 5
    max_artifacts_gb: float = 10.0

    @classmethod
    def from_env(cls) -> TenantContext:
        """Create tenant context from environment variables."""
        return cls(
            tenant_id=os.environ.get("TENANT_ID", DEFAULT_TENANT_ID),
            display_name=os.environ.get("TENANT_NAME", "Default Tenant"),
            tier=os.environ.get("TENANT_TIER", "standard"),
        )


class TenantScopedKey:
    """Generates tenant-scoped keys for DynamoDB and S3.

    All keys follow the pattern: {tenant_id}/{resource_type}/{resource_id}
    """

    @staticmethod
    def dynamodb_pk(tenant_id: str, resource_type: str, resource_id: str) -> str:
        """Generate DynamoDB partition key with tenant scope."""
        return f"TENANT#{tenant_id}#TYPE#{resource_type}#ID#{resource_id}"

    @staticmethod
    def s3_prefix(tenant_id: str, resource_type: str) -> str:
        """Generate S3 key prefix with tenant scope."""
        return f"tenants/{tenant_id}/{resource_type}/"

    @staticmethod
    def s3_key(tenant_id: str, resource_type: str, filename: str) -> str:
        """Generate full S3 key with tenant scope."""
        return f"tenants/{tenant_id}/{resource_type}/{filename}"

    @staticmethod
    def session_id(tenant_id: str, workflow_execution_id: str) -> str:
        """Generate tenant-scoped session ID for AgentCore Memory."""
        return f"{tenant_id}:{workflow_execution_id}"


class TenantResourceGuard:
    """Enforce tenant resource limits.

    Checks that operations do not exceed tenant tier limits.
    Raises TenantLimitExceeded if a limit would be breached.
    """

    def __init__(self, context: TenantContext) -> None:
        self._context = context

    def check_entity_limit(self, current_count: int) -> None:
        """Check if adding an entity would exceed the entity limit."""
        if current_count >= self._context.max_entities:
            raise TenantLimitExceeded(
                f"Entity limit reached ({self._context.max_entities}). "
                f"Upgrade to a higher tier for more capacity."
            )

    def check_concurrent_agents(self, running_count: int) -> None:
        """Check if launching another agent would exceed concurrency limit."""
        if running_count >= self._context.max_concurrent_agents:
            raise TenantLimitExceeded(
                f"Concurrent agent limit reached ({self._context.max_concurrent_agents}). "
                f"Wait for running agents to complete or upgrade tier."
            )

    def check_artifact_storage(self, current_gb: float, additional_gb: float) -> None:
        """Check if storing more artifacts would exceed storage limit."""
        if current_gb + additional_gb > self._context.max_artifacts_gb:
            raise TenantLimitExceeded(
                f"Artifact storage limit reached ({self._context.max_artifacts_gb} GB). "
                f"Delete old artifacts or upgrade tier."
            )


class TenantLimitExceeded(Exception):
    """Raised when a tenant operation would exceed tier limits."""
    pass
