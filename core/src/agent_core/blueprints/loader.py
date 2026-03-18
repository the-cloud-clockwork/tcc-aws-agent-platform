"""BlueprintLoader -- YAML -> Pydantic -> (optionally) Strands Agent."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.blueprints.strategy import StrategyBlueprint
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.prompt.client import PromptRegistryClient

logger = logging.getLogger(__name__)

# Type alias for MCP client map (mcp_name -> client instance).
# Strands MCP clients are typed as Any here to avoid hard-coupling.
McpClientMap = dict[str, Any]


class BlueprintLoadError(Exception):
    """Raised when a blueprint YAML cannot be loaded or validated."""


class BlueprintLoader:
    """Load YAML blueprints from a directory tree and build Strands agents.

    Parameters
    ----------
    blueprints_dir:
        Root directory containing ``agents/``, ``strategies/``, and
        ``workflows/`` sub-directories with YAML files.
    prompt_client:
        Optional :class:`PromptRegistryClient` used when building agents.
        If ``None`` a default client is created.
    """

    def __init__(
        self,
        blueprints_dir: str | Path,
        prompt_client: PromptRegistryClient | None = None,
    ) -> None:
        self.blueprints_dir = Path(blueprints_dir)
        self.prompt_client = prompt_client or PromptRegistryClient()

    # ------------------------------------------------------------------
    # YAML helpers
    # ------------------------------------------------------------------

    def _find_yaml(self, subdir: str, blueprint_id: str) -> Path:
        """Locate a YAML file by *blueprint_id* inside *subdir*."""
        search_dir = self.blueprints_dir / subdir
        for suffix in (".yaml", ".yml"):
            candidate = search_dir / f"{blueprint_id}{suffix}"
            if candidate.exists():
                return candidate
        # Fallback: scan all YAML files for a matching ``id`` field.
        if search_dir.is_dir():
            for p in search_dir.iterdir():
                if p.suffix in (".yaml", ".yml"):
                    with p.open() as fh:
                        data = yaml.safe_load(fh)
                    if isinstance(data, dict) and data.get("id") == blueprint_id:
                        return p
        raise BlueprintLoadError(
            f"Blueprint '{blueprint_id}' not found in {search_dir}"
        )

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        with path.open() as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise BlueprintLoadError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return data

    # ------------------------------------------------------------------
    # Public loaders
    # ------------------------------------------------------------------

    def load_agent(self, agent_id: str) -> AgentBlueprint:
        """Load an agent blueprint YAML and return a validated Pydantic model."""
        path = self._find_yaml("agents", agent_id)
        data = self._read_yaml(path)
        try:
            return AgentBlueprint(**data)
        except Exception as exc:
            raise BlueprintLoadError(f"Validation failed for agent '{agent_id}': {exc}") from exc

    def load_strategy(self, strategy_id: str) -> StrategyBlueprint:
        """Load a strategy blueprint YAML and return a validated Pydantic model."""
        path = self._find_yaml("strategies", strategy_id)
        data = self._read_yaml(path)
        try:
            return StrategyBlueprint(**data)
        except Exception as exc:
            raise BlueprintLoadError(
                f"Validation failed for strategy '{strategy_id}': {exc}"
            ) from exc

    def load_workflow(self, workflow_id: str) -> WorkflowBlueprint:
        """Load a workflow blueprint YAML and return a validated Pydantic model."""
        path = self._find_yaml("workflows", workflow_id)
        data = self._read_yaml(path)
        try:
            return WorkflowBlueprint(**data)
        except Exception as exc:
            raise BlueprintLoadError(
                f"Validation failed for workflow '{workflow_id}': {exc}"
            ) from exc

    def load_agent_from_path(self, path: str | Path) -> AgentBlueprint:
        """Load an agent blueprint from an explicit file path."""
        data = self._read_yaml(Path(path))
        try:
            return AgentBlueprint(**data)
        except Exception as exc:
            raise BlueprintLoadError(f"Validation failed for {path}: {exc}") from exc

    def load_strategy_from_path(self, path: str | Path) -> StrategyBlueprint:
        """Load a strategy blueprint from an explicit file path."""
        data = self._read_yaml(Path(path))
        try:
            return StrategyBlueprint(**data)
        except Exception as exc:
            raise BlueprintLoadError(f"Validation failed for {path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Strands Agent builder
    # ------------------------------------------------------------------

    def build_strands_agent(
        self,
        agent_id: str,
        mcp_clients: McpClientMap | None = None,
        mode: ExecutionMode | None = None,
    ) -> Any:
        """Build a configured Strands ``Agent`` from an agent blueprint.

        Steps:
        1. Load and validate the blueprint YAML.
        2. Verify the current execution mode is allowed.
        3. Resolve the prompt text via :class:`PromptRegistryClient`.
        4. Collect MCP tools (filtered to only those declared in the blueprint).
        5. Instantiate and return the Strands ``Agent``.

        Parameters
        ----------
        agent_id:
            The ``id`` field of the agent blueprint.
        mcp_clients:
            Mapping of MCP server name -> pre-initialised MCP client.
        mode:
            Override execution mode (defaults to env-var-based mode).

        Returns
        -------
        A ``strands.Agent`` instance ready to invoke.
        """
        from strands import Agent  # type: ignore[import-untyped]

        blueprint = self.load_agent(agent_id)
        current_mode = mode or get_execution_mode()

        # -- mode gate --
        if not validate_agent_mode(blueprint.execution_modes, current_mode):
            raise BlueprintLoadError(
                f"Agent '{agent_id}' is not enabled for mode '{current_mode.value}'."
            )

        # -- resolve prompt --
        system_prompt = self.prompt_client.get(blueprint.prompt_ref)
        logger.info("Resolved prompt for %s (%d chars)", agent_id, len(system_prompt))

        # -- build model kwargs --
        model_kwargs: dict[str, Any] = {
            "model_id": blueprint.model.model_id,
            "temperature": blueprint.model.temperature,
            "max_tokens": blueprint.model.max_tokens,
        }

        # -- collect tools --
        tools: list[Any] = []
        if mcp_clients:
            for tool_cfg in blueprint.tools:
                client = mcp_clients.get(tool_cfg.mcp)
                if client is None:
                    logger.warning(
                        "MCP client '%s' not provided -- skipping tools %s",
                        tool_cfg.mcp,
                        tool_cfg.tools,
                    )
                    continue
                # Strands MCP clients expose tools that can be filtered by name.
                if hasattr(client, "tool_names"):
                    # Filter to only declared tools.
                    for tname in tool_cfg.tools:
                        if tname in client.tool_names:
                            tools.append(client[tname])
                        else:
                            logger.warning(
                                "Tool '%s' not found in MCP client '%s'",
                                tname,
                                tool_cfg.mcp,
                            )
                else:
                    # If the client doesn't support filtering, add it wholesale.
                    tools.append(client)

        # -- build agent --
        agent = Agent(
            system_prompt=system_prompt,
            tools=tools if tools else None,
            **model_kwargs,
        )
        logger.info("Built Strands Agent '%s' (mode=%s)", agent_id, current_mode.value)
        return agent
