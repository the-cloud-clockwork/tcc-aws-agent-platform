"""Execution-mode-based provider routing for MCP servers.

Eliminates the duplicated ``get_provider()`` pattern in domain MCPs.
Each MCP declares a registry dict mapping ExecutionMode → provider class,
then calls ``resolve_provider()`` to instantiate the correct one.

Usage::

    from agent_core.mcp.provider_routing import resolve_provider
    from agent_core.execution.mode import ExecutionMode

    PROVIDERS = {
        ExecutionMode.SIMULATION: S3ParquetProvider,
        ExecutionMode.STAGING: PolygonProvider,
        ExecutionMode.PRODUCTION: PolygonProvider,
    }
    provider = resolve_provider(PROVIDERS)
"""

from __future__ import annotations

from agent_core.execution.mode import ExecutionMode, get_execution_mode


def resolve_provider[T](
    registry: dict[ExecutionMode, type[T]],
    *,
    aliases: dict[str, str] | None = None,
) -> T:
    """Read EXECUTION_MODE, resolve to provider class, instantiate.

    Args:
        registry: Mapping of ExecutionMode → provider class.
        aliases: Optional mode aliases forwarded to ``get_execution_mode()``.

    Returns:
        An instance of the resolved provider class.

    Raises:
        ValueError: If no provider is registered for the current mode.
    """
    mode = get_execution_mode(aliases=aliases)
    cls = registry.get(mode)
    if cls is None:
        available = [m.value for m in registry]
        raise ValueError(
            f"No provider registered for mode {mode.value!r}. "
            f"Available modes: {available}"
        )
    return cls()
