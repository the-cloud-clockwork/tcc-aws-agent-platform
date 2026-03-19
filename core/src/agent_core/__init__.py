"""Agent Core -- Blueprint Engine, Execution Modes, Hooks, Schemas, Observability, Runtime."""
from __future__ import annotations

__version__ = "0.6.0"

# -- Public API re-exports --
from agent_core.blueprints.agent import AgentBlueprint
from agent_core.blueprints.loader import BlueprintLoadError, BlueprintLoader
from agent_core.blueprints.session import AgentSession
from agent_core.blueprints.strategy import StrategyBlueprint
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.hooks.constraints import ConstraintHook
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
from agent_core.runtime.adapter import AgentPayload, AgentResult, RuntimeMode, normalize_payload
from agent_core.runtime.agent_config import AgentConfig, AgentConfigRegistry
from agent_core.runtime.handler import GenericHandler
from agent_core.runtime.idempotency import IdempotencyStore, generate_idempotency_key
from agent_core.runtime.marshal import marshal_output
from agent_core.runtime.session import SessionManager, SessionState

__all__ = [
    "AgentBlueprint",
    "AgentConfig",
    "AgentConfigRegistry",
    "AgentPayload",
    "AgentResult",
    "AgentSession",
    "AlertPublisher",
    "AuditLogWriter",
    "BlueprintLoadError",
    "BlueprintLoader",
    "CompositeObservabilityHook",
    "ConstraintHook",
    "CostTracker",
    "ExecutionMode",
    "GenericHandler",
    "IdempotencyStore",
    "LangfuseHook",
    "LogSchema",
    "ObservabilityHook",
    "PromptRegistryClient",
    "PromptResolutionError",
    "RuntimeMode",
    "SessionManager",
    "SessionState",
    "StrategyBlueprint",
    "StructuredLogger",
    "WorkflowBlueprint",
    "XRayTracer",
    "create_observability_hooks",
    "generate_idempotency_key",
    "get_execution_mode",
    "marshal_output",
    "normalize_payload",
    "validate_agent_mode",
]

# Backward compatibility alias (deprecated)
