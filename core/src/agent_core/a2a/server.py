"""A2A server wrapper — blueprint-driven agent card generation.

Wraps ``strands.multiagent.a2a.A2AServer`` and injects agent metadata
(name, description, version, skills) from the AgentBlueprint. Exposes
a Starlette ASGI app on the configured A2A port.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from starlette.applications import Starlette

    from agent_core.blueprints.agent import AgentBlueprint

logger = logging.getLogger(__name__)


class A2AServerWrapper:
    """Blueprint-driven A2A server.

    Generates agent card from blueprint metadata and exposes the
    Strands A2AServer on a configurable port. Returns a Starlette
    ASGI app for composition with the main AgentCore Runtime app.
    """

    def __init__(
        self,
        agent: Any,
        blueprint: AgentBlueprint,
        *,
        host: str = "",
        port: int = 0,
        http_url: str = "",
    ) -> None:
        self._blueprint = blueprint
        resolved_host = host or os.environ.get("A2A_HOST", "0.0.0.0")
        resolved_port = (
            port or blueprint.runtime.a2a_port or int(os.environ.get("A2A_PORT", "0"))
        )
        if resolved_port == 0:
            msg = (
                "A2A port not configured. Set runtime.a2a_port in blueprint "
                "or A2A_PORT environment variable."
            )
            raise ValueError(msg)
        resolved_http_url = (
            http_url
            or os.environ.get("A2A_HTTP_URL", "")
            or f"http://{resolved_host}:{resolved_port}/"
        )

        from strands.multiagent.a2a import A2AServer

        skills = self._build_skills()
        self._server = A2AServer(
            agent=agent,
            host=resolved_host,
            port=resolved_port,
            http_url=resolved_http_url,
            serve_at_root=True,
            version=blueprint.version,
            skills=skills,
        )
        self._host = resolved_host
        self._port = resolved_port
        logger.info(
            "A2AServerWrapper initialized for '%s' on %s:%d",
            blueprint.name,
            resolved_host,
            resolved_port,
        )

    @classmethod
    def from_blueprint(cls, agent: Any, blueprint: AgentBlueprint) -> A2AServerWrapper:
        """Create wrapper using only blueprint configuration."""
        return cls(agent=agent, blueprint=blueprint)

    def _build_skills(self) -> list[dict[str, Any]]:
        """Build skill entries from blueprint tool declarations.

        Each declared tool becomes a skill entry with id and name.
        """
        skills: list[dict[str, Any]] = []
        for tool_decl in self._blueprint.tools:
            mcp_name = getattr(tool_decl, "mcp", None) or ""
            tool_names = getattr(tool_decl, "tools", None) or []
            builtin = getattr(tool_decl, "builtin", None)
            if builtin:
                skills.append({"id": f"builtin_{builtin}", "name": str(builtin)})
            else:
                for tool_name in tool_names:
                    skill_id = f"{mcp_name}_{tool_name}" if mcp_name else tool_name
                    skills.append({"id": skill_id, "name": tool_name})
        return skills

    @property
    def agent_card(self) -> Any:
        """The generated A2A agent card."""
        return self._server.public_agent_card

    @property
    def port(self) -> int:
        """The resolved A2A port."""
        return self._port

    def to_starlette_app(self, **kwargs: Any) -> Starlette:
        """Return a Starlette ASGI application for the A2A server."""
        return self._server.to_starlette_app(**kwargs)

    def serve(self) -> None:
        """Run the A2A server (blocking). Prefer to_starlette_app() for composition."""
        self._server.serve(host=self._host, port=self._port)
