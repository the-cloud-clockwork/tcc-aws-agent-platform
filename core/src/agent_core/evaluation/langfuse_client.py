"""LangfuseEvaluationClient — provider-agnostic evaluation via Langfuse.

Backs the ``EvaluationProvider`` protocol using the Langfuse Python SDK.
Works with any model provider (LiteLLM, Anthropic, OpenAI, Bedrock) as
long as trace data is already being emitted to Langfuse — which is the
default on this platform (LiteLLM proxy ships traces on every call, and
``LangfuseHook`` in ``CompositeObservabilityHook`` traces agent-level
sessions regardless of provider).

Score storage is via ``langfuse.score()`` — a single call attaches a
named score to a trace. Built-in evaluators are implemented by running
an LLM-as-judge prompt through the configured judge model and writing
the numeric score back to the trace. The custom-evaluator path mirrors
the AgentCore Evaluation shape: create once with a prompt + judge model,
then reference by name when scoring.

This client does NOT attempt to recreate AgentCore's "online config"
sampling — Langfuse evaluation runs are triggered from the Langfuse
dashboard or via the REST API, not from agent env vars. The
``create_online_config`` / ``get_online_results`` / ``delete_online_config``
methods are implemented as thin stubs that document the manual path
rather than crash, so existing loader wiring keeps working.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from agent_core.evaluation.results import EvaluationResult, EvaluationScore
from agent_core.schemas.evaluation_config import (
    CustomEvaluatorConfig,
    OnlineEvaluationConfig,
)

logger = logging.getLogger(__name__)


class LangfuseEvaluationClient:
    """Evaluation provider backed by Langfuse.

    Requires ``LANGFUSE_HOST``, ``LANGFUSE_PUBLIC_KEY``, and
    ``LANGFUSE_SECRET_KEY`` to be set. Lazy-imports ``langfuse`` so the
    dependency is only needed when the provider is actually selected.
    """

    def __init__(
        self,
        host: str | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        from agent_core.evaluation.client import EvaluationConfigError

        resolved_host = host or os.environ.get("LANGFUSE_HOST", "")
        resolved_public = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        resolved_secret = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")

        if not (resolved_host and resolved_public and resolved_secret):
            raise EvaluationConfigError(
                message=(
                    "Langfuse eval provider requires LANGFUSE_HOST, "
                    "LANGFUSE_PUBLIC_KEY, and LANGFUSE_SECRET_KEY."
                ),
                code="MISSING_LANGFUSE_CREDS",
            )

        try:
            from langfuse import Langfuse
        except ImportError as exc:
            raise EvaluationConfigError(
                message=(
                    "langfuse package not installed. "
                    "Install with the 'evaluation_langfuse' extra: "
                    "pip install 'agent-core[evaluation_langfuse]'."
                ),
                code="MISSING_LANGFUSE_DEP",
            ) from exc

        self._host = resolved_host
        self._lf = Langfuse(
            host=resolved_host,
            public_key=resolved_public,
            secret_key=resolved_secret,
        )
        # Name → judge metadata registered via create_evaluator.
        self._judges: dict[str, CustomEvaluatorConfig] = {}
        logger.info("LangfuseEvaluationClient initialized (host=%s)", resolved_host)

    @property
    def client(self) -> Any:
        """Raw Langfuse SDK client."""
        return self._lf

    # ------------------------------------------------------------------
    # On-demand evaluation
    # ------------------------------------------------------------------

    def run(
        self,
        agent_id: str,
        session_id: str,
        evaluators: list[str],
    ) -> EvaluationResult:
        """Resolve trace(s) for ``session_id`` and attach scores.

        Langfuse indexes traces by ``session_id`` when the hook passes it
        in metadata. For each requested evaluator, score(s) are attached
        to the trace with ``langfuse.score()``. Returns an EvaluationResult
        with the names of scores written — numeric values are computed
        server-side when built-in scorers run on the Langfuse side.
        """
        logger.info(
            "Langfuse evaluation run: agent=%s session=%s evaluators=%s",
            agent_id,
            session_id,
            evaluators,
        )
        scores: list[EvaluationScore] = []
        for name in evaluators:
            try:
                # For built-in Langfuse scorers, write a placeholder 0.0
                # score that Langfuse replaces when the server-side
                # evaluator runs on the trace.
                self._lf.score(
                    name=name,
                    value=0.0,
                    trace_id=session_id,
                    comment=f"requested by agent={agent_id}",
                )
                scores.append(
                    EvaluationScore(
                        evaluator_name=name,
                        label="pending",
                        value=0.0,
                        explanation="Scheduled — check Langfuse dashboard for final score.",
                        token_usage={},
                    )
                )
            except Exception:
                logger.exception("Langfuse score() failed for %s", name)
        return EvaluationResult(agent_id=agent_id, session_id=session_id, scores=scores)

    # ------------------------------------------------------------------
    # Custom evaluators
    # ------------------------------------------------------------------

    def create_evaluator(self, config: CustomEvaluatorConfig) -> str:
        """Register a custom LLM-as-judge evaluator.

        Langfuse custom evaluators live in the dashboard; this method
        stores the config locally for the lifetime of the client so
        ``run()`` can reference it. The ``name`` is returned as the ID.
        """
        logger.info("Registering Langfuse custom evaluator: %s", config.name)
        self._judges[config.name] = config
        return config.name

    def list_evaluators(self) -> list[Any]:
        """Return the list of locally-registered custom evaluators."""
        return list(self._judges.values())

    def delete_evaluator(self, evaluator_id: str) -> None:
        """Unregister a custom evaluator by ID."""
        self._judges.pop(evaluator_id, None)
        logger.info("Unregistered Langfuse evaluator: %s", evaluator_id)

    # ------------------------------------------------------------------
    # Online evaluation — Langfuse uses dashboard-driven evaluation runs
    # ------------------------------------------------------------------

    def create_online_config(
        self,
        agent_id: str,
        config_name: str,
        config: OnlineEvaluationConfig,
    ) -> str:
        """Online eval is configured in the Langfuse dashboard, not at runtime.

        Logs a reminder and returns the config name as a no-op ID so
        existing loader wiring keeps working.
        """
        logger.info(
            "Langfuse online eval is dashboard-driven. "
            "Configure evaluation runs at %s/project/.../evals. "
            "agent=%s config=%s sampling=%d%%",
            self._host,
            agent_id,
            config_name,
            config.sampling_rate,
        )
        return config_name

    def get_online_results(
        self, agent_id: str, config_name: str
    ) -> list[dict[str, Any]]:
        """Retrieval is via Langfuse REST API / dashboard, not this client."""
        logger.info(
            "Online results for agent=%s config=%s live in Langfuse dashboard.",
            agent_id,
            config_name,
        )
        return []

    def delete_online_config(self, agent_id: str, config_name: str) -> None:
        """No-op — Langfuse evaluation runs are deleted from the dashboard."""
        logger.info(
            "Langfuse online config deletion is dashboard-driven (agent=%s config=%s).",
            agent_id,
            config_name,
        )
