"""Evaluation wiring — bridges blueprint EvaluationConfig to EvaluationClient.

Created once per :meth:`BlueprintLoader.build_agent_session` call when the
blueprint declares evaluation configuration.  Follows the same pattern as
:class:`~agent_core.identity.wiring.IdentityWiring`.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agent_core.evaluation.client import EvaluationClient
from agent_core.evaluation.provider import EvaluationProvider
from agent_core.evaluation.results import EvaluationResult
from agent_core.schemas.evaluation_config import EvaluationConfig


def _build_eval_client(
    config: EvaluationConfig, region: str | None
) -> EvaluationProvider:
    """Dispatch to the configured evaluation backend."""
    if config.provider == "langfuse":
        from agent_core.evaluation.langfuse_client import LangfuseEvaluationClient

        return LangfuseEvaluationClient()
    return EvaluationClient(region=region)

logger = logging.getLogger(__name__)


class EvaluationWiring:
    """Orchestrates evaluation lifecycle from a single EvaluationConfig.

    Exposes:
    - ``client`` — the EvaluationClient for direct SDK access
    - ``evaluator_ids`` — mapping of name → evaluator ID for custom evaluators
    - ``run()`` — run on-demand evaluation with automatic persistence
    - ``get_online_results()`` — fetch continuous evaluation results
    """

    def __init__(
        self,
        config: EvaluationConfig,
        agent_id: str,
        region: str | None = None,
        results_table_name: str | None = None,
    ) -> None:
        self._config = config
        self._agent_id = agent_id
        self._client: EvaluationProvider = _build_eval_client(config, region)
        self._evaluator_ids: dict[str, str] = {}
        self._online_config_name: str | None = None
        self._results_writer: _EvaluationResultWriter | None = None

        if results_table_name:
            retention_days = 90
            if config.persistence is not None:
                retention_days = config.persistence.retention_days
            self._results_writer = _EvaluationResultWriter(
                table_name=results_table_name,
                region=region,
                retention_seconds=retention_days * 86_400,
            )

        for custom_cfg in config.custom_evaluators:
            eid = self._client.create_evaluator(custom_cfg)
            self._evaluator_ids[custom_cfg.name] = eid
            logger.info(
                "Created custom evaluator '%s' -> %s for %s",
                custom_cfg.name,
                eid,
                agent_id,
            )

        if config.online is not None:
            config_name = f"{agent_id}_online_eval"
            self._client.create_online_config(
                agent_id=agent_id,
                config_name=config_name,
                config=config.online,
            )
            self._online_config_name = config_name
            logger.info(
                "Wired online evaluation for %s (sampling=%d%%)",
                agent_id,
                config.online.sampling_rate,
            )

    @property
    def config(self) -> EvaluationConfig:
        return self._config

    @property
    def client(self) -> EvaluationProvider:
        return self._client

    @property
    def evaluator_ids(self) -> dict[str, str]:
        """Mapping of evaluator name -> ID for custom evaluators created by this wiring."""
        return dict(self._evaluator_ids)

    @property
    def online_config_name(self) -> str | None:
        """Name of the online evaluation config, or None if not configured."""
        return self._online_config_name

    def run(
        self,
        session_id: str,
        evaluators: list[str] | None = None,
    ) -> EvaluationResult:
        """Run on-demand evaluation and optionally persist results.

        Parameters
        ----------
        session_id:
            The session to evaluate.
        evaluators:
            Evaluator identifiers.  If ``None``, uses online config evaluators
            or all custom evaluator IDs.
        """
        if evaluators is None:
            if self._config.online is not None:
                evaluators = list(self._config.online.evaluators)
            else:
                evaluators = list(self._evaluator_ids.values())

        result = self._client.run(
            agent_id=self._agent_id,
            session_id=session_id,
            evaluators=evaluators,
        )

        if self._results_writer is not None:
            self._results_writer.write(result)

        return result

    def get_online_results(self) -> list[dict[str, Any]]:
        """Retrieve results from the configured online evaluation."""
        if self._online_config_name is None:
            raise ValueError(
                f"No online evaluation configured for agent '{self._agent_id}'"
            )
        return self._client.get_online_results(
            agent_id=self._agent_id,
            config_name=self._online_config_name,
        )

    def cleanup(self) -> None:
        """Delete online config and custom evaluators.  Call during teardown."""
        if self._online_config_name is not None:
            try:
                self._client.delete_online_config(
                    agent_id=self._agent_id,
                    config_name=self._online_config_name,
                )
            except Exception:
                logger.exception("Failed to delete online config")

        for name, eid in self._evaluator_ids.items():
            try:
                self._client.delete_evaluator(eid)
            except Exception:
                logger.exception("Failed to delete evaluator '%s' (%s)", name, eid)


class _EvaluationResultWriter:
    """Persists EvaluationResult scores to DynamoDB.

    Schema:
    - PK: ``agent_id`` (str)
    - SK: ``{session_id}#{timestamp_ms}#{evaluator_name}`` (str)
    - GSI ``session_id-index``: for querying all scores in a session
    - TTL: configurable retention
    """

    def __init__(
        self,
        table_name: str,
        region: str | None = None,
        retention_seconds: int = 7_776_000,
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._retention_seconds = retention_seconds
        self._table: Any = None

    def _get_table(self) -> Any:
        if self._table is None:
            import boto3

            kwargs: dict[str, Any] = {}
            if self._region:
                kwargs["region_name"] = self._region
            self._table = boto3.resource("dynamodb", **kwargs).Table(self._table_name)
        return self._table

    def write(self, result: EvaluationResult) -> None:
        now_ms = int(time.time() * 1000)
        ttl = int(time.time()) + self._retention_seconds

        for score in result.scores:
            item: dict[str, Any] = {
                "agent_id": result.agent_id,
                "sort_key": f"{result.session_id}#{now_ms}#{score.evaluator_name}",
                "session_id": result.session_id,
                "evaluator_name": score.evaluator_name,
                "label": score.label,
                "value": str(score.value),
                "explanation": score.explanation,
                "token_usage": score.token_usage,
                "timestamp_ms": now_ms,
                "result_id": str(uuid.uuid4()),
                "ttl": ttl,
            }
            try:
                self._get_table().put_item(Item=item)
            except Exception:
                logger.exception(
                    "Failed to persist evaluation score: %s", score.evaluator_name
                )

    def query_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Query all scores for a session via GSI."""
        try:
            response = self._get_table().query(
                IndexName="session_id-index",
                KeyConditionExpression="session_id = :sid",
                ExpressionAttributeValues={":sid": session_id},
            )
            return sorted(
                response.get("Items", []),
                key=lambda x: x.get("timestamp_ms", 0),
            )
        except Exception:
            logger.exception(
                "Failed to query evaluation results for session %s", session_id
            )
            return []
