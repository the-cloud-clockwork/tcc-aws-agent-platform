"""A2A wiring — bridge blueprint config to A2A components.

Creates ``A2AServerWrapper`` for specialists and ``A2AClient`` + remote
tools for coordinators. Handles M2M credential injection.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Callable

from agent_core.a2a.client import A2AClient
from agent_core.a2a.server import A2AServerWrapper
from agent_core.a2a.tools import remote_agent_tool

if TYPE_CHECKING:
    from agent_core.blueprints.agent import AgentBlueprint

logger = logging.getLogger(__name__)


class A2AWiring:
    """Wire A2A communication from blueprint configuration.

    For specialist agents: builds an A2AServerWrapper.
    For coordinator agents: builds an A2AClient and generates
    ``@tool`` functions for each remote node.
    """

    def __init__(
        self,
        blueprint: AgentBlueprint,
        *,
        identity_wiring: Any | None = None,
    ) -> None:
        self._blueprint = blueprint
        self._identity_wiring = identity_wiring
        self._client: A2AClient | None = None

        role = blueprint.multi_agent.role if blueprint.multi_agent else "standalone"
        if role == "coordinator":
            auth_provider = self._build_auth_provider()
            self._client = A2AClient(auth_provider=auth_provider)
            logger.info("A2AWiring: coordinator mode — A2AClient created")
        elif role == "specialist":
            logger.info(
                "A2AWiring: specialist mode — A2AServer will be built on demand"
            )

    def build_server(self, agent: Any) -> A2AServerWrapper:
        """Build A2A server for a specialist agent."""
        return A2AServerWrapper.from_blueprint(agent=agent, blueprint=self._blueprint)

    def build_remote_tools(self) -> list[Any]:
        """Build ``@tool`` functions for remote agent nodes.

        Iterates ``multi_agent.nodes``, filters for those with
        ``a2a_url``/``runtime_arn`` fields, creates a remote tool for each.
        """
        if self._client is None:
            msg = "build_remote_tools() requires coordinator role (A2AClient not initialized)"
            raise RuntimeError(msg)

        ma = self._blueprint.multi_agent
        if ma is None:
            return []

        tools: list[Any] = []
        for node in ma.nodes:
            url = (
                node.a2a_url or os.environ.get(node.a2a_url_env, "")
                if node.a2a_url_env
                else node.a2a_url
            )
            arn = (
                node.runtime_arn or os.environ.get(node.runtime_arn_env, "")
                if node.runtime_arn_env
                else node.runtime_arn
            )
            if not url and not arn:
                continue
            tool_fn = remote_agent_tool(
                node_id=node.node_id,
                name=f"call_{node.node_id}",
                description=f"Call the {node.node_id} agent",
                a2a_client=self._client,
                a2a_url=url,
                runtime_arn=arn,
            )
            tools.append(tool_fn)
            logger.info(
                "Created remote tool 'call_%s' (a2a=%s, direct=%s)",
                node.node_id,
                bool(url),
                bool(arn),
            )
        return tools

    def _build_auth_provider(self) -> Callable[[], str] | None:
        """Create M2M token provider from identity credentials.

        Looks for a credential with ``auth_flow=M2M`` in the blueprint
        and creates a callable that returns fresh bearer tokens.
        """
        if self._identity_wiring is None:
            logger.debug("No identity wiring — A2A calls will be unauthenticated")
            return None

        for cred in self._blueprint.identity.credentials:
            auth_flow = getattr(cred, "auth_flow", None)
            if auth_flow is not None and auth_flow.value == "M2M":
                logger.info("Using M2M credential '%s' for A2A auth", cred.name)
                return self._identity_wiring.get_token_provider(cred.name)

        logger.debug("No M2M credential found — A2A calls will be unauthenticated")
        return None

    @property
    def client(self) -> A2AClient | None:
        """The A2AClient instance (coordinator role only)."""
        return self._client

    def close(self) -> None:
        """Release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None
