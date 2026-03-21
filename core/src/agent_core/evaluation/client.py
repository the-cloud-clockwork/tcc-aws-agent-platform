"""EvaluationClient — thin wrapper around AgentCore Evaluation SDK."""

from __future__ import annotations

import logging
import os
from typing import Any

from agent_core.evaluation.evaluators import resolve_evaluator_ids
from agent_core.evaluation.results import EvaluationResult, EvaluationScore
from agent_core.schemas.evaluation_config import (
    CustomEvaluatorConfig,
    OnlineEvaluationConfig,
)

logger = logging.getLogger(__name__)


class EvaluationError(Exception):
    """Base exception for evaluation operations."""

    def __init__(
        self, message: str = "", agent_id: str = "", code: str = "UNKNOWN"
    ) -> None:
        self.agent_id = agent_id
        self.code = code
        super().__init__(f"Evaluation error [{code}] agent='{agent_id}': {message}")


class EvaluationConfigError(EvaluationError):
    """Raised when evaluation configuration is missing or invalid."""


class EvaluatorNotFoundError(EvaluationError):
    """Raised when a referenced evaluator does not exist."""


class EvaluationClient:
    """Wrapper around ``bedrock_agentcore_starter_toolkit.Evaluation``.

    No hardcoded defaults — region must be provided or set via ``AWS_REGION``.
    Model IDs, sampling rates, and all tunables come from caller / blueprint.
    """

    def __init__(self, region: str | None = None) -> None:
        self._region = region or os.environ.get("AWS_REGION")
        if not self._region:
            raise EvaluationConfigError(
                message="Region required — pass explicitly or set AWS_REGION env var.",
                code="MISSING_REGION",
            )
        from bedrock_agentcore_starter_toolkit import Evaluation

        self._client = Evaluation(region=self._region)
        logger.info("EvaluationClient initialized (region=%s)", self._region)

    @property
    def client(self) -> Any:
        """Raw AgentCore Evaluation SDK client for advanced use cases."""
        return self._client

    # ------------------------------------------------------------------
    # On-demand evaluation
    # ------------------------------------------------------------------

    def run(
        self,
        agent_id: str,
        session_id: str,
        evaluators: list[str],
    ) -> EvaluationResult:
        """Run on-demand evaluation for a specific agent session.

        Reads OTEL traces for the given session and scores them with
        the specified evaluators.

        Parameters
        ----------
        agent_id:
            AgentCore Runtime agent identifier.
        session_id:
            Session to evaluate.
        evaluators:
            List of evaluator identifiers (``Builtin.*`` or custom IDs).
        """
        resolved = resolve_evaluator_ids(evaluators)
        logger.info(
            "Running on-demand evaluation: agent=%s session=%s evaluators=%s",
            agent_id,
            session_id,
            resolved,
        )
        try:
            sdk_result = self._client.run(
                agent_id=agent_id,
                session_id=session_id,
                evaluators=resolved,
            )
        except Exception as exc:
            raise EvaluationError(
                message=str(exc),
                agent_id=agent_id,
                code="RUN_FAILED",
            ) from exc

        scores = [
            EvaluationScore(
                evaluator_name=r.evaluator_name,
                label=r.label,
                value=r.value,
                explanation=getattr(r, "explanation", ""),
                token_usage=getattr(r, "token_usage", {}),
            )
            for r in sdk_result.results
        ]
        logger.info(
            "Evaluation complete: agent=%s session=%s scores=%d",
            agent_id,
            session_id,
            len(scores),
        )
        return EvaluationResult(agent_id=agent_id, session_id=session_id, scores=scores)

    # ------------------------------------------------------------------
    # Custom evaluators
    # ------------------------------------------------------------------

    def create_evaluator(self, config: CustomEvaluatorConfig) -> str:
        """Create a custom LLM-as-judge evaluator.

        Parameters
        ----------
        config:
            Full evaluator configuration from blueprint.

        Returns
        -------
        The evaluator ID assigned by AgentCore.
        """
        logger.info(
            "Creating custom evaluator: %s (level=%s)", config.name, config.level.value
        )
        try:
            result = self._client.create_evaluator(
                name=config.name,
                level=config.level.value,
                config={
                    "llmAsAJudge": {
                        "modelConfig": {
                            "bedrockEvaluatorModelConfig": {
                                "modelId": config.model_id,
                                "inferenceConfig": {
                                    "maxTokens": config.max_tokens,
                                    "temperature": config.temperature,
                                },
                            }
                        },
                        "instructions": config.instructions,
                        "ratingScale": {
                            "numerical": [
                                val
                                for val in range(config.scale[0], config.scale[1] + 1)
                            ]
                        },
                    }
                },
            )
        except Exception as exc:
            raise EvaluationError(
                message=f"Failed to create evaluator '{config.name}': {exc}",
                code="CREATE_EVALUATOR_FAILED",
            ) from exc

        evaluator_id = result.evaluator_id
        logger.info("Created evaluator '%s' -> %s", config.name, evaluator_id)
        return evaluator_id

    def list_evaluators(self) -> list[Any]:
        """List all evaluators (built-in + custom) available in the account."""
        try:
            return self._client.list_evaluators()
        except Exception as exc:
            raise EvaluationError(
                message=f"Failed to list evaluators: {exc}",
                code="LIST_EVALUATORS_FAILED",
            ) from exc

    def delete_evaluator(self, evaluator_id: str) -> None:
        """Delete a custom evaluator by ID."""
        logger.info("Deleting evaluator: %s", evaluator_id)
        try:
            self._client.delete_evaluator(evaluator_id=evaluator_id)
        except Exception as exc:
            raise EvaluationError(
                message=f"Failed to delete evaluator '{evaluator_id}': {exc}",
                code="DELETE_EVALUATOR_FAILED",
            ) from exc

    # ------------------------------------------------------------------
    # Online evaluation (continuous monitoring)
    # ------------------------------------------------------------------

    def create_online_config(
        self,
        agent_id: str,
        config_name: str,
        config: OnlineEvaluationConfig,
    ) -> str:
        """Configure continuous evaluation for an agent.

        Parameters
        ----------
        agent_id:
            AgentCore Runtime agent identifier.
        config_name:
            Human-readable name for this monitoring configuration.
        config:
            Online evaluation settings from blueprint.

        Returns
        -------
        The online config identifier.
        """
        resolved = resolve_evaluator_ids(config.evaluators)
        logger.info(
            "Creating online eval config: agent=%s name=%s sampling=%d%% evaluators=%d",
            agent_id,
            config_name,
            config.sampling_rate,
            len(resolved),
        )
        try:
            result = self._client.create_online_config(
                agent_id=agent_id,
                config_name=config_name,
                sampling_rate=config.sampling_rate,
                evaluator_list=resolved,
                auto_create_execution_role=config.auto_create_execution_role,
            )
        except Exception as exc:
            raise EvaluationError(
                message=f"Failed to create online config '{config_name}': {exc}",
                agent_id=agent_id,
                code="CREATE_ONLINE_CONFIG_FAILED",
            ) from exc

        config_id = getattr(result, "config_id", config_name)
        logger.info("Created online eval config: agent=%s -> %s", agent_id, config_id)
        return config_id

    def get_online_results(
        self, agent_id: str, config_name: str
    ) -> list[dict[str, Any]]:
        """Retrieve results from an online evaluation configuration.

        Parameters
        ----------
        agent_id:
            AgentCore Runtime agent identifier.
        config_name:
            Name of the online evaluation config.
        """
        logger.info(
            "Fetching online eval results: agent=%s config=%s", agent_id, config_name
        )
        try:
            return self._client.get_online_results(
                agent_id=agent_id,
                config_name=config_name,
            )
        except Exception as exc:
            raise EvaluationError(
                message=f"Failed to get online results for '{config_name}': {exc}",
                agent_id=agent_id,
                code="GET_ONLINE_RESULTS_FAILED",
            ) from exc

    def delete_online_config(self, agent_id: str, config_name: str) -> None:
        """Delete an online evaluation configuration."""
        logger.info(
            "Deleting online eval config: agent=%s config=%s", agent_id, config_name
        )
        try:
            self._client.delete_online_config(
                agent_id=agent_id,
                config_name=config_name,
            )
        except Exception as exc:
            raise EvaluationError(
                message=f"Failed to delete online config '{config_name}': {exc}",
                agent_id=agent_id,
                code="DELETE_ONLINE_CONFIG_FAILED",
            ) from exc
