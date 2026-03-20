"""Agent configuration for the generic handler."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    """Per-agent configuration consumed by GenericHandler.

    Attributes:
        agent_id: Blueprint agent ID.
        operation_name: Idempotency key operation (e.g., "process_data").
        required_fields: Event fields validated before agent runs.
        build_prompt: Callable (params, idempotency_key) -> user prompt string.
        defaults: Default parameter values merged into event params.
    """
    agent_id: str
    operation_name: str
    required_fields: list[str]
    build_prompt: Callable[[dict[str, Any], str], str]
    defaults: dict[str, Any] = field(default_factory=dict)


class AgentConfigRegistry:
    """Registry of agent configurations."""

    def __init__(self) -> None:
        self._configs: dict[str, AgentConfig] = {}

    def register(self, config: AgentConfig) -> None:
        self._configs[config.agent_id] = config

    def get(self, agent_id: str) -> AgentConfig | None:
        return self._configs.get(agent_id)

    def list_agents(self) -> list[str]:
        return list(self._configs.keys())

    def __len__(self) -> int:
        return len(self._configs)
