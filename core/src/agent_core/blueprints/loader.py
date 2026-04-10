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
from agent_core.blueprints.strategy import StrategyBlueprint
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import (
    ExecutionMode,
    get_execution_mode,
    validate_agent_mode,
)
from agent_core.prompt.client import PromptRegistryClient
from agent_core.schemas.model_config import ModelConfig

from strands import Agent  # type: ignore[import-untyped]

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
            raise BlueprintLoadError(
                f"Expected a mapping in {path}, got {type(data).__name__}"
            )
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
            raise BlueprintLoadError(
                f"Validation failed for agent '{agent_id}': {exc}"
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

    def load_strategy_from_path(self, path: str | Path) -> StrategyBlueprint:
        """Load a strategy blueprint from an explicit file path."""
        data = self._read_yaml(Path(path))
        try:
            return StrategyBlueprint(**data)
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
        from agent_core.schemas.tool_config import McpToolConfig

        if not mcp_clients:
            return []

        tools: list[Any] = []
        for tool_cfg in blueprint.tools:
            # Only process MCP tool declarations here; builtins are
            # handled separately via BuiltinToolWiring.
            if not isinstance(tool_cfg, McpToolConfig):
                continue
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

        Dispatches on ``model.provider`` to construct the appropriate Strands
        Model instance.  Imports are lazy so non-default providers only require
        their SDK package when actually selected by a blueprint.
        """
        import re

        def _expand_with_defaults(s: str) -> str:
            """Expand ${VAR:-default} and ${VAR} patterns."""
            def _sub(m):
                var = m.group(1)
                default = m.group(2)
                return os.environ.get(var, default if default is not None else m.group(0))
            return re.sub(r'\$\{([^}:]+)(?::-(.*?))?\}', _sub, s)

        provider_model: Any = None
        match model.provider:
            case "bedrock":
                bedrock_region = os.environ.get("BEDROCK_REGION", "")
                if not bedrock_region:
                    raise BlueprintLoadError(
                        "BEDROCK_REGION env var is required for bedrock provider."
                    )
                from strands.models import BedrockModel

                provider_model = BedrockModel(
                    model_id=_expand_with_defaults(model.model_id),
                    region_name=bedrock_region,
                    max_tokens=model.max_tokens,
                )

            case "anthropic":
                from strands.models.anthropic import AnthropicModel

                client_args: dict[str, Any] = {}
                if model.api_key_env:
                    key = os.environ.get(model.api_key_env, "")
                    if key:
                        client_args["api_key"] = key
                provider_model = AnthropicModel(
                    client_args=client_args or None,
                    model_id=_expand_with_defaults(model.model_id),
                    max_tokens=model.max_tokens,
                )

            case "litellm":
                from strands.models.litellm import LiteLLMModel

                # model_id is passed through unchanged — the blueprint
                # author supplies the literal the proxy expects.
                #
                # When base_url is set, we assume the endpoint is
                # OpenAI-compatible (the standard LiteLLM proxy contract)
                # and pin custom_llm_provider="openai". Without this pin,
                # the litellm library's model-name heuristic routes
                # claude-*/gemini-*/deepseek-* to the native provider's
                # endpoint, ignoring api_base. This is a litellm library
                # quirk, not a platform concern — the flag just tells
                # litellm "trust me, it's OpenAI-compatible".
                #
                # client_args is unpacked into litellm.acompletion() via
                # `**self.client_args` (strands/models/litellm.py:466).
                client_args_l: dict[str, Any] = {}
                if model.base_url:
                    client_args_l["api_base"] = model.base_url
                    client_args_l["custom_llm_provider"] = "openai"
                if model.api_key_env:
                    key = os.environ.get(model.api_key_env, "")
                    if key:
                        client_args_l["api_key"] = key
                if model.extra_headers_env:
                    headers = {}
                    for header_name, env_var in model.extra_headers_env.items():
                        val = os.environ.get(env_var, "")
                        if val:
                            headers[header_name] = val
                    if headers:
                        client_args_l["extra_headers"] = headers

                resolved_model_id = _expand_with_defaults(model.model_id)

                provider_model = LiteLLMModel(
                    client_args=client_args_l if client_args_l else None,
                    model_id=resolved_model_id,
                    params={"max_tokens": model.max_tokens, "temperature": model.temperature},
                )

            case "vertex":
                from strands.models.gemini import GeminiModel

                provider_model = GeminiModel(model_id=os.path.expandvars(model.model_id))

            case _:
                raise BlueprintLoadError(
                    f"Unsupported model provider: {model.provider!r}"
                )

        config: dict[str, Any] = {"model": provider_model}
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

    def _create_tool_providers(self, blueprint: AgentBlueprint) -> list[Any]:
        """Create tool providers from the blueprint.

        MCP tools go through the AgentCore Gateway.  Builtin tools (Code
        Interpreter, Browser) are injected as direct Strands tool callables
        alongside the Gateway's MCPClient.

        When GATEWAY_DIRECT_MCP=true, MCP runtime targets are called directly
        (bypassing Gateway) as a workaround for AWS Issue #809.
        See KNOWN_ISSUES.md KI-001.
        """
        import os

        from agent_core.gateway.client import GatewayClient
        from agent_core.schemas.tool_config import BuiltinToolConfig, McpToolConfig

        providers: list[Any] = []

        has_mcp_tools = any(isinstance(t, McpToolConfig) for t in blueprint.tools)
        direct_mcp = os.environ.get("GATEWAY_DIRECT_MCP", "").lower() == "true"

        if has_mcp_tools or not blueprint.tools:
            if direct_mcp and has_mcp_tools:
                # WORKAROUND: AWS Issue #809 — Gateway can't forward tools/call
                # to MCP runtimes. Connect directly with JWT auth.
                # Do NOT add Gateway — it would expose duplicate MCP tools
                # that fail with "internal error." Only direct clients.
                from agent_core.gateway.direct_mcp_client import create_direct_providers

                direct_providers = create_direct_providers(blueprint)
                providers.extend(direct_providers)
                logger.info(
                    "Direct MCP bypass active: %d providers (GATEWAY_DIRECT_MCP=true)",
                    len(direct_providers),
                )
            else:
                # Normal path — all tools via Gateway
                if self._gateway_client is not None:
                    providers.append(self._gateway_client.as_tool_provider())
                else:
                    client = GatewayClient.from_config(blueprint.gateway)
                    providers.append(client.as_tool_provider())

        # Builtin tools (Code Interpreter, Browser) — Gateway-mediated
        builtin_configs = [
            t for t in blueprint.tools if isinstance(t, BuiltinToolConfig)
        ]
        if builtin_configs:
            from agent_core.tools.wiring import BuiltinToolWiring

            gw = self._gateway_client or GatewayClient.from_config(blueprint.gateway)
            wiring = BuiltinToolWiring(configs=builtin_configs, gateway_client=gw)
            providers.extend(wiring.tool_providers)
            # Store wiring reference for lifecycle management
            self._last_builtin_wiring = wiring

        return providers

    def _build_agent_kwargs(
        self,
        blueprint: AgentBlueprint,
        mcp_clients: list[Any],
        *,
        memory_wiring: Any = None,
        local_tools: list[Any] | None = None,
    ) -> tuple[dict[str, Any], Any]:
        """Build common Agent constructor kwargs.

        Returns a tuple of (kwargs_dict, observability_hook) so the caller
        can store the observability hook in the AgentSession.
        """
        system_prompt = self._resolve_prompt(blueprint.prompt_ref)
        structured_output_model = self._resolve_output_schema(blueprint.output_schema)

        # -- auto-wire observability hook from blueprint config --
        # Gated on blueprint.observability.enabled — setting it to false
        # disables Langfuse / audit log / structured log / cost tracking.
        # Infrastructure-level OTEL (ADOT wrapper) is controlled separately
        # by runtime.observability_enabled in the Dockerfile.
        obs_hook: Any | None = None
        if blueprint.observability.enabled:
            from agent_core.hooks.observability_hooks import create_observability_hooks
            from agent_core.observability.data_protection import build_pii_filter

            audit_table = os.environ.get(
                blueprint.observability.audit_log.table_env, None
            )
            pii_filter = build_pii_filter(blueprint.observability.data_protection)
            obs_hook = create_observability_hooks(
                agent_id=blueprint.id,
                prompt_id=blueprint.prompt_ref,
                prompt_version=blueprint.version,
                execution_mode=os.environ.get("EXECUTION_MODE", "simulation"),
                audit_table=audit_table,
                pii_filter=pii_filter,
            )

        # -- auto-wire guardrail hook from blueprint config --
        # Provider-gated: Bedrock Guardrails only fires for bedrock providers.
        # Presidio path is selected when data_protection.provider == "presidio".
        guardrail_hook = None
        dp = blueprint.observability.data_protection
        dp_provider = getattr(dp, "provider", "bedrock")
        if dp_provider == "bedrock" and blueprint.model.provider == "bedrock":
            if os.environ.get(dp.guardrail_id_env):
                from agent_core.hooks.guardrail_hook import GuardrailHook

                guardrail_hook = GuardrailHook(config=dp)
        elif dp_provider == "presidio":
            from agent_core.hooks.presidio_guardrail import PresidioGuardrailHook

            guardrail_hook = PresidioGuardrailHook(
                entities=list(getattr(dp, "presidio_entities", []) or []),
                language=getattr(dp, "presidio_language", "en"),
            )

        # Compose hooks: observability first, then guardrail, then custom, then memory
        hooks: list[Any] = []
        if obs_hook is not None:
            hooks.append(obs_hook)
        if guardrail_hook is not None:
            hooks.append(guardrail_hook)
        hooks.extend(self._resolve_hooks(blueprint.hooks))
        if memory_wiring is not None:
            hooks.append(memory_wiring.hook_provider)

        # -- merge tools: Gateway + builtins + local @tool functions --
        all_tools = list(mcp_clients) if mcp_clients else []
        if local_tools:
            all_tools.extend(local_tools)

        kwargs: dict[str, Any] = {
            "system_prompt": system_prompt,
            "tools": all_tools if all_tools else None,
        }
        kwargs.update(self._build_model_config(blueprint.model, blueprint.thinking))

        # Structured output routing:
        # - bedrock: Strands' native structured_output_model (forced tool pattern)
        #   works reliably via the Converse API
        # - litellm/anthropic/vertex: Strands' forced tool pattern is broken
        #   (upstream issues #743, #1005, #891). Use StructuredOutputEnforcer
        #   hook instead, which runs instructor as a post-processor.
        #   See: core/src/agent_core/hooks/structured_output_enforcer.py
        if structured_output_model is not None:
            if blueprint.model.provider == "bedrock":
                kwargs["structured_output_model"] = structured_output_model
            else:
                from agent_core.hooks.structured_output_enforcer import (
                    StructuredOutputEnforcer,
                )

                enforcer = StructuredOutputEnforcer(
                    schema=structured_output_model,
                    model_id=blueprint.model.model_id,
                    base_url=blueprint.model.base_url,
                    api_key_env=blueprint.model.api_key_env,
                    extra_headers_env=blueprint.model.extra_headers_env,
                )
                hooks.append(enforcer)

        if hooks:
            kwargs["hooks"] = hooks

        # -- wire state dict for memory hook providers --
        if memory_wiring is not None:
            kwargs["state"] = {}

        # -- wire observability: trace_attributes --
        if blueprint.observability.trace_attributes:
            from agent_core.observability.otel import build_trace_attributes

            kwargs["trace_attributes"] = build_trace_attributes(
                blueprint_attrs=blueprint.observability.trace_attributes,
                agent_name=blueprint.id,
                agent_version=blueprint.version,
            )

        return kwargs, obs_hook

    # ------------------------------------------------------------------
    # Agent Session builder
    # ------------------------------------------------------------------

    def _wire_identity(self, blueprint: AgentBlueprint, agent_id: str) -> Any:
        if not blueprint.identity.credentials:
            return None
        from agent_core.identity.cache import CredentialCache
        from agent_core.identity.wiring import IdentityWiring

        wiring = IdentityWiring(credentials=blueprint.identity.credentials, cache=CredentialCache())
        logger.info("Wired %d credential providers for %s", len(blueprint.identity.credentials), agent_id)
        return wiring

    def _wire_memory(self, blueprint: AgentBlueprint, agent_id: str) -> Any:
        if not blueprint.memory.strategies:
            return None
        from agent_core.memory.wiring import MemoryWiring

        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
        if not memory_id:
            raise BlueprintLoadError(
                f"Agent '{agent_id}' declares memory strategies but AGENTCORE_MEMORY_ID env var is not set."
            )
        wiring = MemoryWiring(config=blueprint.memory, memory_id=memory_id)
        logger.info("Wired %d memory strategies for %s (memory_id=%s)", len(blueprint.memory.strategies), agent_id, memory_id)
        return wiring

    def _wire_evaluation(self, blueprint: AgentBlueprint, agent_id: str) -> Any:
        if not blueprint.evaluation.custom_evaluators and not blueprint.evaluation.online:
            return None
        from agent_core.evaluation.wiring import EvaluationWiring

        eval_table = None
        if blueprint.evaluation.persistence is not None and blueprint.evaluation.persistence.enabled:
            eval_table = os.environ.get(blueprint.evaluation.persistence.table_env)
        wiring = EvaluationWiring(config=blueprint.evaluation, agent_id=agent_id, results_table_name=eval_table)
        logger.info("Wired evaluation for %s", agent_id)
        return wiring

    def _wire_policy(self, blueprint: AgentBlueprint, agent_id: str) -> Any:
        if not blueprint.policy or not blueprint.policy.rules:
            return None
        from agent_core.policy.wiring import PolicyWiring

        versions_table = None
        if blueprint.policy.versioning is not None and blueprint.policy.versioning.enabled:
            versions_table = os.environ.get(blueprint.policy.versioning.table_env)
        gateway_arn = os.environ.get("AGENTCORE_GATEWAY_ARN", "")
        if not gateway_arn:
            logger.warning("AGENTCORE_GATEWAY_ARN not set — using agent_id '%s' as resource", agent_id)
            gateway_arn = agent_id
        wiring = PolicyWiring(config=blueprint.policy, agent_id=agent_id, gateway_identifier=gateway_arn, region=None, versions_table_name=versions_table)
        logger.info("Wired policy for %s", agent_id)
        return wiring

    def build_agent_session(
        self,
        agent_id: str,
        mode: ExecutionMode | None = None,
        *,
        local_tools: list[Any] | None = None,
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
        local_tools:
            Optional list of local ``@tool`` functions to mix with
            Gateway and builtin tools.

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

        # -- create tool providers (Gateway + builtins) --
        self._last_builtin_wiring = None
        mcp_clients = self._create_tool_providers(blueprint)
        if local_tools:
            mcp_clients.extend(local_tools)
        builtin_wiring = self._last_builtin_wiring

        identity_wiring = self._wire_identity(blueprint, agent_id)
        memory_wiring = self._wire_memory(blueprint, agent_id)
        evaluation_wiring = self._wire_evaluation(blueprint, agent_id)
        policy_wiring = self._wire_policy(blueprint, agent_id)

        # -- wire session bridge for multi-turn --
        session_bridge = None
        if memory_wiring is not None:
            import uuid

            from agent_core.runtime.session import SessionState
            from agent_core.runtime.strands_session_bridge import StrandsSessionBridge

            session_state = SessionState(
                session_id=str(uuid.uuid4()),
                agent_id=agent_id,
                execution_mode=current_mode.value,
            )
            session_bridge = StrandsSessionBridge(session_state)

        # -- build agent kwargs --
        agent_kwargs, obs_hook = self._build_agent_kwargs(
            blueprint, mcp_clients, memory_wiring=memory_wiring
        )

        agent = Agent(**agent_kwargs)
        logger.info(
            "Built Agent Session '%s' (mode=%s, mcps=%d)",
            agent_id,
            current_mode.value,
            len(mcp_clients),
        )

        # -- multi-agent orchestration --
        ma = blueprint.multi_agent
        if ma is not None:
            # Multi-node path: ma.nodes is non-empty
            if ma.nodes:
                return self._build_multi_node_session(
                    ma,
                    agent,
                    agent_id,
                    mcp_clients,
                    current_mode,
                    evaluation_wiring=evaluation_wiring,
                    policy_wiring=policy_wiring,
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
                    agent=agent,
                    mcp_clients=mcp_clients,
                    multi_agent=swarm,
                    pattern="swarm",
                    identity_wiring=identity_wiring,
                    memory_wiring=memory_wiring,
                    builtin_wiring=builtin_wiring,
                    evaluation_wiring=evaluation_wiring,
                    policy_wiring=policy_wiring,
                    session_bridge=session_bridge,
                    observability_hook=obs_hook,
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
                    agent=agent,
                    mcp_clients=mcp_clients,
                    multi_agent=graph,
                    pattern="graph",
                    identity_wiring=identity_wiring,
                    memory_wiring=memory_wiring,
                    builtin_wiring=builtin_wiring,
                    evaluation_wiring=evaluation_wiring,
                    policy_wiring=policy_wiring,
                    session_bridge=session_bridge,
                    observability_hook=obs_hook,
                )

            else:
                logger.warning(
                    "Unknown pattern '%s', falling back to single", ma.pattern
                )

        return AgentSession(
            agent=agent,
            mcp_clients=mcp_clients,
            identity_wiring=identity_wiring,
            memory_wiring=memory_wiring,
            builtin_wiring=builtin_wiring,
            evaluation_wiring=evaluation_wiring,
            policy_wiring=policy_wiring,
            session_bridge=session_bridge,
            observability_hook=obs_hook,
        )

    def build_entrypoint(
        self,
        agent_id: str,
        *,
        local_tools: list[Any] | None = None,
        middleware: list[Any] | None = None,
    ) -> Any:
        """Build a fully wired ``AgentCoreApp`` from a blueprint.

        Returns an :class:`AgentCoreApp` with a registered ``@app.entrypoint``
        handler that manages the full agent lifecycle:

        - Sets OTEL session baggage from the invocation context
        - Enters the :class:`AgentSession` context manager
        - Routes to ``run()`` or ``stream_async()`` based on payload
        - Handles cleanup on exit

        The consumer's ``app.py`` becomes::

            from agent_core import BlueprintLoader

            loader = BlueprintLoader("blueprints", prompt_dir="prompts")
            app = loader.build_entrypoint("my-agent")

            if __name__ == "__main__":
                app.run()

        Parameters
        ----------
        agent_id:
            The ``id`` field of the agent blueprint.
        local_tools:
            Optional list of local ``@tool`` functions.
        middleware:
            Optional Starlette middleware list for the app.
        """
        from agent_core.runtime.entrypoint import AgentCoreApp

        session = self.build_agent_session(agent_id, local_tools=local_tools)
        app = AgentCoreApp(middleware=middleware)

        @app.entrypoint
        async def handler(payload: dict, context: Any) -> Any:
            from agent_core.observability.otel import (
                detach_session_baggage,
                set_session_baggage,
            )

            token = set_session_baggage(
                session_id=getattr(context, "session_id", ""),
                user_id=payload.get("user_id"),
            )
            try:
                with session:
                    prompt = payload.get("prompt", "")
                    if payload.get("stream", False):
                        async for event in session.stream_async(prompt):
                            yield event
                    else:
                        yield session.run(prompt)
            finally:
                detach_session_baggage(token)

        # Launch A2A server for specialist agents
        blueprint = self.load_agent(agent_id)
        if (
            blueprint.multi_agent is not None
            and blueprint.multi_agent.role == "specialist"
            and blueprint.runtime.a2a_port
        ):
            from agent_core.a2a.server import A2AServerWrapper

            a2a_server = A2AServerWrapper.from_blueprint(
                agent=session.agent, blueprint=blueprint
            )
            a2a_app = a2a_server.to_starlette_app()
            app.mount_a2a(a2a_app, a2a_server.port)
            logger.info(
                "Mounted A2A server for specialist '%s' on port %d",
                agent_id,
                a2a_server.port,
            )

        return app

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
        evaluation_wiring: Any = None,
        policy_wiring: Any = None,
    ) -> AgentSession:
        """Build a multi-node Swarm or Graph session from node configs.

        Each node references a separate blueprint. All MCP clients are
        collected into the AgentSession for proper lifecycle cleanup.
        """
        all_mcp_clients = list(primary_mcp_clients)
        node_agents: dict[str, Any] = {}

        remote_tools: list[Any] = []

        for node_cfg in ma.nodes:
            # Remote nodes: create @tool wrappers instead of loading blueprints
            if self._is_remote_node(node_cfg):
                tool_fn = self._build_remote_node_tool(node_cfg)
                remote_tools.append(tool_fn)
                logger.info("Built remote node tool 'call_%s'", node_cfg.node_id)
                continue

            # In-process nodes: load blueprint and build agent
            node_bp = self.load_agent(node_cfg.agent_ref)

            if not validate_agent_mode(node_bp.execution_modes, current_mode):
                raise BlueprintLoadError(
                    f"Node agent '{node_cfg.agent_ref}' is not enabled for "
                    f"mode '{current_mode.value}'."
                )

            node_mcp_clients = self._create_tool_providers(node_bp)
            all_mcp_clients.extend(node_mcp_clients)

            node_kwargs, _ = self._build_agent_kwargs(node_bp, node_mcp_clients)
            node_agent = Agent(**node_kwargs)
            node_agents[node_cfg.node_id] = node_agent
            logger.info(
                "Built node agent '%s' (blueprint=%s)",
                node_cfg.node_id,
                node_cfg.agent_ref,
            )

        # Inject remote tools into the primary agent if any
        if remote_tools:
            existing = (
                list(primary_agent.tool_registry.get_all_tools_config().keys())
                if hasattr(primary_agent, "tool_registry")
                else []
            )
            logger.info(
                "Injecting %d remote agent tools into coordinator (existing tools: %d)",
                len(remote_tools),
                len(existing),
            )

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
            logger.info(
                "Built multi-node Swarm '%s' (%d nodes)", primary_id, len(agent_list)
            )
            return AgentSession(
                agent=primary_agent,
                mcp_clients=all_mcp_clients,
                multi_agent=swarm,
                pattern="swarm",
                evaluation_wiring=evaluation_wiring,
                policy_wiring=policy_wiring,
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
            logger.info(
                "Built multi-node Graph '%s' (%d nodes, %d edges)",
                primary_id,
                len(node_agents),
                len(ma.edges),
            )
            return AgentSession(
                agent=primary_agent,
                mcp_clients=all_mcp_clients,
                multi_agent=graph,
                pattern="graph",
                evaluation_wiring=evaluation_wiring,
                policy_wiring=policy_wiring,
            )

        raise BlueprintLoadError(f"Unknown multi-agent pattern: {ma.pattern}")

    @staticmethod
    def _is_remote_node(node_cfg: Any) -> bool:
        """Check if a node config specifies a remote agent."""
        return bool(
            node_cfg.a2a_url
            or node_cfg.a2a_url_env
            or node_cfg.runtime_arn
            or node_cfg.runtime_arn_env
        )

    def _build_remote_node_tool(self, node_cfg: Any) -> Any:
        """Build a @tool function for a remote agent node."""
        from agent_core.a2a.tools import remote_agent_tool
        from agent_core.a2a.client import A2AClient

        a2a_url = (
            node_cfg.a2a_url or os.environ.get(node_cfg.a2a_url_env, "")
            if node_cfg.a2a_url_env
            else node_cfg.a2a_url
        )
        runtime_arn = (
            node_cfg.runtime_arn or os.environ.get(node_cfg.runtime_arn_env, "")
            if node_cfg.runtime_arn_env
            else node_cfg.runtime_arn
        )

        if not hasattr(self, "_a2a_client") or self._a2a_client is None:
            self._a2a_client = A2AClient()

        return remote_agent_tool(
            node_id=node_cfg.node_id,
            name=f"call_{node_cfg.node_id}",
            description=f"Call the {node_cfg.node_id} agent",
            a2a_client=self._a2a_client,
            a2a_url=a2a_url,
            runtime_arn=runtime_arn,
        )
