"""Agent Core -- Blueprint Engine, Execution Modes, Hooks, Schemas, Observability."""
from __future__ import annotations

__version__ = "0.4.0"

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

__all__ = [
    "AgentBlueprint",
    "AgentSession",
    "AlertPublisher",
    "AuditLogWriter",
    "BlueprintLoadError",
    "BlueprintLoader",
    "CompositeObservabilityHook",
    "ConstraintHook",
    "CostTracker",
    "ExecutionMode",
    "LangfuseHook",
    "LogSchema",
    "ObservabilityHook",
    "PromptRegistryClient",
    "PromptResolutionError",
    "StrategyBlueprint",
    "StructuredLogger",
    "WorkflowBlueprint",
    "XRayTracer",
    "create_observability_hooks",
    "get_execution_mode",
    "validate_agent_mode",
]

# Backward compatibility alias (deprecated)
