"""BlueprintLoader -- YAML -> Pydantic -> (optionally) Strands Agent."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.blueprints.session import AgentSession
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.prompt.client import PromptRegistryClient
from agent_core.schemas.model_config import ModelConfig

try:
    from strands import Agent  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    Agent = None  # type: ignore[assignment,misc]

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
    prompt_dir:
        Optional local prompt directory. If *prompt_client* is ``None`` and
        *prompt_dir* is provided, a :class:`PromptRegistryClient` is created
        with this directory as its local fallback.
    gateway_client:
        Optional pre-built :class:`GatewayClient` instance.  When provided,
        all agents share this client instead of creating their own.
    hook_registry:
        Mapping of hook name to hook class, used by
        :meth:`build_agent_session` to instantiate hooks declared in blueprints.
    schema_registry:
        Mapping of schema name to Pydantic model class, used by
        :meth:`build_agent_session` to resolve ``output_schema`` references.
    """

    def __init__(
        self,
        blueprints_dir: str | Path,
        prompt_client: PromptRegistryClient | None = None,
        *,
        prompt_dir: str | Path | None = None,
        hook_registry: dict[str, type] | None = None,
        schema_registry: dict[str, type[BaseModel]] | None = None,
        gateway_client: Any = None,
    ) -> None:
        self.blueprints_dir = Path(blueprints_dir)
        self._prompt_dir = Path(prompt_dir) if prompt_dir else None
        self._hook_registry = hook_registry
        self._schema_registry = schema_registry
        self._gateway_client = gateway_client

        if prompt_client is not None:
            self.prompt_client = prompt_client
        elif prompt_dir is not None:
            self.prompt_client = PromptRegistryClient(local_dir=prompt_dir)
        else:
            self.prompt_client = PromptRegistryClient()

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


    # ------------------------------------------------------------------
    # Strands Agent builder -- helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_filtered_tools(client: Any, tool_cfg: Any) -> list[Any]:
        """Extract declared tools from a filterable MCP client."""
        tools: list[Any] = []
        for tname in tool_cfg.tools:
            if tname in client.tool_names:
                tools.append(client[tname])
            else:
                logger.warning(
                    "Tool '%s' not found in MCP client '%s'",
                    tname,
                    tool_cfg.mcp,
                )
        return tools

    def _collect_tools(
        self,
        blueprint: AgentBlueprint,
        mcp_clients: McpClientMap | None,
    ) -> list[Any]:
        """Resolve MCP tools declared in the blueprint."""
        if not mcp_clients:
            return []

        tools: list[Any] = []
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
                tools.extend(self._collect_filtered_tools(client, tool_cfg))
            else:
                # Client doesn't support filtering -- add it wholesale.
                tools.append(client)
        return tools

    def _resolve_prompt(self, prompt_ref: str) -> str:
        """Resolve a prompt reference to its text via the prompt client."""
        try:
            return self.prompt_client.get(prompt_ref)
        except Exception as exc:
            raise BlueprintLoadError(
                f"Failed to resolve prompt '{prompt_ref}': {exc}"
            ) from exc

    def _resolve_hooks(self, hook_names: list[str]) -> list[Any]:
        """Instantiate hooks declared in a blueprint.

        Returns an empty list when no hooks are declared.

        Raises
        ------
        BlueprintLoadError
            If the blueprint declares hooks but no ``hook_registry`` was
            configured, or if a hook name is not found in the registry.
        """
        if not hook_names:
            return []
        if self._hook_registry is None:
            raise BlueprintLoadError(
                f"Blueprint declares hooks {hook_names} but no hook_registry configured."
            )
        hooks: list[Any] = []
        for name in hook_names:
            hook_cls = self._hook_registry.get(name)
            if hook_cls is None:
                raise BlueprintLoadError(
                    f"Unknown hook '{name}'. Available: {list(self._hook_registry.keys())}"
                )
            hooks.append(hook_cls())
        return hooks

    def _resolve_output_schema(self, schema_name: str | None) -> type[BaseModel] | None:
        """Resolve an output schema name to its Pydantic model class.

        Returns ``None`` when *schema_name* is ``None``.
        """
        if schema_name is None:
            return None
        if self._schema_registry is None:
            raise BlueprintLoadError(
                f"Blueprint declares output_schema '{schema_name}' but no schema_registry configured."
            )
        schema_cls = self._schema_registry.get(schema_name)
        if schema_cls is None:
            raise BlueprintLoadError(
                f"Unknown output schema '{schema_name}'. Available: {list(self._schema_registry.keys())}"
            )
        return schema_cls

    @staticmethod
    def _build_model_config(
        model: ModelConfig,
        thinking: Any = None,
    ) -> dict[str, Any]:
        """Build provider-specific model configuration dict.

        Strands Agent accepts ``model`` as a string model-id or a Model object.
        Temperature and max_tokens are passed to the model provider, not the Agent.
        """
        # Use BEDROCK_REGION env var if set, otherwise default to us-west-2
        bedrock_region = os.environ.get("BEDROCK_REGION", "us-west-2")
        from strands.models import BedrockModel
        bedrock_model = BedrockModel(
            model_id=model.model_id,
            region_name=bedrock_region,
        )
        config: dict[str, Any] = {
            "model": bedrock_model,
        }
        if thinking is not None and getattr(thinking, "enabled", False):
            config["thinking"] = {
                "type": "enabled",
                "budget_tokens": getattr(thinking, "budget_tokens", 10000),
            }
        return config

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

        blueprint = self.load_agent(agent_id)
        current_mode = mode or get_execution_mode()

        # -- mode gate --
        if not validate_agent_mode(blueprint.execution_modes, current_mode):
            raise BlueprintLoadError(
                f"Agent '{agent_id}' is not enabled for mode '{current_mode.value}'."
            )

        # -- resolve prompt --
        system_prompt = self._resolve_prompt(blueprint.prompt_ref)
        logger.info("Resolved prompt for %s (%d chars)", agent_id, len(system_prompt))

        # -- build model kwargs --
        model_kwargs = self._build_model_config(blueprint.model, blueprint.thinking)

        # -- collect tools --
        tools = self._collect_tools(blueprint, mcp_clients)

        # -- build agent --
        agent = Agent(
            system_prompt=system_prompt,
            tools=tools if tools else None,
            **model_kwargs,
        )
        logger.info("Built Strands Agent '%s' (mode=%s)", agent_id, current_mode.value)
        return agent

    # ------------------------------------------------------------------
    # Agent Session builder -- single-node helpers
    # ------------------------------------------------------------------

    def _create_mcp_clients(self, blueprint: AgentBlueprint) -> list[Any]:
        """Create a GatewayClient as the sole tool provider.

        All tool access goes through the AgentCore Gateway.  The Gateway
        auto-generates MCP interfaces from registered targets.
        """
        from agent_core.gateway.client import GatewayClient

        if self._gateway_client is not None:
            return [self._gateway_client.as_tool_provider()]

        client = GatewayClient.from_config(blueprint.gateway)
        return [client.as_tool_provider()]

    def _build_agent_kwargs(
        self,
        blueprint: AgentBlueprint,
        mcp_clients: list[Any],
    ) -> dict[str, Any]:
        """Build common Agent constructor kwargs."""
        system_prompt = self._resolve_prompt(blueprint.prompt_ref)
        hooks = self._resolve_hooks(blueprint.hooks)
        structured_output_model = self._resolve_output_schema(blueprint.output_schema)

        kwargs: dict[str, Any] = {
            "system_prompt": system_prompt,
            "tools": mcp_clients if mcp_clients else None,
        }
        kwargs.update(self._build_model_config(blueprint.model, blueprint.thinking))

        if hooks:
            kwargs["hooks"] = hooks
        if structured_output_model is not None:
            kwargs["structured_output_model"] = structured_output_model

        return kwargs

    # ------------------------------------------------------------------
    # Agent Session builder
    # ------------------------------------------------------------------

    def build_agent_session(
        self,
        agent_id: str,
        mode: ExecutionMode | None = None,
    ) -> AgentSession:
        """Build an :class:`AgentSession` with full lifecycle management.

        Unlike :meth:`build_strands_agent`, this method creates a
        ``GatewayClient`` automatically from the blueprint and wraps it in
        an :class:`AgentSession` context manager that ensures proper cleanup.

        Parameters
        ----------
        agent_id:
            The ``id`` field of the agent blueprint.
        mode:
            Override execution mode (defaults to env-var-based mode).

        Returns
        -------
        An :class:`AgentSession` to be used as a context manager.
        """

        blueprint = self.load_agent(agent_id)
        current_mode = mode or get_execution_mode()

        # -- mode gate --
        if not validate_agent_mode(blueprint.execution_modes, current_mode):
            raise BlueprintLoadError(
                f"Agent '{agent_id}' is not enabled for mode '{current_mode.value}'."
            )

        # -- resolve prompt --
        system_prompt = self._resolve_prompt(blueprint.prompt_ref)
        logger.info("Resolved prompt for %s (%d chars)", agent_id, len(system_prompt))

        # -- create MCP clients via factory --
        mcp_clients = self._create_mcp_clients(blueprint)

        # -- build agent kwargs --
        agent_kwargs = self._build_agent_kwargs(blueprint, mcp_clients)

        agent = Agent(**agent_kwargs)
        logger.info("Built Agent Session '%s' (mode=%s, mcps=%d)", agent_id, current_mode.value, len(mcp_clients))

        # -- multi-agent orchestration --
        ma = blueprint.multi_agent
        if ma is not None:
            # Multi-node path: ma.nodes is non-empty
            if ma.nodes:
                return self._build_multi_node_session(
                    ma, agent, agent_id, mcp_clients, current_mode,
                )

            # Single-node path (Phase 4 backward compat)
            if ma.pattern == "swarm":
                from strands.multiagent.swarm import Swarm

                swarm = Swarm(
                    nodes=[agent],
                    max_handoffs=ma.max_handoffs,
                    execution_timeout=float(ma.execution_timeout),
                    node_timeout=float(ma.node_timeout),
                )
                logger.info("Built Swarm session '%s' (1 node)", agent_id)
                return AgentSession(
                    agent=agent, mcp_clients=mcp_clients,
                    multi_agent=swarm, pattern="swarm",
                )

            elif ma.pattern == "graph":
                from strands.multiagent.graph import GraphBuilder

                builder = GraphBuilder()
                builder.add_node(agent, node_id=agent_id)
                builder.set_entry_point(agent_id)
                builder.set_execution_timeout(float(ma.execution_timeout))
                builder.set_node_timeout(float(ma.node_timeout))
                graph = builder.build()
                logger.info("Built Graph session '%s' (1 node)", agent_id)
                return AgentSession(
                    agent=agent, mcp_clients=mcp_clients,
                    multi_agent=graph, pattern="graph",
                )

            else:
                logger.warning("Unknown pattern '%s', falling back to single", ma.pattern)

        return AgentSession(agent=agent, mcp_clients=mcp_clients)

    # ------------------------------------------------------------------
    # Multi-node session builder
    # ------------------------------------------------------------------

    def _build_multi_node_session(
        self,
        ma: Any,
        primary_agent: Any,
        primary_id: str,
        primary_mcp_clients: list[Any],
        current_mode: ExecutionMode,
    ) -> AgentSession:
        """Build a multi-node Swarm or Graph session from node configs.

        Each node references a separate blueprint. All MCP clients are
        collected into the AgentSession for proper lifecycle cleanup.
        """
        all_mcp_clients = list(primary_mcp_clients)
        node_agents: dict[str, Any] = {}

        for node_cfg in ma.nodes:
            node_bp = self.load_agent(node_cfg.agent_ref)

            if not validate_agent_mode(node_bp.execution_modes, current_mode):
                raise BlueprintLoadError(
                    f"Node agent '{node_cfg.agent_ref}' is not enabled for "
                    f"mode '{current_mode.value}'."
                )

            node_mcp_clients = self._create_mcp_clients(node_bp)
            all_mcp_clients.extend(node_mcp_clients)

            node_kwargs = self._build_agent_kwargs(node_bp, node_mcp_clients)
            node_agent = Agent(**node_kwargs)
            node_agents[node_cfg.node_id] = node_agent
            logger.info("Built node agent '%s' (blueprint=%s)", node_cfg.node_id, node_cfg.agent_ref)

        if ma.pattern == "swarm":
            from strands.multiagent.swarm import Swarm

            agent_list = list(node_agents.values())
            entry = node_agents.get(ma.entry_point) if ma.entry_point else None
            swarm = Swarm(
                nodes=agent_list,
                entry_point=entry,
                max_handoffs=ma.max_handoffs,
                max_iterations=ma.max_iterations,
                execution_timeout=float(ma.execution_timeout),
                node_timeout=float(ma.node_timeout),
            )
            logger.info("Built multi-node Swarm '%s' (%d nodes)", primary_id, len(agent_list))
            return AgentSession(
                agent=primary_agent,
                mcp_clients=all_mcp_clients,
                multi_agent=swarm,
                pattern="swarm",
            )

        elif ma.pattern == "graph":
            from strands.multiagent.graph import GraphBuilder

            builder = GraphBuilder()
            for node_id, node_agent in node_agents.items():
                builder.add_node(node_agent, node_id=node_id)

            for edge in ma.edges:
                if edge.condition is not None:
                    from agent_core.blueprints.condition_parser import parse_condition
                    cond_fn = parse_condition(edge.condition)
                    builder.add_edge(edge.from_node, edge.to_node, condition=cond_fn)
                else:
                    builder.add_edge(edge.from_node, edge.to_node)

            if ma.entry_point:
                builder.set_entry_point(ma.entry_point)
            elif ma.nodes:
                builder.set_entry_point(ma.nodes[0].node_id)

            builder.set_execution_timeout(float(ma.execution_timeout))
            builder.set_node_timeout(float(ma.node_timeout))
            if ma.max_node_executions is not None:
                builder.set_max_node_executions(ma.max_node_executions)

            graph = builder.build()
            logger.info("Built multi-node Graph '%s' (%d nodes, %d edges)",
                        primary_id, len(node_agents), len(ma.edges))
            return AgentSession(
                agent=primary_agent,
                mcp_clients=all_mcp_clients,
                multi_agent=graph,
                pattern="graph",
            )

        raise BlueprintLoadError(f"Unknown multi-agent pattern: {ma.pattern}")
