"""Agent Core -- Blueprint Engine, Execution Modes, Hooks, Schemas, Observability."""
from __future__ import annotations

__version__ = "0.1.0"

# -- Public API re-exports --
from agent_core.blueprints.agent import AgentBlueprint
from agent_core.blueprints.loader import BlueprintLoader
from agent_core.blueprints.strategy import StrategyBlueprint
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.hooks.constraints import ConstraintHook
from agent_core.hooks.observability import ObservabilityHook
from agent_core.observability import (
    AlertPublisher,
    AuditLogWriter,
    CostTracker,
    LangfuseHook,
    LogSchema,
    StructuredLogger,
    XRayTracer,
)
from agent_core.prompt.client import PromptRegistryClient

__all__ = [
    "AgentBlueprint",
    "AlertPublisher",
    "AuditLogWriter",
    "BlueprintLoader",
    "CostTracker",
    "ExecutionMode",
    "LangfuseHook",
    "LogSchema",
    "ConstraintHook",
    "PromptRegistryClient",
    "ObservabilityHook",
    "StrategyBlueprint",
    "StructuredLogger",
    "WorkflowBlueprint",
    "XRayTracer",
    "get_execution_mode",
    "validate_agent_mode",
]

# Backward compatibility alias (deprecated)
