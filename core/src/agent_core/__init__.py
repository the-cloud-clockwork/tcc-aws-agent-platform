"""Agent Core -- Blueprint Engine, Execution Modes, Hooks, Schemas, Observability, Runtime."""
from __future__ import annotations

__version__ = "0.7.0"

# -- Public API re-exports --
from agent_core.blueprints.agent import AgentBlueprint, GraphEdgeConfig, GraphNodeConfig
from agent_core.blueprints.loader import BlueprintLoader, BlueprintLoadError
from agent_core.blueprints.session import AgentSession
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.blueprints.workflow_executor import WorkflowExecutor
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.hooks.observability import ObservabilityHook
from agent_core.hooks.observability_hooks import (
    CompositeObservabilityHook,
    create_observability_hooks,
)
from agent_core.observability import (
    AlertPublisher,
    AuditLogWriter,
    CostTracker,
    LangfuseHook,
    LogSchema,
    StructuredLogger,
    XRayTracer,
)
from agent_core.prompt.client import PromptRegistryClient, PromptResolutionError
from agent_core.runtime.adapter import AgentPayload, AgentResult, InvocationContext, normalize_payload
from agent_core.runtime.agent_config import AgentConfig, AgentConfigRegistry
from agent_core.runtime.config_gen import generate_agentcore_config, generate_dockerfile
from agent_core.runtime.entrypoint import AgentCoreApp
from agent_core.runtime.handler import GenericHandler
from agent_core.runtime.idempotency import IdempotencyStore, generate_idempotency_key
from agent_core.runtime.marshal import marshal_output
from agent_core.runtime.session import SessionManager, SessionState
from agent_core.runtime.strands_session_bridge import StrandsSessionBridge
from agent_core.tools.mcp_factory import create_mcp_client

from agent_core.gateway import GatewayClient, ToolDiscovery

from agent_core.mcp import BaseMCPServer, VersionedS3Store, cache_get, cache_set, resolve_provider
__all__ = [
    "AgentBlueprint",
    "AgentConfig",
    "AgentConfigRegistry",
    "AgentCoreApp",
    "AgentPayload",
    "AgentResult",
    "AgentSession",
    "AlertPublisher",
    "AuditLogWriter",
    "BlueprintLoadError",
    "BlueprintLoader",
    "CompositeObservabilityHook",
    "CostTracker",
    "ExecutionMode",
    "GenericHandler",
    "GraphEdgeConfig",
    "GraphNodeConfig",
    "IdempotencyStore",
    "InvocationContext",
    "LangfuseHook",
    "LogSchema",
    "ObservabilityHook",
    "PromptRegistryClient",
    "PromptResolutionError",
    "SessionManager",
    "SessionState",
    "StrandsSessionBridge",
    "StructuredLogger",
    "WorkflowBlueprint",
    "WorkflowExecutor",
    "XRayTracer",
    "GatewayClient",
    "ToolDiscovery",
    "create_mcp_client",
    "create_observability_hooks",
    "generate_agentcore_config",
    "generate_dockerfile",
    "generate_idempotency_key",
    "get_execution_mode",
    "marshal_output",
    "normalize_payload",
    "validate_agent_mode",
    "BaseMCPServer",
    "VersionedS3Store",
    "cache_get",
    "cache_set",
    "resolve_provider",
]
