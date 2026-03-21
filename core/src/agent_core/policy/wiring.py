"""Policy wiring — bridges blueprint PolicyConfig to PolicyClient.

Created once per :meth:`BlueprintLoader.build_agent_session` call when the
blueprint declares ``policy.rules``.  Follows the same pattern as
:class:`~agent_core.evaluation.wiring.EvaluationWiring`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any

from agent_core.policy.client import PolicyClient, PolicyMode
from agent_core.policy.translator import translate_rule
from agent_core.schemas.policy_config import PolicyConfig

logger = logging.getLogger(__name__)


class PolicyWiring:
    """Orchestrates policy lifecycle from a single PolicyConfig.

    Exposes:
    - ``client`` — the PolicyClient for direct SDK access
    - ``engine_id`` — the created/retrieved policy engine ID
    - ``engine_arn`` — the policy engine ARN
    - ``deployed_policy_ids`` — list of policy IDs deployed in this session
    - ``rollback()`` — redeploy policies from a stored version
    - ``list_versions()`` — list stored policy deployment versions
    """

    def __init__(
        self,
        config: PolicyConfig,
        agent_id: str,
        gateway_identifier: str,
        region: str | None = None,
        versions_table_name: str | None = None,
    ) -> None:
        self._config = config
        self._agent_id = agent_id
        self._gateway_identifier = gateway_identifier
        self._client = PolicyClient(region=region)
        self._engine_id: str = ""
        self._engine_arn: str = ""
        self._deployed_policy_ids: list[str] = []
        self._version_writer: _PolicyVersionWriter | None = None

        if versions_table_name:
            max_versions = 10
            if config.versioning is not None:
                max_versions = config.versioning.max_versions
            self._version_writer = _PolicyVersionWriter(
                table_name=versions_table_name,
                region=region,
                max_versions=max_versions,
            )

        engine_result = self._client.create_engine(
            name=config.engine,
            description=f"Policy engine for agent {agent_id}",
        )
        self._engine_id = engine_result.get("policyEngineId", "")
        self._engine_arn = engine_result.get("policyEngineArn", "")
        logger.info("Policy engine '%s' -> %s", config.engine, self._engine_arn)

        cedar_statements: dict[str, str] = {}
        for rule in config.rules:
            cedar = translate_rule(
                rule,
                gateway_arn=gateway_identifier,
                target_prefix=config.target_prefix,
            )
            result = self._client.create_policy(
                engine_id=self._engine_id,
                name=rule.name,
                cedar_statement=cedar,
            )
            policy_id = result.get("policyId", rule.name)
            self._deployed_policy_ids.append(policy_id)
            cedar_statements[rule.name] = cedar
            logger.info(
                "Deployed policy '%s' -> %s in engine %s",
                rule.name,
                policy_id,
                self._engine_id,
            )

        self._client.attach_to_gateway(
            gateway_identifier=gateway_identifier,
            policy_engine_arn=self._engine_arn,
            mode=PolicyMode(config.mode),
        )
        logger.info(
            "Attached engine %s to gateway (mode=%s)",
            self._engine_arn,
            config.mode,
        )

        if self._version_writer is not None:
            self._version_writer.write_version(
                agent_id=agent_id,
                engine_id=self._engine_id,
                policy_ids=self._deployed_policy_ids,
                cedar_statements=cedar_statements,
                mode=config.mode,
            )

    @property
    def config(self) -> PolicyConfig:
        return self._config

    @property
    def client(self) -> PolicyClient:
        return self._client

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def engine_arn(self) -> str:
        return self._engine_arn

    @property
    def deployed_policy_ids(self) -> list[str]:
        return list(self._deployed_policy_ids)

    def rollback(self, version: int) -> None:
        """Redeploy policies from a stored version.

        Deletes current policies, recreates from stored Cedar statements,
        and re-attaches to gateway.
        """
        if self._version_writer is None:
            raise ValueError("Versioning not configured — cannot rollback")

        version_data = self._version_writer.get_version(self._agent_id, version)
        if not version_data:
            raise ValueError(
                f"Version {version} not found for agent '{self._agent_id}'"
            )

        for pid in self._deployed_policy_ids:
            try:
                self._client.delete_policy(self._engine_id, pid)
            except Exception:
                logger.exception("Failed to delete policy '%s' during rollback", pid)

        self._deployed_policy_ids.clear()
        cedar_statements = version_data.get("cedar_statements", {})
        for name, cedar in cedar_statements.items():
            result = self._client.create_policy(
                engine_id=self._engine_id,
                name=name,
                cedar_statement=cedar,
            )
            policy_id = result.get("policyId", name)
            self._deployed_policy_ids.append(policy_id)

        old_mode = version_data.get("mode", self._config.mode)
        self._client.attach_to_gateway(
            gateway_identifier=self._gateway_identifier,
            policy_engine_arn=self._engine_arn,
            mode=PolicyMode(old_mode),
        )
        logger.info("Rolled back to version %d for agent '%s'", version, self._agent_id)

    def list_versions(self) -> list[dict[str, Any]]:
        """List stored policy deployment versions."""
        if self._version_writer is None:
            return []
        return self._version_writer.list_versions(self._agent_id)

    def cleanup(self) -> None:
        """Detach from gateway and delete engine. Call during teardown."""
        try:
            self._client.detach_from_gateway(self._gateway_identifier)
        except Exception:
            logger.exception("Failed to detach policy engine from gateway")

        try:
            self._client.delete_engine(self._engine_id)
        except Exception:
            logger.exception("Failed to delete policy engine '%s'", self._engine_id)


class _PolicyVersionWriter:
    """Persists policy deployment versions to DynamoDB.

    Schema:
    - PK: ``agent_id`` (str)
    - SK: ``version#{version_number}`` (str)
    - Fields: timestamp, engine_id, policy_ids, rules_hash,
              cedar_statements, mode
    """

    def __init__(
        self,
        table_name: str,
        region: str | None = None,
        max_versions: int = 10,
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._max_versions = max_versions
        self._table: Any = None

    def _get_table(self) -> Any:
        if self._table is None:
            import boto3

            kwargs: dict[str, Any] = {}
            if self._region:
                kwargs["region_name"] = self._region
            self._table = boto3.resource("dynamodb", **kwargs).Table(self._table_name)
        return self._table

    def write_version(
        self,
        agent_id: str,
        engine_id: str,
        policy_ids: list[str],
        cedar_statements: dict[str, str],
        mode: str,
    ) -> int:
        """Write a new policy version and prune old ones."""
        existing = self.list_versions(agent_id)
        version_number = len(existing) + 1

        rules_hash = hashlib.sha256(
            json.dumps(cedar_statements, sort_keys=True).encode()
        ).hexdigest()[:16]

        item: dict[str, Any] = {
            "agent_id": agent_id,
            "sort_key": f"version#{version_number}",
            "version": version_number,
            "timestamp_ms": int(time.time() * 1000),
            "engine_id": engine_id,
            "policy_ids": policy_ids,
            "rules_hash": rules_hash,
            "cedar_statements": cedar_statements,
            "mode": mode,
            "version_id": str(uuid.uuid4()),
        }
        try:
            self._get_table().put_item(Item=item)
            logger.info(
                "Stored policy version %d for agent '%s' (hash=%s)",
                version_number,
                agent_id,
                rules_hash,
            )
        except Exception:
            logger.exception("Failed to persist policy version")
            return version_number

        if len(existing) >= self._max_versions:
            self._prune_oldest(agent_id, existing)

        return version_number

    def get_version(self, agent_id: str, version: int) -> dict[str, Any]:
        """Get a specific policy version."""
        try:
            response = self._get_table().get_item(
                Key={"agent_id": agent_id, "sort_key": f"version#{version}"}
            )
            return response.get("Item", {})
        except Exception:
            logger.exception(
                "Failed to get policy version %d for agent %s", version, agent_id
            )
            return {}

    def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        """List all versions for an agent, sorted by version number."""
        try:
            response = self._get_table().query(
                KeyConditionExpression="agent_id = :aid AND begins_with(sort_key, :prefix)",
                ExpressionAttributeValues={
                    ":aid": agent_id,
                    ":prefix": "version#",
                },
            )
            items = response.get("Items", [])
            return sorted(items, key=lambda x: x.get("version", 0))
        except Exception:
            logger.exception("Failed to list policy versions for agent %s", agent_id)
            return []

    def _prune_oldest(self, agent_id: str, versions: list[dict[str, Any]]) -> None:
        """Delete oldest versions beyond max_versions limit."""
        to_delete = sorted(versions, key=lambda x: x.get("version", 0))
        to_delete = to_delete[: len(to_delete) - self._max_versions + 1]
        for v in to_delete:
            try:
                self._get_table().delete_item(
                    Key={
                        "agent_id": agent_id,
                        "sort_key": v.get("sort_key", ""),
                    }
                )
            except Exception:
                logger.exception("Failed to prune policy version")
