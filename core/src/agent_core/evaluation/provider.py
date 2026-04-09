"""EvaluationProvider protocol — backend-agnostic evaluation interface.

Two concrete implementations:

- ``EvaluationClient`` (a.k.a. ``BedrockAgentCoreEvaluationClient``)
  wraps ``bedrock_agentcore_starter_toolkit.Evaluation``. Requires a
  Bedrock judge model. Default when blueprint ``evaluation.provider``
  is ``"agentcore"`` (or omitted).

- ``LangfuseEvaluationClient`` wraps the Langfuse Python SDK. Uses
  Langfuse LLM-as-judge scorers and built-in evaluators (Hallucination,
  Toxicity, Helpfulness, Context-Relevance, ...). Provider-agnostic
  — works with any model returning standard token counts. Selected
  when blueprint ``evaluation.provider`` is ``"langfuse"``.

The loader dispatches on ``evaluation.provider`` at wire-up time and
instantiates the matching client.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_core.evaluation.results import EvaluationResult
from agent_core.schemas.evaluation_config import (
    CustomEvaluatorConfig,
    OnlineEvaluationConfig,
)


@runtime_checkable
class EvaluationProvider(Protocol):
    """Backend-agnostic evaluation interface.

    All methods may raise ``agent_core.evaluation.client.EvaluationError``
    or a subclass on failure. Implementations are expected to be
    idempotent where practical (e.g. ``create_evaluator`` with the same
    name should return the existing ID instead of duplicating).
    """

    @property
    def client(self) -> Any:
        """Raw backend SDK client for advanced use cases."""
        ...

    def run(
        self,
        agent_id: str,
        session_id: str,
        evaluators: list[str],
    ) -> EvaluationResult:
        """Run on-demand evaluation for a single agent session."""
        ...

    def create_evaluator(self, config: CustomEvaluatorConfig) -> str:
        """Create a custom LLM-as-judge evaluator. Returns the backend ID."""
        ...

    def list_evaluators(self) -> list[Any]:
        """List all evaluators (built-in + custom) available in the backend."""
        ...

    def delete_evaluator(self, evaluator_id: str) -> None:
        """Delete a custom evaluator by ID."""
        ...

    def create_online_config(
        self,
        agent_id: str,
        config_name: str,
        config: OnlineEvaluationConfig,
    ) -> str:
        """Configure continuous evaluation. Returns the config identifier."""
        ...

    def get_online_results(
        self, agent_id: str, config_name: str
    ) -> list[dict[str, Any]]:
        """Retrieve results from an online evaluation configuration."""
        ...

    def delete_online_config(self, agent_id: str, config_name: str) -> None:
        """Delete an online evaluation configuration."""
        ...
