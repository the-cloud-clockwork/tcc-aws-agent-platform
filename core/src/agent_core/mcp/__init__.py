"""MCP server infrastructure utilities.

Domain MCP servers may import from this subpackage for shared
infrastructure: base server class, caching, provider routing,
and versioned S3 artifact storage.

This subpackage is domain-agnostic — no domain-specific imports allowed.
"""

from agent_core.mcp.base_server import BaseMCPServer
from agent_core.mcp.cache import cache_get, cache_set
from agent_core.mcp.provider_routing import resolve_provider
from agent_core.mcp.observability import MCPObservabilityHook
from agent_core.mcp.versioned_store import VersionedS3Store

__all__ = [
    "BaseMCPServer",
    "VersionedS3Store",
    "cache_get",
    "cache_set",
    "MCPObservabilityHook",
    "resolve_provider",
]
