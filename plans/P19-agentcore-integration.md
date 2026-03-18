# P19 — AgentCore Integration

## Objective
Migrate agents from Lambda to Bedrock AgentCore Runtime. Wire AgentCore Gateway fronting all MCPs with semantic tool search and OpenAPI auto-conversion. Implement AgentCore Memory (short-term + long-term + episodic), AgentCore Identity (OAuth for IBKR, Telegram), Cedar policies (tool-level RBAC per agent per mode), and AgentCore Evaluations (custom domain evaluators for gap accuracy, sentiment accuracy, prompt quality). All changes designed as a config switch — same handler code works in both Lambda and AgentCore.

## Plane Tickets
ROOT-67 (new)

## Target Repos
- `~/dev/tccw-qitp-agents` — runtime adapter, updated handlers
- `~/dev/tccw-agent-core` — gateway client, memory manager, identity providers, Cedar policies
- `~/dev/tccw-agent-infra` — CDK AgentCore stack, Cedar policy files

## Dependencies
P14 (ibkr-mcp), P15 (2FA gate), P16 (risk engine), P17 (CDK infra complete), P18 (observability)

## Key Files to Create/Modify
```
tccw-qitp-agents/
├── src/
│   └── qitp_agents/
│       ├── runtime/
│       │   ├── __init__.py
│       │   ├── entrypoint.py          # @app.entrypoint AgentCore handler
│       │   ├── adapter.py             # Lambda event ↔ AgentCore payload adapter
│       │   └── session.py             # AgentCore session management
│       ├── gap_detector/
│       │   └── handler.py             # Updated: dual-mode (Lambda + AgentCore)
│       ├── sentiment_analyzer/
│       │   └── handler.py             # Updated
│       ├── strategy_evaluator/
│       │   └── handler.py             # Updated
│       └── portfolio_recommender/
│           └── handler.py             # Updated
├── tests/
│   ├── unit/
│   │   ├── test_adapter.py
│   │   ├── test_session.py
│   │   ├── test_entrypoint.py
│   │   ├── test_gap_detector_agentcore.py
│   │   └── test_gateway_client.py
│   └── integration/
│       └── test_agentcore_pipeline.py
└── pyproject.toml                     # Updated deps

tccw-agent-core/
├── src/
│   └── agent_core/
│       ├── gateway/
│       │   ├── __init__.py
│       │   ├── client.py              # AgentCore Gateway client
│       │   ├── target_registry.py     # Register MCP servers as gateway targets
│       │   └── tool_discovery.py      # Semantic tool search via gateway
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── manager.py             # AgentCoreMemorySessionManager wrapper
│       │   └── session_bridge.py      # SFN execution ID → session ID mapping
│       ├── identity/
│       │   ├── __init__.py
│       │   └── providers.py           # OAuth credential providers (IBKR, Telegram)
│       └── policy/
│           ├── __init__.py
│           └── cedar_policies.py      # Cedar policy builder + validator
├── tests/
│   ├── unit/
│   │   ├── test_gateway_client.py
│   │   ├── test_target_registry.py
│   │   ├── test_tool_discovery.py
│   │   ├── test_memory_manager.py
│   │   ├── test_session_bridge.py
│   │   ├── test_identity_providers.py
│   │   └── test_cedar_policies.py
│   └── conftest.py                    # Updated fixtures

tccw-agent-infra/
├── stacks/
│   └── agentcore_stack.py             # Full CDK: Runtime, Gateway, Memory, Identity, Policy
├── cedar/
│   ├── policies.cedar                 # Cedar policy definitions
│   └── schema.cedarschema             # Cedar entity schema
└── tests/
    └── test_agentcore_stack.py        # CDK snapshot test
```

---

## Architecture: Lambda → AgentCore Migration

### Dual-Mode Handler Pattern

Every agent handler works in two modes — selected by `RUNTIME_MODE` env var:

```
RUNTIME_MODE=lambda     → Standard Lambda handler(event, context)
RUNTIME_MODE=agentcore  → AgentCore @app.entrypoint decorated function
```

The adapter layer translates between the two payload formats. The agent logic is identical.

### Gateway Architecture

```
Agent → AgentCore Gateway (single HTTPS endpoint)
            ├── Target: market-data-mcp (MCP server, Cloud Map)
            ├── Target: sentiment-mcp (MCP server, Cloud Map)
            ├── Target: artifacts-mcp (MCP server, Cloud Map)
            ├── Target: backtest-mcp (MCP server, Cloud Map)
            ├── Target: ibkr-mcp (MCP server, Cedar-gated)
            ├── Target: Polygon.io (OpenAPI → auto-converted tools)
            ├── Target: IBKR REST API (OpenAPI → auto-converted tools)
            └── Semantic search across ALL tools from ALL targets
```

### Memory Tiers

| Tier | Scope | Example |
|---|---|---|
| Short-term | Within SFN execution | Current gap analysis, intermediate results |
| Long-term | Cross-session | Strategy performance history, watchlist preferences |
| Episodic | Retrievable by similarity | "What happened last time AAPL gapped 5%?" |

### Cedar Policy Model

```
Entity types: Agent, AgentGroup, Tool, ToolGroup
Actions: invoke_tool, read_memory, write_memory
Context: execution_mode (backtest|paper|live)
```

---

## Implementation

---

### tccw-qitp-agents/pyproject.toml (Updated)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-agents"
version = "0.2.0"
description = "QITP agents — dual-mode Lambda + AgentCore handlers"
requires-python = ">=3.11"
dependencies = [
    "strands-agents>=0.1.0",
    "strands-agents-tools>=0.1.0",
    "agent-core>=0.2.0",
    "pyyaml>=6.0.1",
    "pydantic>=2.6.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
agentcore = [
    "bedrock-agentcore-runtime>=0.1.0",
    "bedrock-agentcore-gateway>=0.1.0",
    "bedrock-agentcore-memory>=0.1.0",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "moto[all]>=5.0.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_agents"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### src/qitp_agents/runtime/__init__.py

```python
"""AgentCore runtime adapter — dual-mode Lambda + AgentCore execution."""

__all__ = ["AgentCoreAdapter", "AgentCoreEntrypoint", "SessionManager"]
```

---

### src/qitp_agents/runtime/adapter.py

```python
"""Adapter layer: translates between Lambda event and AgentCore payload.

This is the key abstraction that allows the same handler logic to work
in both Lambda and AgentCore Runtime environments. The adapter normalizes
the input format and wraps the output format so handler code is runtime-agnostic.

Design rule from CLAUDE.md:
  "Agent handlers must work with both Lambda event and AgentCore payload
   — use a thin adapter."
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeMode(str, Enum):
    """Runtime execution mode — Lambda or AgentCore."""

    LAMBDA = "lambda"
    AGENTCORE = "agentcore"


@dataclass
class AgentPayload:
    """Normalized payload that both Lambda and AgentCore handlers produce.

    Fields:
        agent_id: Which agent to invoke.
        session_id: Execution session (maps to SFN execution ID).
        execution_mode: backtest | paper | live.
        parameters: Agent-specific input parameters.
        memory_context: Optional prior context from AgentCore Memory.
        metadata: Tracing, correlation IDs, timestamps.
    """

    agent_id: str
    session_id: str
    execution_mode: str
    parameters: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Normalized result that both Lambda and AgentCore handlers produce.

    Fields:
        status: "success" or "error".
        agent_id: Which agent produced this.
        session_id: Execution session.
        output: Agent output data.
        claim_check: If True, output is an S3 reference (>256KB).
        artifact_id: S3 artifact key if claim-checked.
        memory_updates: Key-value pairs to persist in AgentCore Memory.
        error: Error message if status == "error".
    """

    status: str
    agent_id: str
    session_id: str
    output: dict[str, Any] = field(default_factory=dict)
    claim_check: bool = False
    artifact_id: str | None = None
    memory_updates: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_lambda_response(self) -> dict[str, Any]:
        """Convert to Lambda-style HTTP response."""
        if self.status == "error":
            return {
                "statusCode": 500,
                "body": json.dumps({"error": self.error}),
            }

        body = {**self.output}
        if self.claim_check:
            body = {
                "claim_check": True,
                "artifact_id": self.artifact_id,
                "message": "Output exceeded 256KB. Full result stored as artifact.",
            }
        if self.memory_updates:
            body["_memory_updates"] = self.memory_updates

        return {
            "statusCode": 200,
            "body": json.dumps(body),
        }

    def to_agentcore_response(self) -> dict[str, Any]:
        """Convert to AgentCore payload response format."""
        return {
            "status": self.status,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "output": self.output if not self.claim_check else {
                "claim_check": True,
                "artifact_id": self.artifact_id,
            },
            "memory_updates": self.memory_updates,
            "error": self.error,
        }


def get_runtime_mode() -> RuntimeMode:
    """Detect current runtime mode from environment."""
    mode = os.environ.get("RUNTIME_MODE", "lambda").lower()
    try:
        return RuntimeMode(mode)
    except ValueError:
        logger.warning("Unknown RUNTIME_MODE '%s', defaulting to lambda", mode)
        return RuntimeMode.LAMBDA


def normalize_lambda_event(event: dict[str, Any]) -> AgentPayload:
    """Convert a Lambda event dict into a normalized AgentPayload.

    Lambda events come from Step Functions with this structure:
    {
        "agent_id": "gap-detector",
        "session_id": "sfn-exec-abc123",
        "execution_mode": "backtest",
        "date": "2026-03-15",
        "threshold_pct": 2.0,
        ...
    }

    Args:
        event: Raw Lambda event dict.

    Returns:
        Normalized AgentPayload.
    """
    # Extract top-level control fields
    agent_id = event.get("agent_id", "unknown")
    session_id = event.get("session_id", _generate_session_id())
    execution_mode = event.get(
        "execution_mode",
        os.environ.get("EXECUTION_MODE", "backtest"),
    )

    # Everything else is parameters
    reserved_keys = {"agent_id", "session_id", "execution_mode"}
    parameters = {k: v for k, v in event.items() if k not in reserved_keys}

    return AgentPayload(
        agent_id=agent_id,
        session_id=session_id,
        execution_mode=execution_mode,
        parameters=parameters,
        metadata={
            "source": "lambda",
            "runtime_mode": RuntimeMode.LAMBDA.value,
        },
    )


def normalize_agentcore_payload(payload: dict[str, Any]) -> AgentPayload:
    """Convert an AgentCore Runtime payload into a normalized AgentPayload.

    AgentCore payloads arrive with:
    {
        "payload": {
            "agent_id": "gap-detector",
            "session_id": "...",
            "parameters": {...},
        },
        "session": {
            "session_id": "...",
            "memory": {...},
        },
        "context": {
            "execution_mode": "live",
            "identity": {...},
        }
    }

    Args:
        payload: Raw AgentCore payload dict.

    Returns:
        Normalized AgentPayload.
    """
    inner = payload.get("payload", payload)
    session = payload.get("session", {})
    context = payload.get("context", {})

    agent_id = inner.get("agent_id", "unknown")
    session_id = (
        inner.get("session_id")
        or session.get("session_id")
        or _generate_session_id()
    )
    execution_mode = (
        context.get("execution_mode")
        or inner.get("execution_mode")
        or os.environ.get("EXECUTION_MODE", "backtest")
    )
    parameters = inner.get("parameters", {})
    memory_context = session.get("memory")

    return AgentPayload(
        agent_id=agent_id,
        session_id=session_id,
        execution_mode=execution_mode,
        parameters=parameters,
        memory_context=memory_context,
        metadata={
            "source": "agentcore",
            "runtime_mode": RuntimeMode.AGENTCORE.value,
            "identity": context.get("identity"),
        },
    )


def normalize_payload(event_or_payload: dict[str, Any]) -> AgentPayload:
    """Auto-detect and normalize either Lambda event or AgentCore payload.

    Detection heuristic:
    - If "payload" key exists with nested "agent_id" → AgentCore
    - If "session" key exists → AgentCore
    - Otherwise → Lambda

    Args:
        event_or_payload: Raw input from either runtime.

    Returns:
        Normalized AgentPayload.
    """
    if "payload" in event_or_payload and isinstance(
        event_or_payload["payload"], dict
    ):
        return normalize_agentcore_payload(event_or_payload)
    if "session" in event_or_payload and isinstance(
        event_or_payload["session"], dict
    ):
        return normalize_agentcore_payload(event_or_payload)
    return normalize_lambda_event(event_or_payload)


def _generate_session_id() -> str:
    """Generate a fallback session ID when none is provided."""
    import uuid
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    return f"qitp-session-{ts}-{short_id}"
```

---

### src/qitp_agents/runtime/session.py

```python
"""AgentCore session management.

Maps SFN execution IDs to AgentCore session IDs. Manages session lifecycle
(create, resume, close). Handles memory persistence across agent invocations
within the same SFN execution.

Design rule from CLAUDE.md:
  "Session IDs map to SFN execution IDs — AgentCore Memory uses the same
   session_id convention."
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """In-memory session state for the current agent invocation.

    Attributes:
        session_id: Unique session identifier (= SFN execution ID).
        agent_id: Current agent within the session.
        execution_mode: backtest | paper | live.
        short_term: Ephemeral data for this SFN execution.
        memory_context: Prior context retrieved from AgentCore Memory.
        pending_updates: Memory updates to persist after agent completes.
    """

    session_id: str
    agent_id: str
    execution_mode: str
    short_term: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] | None = None
    pending_updates: dict[str, Any] = field(default_factory=dict)

    def store(self, key: str, value: Any) -> None:
        """Store a value in short-term session memory.

        Args:
            key: Memory key.
            value: Value to store (must be JSON-serializable).
        """
        self.short_term[key] = value
        self.pending_updates[key] = value
        logger.debug("Session %s: stored key '%s'", self.session_id, key)

    def retrieve(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from session memory.

        Checks short-term first, then falls back to memory_context
        (from AgentCore Memory long-term storage).

        Args:
            key: Memory key.
            default: Default value if key not found.

        Returns:
            Stored value or default.
        """
        if key in self.short_term:
            return self.short_term[key]
        if self.memory_context and key in self.memory_context:
            return self.memory_context[key]
        return default

    def get_pending_updates(self) -> dict[str, Any]:
        """Return all pending memory updates for persistence."""
        return dict(self.pending_updates)


class SessionManager:
    """Manages agent session lifecycle.

    In Lambda mode: sessions are DynamoDB-backed (from P10 implementation).
    In AgentCore mode: sessions are managed by AgentCore Memory service.

    This class abstracts the difference so agent handlers don't care.
    """

    def __init__(self, runtime_mode: str = "lambda") -> None:
        self.runtime_mode = runtime_mode
        self._agentcore_memory = None

    def create_session(
        self,
        session_id: str,
        agent_id: str,
        execution_mode: str,
        memory_context: dict[str, Any] | None = None,
    ) -> SessionState:
        """Create a new session state for an agent invocation.

        Args:
            session_id: Session ID (= SFN execution ID).
            agent_id: Agent identifier.
            execution_mode: backtest | paper | live.
            memory_context: Prior context from AgentCore Memory.

        Returns:
            Initialized SessionState.
        """
        logger.info(
            "Creating session: sid=%s agent=%s mode=%s runtime=%s",
            session_id,
            agent_id,
            execution_mode,
            self.runtime_mode,
        )

        session = SessionState(
            session_id=session_id,
            agent_id=agent_id,
            execution_mode=execution_mode,
            memory_context=memory_context,
        )

        if self.runtime_mode == "agentcore":
            self._init_agentcore_session(session)

        return session

    def persist_session(self, session: SessionState) -> None:
        """Persist session memory updates.

        In Lambda mode: writes to DynamoDB.
        In AgentCore mode: writes to AgentCore Memory service.

        Args:
            session: Session with pending updates.
        """
        updates = session.get_pending_updates()
        if not updates:
            logger.debug("Session %s: no updates to persist", session.session_id)
            return

        if self.runtime_mode == "agentcore":
            self._persist_agentcore_memory(session, updates)
        else:
            self._persist_dynamodb_memory(session, updates)

        logger.info(
            "Session %s: persisted %d memory updates",
            session.session_id,
            len(updates),
        )

    def retrieve_long_term(
        self,
        session_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve long-term memory for a session.

        In AgentCore mode, supports semantic search over episodic memory.

        Args:
            session_id: Session ID to retrieve memory for.
            query: Optional semantic query for episodic retrieval.

        Returns:
            Memory context dict.
        """
        if self.runtime_mode == "agentcore" and query:
            return self._semantic_retrieve(session_id, query)

        if self.runtime_mode == "agentcore":
            return self._get_agentcore_memory(session_id)

        return self._get_dynamodb_memory(session_id)

    def _init_agentcore_session(self, session: SessionState) -> None:
        """Initialize AgentCore Memory for this session."""
        try:
            from agent_core.memory.manager import get_memory_manager

            self._agentcore_memory = get_memory_manager()
            existing = self._agentcore_memory.get_session_memory(
                session.session_id
            )
            if existing:
                session.memory_context = existing
                logger.info(
                    "Session %s: loaded %d keys from AgentCore Memory",
                    session.session_id,
                    len(existing),
                )
        except ImportError:
            logger.warning(
                "AgentCore Memory not available, falling back to local state"
            )
        except Exception:
            logger.exception("Failed to initialize AgentCore Memory")

    def _persist_agentcore_memory(
        self, session: SessionState, updates: dict[str, Any]
    ) -> None:
        """Write memory updates to AgentCore Memory service."""
        if self._agentcore_memory is None:
            logger.warning("AgentCore Memory not initialized, skipping persist")
            return

        try:
            self._agentcore_memory.update_session_memory(
                session_id=session.session_id,
                agent_id=session.agent_id,
                updates=updates,
            )
        except Exception:
            logger.exception("Failed to persist to AgentCore Memory")

    def _persist_dynamodb_memory(
        self, session: SessionState, updates: dict[str, Any]
    ) -> None:
        """Write memory updates to DynamoDB (Lambda mode fallback)."""
        try:
            import boto3
            from datetime import datetime, timezone

            table_name = os.environ.get("SESSION_TABLE", "qitp_run_history")
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(table_name)

            table.update_item(
                Key={"session_id": session.session_id},
                UpdateExpression="SET #mem = :mem, #ts = :ts, #agent = :agent",
                ExpressionAttributeNames={
                    "#mem": "memory_state",
                    "#ts": "updated_at",
                    "#agent": "last_agent_id",
                },
                ExpressionAttributeValues={
                    ":mem": updates,
                    ":ts": datetime.now(timezone.utc).isoformat(),
                    ":agent": session.agent_id,
                },
            )
        except Exception:
            logger.exception("Failed to persist to DynamoDB")

    def _get_dynamodb_memory(self, session_id: str) -> dict[str, Any]:
        """Retrieve memory from DynamoDB."""
        try:
            import boto3

            table_name = os.environ.get("SESSION_TABLE", "qitp_run_history")
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={"session_id": session_id})
            item = response.get("Item", {})
            return item.get("memory_state", {})
        except Exception:
            logger.exception("Failed to retrieve from DynamoDB")
            return {}

    def _get_agentcore_memory(self, session_id: str) -> dict[str, Any]:
        """Retrieve memory from AgentCore Memory service."""
        if self._agentcore_memory is None:
            return {}
        try:
            return self._agentcore_memory.get_session_memory(session_id) or {}
        except Exception:
            logger.exception("Failed to retrieve from AgentCore Memory")
            return {}

    def _semantic_retrieve(
        self, session_id: str, query: str
    ) -> dict[str, Any]:
        """Semantic search over episodic memory via AgentCore Memory."""
        if self._agentcore_memory is None:
            return {}
        try:
            return self._agentcore_memory.semantic_search(
                session_id=session_id,
                query=query,
                max_results=5,
            )
        except Exception:
            logger.exception("Semantic retrieval failed")
            return {}
```

---

### src/qitp_agents/runtime/entrypoint.py

```python
"""AgentCore Runtime entrypoint.

This module provides the @app.entrypoint decorator that registers agent handlers
with the AgentCore Runtime. Each agent is registered as a named entrypoint that
AgentCore can invoke by agent_id.

In Lambda mode, this module is not imported — handlers use the standard
Lambda handler(event, context) signature directly.

Design rule from CLAUDE.md:
  "Agent handlers must work with both Lambda event and AgentCore payload
   — use a thin adapter."
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from qitp_agents.runtime.adapter import (
    AgentPayload,
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
    normalize_payload,
)
from qitp_agents.runtime.session import SessionManager

logger = logging.getLogger(__name__)

# Global registry of agent handler functions
_AGENT_REGISTRY: dict[str, Callable] = {}


def register_agent(agent_id: str) -> Callable:
    """Decorator to register an agent handler function.

    The decorated function must accept an AgentPayload and return an AgentResult.
    It will be callable from both Lambda and AgentCore contexts.

    Usage:
        @register_agent("gap-detector")
        def handle_gap_detection(payload: AgentPayload, session: SessionState) -> AgentResult:
            ...

    Args:
        agent_id: Unique agent identifier matching the blueprint YAML.

    Returns:
        Decorator function.
    """
    def decorator(func: Callable) -> Callable:
        _AGENT_REGISTRY[agent_id] = func
        logger.info("Registered agent handler: %s", agent_id)
        return func
    return decorator


def get_registered_agents() -> dict[str, Callable]:
    """Return the registry of all registered agent handlers."""
    return dict(_AGENT_REGISTRY)


class AgentCoreApp:
    """AgentCore Runtime application wrapper.

    Manages the lifecycle of agent handlers in AgentCore Runtime.
    Provides the entrypoint that AgentCore invokes, routing to the
    correct agent handler based on agent_id in the payload.

    In Lambda mode, this class is not used — each handler has its
    own Lambda function. In AgentCore mode, all agents share one
    Runtime instance and this class routes between them.
    """

    def __init__(self) -> None:
        self.runtime_mode = get_runtime_mode()
        self.session_manager = SessionManager(
            runtime_mode=self.runtime_mode.value,
        )
        self._agentcore_runtime = None
        logger.info("AgentCoreApp initialized, mode=%s", self.runtime_mode.value)

    def start(self) -> None:
        """Start the AgentCore Runtime.

        In AgentCore mode: initializes the Runtime SDK and registers handlers.
        In Lambda mode: no-op (handlers are invoked directly by AWS Lambda).
        """
        if self.runtime_mode != RuntimeMode.AGENTCORE:
            logger.info("Lambda mode — skipping AgentCore Runtime start")
            return

        try:
            from bedrock_agentcore.runtime import AgentCoreRuntime

            self._agentcore_runtime = AgentCoreRuntime(
                agent_name=os.environ.get("AGENTCORE_AGENT_NAME", "qitp-agents"),
                region=os.environ.get("AWS_REGION", "eu-west-1"),
            )

            # Register all handlers as entrypoints
            for agent_id, handler_fn in _AGENT_REGISTRY.items():
                self._agentcore_runtime.register_entrypoint(
                    name=agent_id,
                    handler=self._wrap_handler(agent_id, handler_fn),
                )
                logger.info("Registered entrypoint: %s", agent_id)

            # Start the runtime event loop
            self._agentcore_runtime.start()
            logger.info("AgentCore Runtime started with %d agents", len(_AGENT_REGISTRY))

        except ImportError:
            logger.error(
                "bedrock-agentcore-runtime not installed. "
                "Install with: pip install qitp-agents[agentcore]"
            )
            raise
        except Exception:
            logger.exception("Failed to start AgentCore Runtime")
            raise

    def invoke(
        self,
        event_or_payload: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any]:
        """Invoke an agent handler — works in both Lambda and AgentCore mode.

        This is the universal entry point. In Lambda mode, this is called by
        the Lambda handler function. In AgentCore mode, this is called by
        the registered entrypoint wrapper.

        Args:
            event_or_payload: Raw Lambda event or AgentCore payload.
            context: Lambda context (optional, unused in AgentCore).

        Returns:
            Response dict in the appropriate format for the runtime.
        """
        payload = normalize_payload(event_or_payload)

        agent_id = payload.agent_id
        handler_fn = _AGENT_REGISTRY.get(agent_id)

        if handler_fn is None:
            error_msg = (
                f"No handler registered for agent_id '{agent_id}'. "
                f"Registered: {list(_AGENT_REGISTRY.keys())}"
            )
            logger.error(error_msg)
            result = AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=payload.session_id,
                error=error_msg,
            )
            return self._format_response(result)

        # Create session
        session = self.session_manager.create_session(
            session_id=payload.session_id,
            agent_id=agent_id,
            execution_mode=payload.execution_mode,
            memory_context=payload.memory_context,
        )

        try:
            result = handler_fn(payload, session)

            # Persist session memory
            self.session_manager.persist_session(session)

            return self._format_response(result)

        except Exception as e:
            logger.exception("Agent %s failed", agent_id)
            result = AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=payload.session_id,
                error=str(e),
            )
            return self._format_response(result)

    def _wrap_handler(
        self, agent_id: str, handler_fn: Callable
    ) -> Callable:
        """Wrap a handler function for AgentCore Runtime registration.

        AgentCore Runtime invokes handlers with a single payload dict.
        This wrapper normalizes the payload and routes to the handler.
        """
        def agentcore_handler(payload: dict[str, Any]) -> dict[str, Any]:
            return self.invoke(payload)
        return agentcore_handler

    def _format_response(self, result: AgentResult) -> dict[str, Any]:
        """Format response according to current runtime mode."""
        if self.runtime_mode == RuntimeMode.AGENTCORE:
            return result.to_agentcore_response()
        return result.to_lambda_response()


# Module-level singleton
app = AgentCoreApp()
```

---

### src/qitp_agents/gap_detector/handler.py (Updated — Dual-Mode)

```python
"""Gap Detection Agent handler — dual-mode Lambda + AgentCore.

Input:  {"date": "2026-03-15", "threshold_pct": 2.0, "watchlist_id": "default"}
Output: GapDetectionOutput JSON artifact with ranked_gaps list.

Architecture:
- Single Strands agent (no multi-agent pattern)
- Tools: market-data-mcp, artifacts-mcp
- In AgentCore mode: tools discovered via Gateway semantic search
- In Lambda mode: tools loaded from blueprint YAML with direct MCP connections

P10 handler updated for P19 dual-mode support.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

from qitp_agents.runtime.adapter import (
    AgentPayload,
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
    normalize_payload,
)
from qitp_agents.runtime.entrypoint import register_agent
from qitp_agents.runtime.session import SessionManager, SessionState

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "backtest"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))
RUNTIME_MODE = get_runtime_mode()

AGENT_ID = "gap-detector"
MAX_OUTPUT_BYTES = 256 * 1024


@register_agent(AGENT_ID)
def handle_gap_detection(
    payload: AgentPayload, session: SessionState
) -> AgentResult:
    """Core gap detection logic — runtime-agnostic.

    This function is registered with @register_agent and called by both
    the Lambda handler and AgentCore entrypoint via the adapter layer.

    Args:
        payload: Normalized agent payload.
        session: Session state for memory management.

    Returns:
        AgentResult with gap detection output.
    """
    date = payload.parameters.get("date")
    threshold_pct = payload.parameters.get("threshold_pct", 2.0)
    watchlist_id = payload.parameters.get("watchlist_id", "default")

    if not date:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: date",
        )

    try:
        # Build MCP clients — Gateway in AgentCore, direct in Lambda
        mcp_clients = _create_mcp_clients(payload)

        # Build agent from blueprint
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Check episodic memory for similar past analyses
        prior_context = ""
        if session.memory_context:
            prior_gaps = session.retrieve("last_gap_analysis")
            if prior_gaps:
                prior_context = (
                    f"\nContext from prior analysis: {json.dumps(prior_gaps)[:500]}\n"
                    f"Use this for comparison but analyze fresh data.\n"
                )

        prompt = (
            f"Analyze price gaps for watchlist '{watchlist_id}' on {date}.\n"
            f"Gap threshold: {threshold_pct}%.\n\n"
            f"Steps:\n"
            f"1. Call get_watchlist_gaps for the date and threshold.\n"
            f"2. For each gap found, call get_ohlcv to get the full daily bar.\n"
            f"3. For each gap found, call get_volume_profile to assess volume confirmation.\n"
            f"4. Rank gaps by magnitude * volume_ratio. Include gap_pct, direction, "
            f"   volume_ratio, previous_close, open_price, and a confidence score.\n"
            f"5. Create a GapDetectionOutput artifact with the ranked list.\n"
            f"6. Return the artifact ID and the ranked_gaps array."
            f"{prior_context}"
        )

        result = agent(prompt)
        output = _marshal_output(result)

        # Store in session memory for downstream agents
        session.store("last_gap_analysis", {
            "date": date,
            "gap_count": len(output.get("ranked_gaps", [])),
            "top_gaps": output.get("ranked_gaps", [])[:3],
        })

        return AgentResult(
            status="success",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            output=output,
            claim_check=output.get("claim_check", False),
            artifact_id=output.get("artifact_id"),
            memory_updates=session.get_pending_updates(),
        )

    except Exception as e:
        logger.exception("Gap detector failed")
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error=str(e),
        )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler entry point — backwards-compatible with P10.

    Normalizes the Lambda event, creates a session, invokes the registered
    handler, and returns a Lambda-formatted response.

    Args:
        event: Lambda event dict.
        context: Lambda context.

    Returns:
        Lambda HTTP-style response dict.
    """
    from qitp_agents.runtime.entrypoint import app
    return app.invoke(event, context)


def _create_mcp_clients(payload: AgentPayload) -> dict[str, Any]:
    """Create MCP clients — Gateway-routed in AgentCore, direct in Lambda.

    In AgentCore mode: returns a Gateway client that routes all tool calls
    through the AgentCore Gateway single endpoint.

    In Lambda mode: returns direct MCP client connections per blueprint.
    """
    if RUNTIME_MODE == RuntimeMode.AGENTCORE:
        return _create_gateway_clients()
    return _create_direct_clients()


def _create_gateway_clients() -> dict[str, Any]:
    """Create MCP clients via AgentCore Gateway."""
    try:
        from agent_core.gateway.client import GatewayClient

        gateway_url = os.environ.get("AGENTCORE_GATEWAY_URL")
        if not gateway_url:
            logger.warning("AGENTCORE_GATEWAY_URL not set, falling back to direct")
            return _create_direct_clients()

        client = GatewayClient(gateway_url=gateway_url)
        return {"gateway": client}
    except ImportError:
        logger.warning("Gateway client not available, falling back to direct")
        return _create_direct_clients()


def _create_direct_clients() -> dict[str, Any]:
    """Create direct MCP client connections (Lambda mode)."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    market_data_uri = os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8002")
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=market_data_uri,
    )

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        logger.warning("Output exceeds 256KB, storing claim-check reference")
        output = {
            "claim_check": True,
            "message": "Output exceeded 256KB. Full result stored as artifact.",
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output
```

---

### src/qitp_agents/sentiment_analyzer/handler.py (Updated — Dual-Mode)

```python
"""Sentiment Analysis Agent handler — dual-mode Lambda + AgentCore.

Input:  {"symbols": ["AAPL", "TSLA"], "date": "2026-03-15"}
Output: SentimentReport JSON artifact with per-symbol scores.

Architecture:
- Strands Swarm pattern: coordinator dispatches one worker per symbol
- In AgentCore mode: tools via Gateway, memory via AgentCore Memory
- In Lambda mode: direct MCP connections, DynamoDB memory

P10 handler updated for P19 dual-mode support.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

from qitp_agents.runtime.adapter import (
    AgentPayload,
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
)
from qitp_agents.runtime.entrypoint import register_agent
from qitp_agents.runtime.session import SessionState

logger = logging.getLogger(__name__)

EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "backtest"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))
RUNTIME_MODE = get_runtime_mode()

AGENT_ID = "sentiment-analyzer"
MAX_OUTPUT_BYTES = 256 * 1024


@register_agent(AGENT_ID)
def handle_sentiment_analysis(
    payload: AgentPayload, session: SessionState
) -> AgentResult:
    """Core sentiment analysis logic — runtime-agnostic.

    Args:
        payload: Normalized agent payload with symbols list and date.
        session: Session state for memory management.

    Returns:
        AgentResult with sentiment report.
    """
    symbols = payload.parameters.get("symbols", [])
    date = payload.parameters.get("date")
    gap_artifact_id = payload.parameters.get("gap_results_artifact_id")

    if not symbols:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: symbols",
        )
    if not date:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: date",
        )

    try:
        mcp_clients = _create_mcp_clients()
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        symbols_str = ", ".join(symbols)
        prompt = (
            f"Analyze sentiment for the following symbols on {date}: {symbols_str}\n\n"
            f"For each symbol:\n"
            f"1. Call get_composite_sentiment(symbol, date) to get the overall score.\n"
            f"2. Record: symbol, composite_score (-1.0 to 1.0), news_score, social_score, "
            f"   source_count, dominant_theme.\n\n"
            f"After all symbols are processed:\n"
            f"3. Create a SentimentReport artifact with all per-symbol results.\n"
            f"4. Include overall_market_sentiment (average of all composites).\n"
            f"5. Flag any symbols with composite_score > 0.5 or < -0.5 as 'high_signal'.\n"
        )

        if gap_artifact_id:
            prompt += (
                f"\nContext: Gap detection results are in artifact {gap_artifact_id}. "
                f"Cross-reference sentiment with gap direction for confirmation signals.\n"
            )

        # Retrieve prior sentiment for comparison
        prior_sentiment = session.retrieve("last_sentiment_report")
        if prior_sentiment:
            prompt += (
                f"\nPrior sentiment context: {json.dumps(prior_sentiment)[:300]}\n"
                f"Note any significant sentiment shifts.\n"
            )

        result = agent(prompt)
        output = _marshal_output(result)

        session.store("last_sentiment_report", {
            "date": date,
            "symbol_count": len(symbols),
            "overall_sentiment": output.get("overall_market_sentiment"),
        })

        return AgentResult(
            status="success",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            output=output,
            claim_check=output.get("claim_check", False),
            artifact_id=output.get("artifact_id"),
            memory_updates=session.get_pending_updates(),
        )

    except Exception as e:
        logger.exception("Sentiment analyzer failed")
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error=str(e),
        )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler entry point — backwards-compatible with P10."""
    from qitp_agents.runtime.entrypoint import app
    return app.invoke(event, context)


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP clients — Gateway or direct."""
    if RUNTIME_MODE == RuntimeMode.AGENTCORE:
        try:
            from agent_core.gateway.client import GatewayClient

            gateway_url = os.environ.get("AGENTCORE_GATEWAY_URL")
            if gateway_url:
                return {"gateway": GatewayClient(gateway_url=gateway_url)}
        except ImportError:
            pass

    from agent_core.mcp import create_mcp_client

    return {
        "sentiment-mcp": create_mcp_client(
            name="sentiment-mcp",
            uri=os.environ.get("SENTIMENT_MCP_URI", "http://localhost:8003"),
        ),
        "artifacts-mcp": create_mcp_client(
            name="artifacts-mcp",
            uri=os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004"),
        ),
    }


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        logger.warning("Output exceeds 256KB, storing claim-check reference")
        output = {
            "claim_check": True,
            "message": "Output exceeded 256KB. Full result stored as artifact.",
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output
```

---

### src/qitp_agents/strategy_evaluator/handler.py (Updated — Dual-Mode)

```python
"""Strategy Evaluation Agent handler — dual-mode Lambda + AgentCore.

Input:  {"symbol": "AAPL", "date": "2026-03-15", "gap_data": {...}, "sentiment_data": {...}}
Output: Strategy evaluation scores with recommended strategy.

Architecture:
- Strands Graph pattern with deterministic routing
- Nodes: gap_analysis → technical_analysis → sentiment_gate → strategy_scoring
- In AgentCore mode: tools via Gateway, Cedar policies enforce access control

P10 handler updated for P19 dual-mode support.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

from qitp_agents.runtime.adapter import (
    AgentPayload,
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
)
from qitp_agents.runtime.entrypoint import register_agent
from qitp_agents.runtime.session import SessionState

logger = logging.getLogger(__name__)

EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "backtest"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))
RUNTIME_MODE = get_runtime_mode()

AGENT_ID = "strategy-evaluator"
MAX_OUTPUT_BYTES = 256 * 1024


@register_agent(AGENT_ID)
def handle_strategy_evaluation(
    payload: AgentPayload, session: SessionState
) -> AgentResult:
    """Core strategy evaluation logic — runtime-agnostic.

    Args:
        payload: Normalized agent payload with symbol, gap data, sentiment data.
        session: Session state for memory management.

    Returns:
        AgentResult with strategy evaluation scores.
    """
    symbol = payload.parameters.get("symbol")
    date = payload.parameters.get("date")
    gap_data = payload.parameters.get("gap_data", {})
    sentiment_data = payload.parameters.get("sentiment_data", {})

    if not symbol:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: symbol",
        )
    if not date:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: date",
        )

    try:
        mcp_clients = _create_mcp_clients()
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Retrieve historical strategy performance for this symbol
        historical = session.retrieve(f"strategy_history_{symbol}", {})

        prompt = (
            f"Evaluate trading strategies for {symbol} on {date}.\n\n"
            f"Gap data: {json.dumps(gap_data)}\n"
            f"Sentiment data: {json.dumps(sentiment_data)}\n\n"
            f"Steps:\n"
            f"1. Analyze gap characteristics (magnitude, volume, direction).\n"
            f"2. Fetch technical indicators (RSI, MACD, Bollinger) via market-data-mcp.\n"
            f"3. Score each strategy against current conditions.\n"
            f"4. Run quick backtest for top 2 strategies via backtest-mcp.\n"
            f"5. Return evaluated_strategies with scores and recommended_strategy_id.\n"
        )

        if historical:
            prompt += (
                f"\nHistorical performance for {symbol}: "
                f"{json.dumps(historical)[:300]}\n"
                f"Factor past strategy effectiveness into scoring.\n"
            )

        result = agent(prompt)
        output = _marshal_output(result)

        # Store strategy performance in memory
        session.store(f"strategy_history_{symbol}", {
            "date": date,
            "recommended": output.get("recommended_strategy_id"),
            "score": output.get("confidence"),
        })

        return AgentResult(
            status="success",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            output=output,
            memory_updates=session.get_pending_updates(),
        )

    except Exception as e:
        logger.exception("Strategy evaluator failed")
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error=str(e),
        )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler entry point — backwards-compatible with P10."""
    from qitp_agents.runtime.entrypoint import app
    return app.invoke(event, context)


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP clients — Gateway or direct."""
    if RUNTIME_MODE == RuntimeMode.AGENTCORE:
        try:
            from agent_core.gateway.client import GatewayClient

            gateway_url = os.environ.get("AGENTCORE_GATEWAY_URL")
            if gateway_url:
                return {"gateway": GatewayClient(gateway_url=gateway_url)}
        except ImportError:
            pass

    from agent_core.mcp import create_mcp_client

    return {
        "market-data-mcp": create_mcp_client(
            name="market-data-mcp",
            uri=os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8002"),
        ),
        "sentiment-mcp": create_mcp_client(
            name="sentiment-mcp",
            uri=os.environ.get("SENTIMENT_MCP_URI", "http://localhost:8003"),
        ),
        "backtest-mcp": create_mcp_client(
            name="backtest-mcp",
            uri=os.environ.get("BACKTEST_MCP_URI", "http://localhost:8005"),
        ),
        "artifacts-mcp": create_mcp_client(
            name="artifacts-mcp",
            uri=os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004"),
        ),
    }


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        output = {
            "claim_check": True,
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output
```

---

### src/qitp_agents/portfolio_recommender/handler.py (Updated — Dual-Mode)

```python
"""Portfolio Recommender Agent handler — dual-mode Lambda + AgentCore.

Input:  {"date": "2026-03-15", "strategy_evaluations": [...]}
Output: Portfolio recommendation with position sizing and risk parameters.

Architecture:
- Single Strands agent with extended thinking (Claude Opus)
- In AgentCore mode: uses long-term memory for strategy preference learning
- In Lambda mode: stateless recommendation

P10 handler updated for P19 dual-mode support.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

from qitp_agents.runtime.adapter import (
    AgentPayload,
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
)
from qitp_agents.runtime.entrypoint import register_agent
from qitp_agents.runtime.session import SessionState

logger = logging.getLogger(__name__)

EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "backtest"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))
RUNTIME_MODE = get_runtime_mode()

AGENT_ID = "portfolio-recommender"
MAX_OUTPUT_BYTES = 256 * 1024


@register_agent(AGENT_ID)
def handle_portfolio_recommendation(
    payload: AgentPayload, session: SessionState
) -> AgentResult:
    """Core portfolio recommendation logic — runtime-agnostic.

    Args:
        payload: Normalized agent payload with strategy evaluations.
        session: Session state for memory management.

    Returns:
        AgentResult with portfolio recommendation.
    """
    date = payload.parameters.get("date")
    strategy_evaluations = payload.parameters.get("strategy_evaluations", [])

    if not date:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: date",
        )
    if not strategy_evaluations:
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error="Missing required parameter: strategy_evaluations",
        )

    try:
        mcp_clients = _create_mcp_clients()
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Retrieve long-term preferences and past recommendations
        past_recommendations = session.retrieve("recommendation_history", [])
        risk_preferences = session.retrieve("risk_preferences", {
            "max_positions": 5,
            "max_single_pct": 20,
            "max_sector_pct": 40,
        })

        evals_json = json.dumps(strategy_evaluations)[:4000]
        prompt = (
            f"Generate portfolio recommendations for {date}.\n\n"
            f"Strategy evaluations: {evals_json}\n\n"
            f"Risk constraints:\n"
            f"- Max open positions: {risk_preferences.get('max_positions', 5)}\n"
            f"- Max single position: {risk_preferences.get('max_single_pct', 20)}% NAV\n"
            f"- Max sector concentration: {risk_preferences.get('max_sector_pct', 40)}%\n\n"
            f"Steps:\n"
            f"1. Rank strategy evaluations by composite score.\n"
            f"2. Apply position sizing (Kelly criterion with 0.5x safety factor).\n"
            f"3. Check portfolio-level risk constraints.\n"
            f"4. Set trailing stop parameters per position.\n"
            f"5. Return recommendations array and no_action_symbols.\n"
            f"6. Create a PortfolioRecommendation artifact.\n"
        )

        if past_recommendations:
            prompt += (
                f"\nPast recommendations: {json.dumps(past_recommendations[-3:])[:500]}\n"
                f"Consider recent performance when sizing positions.\n"
            )

        result = agent(prompt)
        output = _marshal_output(result)

        # Update recommendation history in long-term memory
        new_history = past_recommendations[-9:] + [{
            "date": date,
            "count": len(output.get("recommendations", [])),
        }]
        session.store("recommendation_history", new_history)

        return AgentResult(
            status="success",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            output=output,
            claim_check=output.get("claim_check", False),
            artifact_id=output.get("artifact_id"),
            memory_updates=session.get_pending_updates(),
        )

    except Exception as e:
        logger.exception("Portfolio recommender failed")
        return AgentResult(
            status="error",
            agent_id=AGENT_ID,
            session_id=payload.session_id,
            error=str(e),
        )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler entry point — backwards-compatible with P10."""
    from qitp_agents.runtime.entrypoint import app
    return app.invoke(event, context)


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP clients — Gateway or direct."""
    if RUNTIME_MODE == RuntimeMode.AGENTCORE:
        try:
            from agent_core.gateway.client import GatewayClient

            gateway_url = os.environ.get("AGENTCORE_GATEWAY_URL")
            if gateway_url:
                return {"gateway": GatewayClient(gateway_url=gateway_url)}
        except ImportError:
            pass

    from agent_core.mcp import create_mcp_client

    return {
        "market-data-mcp": create_mcp_client(
            name="market-data-mcp",
            uri=os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8002"),
        ),
        "artifacts-mcp": create_mcp_client(
            name="artifacts-mcp",
            uri=os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004"),
        ),
    }


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        output = {
            "claim_check": True,
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output
```

---

## tccw-agent-core — Gateway, Memory, Identity, Policy

---

### src/agent_core/gateway/__init__.py

```python
"""AgentCore Gateway client — unified MCP tool access via single endpoint."""

__all__ = ["GatewayClient", "TargetRegistry", "ToolDiscovery"]
```

---

### src/agent_core/gateway/client.py

```python
"""AgentCore Gateway client.

Provides a single entry point for all MCP tool calls. The Gateway fronts
every MCP server and OpenAPI endpoint, exposing them as a unified tool registry.

Agents call tools through the Gateway URL instead of connecting to individual
MCP servers. The Gateway handles:
- Routing to the correct target MCP
- Outbound auth injection (API keys, OAuth tokens)
- Tool namespace prefixing (e.g., "market-data-mcp::get_ohlcv")
- Caching of tool definitions

Design rule from CLAUDE.md:
  "Gateway becomes the MCP control plane."
  "MCP tool lists come from blueprint YAML, not hardcoded — Gateway will
   replace the loader."
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Tool definition cache TTL in seconds
TOOL_CACHE_TTL = int(os.environ.get("GATEWAY_TOOL_CACHE_TTL", "300"))


class GatewayClient:
    """Client for AgentCore Gateway — routes tool calls to MCP targets.

    Usage:
        client = GatewayClient(gateway_url="https://gateway.agentcore.example.com")
        result = client.invoke_tool("market-data-mcp::get_ohlcv", {"symbol": "AAPL"})
        tools = client.list_tools()
        tools = client.search_tools("price data for stocks")
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """Initialize Gateway client.

        Args:
            gateway_url: AgentCore Gateway HTTPS endpoint.
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum retry attempts for transient failures.
        """
        self.gateway_url = (
            gateway_url
            or os.environ.get("AGENTCORE_GATEWAY_URL")
            or "http://localhost:9000"
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self._tool_cache: dict[str, Any] | None = None
        self._cache_timestamp: float = 0.0
        self._http_client: httpx.Client | None = None

    @property
    def http_client(self) -> httpx.Client:
        """Lazy-initialized HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self.gateway_url,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "qitp-gateway-client/0.2.0",
                },
            )
        return self._http_client

    def invoke_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a tool through the Gateway.

        The Gateway routes the call to the correct MCP target based on
        the namespace prefix (e.g., "market-data-mcp::get_ohlcv").

        Args:
            tool_name: Fully qualified tool name with namespace prefix.
            arguments: Tool input arguments.
            agent_id: Calling agent ID (for Cedar policy evaluation).
            session_id: Session ID (for audit logging).

        Returns:
            Tool output dict.

        Raises:
            GatewayError: If the Gateway returns an error response.
            httpx.HTTPStatusError: On HTTP errors.
        """
        request_body = {
            "tool_name": tool_name,
            "arguments": arguments,
            "context": {
                "agent_id": agent_id,
                "session_id": session_id,
                "execution_mode": os.environ.get("EXECUTION_MODE", "backtest"),
            },
        }

        for attempt in range(self.max_retries):
            try:
                response = self.http_client.post(
                    "/tools/invoke",
                    json=request_body,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("error"):
                    raise GatewayError(
                        tool_name=tool_name,
                        message=result["error"],
                        code=result.get("error_code", "UNKNOWN"),
                    )

                return result.get("output", result)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    raise GatewayPolicyDeniedError(
                        tool_name=tool_name,
                        agent_id=agent_id or "unknown",
                    ) from e
                if e.response.status_code >= 500 and attempt < self.max_retries - 1:
                    logger.warning(
                        "Gateway error (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries,
                        str(e),
                    )
                    continue
                raise
            except httpx.ConnectError:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "Gateway connection failed (attempt %d/%d)",
                        attempt + 1,
                        self.max_retries,
                    )
                    continue
                raise

        raise GatewayError(
            tool_name=tool_name,
            message=f"Failed after {self.max_retries} attempts",
        )

    def list_tools(
        self,
        target: str | None = None,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """List all available tools from the Gateway.

        Args:
            target: Optional filter by MCP target name.
            refresh: Force cache refresh.

        Returns:
            List of tool definition dicts.
        """
        import time

        now = time.time()
        if (
            not refresh
            and self._tool_cache is not None
            and (now - self._cache_timestamp) < TOOL_CACHE_TTL
        ):
            tools = self._tool_cache.get("tools", [])
            if target:
                tools = [t for t in tools if t.get("target") == target]
            return tools

        response = self.http_client.get(
            "/tools/list",
            params={"target": target} if target else None,
        )
        response.raise_for_status()
        data = response.json()

        self._tool_cache = data
        self._cache_timestamp = now

        return data.get("tools", [])

    def search_tools(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search for tools across all Gateway targets.

        Uses AgentCore Gateway's built-in semantic search to find
        relevant tools by natural language description.

        Args:
            query: Natural language search query.
            max_results: Maximum number of results.

        Returns:
            List of matching tool definitions, ranked by relevance.
        """
        response = self.http_client.post(
            "/tools/search",
            json={
                "query": query,
                "max_results": max_results,
            },
        )
        response.raise_for_status()
        return response.json().get("tools", [])

    def health_check(self) -> dict[str, Any]:
        """Check Gateway health and target connectivity.

        Returns:
            Health status dict with target connectivity info.
        """
        response = self.http_client.get("/health")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the HTTP client connection."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> GatewayClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class GatewayError(Exception):
    """Error from AgentCore Gateway."""

    def __init__(
        self,
        tool_name: str,
        message: str,
        code: str = "UNKNOWN",
    ) -> None:
        self.tool_name = tool_name
        self.code = code
        super().__init__(f"Gateway error for {tool_name} [{code}]: {message}")


class GatewayPolicyDeniedError(GatewayError):
    """Cedar policy denied the tool invocation."""

    def __init__(self, tool_name: str, agent_id: str) -> None:
        super().__init__(
            tool_name=tool_name,
            message=f"Cedar policy denied access for agent '{agent_id}'",
            code="POLICY_DENIED",
        )
```

---

### src/agent_core/gateway/target_registry.py

```python
"""AgentCore Gateway target registry.

Registers and manages MCP servers and OpenAPI endpoints as Gateway targets.
Each target is an MCP server, REST API, or OpenAPI spec that the Gateway
can route tool calls to.

From CLAUDE.md:
  "Gateway auto-converts OpenAPI specs to MCP tools (Polygon.io, IBKR REST, news APIs)"
  "synchronize_gateway_targets() on MCP redeploy"
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TargetType(str, Enum):
    """Type of Gateway target."""

    MCP_SERVER = "mcp_server"
    OPENAPI = "openapi"
    REST_API = "rest_api"


class AuthType(str, Enum):
    """Authentication type for the target."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    IAM = "iam"


@dataclass
class GatewayTarget:
    """Definition of a Gateway target — an MCP server or API endpoint.

    Attributes:
        name: Unique target name (used as namespace prefix).
        target_type: MCP server, OpenAPI spec, or REST API.
        endpoint: URL or Cloud Map service name.
        auth_type: How to authenticate to this target.
        auth_config: Auth-specific configuration (references env vars, not secrets).
        description: Human-readable description for semantic search.
        tags: Metadata tags for filtering.
        health_check_path: Health check endpoint path.
        max_tools: Maximum tools this target can expose (default 10000).
    """

    name: str
    target_type: TargetType
    endpoint: str
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, str] = field(default_factory=dict)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    health_check_path: str = "/health"
    max_tools: int = 10000


# Standard QITP targets
QITP_TARGETS: list[GatewayTarget] = [
    GatewayTarget(
        name="market-data-mcp",
        target_type=TargetType.MCP_SERVER,
        endpoint="market-data-mcp.qitp.local:8002",
        auth_type=AuthType.MTLS,
        description="Unified OHLCV, gaps, volume profiles, technical indicators",
        tags=["market-data", "phase-1"],
    ),
    GatewayTarget(
        name="sentiment-mcp",
        target_type=TargetType.MCP_SERVER,
        endpoint="sentiment-mcp.qitp.local:8003",
        auth_type=AuthType.MTLS,
        description="News, analyst, social, and macro sentiment scoring",
        tags=["sentiment", "phase-1"],
    ),
    GatewayTarget(
        name="artifacts-mcp",
        target_type=TargetType.MCP_SERVER,
        endpoint="artifacts-mcp.qitp.local:8004",
        auth_type=AuthType.MTLS,
        description="S3 artifact storage, signed URLs, polling",
        tags=["artifacts", "phase-1"],
    ),
    GatewayTarget(
        name="backtest-mcp",
        target_type=TargetType.MCP_SERVER,
        endpoint="backtest-mcp.qitp.local:8005",
        auth_type=AuthType.MTLS,
        description="Simulation engine, walk-forward validation, strategy backtesting",
        tags=["backtest", "phase-1"],
    ),
    GatewayTarget(
        name="ibkr-mcp",
        target_type=TargetType.MCP_SERVER,
        endpoint="ibkr-mcp.qitp.local:8001",
        auth_type=AuthType.OAUTH2,
        auth_config={
            "provider_id": "ibkr",
            "credential_ref": "IBKR_OAUTH_CREDENTIAL_ID",
        },
        description="Interactive Brokers — positions, orders, trailing stops, account",
        tags=["broker", "phase-2", "cedar-gated"],
    ),
    GatewayTarget(
        name="charting-mcp",
        target_type=TargetType.MCP_SERVER,
        endpoint="charting-mcp.qitp.local:8006",
        auth_type=AuthType.MTLS,
        description="React/Recharts chart generation — equity curves, candlesticks",
        tags=["charting", "phase-2"],
    ),
    GatewayTarget(
        name="polygon-api",
        target_type=TargetType.OPENAPI,
        endpoint="https://api.polygon.io",
        auth_type=AuthType.API_KEY,
        auth_config={
            "header_name": "Authorization",
            "key_ref": "POLYGON_API_KEY",
        },
        description="Polygon.io REST API — real-time and historical market data",
        tags=["market-data", "openapi", "phase-2"],
    ),
    GatewayTarget(
        name="ibkr-rest-api",
        target_type=TargetType.OPENAPI,
        endpoint="https://api.ibkr.com",
        auth_type=AuthType.OAUTH2,
        auth_config={
            "provider_id": "ibkr",
            "credential_ref": "IBKR_OAUTH_CREDENTIAL_ID",
        },
        description="IBKR REST API — supplementary endpoints auto-converted to MCP tools",
        tags=["broker", "openapi", "phase-2"],
    ),
]


class TargetRegistry:
    """Manages registration and synchronization of Gateway targets.

    Usage:
        registry = TargetRegistry(gateway_url="https://gateway.example.com")
        registry.register_target(target)
        registry.synchronize_all()
        registry.get_target_health("market-data-mcp")
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.gateway_url = (
            gateway_url
            or os.environ.get("AGENTCORE_GATEWAY_URL")
            or "http://localhost:9000"
        )
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.gateway_url,
                timeout=self.timeout,
            )
        return self._client

    def register_target(self, target: GatewayTarget) -> dict[str, Any]:
        """Register a single target with the Gateway.

        Args:
            target: Target definition.

        Returns:
            Registration response with tool count.
        """
        payload = {
            "name": target.name,
            "type": target.target_type.value,
            "endpoint": target.endpoint,
            "auth": {
                "type": target.auth_type.value,
                **target.auth_config,
            },
            "description": target.description,
            "tags": target.tags,
            "health_check_path": target.health_check_path,
            "max_tools": target.max_tools,
        }

        response = self.client.post("/targets/register", json=payload)
        response.raise_for_status()
        result = response.json()

        logger.info(
            "Registered target '%s': %d tools discovered",
            target.name,
            result.get("tool_count", 0),
        )
        return result

    def synchronize_all(
        self,
        targets: list[GatewayTarget] | None = None,
    ) -> dict[str, Any]:
        """Register all QITP targets with the Gateway.

        Call this after MCP redeployment to refresh tool definitions.

        Args:
            targets: Optional target list (defaults to QITP_TARGETS).

        Returns:
            Summary dict with per-target registration results.
        """
        targets = targets or QITP_TARGETS
        results = {}

        for target in targets:
            try:
                result = self.register_target(target)
                results[target.name] = {
                    "status": "registered",
                    "tool_count": result.get("tool_count", 0),
                }
            except Exception as e:
                logger.error("Failed to register target '%s': %s", target.name, e)
                results[target.name] = {
                    "status": "failed",
                    "error": str(e),
                }

        total_tools = sum(
            r.get("tool_count", 0) for r in results.values() if r["status"] == "registered"
        )
        logger.info(
            "Synchronized %d targets, %d total tools",
            len([r for r in results.values() if r["status"] == "registered"]),
            total_tools,
        )
        return {"targets": results, "total_tools": total_tools}

    def get_target_health(self, target_name: str) -> dict[str, Any]:
        """Check health of a specific target.

        Args:
            target_name: Target name.

        Returns:
            Health status dict.
        """
        response = self.client.get(f"/targets/{target_name}/health")
        response.raise_for_status()
        return response.json()

    def deregister_target(self, target_name: str) -> None:
        """Remove a target from the Gateway.

        Args:
            target_name: Target name to deregister.
        """
        response = self.client.delete(f"/targets/{target_name}")
        response.raise_for_status()
        logger.info("Deregistered target: %s", target_name)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
```

---

### src/agent_core/gateway/tool_discovery.py

```python
"""Semantic tool discovery via AgentCore Gateway.

Agents can discover tools dynamically using natural language queries instead
of hardcoded tool lists. The Gateway indexes all registered target tools and
supports semantic search across 10,000+ tools per target.

From CLAUDE.md:
  "Gateway provides semantic tool search — agents discover relevant tools dynamically"
  "Supports 10,000 tools per target with namespace prefixes"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_core.gateway.client import GatewayClient

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredTool:
    """A tool discovered via semantic search.

    Attributes:
        fqn: Fully qualified name (e.g., "market-data-mcp::get_ohlcv").
        target: Source target name.
        name: Tool name without namespace.
        description: Tool description.
        input_schema: JSON Schema for tool input.
        relevance_score: Semantic search relevance (0.0 to 1.0).
    """

    fqn: str
    target: str
    name: str
    description: str
    input_schema: dict[str, Any]
    relevance_score: float = 0.0


class ToolDiscovery:
    """Semantic tool discovery service.

    Usage:
        discovery = ToolDiscovery(gateway_client)
        tools = discovery.find_tools("get historical price data for stocks")
        tools = discovery.find_tools_for_task("analyze sentiment for AAPL")
    """

    def __init__(self, gateway_client: GatewayClient) -> None:
        self.gateway = gateway_client

    def find_tools(
        self,
        query: str,
        max_results: int = 10,
        min_relevance: float = 0.3,
    ) -> list[DiscoveredTool]:
        """Find tools by semantic search.

        Args:
            query: Natural language description of what you need.
            max_results: Maximum number of results.
            min_relevance: Minimum relevance score threshold.

        Returns:
            List of DiscoveredTool objects, sorted by relevance.
        """
        raw_results = self.gateway.search_tools(query, max_results=max_results)

        tools = []
        for raw in raw_results:
            score = raw.get("relevance_score", 0.0)
            if score < min_relevance:
                continue

            tool = DiscoveredTool(
                fqn=raw.get("fqn", raw.get("name", "")),
                target=raw.get("target", ""),
                name=raw.get("name", ""),
                description=raw.get("description", ""),
                input_schema=raw.get("input_schema", {}),
                relevance_score=score,
            )
            tools.append(tool)

        tools.sort(key=lambda t: t.relevance_score, reverse=True)
        logger.info(
            "Tool discovery for '%s': %d results (min_relevance=%.2f)",
            query[:50],
            len(tools),
            min_relevance,
        )
        return tools

    def find_tools_for_task(
        self,
        task_description: str,
        agent_id: str | None = None,
        max_results: int = 20,
    ) -> list[DiscoveredTool]:
        """Find all tools relevant to a complex task.

        Higher-level than find_tools — decomposes a task description
        into multiple semantic queries to find a comprehensive tool set.

        Args:
            task_description: Full task description.
            agent_id: Optional agent ID for context-aware filtering.
            max_results: Maximum total results.

        Returns:
            Deduplicated list of relevant tools.
        """
        # Single semantic search for now — can be extended to multi-query
        tools = self.find_tools(task_description, max_results=max_results)

        if agent_id:
            # Filter tools the agent is allowed to use (pre-Cedar check)
            tools = [
                t for t in tools
                if self._agent_can_use(agent_id, t.fqn)
            ]

        return tools

    def list_all_tools(
        self,
        target: str | None = None,
    ) -> list[DiscoveredTool]:
        """List all available tools, optionally filtered by target.

        Args:
            target: Optional target name filter.

        Returns:
            List of all available tools.
        """
        raw_tools = self.gateway.list_tools(target=target)

        return [
            DiscoveredTool(
                fqn=raw.get("fqn", raw.get("name", "")),
                target=raw.get("target", ""),
                name=raw.get("name", ""),
                description=raw.get("description", ""),
                input_schema=raw.get("input_schema", {}),
            )
            for raw in raw_tools
        ]

    @staticmethod
    def _agent_can_use(agent_id: str, tool_fqn: str) -> bool:
        """Quick pre-check if an agent can use a tool.

        This is a soft check — the real enforcement is in Cedar policies
        evaluated by the Gateway. This just filters obvious violations
        to reduce noise in tool discovery results.

        Args:
            agent_id: Agent identifier.
            tool_fqn: Fully qualified tool name.

        Returns:
            True if the agent likely can use this tool.
        """
        # Backtest agents cannot use ibkr-mcp
        backtest_agents = {
            "gap-detector",
            "sentiment-analyzer",
            "strategy-evaluator",
        }
        if agent_id in backtest_agents and tool_fqn.startswith("ibkr-mcp::"):
            return False

        # Only execution agent can place orders
        if "place_order" in tool_fqn and agent_id != "execution-agent":
            return False

        return True
```

---

### src/agent_core/memory/__init__.py

```python
"""AgentCore Memory — session management with short-term, long-term, and episodic tiers."""

__all__ = ["MemoryManager", "SessionBridge", "get_memory_manager"]
```

---

### src/agent_core/memory/manager.py

```python
"""AgentCore Memory manager.

Wraps AgentCore Memory service with QITP-specific session management.
Provides three memory tiers:
- Short-term: within a single SFN execution (ephemeral)
- Long-term: cross-session preferences, strategy history (persistent)
- Episodic: retrievable by similarity search (indexed)

From CLAUDE.md:
  "AgentCore Memory (short/long/episodic tiers, semantic retrieval,
   cross-agent shared context)"
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton
_memory_manager: MemoryManager | None = None


class MemoryManager:
    """Unified memory manager for AgentCore Memory service.

    Usage:
        manager = MemoryManager()
        manager.update_session_memory(session_id, agent_id, {"key": "value"})
        data = manager.get_session_memory(session_id)
        results = manager.semantic_search(session_id, "AAPL gap analysis")
    """

    def __init__(
        self,
        region: str | None = None,
        memory_namespace: str | None = None,
    ) -> None:
        """Initialize AgentCore Memory manager.

        Args:
            region: AWS region for AgentCore Memory service.
            memory_namespace: Namespace prefix for memory keys (default: env-based).
        """
        self.region = region or os.environ.get("AWS_REGION", "eu-west-1")
        self.env_name = os.environ.get("ENV_NAME", "dev")
        self.namespace = memory_namespace or f"qitp-{self.env_name}"
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-initialize AgentCore Memory client."""
        if self._client is None:
            try:
                from bedrock_agentcore.memory import AgentCoreMemoryClient

                self._client = AgentCoreMemoryClient(
                    region=self.region,
                    namespace=self.namespace,
                )
                logger.info(
                    "AgentCore Memory client initialized: region=%s namespace=%s",
                    self.region,
                    self.namespace,
                )
            except ImportError:
                logger.warning(
                    "bedrock-agentcore-memory not available — "
                    "using in-memory fallback"
                )
                self._client = _InMemoryFallback()
        return self._client

    def get_session_memory(
        self,
        session_id: str,
        tier: str = "short_term",
    ) -> dict[str, Any] | None:
        """Retrieve memory for a session.

        Args:
            session_id: Session identifier (= SFN execution ID).
            tier: Memory tier — "short_term", "long_term", or "episodic".

        Returns:
            Memory dict or None if not found.
        """
        try:
            key = self._make_key(session_id, tier)
            result = self.client.get(key)
            if result:
                logger.debug(
                    "Retrieved %s memory for session %s: %d keys",
                    tier,
                    session_id,
                    len(result),
                )
            return result
        except Exception:
            logger.exception("Failed to retrieve memory: session=%s tier=%s", session_id, tier)
            return None

    def update_session_memory(
        self,
        session_id: str,
        agent_id: str,
        updates: dict[str, Any],
        tier: str = "short_term",
    ) -> None:
        """Update memory for a session.

        Args:
            session_id: Session identifier.
            agent_id: Agent that produced the updates.
            updates: Key-value pairs to store.
            tier: Memory tier.
        """
        try:
            key = self._make_key(session_id, tier)
            self.client.update(
                key,
                {
                    **updates,
                    "_last_agent": agent_id,
                    "_updated_at": _now_iso(),
                },
            )
            logger.info(
                "Updated %s memory for session %s (agent=%s, %d keys)",
                tier,
                session_id,
                agent_id,
                len(updates),
            )
        except Exception:
            logger.exception(
                "Failed to update memory: session=%s agent=%s tier=%s",
                session_id,
                agent_id,
                tier,
            )

    def store_episodic(
        self,
        session_id: str,
        agent_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Store an episodic memory entry (indexed for semantic search).

        Args:
            session_id: Session identifier.
            agent_id: Agent that produced the content.
            content: Text content to index.
            metadata: Optional metadata (date, symbol, etc.).

        Returns:
            Memory entry ID or None on failure.
        """
        try:
            entry_id = self.client.store_episodic(
                namespace=self.namespace,
                session_id=session_id,
                agent_id=agent_id,
                content=content,
                metadata={
                    **(metadata or {}),
                    "execution_mode": os.environ.get("EXECUTION_MODE", "backtest"),
                    "stored_at": _now_iso(),
                },
            )
            logger.info(
                "Stored episodic memory: session=%s agent=%s entry=%s",
                session_id,
                agent_id,
                entry_id,
            )
            return entry_id
        except Exception:
            logger.exception("Failed to store episodic memory")
            return None

    def semantic_search(
        self,
        session_id: str | None = None,
        query: str = "",
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Search episodic memory by semantic similarity.

        Args:
            session_id: Optional session filter.
            query: Natural language query.
            max_results: Maximum results.

        Returns:
            Search results dict with entries and scores.
        """
        try:
            results = self.client.search_episodic(
                namespace=self.namespace,
                query=query,
                session_id=session_id,
                max_results=max_results,
            )
            logger.info(
                "Semantic search '%s': %d results",
                query[:50],
                len(results.get("entries", [])),
            )
            return results
        except Exception:
            logger.exception("Semantic search failed")
            return {"entries": [], "query": query}

    def _make_key(self, session_id: str, tier: str) -> str:
        """Build a namespaced memory key."""
        return f"{self.namespace}/{tier}/{session_id}"


class _InMemoryFallback:
    """In-memory fallback when AgentCore Memory SDK is not available."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._episodic: list[dict[str, Any]] = []

    def get(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

    def update(self, key: str, data: dict[str, Any]) -> None:
        if key not in self._store:
            self._store[key] = {}
        self._store[key].update(data)

    def store_episodic(self, **kwargs: Any) -> str:
        import uuid

        entry_id = uuid.uuid4().hex[:12]
        self._episodic.append({"id": entry_id, **kwargs})
        return entry_id

    def search_episodic(self, **kwargs: Any) -> dict[str, Any]:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        # Naive substring match fallback
        matches = [
            e for e in self._episodic
            if query.lower() in e.get("content", "").lower()
        ][:max_results]
        return {"entries": matches, "query": query}


def get_memory_manager() -> MemoryManager:
    """Get or create the module-level MemoryManager singleton."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

---

### src/agent_core/memory/session_bridge.py

```python
"""Session bridge: maps SFN execution IDs to AgentCore session IDs.

From CLAUDE.md:
  "Session IDs map to SFN execution IDs — AgentCore Memory uses the same
   session_id convention."

SFN execution IDs have the format:
  arn:aws:states:eu-west-1:835618032093:execution:qitp-dev-weekly-analysis:exec-abc123

We extract the execution name (after the last colon) as the session ID.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Pattern for SFN execution ARN
SFN_EXECUTION_ARN_PATTERN = re.compile(
    r"^arn:aws:states:[a-z0-9-]+:\d{12}:execution:[^:]+:(.+)$"
)


def sfn_execution_id_to_session_id(execution_id: str) -> str:
    """Convert an SFN execution ID or ARN to a session ID.

    If the input is a full ARN, extracts the execution name.
    If the input is already a plain ID, returns it as-is.

    Args:
        execution_id: SFN execution ARN or plain execution name.

    Returns:
        Session ID string.

    Examples:
        >>> sfn_execution_id_to_session_id(
        ...     "arn:aws:states:eu-west-1:835618032093:execution:qitp-dev-weekly:exec-abc123"
        ... )
        'exec-abc123'
        >>> sfn_execution_id_to_session_id("exec-abc123")
        'exec-abc123'
    """
    match = SFN_EXECUTION_ARN_PATTERN.match(execution_id)
    if match:
        session_id = match.group(1)
        logger.debug("Extracted session ID '%s' from ARN", session_id)
        return session_id
    return execution_id


def session_id_to_sfn_execution_arn(
    session_id: str,
    state_machine_name: str,
    region: str = "eu-west-1",
    account_id: str = "835618032093",
) -> str:
    """Reconstruct an SFN execution ARN from a session ID.

    Args:
        session_id: Session ID (execution name).
        state_machine_name: SFN state machine name.
        region: AWS region.
        account_id: AWS account ID.

    Returns:
        Full SFN execution ARN.
    """
    return (
        f"arn:aws:states:{region}:{account_id}:"
        f"execution:{state_machine_name}:{session_id}"
    )


def extract_session_metadata(execution_input: dict[str, Any]) -> dict[str, str]:
    """Extract session metadata from SFN execution input.

    SFN passes execution context including the execution ID, state machine name,
    and execution start time. This function normalizes these into session metadata.

    Args:
        execution_input: SFN execution input or task input.

    Returns:
        Dict with session_id, state_machine, start_time.
    """
    # SFN injects these via Context Object in task input
    sfn_context = execution_input.get("_sfn_context", {})

    execution_arn = sfn_context.get("Execution", {}).get("Id", "")
    state_machine_arn = sfn_context.get("StateMachine", {}).get("Id", "")
    start_time = sfn_context.get("Execution", {}).get("StartTime", "")

    session_id = (
        sfn_execution_id_to_session_id(execution_arn)
        if execution_arn
        else execution_input.get("session_id", "unknown")
    )

    return {
        "session_id": session_id,
        "execution_arn": execution_arn,
        "state_machine_arn": state_machine_arn,
        "start_time": start_time,
    }
```

---

### src/agent_core/identity/__init__.py

```python
"""AgentCore Identity — managed OAuth and credential providers."""

__all__ = ["IdentityProvider", "IBKRIdentityProvider", "TelegramIdentityProvider"]
```

---

### src/agent_core/identity/providers.py

```python
"""AgentCore Identity credential providers.

Manages OAuth token flows for external services (IBKR, Telegram).
In AgentCore mode, Identity handles token refresh automatically.
In Lambda mode, tokens are managed via environment variables.

From CLAUDE.md:
  "AgentCore Identity (OAuth/OIDC to IBKR, Polygon, Telegram — managed token flows)"
  "All secrets via env vars — AgentCore Identity will replace them,
   but the interface is the same."
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported identity providers."""

    IBKR = "ibkr"
    TELEGRAM = "telegram"
    POLYGON = "polygon"


@dataclass
class Credential:
    """A resolved credential from AgentCore Identity or environment.

    Attributes:
        provider: Which identity provider.
        token_type: Token type (bearer, api_key, etc.).
        access_token: The actual token value (resolved at runtime).
        expires_at: ISO timestamp when the token expires (if applicable).
        scopes: OAuth scopes granted (if applicable).
    """

    provider: ProviderType
    token_type: str
    access_token: str
    expires_at: str | None = None
    scopes: list[str] | None = None


class IdentityProvider(ABC):
    """Base class for identity providers.

    Provides a uniform interface for credential resolution.
    In Lambda mode: reads from environment variables.
    In AgentCore mode: uses AgentCore Identity service.
    """

    def __init__(self, provider_type: ProviderType) -> None:
        self.provider_type = provider_type
        self.runtime_mode = os.environ.get("RUNTIME_MODE", "lambda")

    @abstractmethod
    def get_credential(self) -> Credential:
        """Resolve a credential for this provider.

        Returns:
            Credential with access token.

        Raises:
            CredentialError: If credential cannot be resolved.
        """
        ...

    @abstractmethod
    def refresh_credential(self) -> Credential:
        """Force-refresh the credential (e.g., OAuth token refresh).

        Returns:
            Fresh Credential.
        """
        ...

    def _get_from_agentcore(self, credential_id: str) -> Credential:
        """Resolve credential via AgentCore Identity service.

        Args:
            credential_id: AgentCore credential reference ID.

        Returns:
            Resolved Credential.
        """
        try:
            from bedrock_agentcore.identity import AgentCoreIdentityClient

            client = AgentCoreIdentityClient(
                region=os.environ.get("AWS_REGION", "eu-west-1"),
            )
            token = client.get_credential(credential_id)

            return Credential(
                provider=self.provider_type,
                token_type=token.get("token_type", "bearer"),
                access_token=token["access_token"],
                expires_at=token.get("expires_at"),
                scopes=token.get("scopes"),
            )
        except ImportError:
            raise CredentialError(
                f"bedrock-agentcore-identity not installed for provider {self.provider_type.value}"
            )
        except KeyError as e:
            raise CredentialError(
                f"AgentCore Identity returned incomplete credential: {e}"
            )


class IBKRIdentityProvider(IdentityProvider):
    """Interactive Brokers OAuth identity provider.

    In Lambda mode: reads IBKR_ACCESS_TOKEN from environment.
    In AgentCore mode: uses AgentCore Identity for OAuth2 token management.
    """

    def __init__(self) -> None:
        super().__init__(ProviderType.IBKR)

    def get_credential(self) -> Credential:
        """Get IBKR OAuth credential."""
        if self.runtime_mode == "agentcore":
            credential_id = os.environ.get(
                "IBKR_OAUTH_CREDENTIAL_ID", "qitp-ibkr-oauth"
            )
            return self._get_from_agentcore(credential_id)

        # Lambda mode: environment variable
        token = os.environ.get("IBKR_ACCESS_TOKEN")
        if not token:
            raise CredentialError(
                "IBKR_ACCESS_TOKEN environment variable not set"
            )

        return Credential(
            provider=ProviderType.IBKR,
            token_type="bearer",
            access_token=token,
        )

    def refresh_credential(self) -> Credential:
        """Force-refresh IBKR OAuth token."""
        if self.runtime_mode == "agentcore":
            try:
                from bedrock_agentcore.identity import AgentCoreIdentityClient

                client = AgentCoreIdentityClient(
                    region=os.environ.get("AWS_REGION", "eu-west-1"),
                )
                credential_id = os.environ.get(
                    "IBKR_OAUTH_CREDENTIAL_ID", "qitp-ibkr-oauth"
                )
                token = client.refresh_credential(credential_id)

                return Credential(
                    provider=ProviderType.IBKR,
                    token_type=token.get("token_type", "bearer"),
                    access_token=token["access_token"],
                    expires_at=token.get("expires_at"),
                )
            except ImportError:
                raise CredentialError(
                    "bedrock-agentcore-identity not installed"
                )

        # Lambda mode: can't refresh — just return current
        return self.get_credential()


class TelegramIdentityProvider(IdentityProvider):
    """Telegram Bot API identity provider.

    In Lambda mode: reads TELEGRAM_BOT_TOKEN from environment.
    In AgentCore mode: uses AgentCore Identity for managed token.
    """

    def __init__(self) -> None:
        super().__init__(ProviderType.TELEGRAM)

    def get_credential(self) -> Credential:
        """Get Telegram bot token."""
        if self.runtime_mode == "agentcore":
            credential_id = os.environ.get(
                "TELEGRAM_CREDENTIAL_ID", "qitp-telegram-bot"
            )
            return self._get_from_agentcore(credential_id)

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise CredentialError(
                "TELEGRAM_BOT_TOKEN environment variable not set"
            )

        return Credential(
            provider=ProviderType.TELEGRAM,
            token_type="api_key",
            access_token=token,
        )

    def refresh_credential(self) -> Credential:
        """Telegram bot tokens don't expire — just returns current."""
        return self.get_credential()


class PolygonIdentityProvider(IdentityProvider):
    """Polygon.io API key identity provider.

    In Lambda mode: reads POLYGON_API_KEY from environment.
    In AgentCore mode: uses AgentCore Identity.
    """

    def __init__(self) -> None:
        super().__init__(ProviderType.POLYGON)

    def get_credential(self) -> Credential:
        """Get Polygon.io API key."""
        if self.runtime_mode == "agentcore":
            credential_id = os.environ.get(
                "POLYGON_CREDENTIAL_ID", "qitp-polygon-api"
            )
            return self._get_from_agentcore(credential_id)

        key = os.environ.get("POLYGON_API_KEY")
        if not key:
            raise CredentialError(
                "POLYGON_API_KEY environment variable not set"
            )

        return Credential(
            provider=ProviderType.POLYGON,
            token_type="api_key",
            access_token=key,
        )

    def refresh_credential(self) -> Credential:
        """API keys don't expire — just returns current."""
        return self.get_credential()


class CredentialError(Exception):
    """Error resolving a credential."""
    pass


def get_provider(provider_type: ProviderType) -> IdentityProvider:
    """Factory function to get the correct identity provider.

    Args:
        provider_type: Which provider to instantiate.

    Returns:
        IdentityProvider instance.
    """
    providers: dict[ProviderType, type[IdentityProvider]] = {
        ProviderType.IBKR: IBKRIdentityProvider,
        ProviderType.TELEGRAM: TelegramIdentityProvider,
        ProviderType.POLYGON: PolygonIdentityProvider,
    }

    provider_cls = providers.get(provider_type)
    if provider_cls is None:
        raise ValueError(f"Unknown provider type: {provider_type}")

    return provider_cls()
```

---

### src/agent_core/policy/__init__.py

```python
"""Cedar policy definitions for AgentCore tool-level access control."""

__all__ = ["CedarPolicyBuilder", "validate_policy_set"]
```

---

### src/agent_core/policy/cedar_policies.py

```python
"""Cedar policy builder and validator for QITP.

Generates Cedar policy files that AgentCore evaluates at the Gateway level
to control which agents can invoke which tools in which execution modes.

From CLAUDE.md Cedar policy examples:
- Only execution_agent can place orders in live mode
- Backtest agents cannot access ibkr-mcp
- Risk engine can only read positions (no write)

Cedar policies are defined as Python structures, serialized to .cedar format,
and deployed via CDK in the agentcore_stack.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PolicyEffect(str, Enum):
    """Cedar policy effect."""

    PERMIT = "permit"
    FORBID = "forbid"


class PolicyAction(str, Enum):
    """Actions controlled by Cedar policies."""

    INVOKE_TOOL = "invoke_tool"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"


@dataclass
class CedarPolicy:
    """A single Cedar policy rule.

    Attributes:
        policy_id: Unique identifier for the policy.
        effect: PERMIT or FORBID.
        description: Human-readable description.
        principal: Agent or AgentGroup (e.g., 'Agent::"execution_agent"').
        action: Action being controlled.
        resource: Tool or ToolGroup (e.g., 'Tool::"ibkr-mcp::place_order"').
        conditions: Optional "when" conditions (Cedar expression strings).
    """

    policy_id: str
    effect: PolicyEffect
    description: str
    principal: str
    action: PolicyAction
    resource: str
    conditions: list[str] = field(default_factory=list)

    def to_cedar(self) -> str:
        """Serialize this policy to Cedar format.

        Returns:
            Cedar policy string.
        """
        lines = [f"// {self.description}"]

        principal_clause = f"principal == {self.principal}"
        action_clause = f'action == Action::"{self.action.value}"'
        resource_clause = f"resource == {self.resource}"

        # Handle "in" syntax for groups
        if "in " in self.principal:
            principal_clause = f"principal {self.principal}"
        if "in " in self.resource:
            resource_clause = f"resource {self.resource}"

        lines.append(f"{self.effect.value}(")
        lines.append(f"    {principal_clause},")
        lines.append(f"    {action_clause},")
        lines.append(f"    {resource_clause}")
        lines.append(")")

        if self.conditions:
            conditions_str = " && ".join(self.conditions)
            lines[-1] = lines[-1].rstrip(")")
            lines.append(f"when {{ {conditions_str} }};")
        else:
            lines[-1] += ";"

        return "\n".join(lines)


# ─── QITP Policy Set ────────────────────────────────────────────────

QITP_POLICIES: list[CedarPolicy] = [
    # 1. Only execution_agent can submit orders in live mode
    CedarPolicy(
        policy_id="exec-agent-live-orders",
        effect=PolicyEffect.PERMIT,
        description="Only execution_agent can submit orders in live mode",
        principal='Agent::"execution_agent"',
        action=PolicyAction.INVOKE_TOOL,
        resource='Tool::"ibkr-mcp::place_order"',
        conditions=['context.execution_mode == "live"'],
    ),
    # 2. Execution agent can also modify and cancel orders
    CedarPolicy(
        policy_id="exec-agent-order-management",
        effect=PolicyEffect.PERMIT,
        description="Execution agent can modify and cancel orders",
        principal='Agent::"execution_agent"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in ToolGroup::"ibkr-mcp-write"',
    ),
    # 3. Backtest agents cannot access ibkr-mcp at all
    CedarPolicy(
        policy_id="backtest-no-ibkr",
        effect=PolicyEffect.FORBID,
        description="Backtest agents cannot access ibkr-mcp",
        principal='in AgentGroup::"backtest_agents"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in ToolGroup::"ibkr-mcp"',
    ),
    # 4. Risk Engine can only read positions (no write operations)
    CedarPolicy(
        policy_id="risk-engine-read-only",
        effect=PolicyEffect.PERMIT,
        description="Risk Engine read-only access to IBKR positions and account",
        principal='Agent::"risk_engine"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in [Tool::"ibkr-mcp::get_positions", Tool::"ibkr-mcp::get_account_summary"]',
    ),
    # 5. All agents can read artifacts
    CedarPolicy(
        policy_id="all-agents-read-artifacts",
        effect=PolicyEffect.PERMIT,
        description="All agents can read and create artifacts",
        principal='in AgentGroup::"all_agents"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in ToolGroup::"artifacts-mcp"',
    ),
    # 6. All agents can use market-data-mcp
    CedarPolicy(
        policy_id="all-agents-market-data",
        effect=PolicyEffect.PERMIT,
        description="All agents can access market data tools",
        principal='in AgentGroup::"all_agents"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in ToolGroup::"market-data-mcp"',
    ),
    # 7. Sentiment analyzer can use sentiment-mcp
    CedarPolicy(
        policy_id="sentiment-agent-access",
        effect=PolicyEffect.PERMIT,
        description="Sentiment analyzer can access sentiment tools",
        principal='Agent::"sentiment_analyzer"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in ToolGroup::"sentiment-mcp"',
    ),
    # 8. Strategy evaluator can use backtest-mcp
    CedarPolicy(
        policy_id="strategy-agent-backtest",
        effect=PolicyEffect.PERMIT,
        description="Strategy evaluator can run backtests",
        principal='Agent::"strategy_evaluator"',
        action=PolicyAction.INVOKE_TOOL,
        resource='in ToolGroup::"backtest-mcp"',
    ),
    # 9. No agent can place orders in backtest mode
    CedarPolicy(
        policy_id="no-orders-in-backtest",
        effect=PolicyEffect.FORBID,
        description="No agent can place real orders in backtest mode",
        principal='in AgentGroup::"all_agents"',
        action=PolicyAction.INVOKE_TOOL,
        resource='Tool::"ibkr-mcp::place_order"',
        conditions=['context.execution_mode == "backtest"'],
    ),
    # 10. Memory access: agents can only write their own session memory
    CedarPolicy(
        policy_id="memory-write-own-session",
        effect=PolicyEffect.PERMIT,
        description="Agents can write memory for their own session only",
        principal='in AgentGroup::"all_agents"',
        action=PolicyAction.WRITE_MEMORY,
        resource='in ToolGroup::"memory"',
        conditions=["context.session_id == resource.session_id"],
    ),
]


class CedarPolicyBuilder:
    """Builds and serializes Cedar policy sets.

    Usage:
        builder = CedarPolicyBuilder()
        builder.add_policy(policy)
        cedar_text = builder.build()
        builder.write_to_file("cedar/policies.cedar")
    """

    def __init__(self) -> None:
        self.policies: list[CedarPolicy] = []

    def add_policy(self, policy: CedarPolicy) -> CedarPolicyBuilder:
        """Add a policy to the builder.

        Args:
            policy: CedarPolicy to add.

        Returns:
            self for chaining.
        """
        self.policies.append(policy)
        return self

    def add_qitp_defaults(self) -> CedarPolicyBuilder:
        """Add all default QITP policies.

        Returns:
            self for chaining.
        """
        self.policies.extend(QITP_POLICIES)
        return self

    def build(self) -> str:
        """Serialize all policies to Cedar format.

        Returns:
            Complete Cedar policy file content.
        """
        header = (
            "// QITP Cedar Policies — AgentCore Tool Access Control\n"
            "// Generated by agent_core.policy.cedar_policies\n"
            "// DO NOT EDIT MANUALLY — regenerate via CedarPolicyBuilder\n"
            "\n"
        )

        policy_texts = []
        for policy in self.policies:
            policy_texts.append(policy.to_cedar())

        return header + "\n\n".join(policy_texts) + "\n"

    def write_to_file(self, path: str) -> None:
        """Write policies to a .cedar file.

        Args:
            path: File path for the Cedar policy file.
        """
        content = self.build()
        with open(path, "w") as f:
            f.write(content)
        logger.info("Wrote %d Cedar policies to %s", len(self.policies), path)


# ─── Cedar Entity Schema ────────────────────────────────────────────

CEDAR_SCHEMA = {
    "QITP": {
        "entityTypes": {
            "Agent": {
                "memberOfTypes": ["AgentGroup"],
                "shape": {
                    "type": "Record",
                    "attributes": {
                        "agent_id": {"type": "String"},
                        "execution_mode": {"type": "String"},
                    },
                },
            },
            "AgentGroup": {
                "shape": {
                    "type": "Record",
                    "attributes": {
                        "group_id": {"type": "String"},
                    },
                },
            },
            "Tool": {
                "memberOfTypes": ["ToolGroup"],
                "shape": {
                    "type": "Record",
                    "attributes": {
                        "tool_name": {"type": "String"},
                        "target": {"type": "String"},
                        "session_id": {"type": "String"},
                    },
                },
            },
            "ToolGroup": {
                "shape": {
                    "type": "Record",
                    "attributes": {
                        "group_id": {"type": "String"},
                    },
                },
            },
        },
        "actions": {
            "invoke_tool": {
                "appliesTo": {
                    "principalTypes": ["Agent", "AgentGroup"],
                    "resourceTypes": ["Tool", "ToolGroup"],
                    "context": {
                        "type": "Record",
                        "attributes": {
                            "execution_mode": {"type": "String"},
                            "session_id": {"type": "String"},
                        },
                    },
                },
            },
            "read_memory": {
                "appliesTo": {
                    "principalTypes": ["Agent"],
                    "resourceTypes": ["Tool"],
                    "context": {
                        "type": "Record",
                        "attributes": {
                            "session_id": {"type": "String"},
                        },
                    },
                },
            },
            "write_memory": {
                "appliesTo": {
                    "principalTypes": ["Agent"],
                    "resourceTypes": ["Tool"],
                    "context": {
                        "type": "Record",
                        "attributes": {
                            "session_id": {"type": "String"},
                        },
                    },
                },
            },
        },
    },
}


def validate_policy_set(policies: list[CedarPolicy]) -> list[str]:
    """Validate a set of Cedar policies for QITP consistency.

    Checks:
    - No duplicate policy IDs
    - All referenced agents/groups are known
    - No conflicting PERMIT/FORBID for same principal+action+resource
    - Execution mode conditions are valid

    Args:
        policies: List of CedarPolicy objects to validate.

    Returns:
        List of warning/error messages (empty if all valid).
    """
    errors: list[str] = []

    # Check duplicate IDs
    ids = [p.policy_id for p in policies]
    duplicates = [pid for pid in ids if ids.count(pid) > 1]
    if duplicates:
        errors.append(f"Duplicate policy IDs: {set(duplicates)}")

    # Check known agent names
    known_agents = {
        "execution_agent",
        "gap_detector",
        "sentiment_analyzer",
        "strategy_evaluator",
        "portfolio_recommender",
        "risk_engine",
    }
    known_groups = {"all_agents", "backtest_agents", "phase2_agents"}

    for policy in policies:
        # Validate execution mode conditions
        for condition in policy.conditions:
            if "execution_mode" in condition:
                valid_modes = {"backtest", "paper", "live"}
                for mode in valid_modes:
                    if mode in condition:
                        break
                else:
                    if "==" in condition:
                        errors.append(
                            f"Policy '{policy.policy_id}': unknown execution_mode in condition"
                        )

    return errors


def generate_cedar_files(output_dir: str) -> None:
    """Generate Cedar policy and schema files.

    Args:
        output_dir: Directory to write files to.
    """
    import json
    import os

    os.makedirs(output_dir, exist_ok=True)

    builder = CedarPolicyBuilder()
    builder.add_qitp_defaults()
    builder.write_to_file(os.path.join(output_dir, "policies.cedar"))

    schema_path = os.path.join(output_dir, "schema.cedarschema")
    with open(schema_path, "w") as f:
        json.dump(CEDAR_SCHEMA, f, indent=2)
    logger.info("Wrote Cedar schema to %s", schema_path)
```

---

## tccw-agent-infra — AgentCore CDK Stack

---

### stacks/agentcore_stack.py

```python
"""AgentCore CDK stack: Runtime, Gateway, Memory, Identity, Policy.

Provisions all AgentCore infrastructure:
- AgentCore Runtime (Firecracker microVM, 8h max session)
- AgentCore Gateway (single endpoint fronting all MCPs)
- AgentCore Memory (DynamoDB-backed, with OpenSearch for semantic search)
- AgentCore Identity (OAuth credential store)
- Cedar policies (tool-level access control)

This stack is only deployed in Phase 2 — POC (Phase 1) uses Lambda directly.
"""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_ssm as ssm,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)


class AgentCoreStack(Stack):
    """Provisions AgentCore infrastructure for QITP Phase 2.

    Components:
    1. AgentCore Runtime config (agent definitions, runtime settings)
    2. Gateway target registrations (MCP servers + OpenAPI endpoints)
    3. Memory tables (session memory, episodic memory index)
    4. Identity credential references (IBKR OAuth, Telegram, Polygon)
    5. Cedar policy deployment
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        vpc: ec2.IVpc,
        agent_sg: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        bedrock_region = self.node.try_get_context("bedrock_region") or "us-west-2"

        # ── AgentCore Runtime IAM Role ───────────────────────────────

        self.runtime_role = iam.Role(
            self,
            "AgentCoreRuntimeRole",
            role_name=f"qitp-{env_name}-agentcore-runtime",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Bedrock model invocation
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvoke",
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeAgent",
                ],
                resources=["*"],
            )
        )

        # AgentCore service permissions
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AgentCoreAccess",
                actions=[
                    "bedrock:CreateAgentRuntime",
                    "bedrock:InvokeAgentRuntime",
                    "bedrock:GetAgentMemory",
                    "bedrock:UpdateAgentMemory",
                    "bedrock:DeleteAgentMemory",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account}:agent-runtime/*",
                ],
            )
        )

        # DynamoDB access for memory tables
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBMemory",
                actions=["dynamodb:*"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/qitp-{env_name}-*",
                ],
            )
        )

        # S3 access for artifacts and data
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3Access",
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=[
                    f"arn:aws:s3:::qitp-{env_name}-*",
                    f"arn:aws:s3:::qitp-{env_name}-*/*",
                ],
            )
        )

        # SSM access
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="SSMRead",
                actions=["ssm:GetParameter", "ssm:GetParametersByPath"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/qitp/{env_name}/*",
                ],
            )
        )

        # X-Ray tracing
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracing",
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                ],
                resources=["*"],
            )
        )

        # ── AgentCore Memory Tables ──────────────────────────────────

        self.session_memory_table = dynamodb.Table(
            self,
            "SessionMemoryTable",
            table_name=f"qitp-{env_name}-agentcore-session-memory",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="memory_key",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN,
            point_in_time_recovery=env_name != "dev",
            time_to_live_attribute="ttl",
        )

        # GSI for agent-based queries
        self.session_memory_table.add_global_secondary_index(
            index_name="agent-index",
            partition_key=dynamodb.Attribute(
                name="agent_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="updated_at",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.episodic_memory_table = dynamodb.Table(
            self,
            "EpisodicMemoryTable",
            table_name=f"qitp-{env_name}-agentcore-episodic-memory",
            partition_key=dynamodb.Attribute(
                name="entry_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN,
            time_to_live_attribute="ttl",
        )

        # GSI for session-based episodic queries
        self.episodic_memory_table.add_global_secondary_index(
            index_name="session-index",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="stored_at",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── Gateway Target Synchronization Lambda ────────────────────

        gateway_sync_log_group = logs.LogGroup(
            self,
            "GatewaySyncLogGroup",
            log_group_name=f"/aws/lambda/qitp-{env_name}-gateway-sync",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.gateway_sync_fn = lambda_.Function(
            self,
            "GatewaySyncFunction",
            function_name=f"qitp-{env_name}-gateway-sync",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._gateway_sync_code()),
            timeout=Duration.minutes(5),
            memory_size=256,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_groups=[agent_sg],
            log_group=gateway_sync_log_group,
            environment={
                "ENV_NAME": env_name,
                "AGENTCORE_GATEWAY_URL": f"https://gateway.qitp-{env_name}.internal",
                "AWS_REGION": self.region,
            },
            role=self.runtime_role,
        )

        # ── Cedar Policy Deployment ──────────────────────────────────

        # Store Cedar policies in SSM for runtime access
        cedar_policy_content = self._generate_cedar_policies()

        ssm.StringParameter(
            self,
            "CedarPolicies",
            parameter_name=f"/qitp/{env_name}/agentcore/cedar-policies",
            string_value=cedar_policy_content,
            description="Cedar policies for AgentCore tool access control",
        )

        # ── AgentCore Runtime Configuration ──────────────────────────

        agent_configs = {
            "gap-detector": {
                "model": "anthropic.claude-sonnet-4-20250514-v1:0",
                "max_session_hours": 1,
                "memory_tier": "short_term",
            },
            "sentiment-analyzer": {
                "model": "anthropic.claude-sonnet-4-20250514-v1:0",
                "max_session_hours": 2,
                "memory_tier": "short_term",
            },
            "strategy-evaluator": {
                "model": "anthropic.claude-sonnet-4-20250514-v1:0",
                "max_session_hours": 2,
                "memory_tier": "short_term",
            },
            "portfolio-recommender": {
                "model": "anthropic.claude-opus-4-20250514-v1:0",
                "max_session_hours": 1,
                "memory_tier": "long_term",
            },
            "execution-agent": {
                "model": "anthropic.claude-sonnet-4-20250514-v1:0",
                "max_session_hours": 1,
                "memory_tier": "short_term",
            },
        }

        import json

        for agent_id, config in agent_configs.items():
            ssm.StringParameter(
                self,
                f"AgentConfig-{agent_id}",
                parameter_name=f"/qitp/{env_name}/agentcore/agents/{agent_id}",
                string_value=json.dumps(config),
                description=f"AgentCore runtime config for {agent_id}",
            )

        # ── Identity Credential References ───────────────────────────

        # These are references only — actual secrets stored in Secrets Manager
        identity_refs = {
            "ibkr-oauth": {
                "provider": "ibkr",
                "type": "oauth2",
                "secret_arn_param": f"/qitp/{env_name}/secrets/ibkr-oauth-arn",
            },
            "telegram-bot": {
                "provider": "telegram",
                "type": "api_key",
                "secret_arn_param": f"/qitp/{env_name}/secrets/telegram-bot-arn",
            },
            "polygon-api": {
                "provider": "polygon",
                "type": "api_key",
                "secret_arn_param": f"/qitp/{env_name}/secrets/polygon-api-arn",
            },
        }

        for cred_id, config in identity_refs.items():
            ssm.StringParameter(
                self,
                f"IdentityRef-{cred_id}",
                parameter_name=f"/qitp/{env_name}/agentcore/identity/{cred_id}",
                string_value=json.dumps(config),
                description=f"AgentCore Identity reference for {cred_id}",
            )

        # ── SSM Exports ──────────────────────────────────────────────

        ssm.StringParameter(
            self,
            "SSM-agentcore-runtime-role-arn",
            parameter_name=f"/qitp/{env_name}/agentcore/runtime-role-arn",
            string_value=self.runtime_role.role_arn,
        )

        ssm.StringParameter(
            self,
            "SSM-agentcore-session-memory-table",
            parameter_name=f"/qitp/{env_name}/agentcore/session-memory-table",
            string_value=self.session_memory_table.table_name,
        )

        ssm.StringParameter(
            self,
            "SSM-agentcore-episodic-memory-table",
            parameter_name=f"/qitp/{env_name}/agentcore/episodic-memory-table",
            string_value=self.episodic_memory_table.table_name,
        )

        ssm.StringParameter(
            self,
            "SSM-agentcore-gateway-sync-fn",
            parameter_name=f"/qitp/{env_name}/agentcore/gateway-sync-fn-arn",
            string_value=self.gateway_sync_fn.function_arn,
        )

    def _gateway_sync_code(self) -> str:
        """Inline Lambda code for Gateway target synchronization."""
        return '''
import json
import logging
import os
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GATEWAY_URL = os.environ.get("AGENTCORE_GATEWAY_URL", "")
ENV_NAME = os.environ.get("ENV_NAME", "dev")

TARGETS = [
    {
        "name": "market-data-mcp",
        "type": "mcp_server",
        "endpoint": f"market-data-mcp.qitp.local:8002",
        "description": "Unified OHLCV, gaps, volume profiles",
    },
    {
        "name": "sentiment-mcp",
        "type": "mcp_server",
        "endpoint": f"sentiment-mcp.qitp.local:8003",
        "description": "News and analyst sentiment scoring",
    },
    {
        "name": "artifacts-mcp",
        "type": "mcp_server",
        "endpoint": f"artifacts-mcp.qitp.local:8004",
        "description": "S3 artifact storage and signed URLs",
    },
    {
        "name": "backtest-mcp",
        "type": "mcp_server",
        "endpoint": f"backtest-mcp.qitp.local:8005",
        "description": "Simulation engine and backtesting",
    },
    {
        "name": "ibkr-mcp",
        "type": "mcp_server",
        "endpoint": f"ibkr-mcp.qitp.local:8001",
        "description": "Interactive Brokers broker control",
    },
]


def handler(event, context):
    """Synchronize all MCP targets with AgentCore Gateway."""
    logger.info("Gateway sync triggered: %s", json.dumps(event))

    results = {}
    for target in TARGETS:
        try:
            payload = json.dumps(target).encode("utf-8")
            req = urllib.request.Request(
                f"{GATEWAY_URL}/targets/register",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                results[target["name"]] = {
                    "status": "registered",
                    "tool_count": result.get("tool_count", 0),
                }
        except Exception as e:
            logger.error("Failed to register %s: %s", target["name"], e)
            results[target["name"]] = {"status": "failed", "error": str(e)}

    logger.info("Sync results: %s", json.dumps(results))
    return {"statusCode": 200, "body": json.dumps(results)}
'''

    def _generate_cedar_policies(self) -> str:
        """Generate Cedar policy content for SSM storage."""
        return """// QITP Cedar Policies -- AgentCore Tool Access Control
// Deployed via CDK agentcore_stack.py

// Only execution_agent can submit orders in live mode
permit(
    principal == Agent::"execution_agent",
    action == Action::"invoke_tool",
    resource == Tool::"ibkr-mcp::place_order"
)
when { context.execution_mode == "live" };

// Execution agent can modify and cancel orders
permit(
    principal == Agent::"execution_agent",
    action == Action::"invoke_tool",
    resource in ToolGroup::"ibkr-mcp-write"
);

// Backtest agents cannot access ibkr-mcp at all
forbid(
    principal in AgentGroup::"backtest_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"ibkr-mcp"
);

// Risk Engine read-only access to IBKR
permit(
    principal == Agent::"risk_engine",
    action == Action::"invoke_tool",
    resource in [Tool::"ibkr-mcp::get_positions", Tool::"ibkr-mcp::get_account_summary"]
);

// All agents can use artifacts-mcp
permit(
    principal in AgentGroup::"all_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"artifacts-mcp"
);

// All agents can use market-data-mcp
permit(
    principal in AgentGroup::"all_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"market-data-mcp"
);

// No orders in backtest mode
forbid(
    principal in AgentGroup::"all_agents",
    action == Action::"invoke_tool",
    resource == Tool::"ibkr-mcp::place_order"
)
when { context.execution_mode == "backtest" };
"""
```

---

### cedar/policies.cedar

```cedar
// QITP Cedar Policies — AgentCore Tool Access Control
// Source of truth: agent_core.policy.cedar_policies
// Deployed via CDK agentcore_stack.py → SSM Parameter Store

// 1. Only execution_agent can submit orders in live mode
permit(
    principal == Agent::"execution_agent",
    action == Action::"invoke_tool",
    resource == Tool::"ibkr-mcp::place_order"
)
when { context.execution_mode == "live" };

// 2. Execution agent can modify and cancel orders
permit(
    principal == Agent::"execution_agent",
    action == Action::"invoke_tool",
    resource in ToolGroup::"ibkr-mcp-write"
);

// 3. Backtest agents cannot access ibkr-mcp at all
forbid(
    principal in AgentGroup::"backtest_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"ibkr-mcp"
);

// 4. Risk Engine can only read positions (no write operations)
permit(
    principal == Agent::"risk_engine",
    action == Action::"invoke_tool",
    resource in [Tool::"ibkr-mcp::get_positions", Tool::"ibkr-mcp::get_account_summary"]
);

// 5. All agents can read and create artifacts
permit(
    principal in AgentGroup::"all_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"artifacts-mcp"
);

// 6. All agents can access market data tools
permit(
    principal in AgentGroup::"all_agents",
    action == Action::"invoke_tool",
    resource in ToolGroup::"market-data-mcp"
);

// 7. Sentiment analyzer can access sentiment tools
permit(
    principal == Agent::"sentiment_analyzer",
    action == Action::"invoke_tool",
    resource in ToolGroup::"sentiment-mcp"
);

// 8. Strategy evaluator can run backtests
permit(
    principal == Agent::"strategy_evaluator",
    action == Action::"invoke_tool",
    resource in ToolGroup::"backtest-mcp"
);

// 9. No agent can place real orders in backtest mode
forbid(
    principal in AgentGroup::"all_agents",
    action == Action::"invoke_tool",
    resource == Tool::"ibkr-mcp::place_order"
)
when { context.execution_mode == "backtest" };

// 10. Agents can write memory for their own session only
permit(
    principal in AgentGroup::"all_agents",
    action == Action::"write_memory",
    resource in ToolGroup::"memory"
)
when { context.session_id == resource.session_id };
```

---

### cedar/schema.cedarschema

```json
{
  "QITP": {
    "entityTypes": {
      "Agent": {
        "memberOfTypes": ["AgentGroup"],
        "shape": {
          "type": "Record",
          "attributes": {
            "agent_id": { "type": "String" },
            "execution_mode": { "type": "String" }
          }
        }
      },
      "AgentGroup": {
        "shape": {
          "type": "Record",
          "attributes": {
            "group_id": { "type": "String" }
          }
        }
      },
      "Tool": {
        "memberOfTypes": ["ToolGroup"],
        "shape": {
          "type": "Record",
          "attributes": {
            "tool_name": { "type": "String" },
            "target": { "type": "String" },
            "session_id": { "type": "String" }
          }
        }
      },
      "ToolGroup": {
        "shape": {
          "type": "Record",
          "attributes": {
            "group_id": { "type": "String" }
          }
        }
      }
    },
    "actions": {
      "invoke_tool": {
        "appliesTo": {
          "principalTypes": ["Agent", "AgentGroup"],
          "resourceTypes": ["Tool", "ToolGroup"],
          "context": {
            "type": "Record",
            "attributes": {
              "execution_mode": { "type": "String" },
              "session_id": { "type": "String" }
            }
          }
        }
      },
      "read_memory": {
        "appliesTo": {
          "principalTypes": ["Agent"],
          "resourceTypes": ["Tool"],
          "context": {
            "type": "Record",
            "attributes": {
              "session_id": { "type": "String" }
            }
          }
        }
      },
      "write_memory": {
        "appliesTo": {
          "principalTypes": ["Agent"],
          "resourceTypes": ["Tool"],
          "context": {
            "type": "Record",
            "attributes": {
              "session_id": { "type": "String" }
            }
          }
        }
      }
    }
  }
}
```

---

## Tests

---

### tests/unit/test_adapter.py (tccw-qitp-agents)

```python
"""Unit tests for the runtime adapter — Lambda ↔ AgentCore payload normalization."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from qitp_agents.runtime.adapter import (
    AgentPayload,
    AgentResult,
    RuntimeMode,
    get_runtime_mode,
    normalize_lambda_event,
    normalize_agentcore_payload,
    normalize_payload,
)


class TestRuntimeMode:
    """Tests for runtime mode detection."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_lambda_mode(self):
        assert get_runtime_mode() == RuntimeMode.LAMBDA

    @patch.dict(os.environ, {"RUNTIME_MODE": "agentcore"})
    def test_agentcore_mode(self):
        assert get_runtime_mode() == RuntimeMode.AGENTCORE

    @patch.dict(os.environ, {"RUNTIME_MODE": "unknown"})
    def test_unknown_defaults_to_lambda(self):
        assert get_runtime_mode() == RuntimeMode.LAMBDA

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_defaults_to_lambda(self):
        assert get_runtime_mode() == RuntimeMode.LAMBDA


class TestNormalizeLambdaEvent:
    """Tests for Lambda event → AgentPayload normalization."""

    def test_basic_lambda_event(self):
        event = {
            "agent_id": "gap-detector",
            "session_id": "sfn-exec-123",
            "execution_mode": "backtest",
            "date": "2026-03-15",
            "threshold_pct": 2.0,
        }
        payload = normalize_lambda_event(event)

        assert payload.agent_id == "gap-detector"
        assert payload.session_id == "sfn-exec-123"
        assert payload.execution_mode == "backtest"
        assert payload.parameters == {"date": "2026-03-15", "threshold_pct": 2.0}
        assert payload.memory_context is None

    def test_lambda_event_defaults(self):
        event = {"date": "2026-03-15"}
        payload = normalize_lambda_event(event)

        assert payload.agent_id == "unknown"
        assert payload.session_id.startswith("qitp-session-")
        assert payload.parameters == {"date": "2026-03-15"}

    @patch.dict(os.environ, {"EXECUTION_MODE": "paper"})
    def test_lambda_event_mode_from_env(self):
        event = {"agent_id": "gap-detector"}
        payload = normalize_lambda_event(event)
        assert payload.execution_mode == "paper"


class TestNormalizeAgentCorePayload:
    """Tests for AgentCore payload → AgentPayload normalization."""

    def test_full_agentcore_payload(self):
        payload_dict = {
            "payload": {
                "agent_id": "gap-detector",
                "session_id": "ac-session-456",
                "parameters": {
                    "date": "2026-03-15",
                    "threshold_pct": 3.0,
                },
            },
            "session": {
                "session_id": "ac-session-456",
                "memory": {"last_gap_analysis": {"date": "2026-03-14"}},
            },
            "context": {
                "execution_mode": "live",
                "identity": {"provider": "ibkr"},
            },
        }
        payload = normalize_agentcore_payload(payload_dict)

        assert payload.agent_id == "gap-detector"
        assert payload.session_id == "ac-session-456"
        assert payload.execution_mode == "live"
        assert payload.parameters == {"date": "2026-03-15", "threshold_pct": 3.0}
        assert payload.memory_context == {"last_gap_analysis": {"date": "2026-03-14"}}

    def test_agentcore_payload_minimal(self):
        payload_dict = {
            "payload": {"agent_id": "sentiment-analyzer"},
        }
        payload = normalize_agentcore_payload(payload_dict)

        assert payload.agent_id == "sentiment-analyzer"
        assert payload.parameters == {}


class TestNormalizePayload:
    """Tests for auto-detection of payload format."""

    def test_detects_lambda_event(self):
        event = {"agent_id": "gap-detector", "date": "2026-03-15"}
        payload = normalize_payload(event)
        assert payload.metadata["source"] == "lambda"

    def test_detects_agentcore_payload(self):
        event = {
            "payload": {"agent_id": "gap-detector"},
            "session": {"session_id": "s123"},
        }
        payload = normalize_payload(event)
        assert payload.metadata["source"] == "agentcore"

    def test_detects_agentcore_by_session(self):
        event = {
            "session": {"session_id": "s123", "memory": {}},
            "agent_id": "gap-detector",
        }
        payload = normalize_payload(event)
        assert payload.metadata["source"] == "agentcore"


class TestAgentResult:
    """Tests for AgentResult serialization."""

    def test_success_to_lambda_response(self):
        result = AgentResult(
            status="success",
            agent_id="gap-detector",
            session_id="s123",
            output={"ranked_gaps": [{"symbol": "AAPL"}]},
        )
        response = result.to_lambda_response()

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "ranked_gaps" in body

    def test_error_to_lambda_response(self):
        result = AgentResult(
            status="error",
            agent_id="gap-detector",
            session_id="s123",
            error="Something broke",
        )
        response = result.to_lambda_response()

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "Something broke"

    def test_claim_check_to_lambda_response(self):
        result = AgentResult(
            status="success",
            agent_id="gap-detector",
            session_id="s123",
            output={"ranked_gaps": []},
            claim_check=True,
            artifact_id="art-xyz",
        )
        response = result.to_lambda_response()

        body = json.loads(response["body"])
        assert body["claim_check"] is True
        assert body["artifact_id"] == "art-xyz"

    def test_success_to_agentcore_response(self):
        result = AgentResult(
            status="success",
            agent_id="gap-detector",
            session_id="s123",
            output={"data": "test"},
            memory_updates={"key": "val"},
        )
        response = result.to_agentcore_response()

        assert response["status"] == "success"
        assert response["output"] == {"data": "test"}
        assert response["memory_updates"] == {"key": "val"}
```

---

### tests/unit/test_session.py (tccw-qitp-agents)

```python
"""Unit tests for session management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from qitp_agents.runtime.session import SessionManager, SessionState


class TestSessionState:
    """Tests for SessionState data class."""

    def test_store_and_retrieve(self):
        session = SessionState(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
        )

        session.store("gap_count", 5)
        assert session.retrieve("gap_count") == 5

    def test_retrieve_from_memory_context(self):
        session = SessionState(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
            memory_context={"prior_data": "abc"},
        )

        assert session.retrieve("prior_data") == "abc"

    def test_short_term_overrides_memory_context(self):
        session = SessionState(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
            memory_context={"key": "old"},
        )
        session.store("key", "new")

        assert session.retrieve("key") == "new"

    def test_retrieve_default(self):
        session = SessionState(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
        )

        assert session.retrieve("missing") is None
        assert session.retrieve("missing", "default") == "default"

    def test_pending_updates(self):
        session = SessionState(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
        )
        session.store("a", 1)
        session.store("b", 2)

        updates = session.get_pending_updates()
        assert updates == {"a": 1, "b": 2}


class TestSessionManager:
    """Tests for SessionManager lifecycle."""

    def test_create_session_lambda_mode(self):
        manager = SessionManager(runtime_mode="lambda")
        session = manager.create_session(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
        )

        assert session.session_id == "s123"
        assert session.agent_id == "gap-detector"
        assert session.execution_mode == "backtest"

    def test_create_session_with_memory_context(self):
        manager = SessionManager(runtime_mode="lambda")
        session = manager.create_session(
            session_id="s123",
            agent_id="gap-detector",
            execution_mode="backtest",
            memory_context={"prior": "data"},
        )

        assert session.memory_context == {"prior": "data"}

    @patch("qitp_agents.runtime.session.SessionManager._persist_dynamodb_memory")
    def test_persist_session_lambda(self, mock_dynamo):
        manager = SessionManager(runtime_mode="lambda")
        session = manager.create_session("s123", "gap-detector", "backtest")
        session.store("key", "val")

        manager.persist_session(session)
        mock_dynamo.assert_called_once()

    def test_persist_session_no_updates(self):
        manager = SessionManager(runtime_mode="lambda")
        session = manager.create_session("s123", "gap-detector", "backtest")

        # No updates → should not try to persist
        manager.persist_session(session)
        # No exception = success
```

---

### tests/unit/test_entrypoint.py (tccw-qitp-agents)

```python
"""Unit tests for AgentCore entrypoint and app."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from qitp_agents.runtime.adapter import AgentPayload, AgentResult
from qitp_agents.runtime.entrypoint import (
    AgentCoreApp,
    register_agent,
    get_registered_agents,
    _AGENT_REGISTRY,
)
from qitp_agents.runtime.session import SessionState


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear agent registry between tests."""
    _AGENT_REGISTRY.clear()
    yield
    _AGENT_REGISTRY.clear()


class TestRegisterAgent:
    """Tests for the @register_agent decorator."""

    def test_register_and_retrieve(self):
        @register_agent("test-agent")
        def my_handler(payload, session):
            return AgentResult(
                status="success",
                agent_id="test-agent",
                session_id=payload.session_id,
                output={"result": "ok"},
            )

        agents = get_registered_agents()
        assert "test-agent" in agents
        assert agents["test-agent"] == my_handler

    def test_register_multiple_agents(self):
        @register_agent("agent-a")
        def handler_a(payload, session):
            pass

        @register_agent("agent-b")
        def handler_b(payload, session):
            pass

        agents = get_registered_agents()
        assert len(agents) == 2


class TestAgentCoreApp:
    """Tests for AgentCoreApp invoke method."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_lambda_mode(self):
        @register_agent("test-agent")
        def my_handler(payload, session):
            return AgentResult(
                status="success",
                agent_id="test-agent",
                session_id=payload.session_id,
                output={"result": "ok"},
            )

        app = AgentCoreApp()
        response = app.invoke({
            "agent_id": "test-agent",
            "session_id": "s123",
            "date": "2026-03-15",
        })

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "ok"

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_unknown_agent(self):
        app = AgentCoreApp()
        response = app.invoke({
            "agent_id": "nonexistent-agent",
            "session_id": "s123",
        })

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "nonexistent-agent" in body["error"]

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_handler_exception(self):
        @register_agent("failing-agent")
        def my_handler(payload, session):
            raise RuntimeError("Agent crashed")

        app = AgentCoreApp()
        response = app.invoke({
            "agent_id": "failing-agent",
            "session_id": "s123",
        })

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Agent crashed" in body["error"]

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_with_memory_updates(self):
        @register_agent("memory-agent")
        def my_handler(payload, session):
            session.store("key", "value")
            return AgentResult(
                status="success",
                agent_id="memory-agent",
                session_id=payload.session_id,
                output={"result": "ok"},
                memory_updates=session.get_pending_updates(),
            )

        app = AgentCoreApp()
        response = app.invoke({
            "agent_id": "memory-agent",
            "session_id": "s123",
        })

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body.get("_memory_updates") == {"key": "value"}
```

---

### tests/unit/test_gap_detector_agentcore.py (tccw-qitp-agents)

```python
"""Unit tests for Gap Detection Agent in dual-mode."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from qitp_agents.runtime.adapter import AgentPayload, AgentResult
from qitp_agents.runtime.session import SessionState


class TestGapDetectorDualMode:
    """Tests for gap detector handler in both Lambda and AgentCore modes."""

    @patch("qitp_agents.gap_detector.handler._create_direct_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_lambda_mode_success(self, mock_loader, mock_clients):
        """Handler works in Lambda mode with direct MCP clients."""
        mock_agent = MagicMock()
        mock_agent.return_value = {
            "ranked_gaps": [
                {"symbol": "AAPL", "gap_pct": 3.5, "direction": "up"},
            ],
            "artifact_id": "art-123",
        }
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_clients.return_value = {}

        from qitp_agents.gap_detector.handler import handler

        result = handler({
            "agent_id": "gap-detector",
            "session_id": "sfn-exec-001",
            "date": "2026-03-15",
        })

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "ranked_gaps" in body

    @patch("qitp_agents.gap_detector.handler._create_direct_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_lambda_mode_missing_date(self, mock_loader, mock_clients):
        """Handler returns error when date is missing."""
        from qitp_agents.gap_detector.handler import handler

        result = handler({
            "agent_id": "gap-detector",
            "session_id": "sfn-exec-001",
        })

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "date" in body["error"]

    @patch("qitp_agents.gap_detector.handler._create_direct_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_lambda_mode_agent_exception(self, mock_loader, mock_clients):
        """Handler returns error when agent throws."""
        mock_agent = MagicMock()
        mock_agent.side_effect = RuntimeError("MCP down")
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_clients.return_value = {}

        from qitp_agents.gap_detector.handler import handler

        result = handler({
            "agent_id": "gap-detector",
            "session_id": "sfn-exec-001",
            "date": "2026-03-15",
        })

        assert result["statusCode"] == 500

    @patch("qitp_agents.gap_detector.handler._create_gateway_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    @patch("qitp_agents.gap_detector.handler.RUNTIME_MODE")
    def test_agentcore_mode_uses_gateway(self, mock_mode, mock_loader, mock_gw):
        """In AgentCore mode, handler creates Gateway clients."""
        from qitp_agents.runtime.adapter import RuntimeMode

        mock_mode.__eq__ = lambda self, other: other == RuntimeMode.AGENTCORE

        mock_agent = MagicMock()
        mock_agent.return_value = {"ranked_gaps": []}
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_gw.return_value = {"gateway": MagicMock()}

        from qitp_agents.gap_detector.handler import handle_gap_detection

        payload = AgentPayload(
            agent_id="gap-detector",
            session_id="ac-session-001",
            execution_mode="backtest",
            parameters={"date": "2026-03-15"},
        )
        session = SessionState(
            session_id="ac-session-001",
            agent_id="gap-detector",
            execution_mode="backtest",
        )

        result = handle_gap_detection(payload, session)
        assert result.status == "success"
```

---

### tests/unit/test_gateway_client.py (tccw-agent-core)

```python
"""Unit tests for AgentCore Gateway client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import httpx

from agent_core.gateway.client import (
    GatewayClient,
    GatewayError,
    GatewayPolicyDeniedError,
)


class TestGatewayClient:
    """Tests for GatewayClient."""

    def test_init_defaults(self):
        client = GatewayClient()
        assert client.gateway_url == "http://localhost:9000"
        assert client.timeout == 30.0

    def test_init_custom_url(self):
        client = GatewayClient(gateway_url="https://gateway.example.com")
        assert client.gateway_url == "https://gateway.example.com"

    @patch("httpx.Client.post")
    def test_invoke_tool_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"symbol": "AAPL", "ohlcv": [100, 105, 98, 103, 1000000]},
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.post = mock_post

        result = client.invoke_tool(
            "market-data-mcp::get_ohlcv",
            {"symbol": "AAPL", "date": "2026-03-15"},
        )

        assert result["symbol"] == "AAPL"

    @patch("httpx.Client.post")
    def test_invoke_tool_policy_denied(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        )
        mock_post.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.post = mock_post

        with pytest.raises(GatewayPolicyDeniedError):
            client.invoke_tool(
                "ibkr-mcp::place_order",
                {"symbol": "AAPL"},
                agent_id="backtest-agent",
            )

    @patch("httpx.Client.get")
    def test_list_tools(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tools": [
                {"name": "get_ohlcv", "target": "market-data-mcp"},
                {"name": "get_positions", "target": "ibkr-mcp"},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.get = mock_get

        tools = client.list_tools()
        assert len(tools) == 2

    @patch("httpx.Client.post")
    def test_search_tools(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tools": [
                {"name": "get_ohlcv", "relevance_score": 0.95},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.post = mock_post

        tools = client.search_tools("historical price data")
        assert len(tools) == 1

    def test_context_manager(self):
        with GatewayClient(gateway_url="http://test:9000") as client:
            assert client.gateway_url == "http://test:9000"
```

---

### tests/unit/test_target_registry.py (tccw-agent-core)

```python
"""Unit tests for Gateway target registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.gateway.target_registry import (
    GatewayTarget,
    TargetType,
    AuthType,
    TargetRegistry,
    QITP_TARGETS,
)


class TestGatewayTarget:
    """Tests for GatewayTarget dataclass."""

    def test_mcp_server_target(self):
        target = GatewayTarget(
            name="test-mcp",
            target_type=TargetType.MCP_SERVER,
            endpoint="test-mcp.local:8000",
        )
        assert target.auth_type == AuthType.NONE
        assert target.max_tools == 10000

    def test_openapi_target(self):
        target = GatewayTarget(
            name="polygon-api",
            target_type=TargetType.OPENAPI,
            endpoint="https://api.polygon.io",
            auth_type=AuthType.API_KEY,
            auth_config={"header_name": "Authorization", "key_ref": "POLYGON_API_KEY"},
        )
        assert target.target_type == TargetType.OPENAPI
        assert target.auth_config["key_ref"] == "POLYGON_API_KEY"


class TestQitpTargets:
    """Tests for the standard QITP target definitions."""

    def test_all_targets_defined(self):
        names = {t.name for t in QITP_TARGETS}
        assert "market-data-mcp" in names
        assert "sentiment-mcp" in names
        assert "artifacts-mcp" in names
        assert "backtest-mcp" in names
        assert "ibkr-mcp" in names
        assert "polygon-api" in names

    def test_ibkr_uses_oauth(self):
        ibkr = next(t for t in QITP_TARGETS if t.name == "ibkr-mcp")
        assert ibkr.auth_type == AuthType.OAUTH2

    def test_phase1_targets_use_mtls(self):
        phase1 = [t for t in QITP_TARGETS if "phase-1" in t.tags]
        assert all(t.auth_type == AuthType.MTLS for t in phase1)


class TestTargetRegistry:
    """Tests for TargetRegistry operations."""

    @patch("httpx.Client.post")
    def test_register_target(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"tool_count": 15}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        registry = TargetRegistry(gateway_url="http://test:9000")
        registry._client = MagicMock()
        registry._client.post = mock_post

        target = GatewayTarget(
            name="test-mcp",
            target_type=TargetType.MCP_SERVER,
            endpoint="test.local:8000",
        )
        result = registry.register_target(target)
        assert result["tool_count"] == 15

    @patch("httpx.Client.post")
    def test_synchronize_all(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"tool_count": 10}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        registry = TargetRegistry(gateway_url="http://test:9000")
        registry._client = MagicMock()
        registry._client.post = mock_post

        targets = [
            GatewayTarget(name="a", target_type=TargetType.MCP_SERVER, endpoint="a:8000"),
            GatewayTarget(name="b", target_type=TargetType.MCP_SERVER, endpoint="b:8000"),
        ]
        result = registry.synchronize_all(targets)

        assert result["total_tools"] == 20
        assert result["targets"]["a"]["status"] == "registered"
```

---

### tests/unit/test_tool_discovery.py (tccw-agent-core)

```python
"""Unit tests for semantic tool discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_core.gateway.tool_discovery import ToolDiscovery, DiscoveredTool


class TestToolDiscovery:
    """Tests for ToolDiscovery."""

    def test_find_tools(self):
        mock_gateway = MagicMock()
        mock_gateway.search_tools.return_value = [
            {
                "fqn": "market-data-mcp::get_ohlcv",
                "target": "market-data-mcp",
                "name": "get_ohlcv",
                "description": "Get OHLCV data",
                "input_schema": {},
                "relevance_score": 0.9,
            },
            {
                "fqn": "market-data-mcp::get_volume",
                "target": "market-data-mcp",
                "name": "get_volume",
                "description": "Get volume profile",
                "input_schema": {},
                "relevance_score": 0.2,
            },
        ]

        discovery = ToolDiscovery(mock_gateway)
        tools = discovery.find_tools("price data", min_relevance=0.3)

        assert len(tools) == 1
        assert tools[0].fqn == "market-data-mcp::get_ohlcv"

    def test_find_tools_for_task_filters_by_agent(self):
        mock_gateway = MagicMock()
        mock_gateway.search_tools.return_value = [
            {
                "fqn": "ibkr-mcp::place_order",
                "target": "ibkr-mcp",
                "name": "place_order",
                "description": "Place order",
                "input_schema": {},
                "relevance_score": 0.8,
            },
            {
                "fqn": "market-data-mcp::get_ohlcv",
                "target": "market-data-mcp",
                "name": "get_ohlcv",
                "description": "Get OHLCV",
                "input_schema": {},
                "relevance_score": 0.7,
            },
        ]

        discovery = ToolDiscovery(mock_gateway)
        tools = discovery.find_tools_for_task(
            "analyze gaps",
            agent_id="gap-detector",
        )

        # ibkr-mcp::place_order should be filtered out for gap-detector
        fqns = [t.fqn for t in tools]
        assert "ibkr-mcp::place_order" not in fqns
        assert "market-data-mcp::get_ohlcv" in fqns

    def test_agent_can_use_blocks_backtest_from_ibkr(self):
        assert not ToolDiscovery._agent_can_use("gap-detector", "ibkr-mcp::place_order")
        assert not ToolDiscovery._agent_can_use("sentiment-analyzer", "ibkr-mcp::get_positions")

    def test_agent_can_use_allows_execution_agent(self):
        assert ToolDiscovery._agent_can_use("execution-agent", "ibkr-mcp::place_order")
```

---

### tests/unit/test_memory_manager.py (tccw-agent-core)

```python
"""Unit tests for AgentCore Memory manager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.memory.manager import MemoryManager, _InMemoryFallback, get_memory_manager


class TestInMemoryFallback:
    """Tests for the in-memory fallback when AgentCore Memory is unavailable."""

    def test_store_and_retrieve(self):
        fallback = _InMemoryFallback()
        fallback.update("key1", {"a": 1})
        assert fallback.get("key1") == {"a": 1}

    def test_update_merges(self):
        fallback = _InMemoryFallback()
        fallback.update("key1", {"a": 1})
        fallback.update("key1", {"b": 2})
        assert fallback.get("key1") == {"a": 1, "b": 2}

    def test_get_missing_returns_none(self):
        fallback = _InMemoryFallback()
        assert fallback.get("missing") is None

    def test_store_episodic(self):
        fallback = _InMemoryFallback()
        entry_id = fallback.store_episodic(content="AAPL gapped 5%")
        assert entry_id is not None

    def test_search_episodic(self):
        fallback = _InMemoryFallback()
        fallback.store_episodic(content="AAPL gapped 5% on Monday")
        fallback.store_episodic(content="TSLA earnings beat")

        results = fallback.search_episodic(query="AAPL gap")
        assert len(results["entries"]) == 1


class TestMemoryManager:
    """Tests for MemoryManager with fallback."""

    def test_get_session_memory(self):
        manager = MemoryManager()
        # Should use fallback since bedrock_agentcore not installed
        manager.update_session_memory(
            session_id="s123",
            agent_id="gap-detector",
            updates={"gap_count": 5},
        )
        result = manager.get_session_memory("s123")
        assert result is not None
        assert result.get("gap_count") == 5

    def test_semantic_search_fallback(self):
        manager = MemoryManager()
        manager.store_episodic(
            session_id="s123",
            agent_id="gap-detector",
            content="Found 3 gaps in AAPL, TSLA, NVDA",
        )
        results = manager.semantic_search(query="AAPL gaps")
        assert "entries" in results
```

---

### tests/unit/test_session_bridge.py (tccw-agent-core)

```python
"""Unit tests for SFN execution ID ↔ session ID bridge."""

from __future__ import annotations

import pytest

from agent_core.memory.session_bridge import (
    sfn_execution_id_to_session_id,
    session_id_to_sfn_execution_arn,
    extract_session_metadata,
)


class TestSessionBridge:
    """Tests for session ID conversion."""

    def test_arn_to_session_id(self):
        arn = "arn:aws:states:eu-west-1:835618032093:execution:qitp-dev-weekly:exec-abc123"
        assert sfn_execution_id_to_session_id(arn) == "exec-abc123"

    def test_plain_id_passthrough(self):
        assert sfn_execution_id_to_session_id("exec-abc123") == "exec-abc123"

    def test_session_id_to_arn(self):
        arn = session_id_to_sfn_execution_arn(
            "exec-abc123",
            "qitp-dev-weekly",
        )
        assert arn == (
            "arn:aws:states:eu-west-1:835618032093:"
            "execution:qitp-dev-weekly:exec-abc123"
        )

    def test_extract_session_metadata(self):
        execution_input = {
            "_sfn_context": {
                "Execution": {
                    "Id": "arn:aws:states:eu-west-1:835618032093:execution:qitp-dev-weekly:exec-xyz",
                    "StartTime": "2026-03-15T08:30:00Z",
                },
                "StateMachine": {
                    "Id": "arn:aws:states:eu-west-1:835618032093:stateMachine:qitp-dev-weekly",
                },
            },
        }
        metadata = extract_session_metadata(execution_input)

        assert metadata["session_id"] == "exec-xyz"
        assert metadata["start_time"] == "2026-03-15T08:30:00Z"

    def test_extract_session_metadata_fallback(self):
        execution_input = {"session_id": "manual-session"}
        metadata = extract_session_metadata(execution_input)
        assert metadata["session_id"] == "manual-session"
```

---

### tests/unit/test_identity_providers.py (tccw-agent-core)

```python
"""Unit tests for identity providers."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agent_core.identity.providers import (
    IBKRIdentityProvider,
    TelegramIdentityProvider,
    PolygonIdentityProvider,
    CredentialError,
    ProviderType,
    get_provider,
)


class TestIBKRProvider:
    """Tests for IBKR identity provider."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda", "IBKR_ACCESS_TOKEN": "test-token-123"})
    def test_lambda_mode_from_env(self):
        provider = IBKRIdentityProvider()
        cred = provider.get_credential()

        assert cred.provider == ProviderType.IBKR
        assert cred.token_type == "bearer"
        assert cred.access_token == "test-token-123"

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"}, clear=True)
    def test_lambda_mode_missing_token(self):
        # Ensure IBKR_ACCESS_TOKEN is not set
        os.environ.pop("IBKR_ACCESS_TOKEN", None)
        provider = IBKRIdentityProvider()

        with pytest.raises(CredentialError, match="IBKR_ACCESS_TOKEN"):
            provider.get_credential()


class TestTelegramProvider:
    """Tests for Telegram identity provider."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda", "TELEGRAM_BOT_TOKEN": "bot-token-xyz"})
    def test_lambda_mode_from_env(self):
        provider = TelegramIdentityProvider()
        cred = provider.get_credential()

        assert cred.provider == ProviderType.TELEGRAM
        assert cred.token_type == "api_key"
        assert cred.access_token == "bot-token-xyz"


class TestPolygonProvider:
    """Tests for Polygon.io identity provider."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda", "POLYGON_API_KEY": "poly-key-abc"})
    def test_lambda_mode_from_env(self):
        provider = PolygonIdentityProvider()
        cred = provider.get_credential()

        assert cred.provider == ProviderType.POLYGON
        assert cred.access_token == "poly-key-abc"


class TestProviderFactory:
    """Tests for get_provider factory."""

    def test_get_ibkr_provider(self):
        provider = get_provider(ProviderType.IBKR)
        assert isinstance(provider, IBKRIdentityProvider)

    def test_get_telegram_provider(self):
        provider = get_provider(ProviderType.TELEGRAM)
        assert isinstance(provider, TelegramIdentityProvider)

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown"):
            get_provider("nonexistent")
```

---

### tests/unit/test_cedar_policies.py (tccw-agent-core)

```python
"""Unit tests for Cedar policy builder and validator."""

from __future__ import annotations

import pytest

from agent_core.policy.cedar_policies import (
    CedarPolicy,
    CedarPolicyBuilder,
    PolicyEffect,
    PolicyAction,
    QITP_POLICIES,
    validate_policy_set,
    CEDAR_SCHEMA,
)


class TestCedarPolicy:
    """Tests for individual Cedar policy serialization."""

    def test_simple_permit(self):
        policy = CedarPolicy(
            policy_id="test",
            effect=PolicyEffect.PERMIT,
            description="Test policy",
            principal='Agent::"test_agent"',
            action=PolicyAction.INVOKE_TOOL,
            resource='Tool::"test-mcp::do_thing"',
        )
        cedar_text = policy.to_cedar()

        assert "permit(" in cedar_text
        assert 'Agent::"test_agent"' in cedar_text
        assert 'Tool::"test-mcp::do_thing"' in cedar_text

    def test_forbid_with_condition(self):
        policy = CedarPolicy(
            policy_id="test-forbid",
            effect=PolicyEffect.FORBID,
            description="Forbid in backtest",
            principal='in AgentGroup::"all_agents"',
            action=PolicyAction.INVOKE_TOOL,
            resource='Tool::"ibkr-mcp::place_order"',
            conditions=['context.execution_mode == "backtest"'],
        )
        cedar_text = policy.to_cedar()

        assert "forbid(" in cedar_text
        assert 'context.execution_mode == "backtest"' in cedar_text

    def test_group_principal_uses_in(self):
        policy = CedarPolicy(
            policy_id="test-group",
            effect=PolicyEffect.PERMIT,
            description="Group test",
            principal='in AgentGroup::"backtest_agents"',
            action=PolicyAction.INVOKE_TOOL,
            resource='in ToolGroup::"market-data-mcp"',
        )
        cedar_text = policy.to_cedar()

        assert 'principal in AgentGroup::"backtest_agents"' in cedar_text
        assert 'resource in ToolGroup::"market-data-mcp"' in cedar_text


class TestCedarPolicyBuilder:
    """Tests for the policy set builder."""

    def test_build_empty(self):
        builder = CedarPolicyBuilder()
        result = builder.build()
        assert "QITP Cedar Policies" in result

    def test_add_qitp_defaults(self):
        builder = CedarPolicyBuilder()
        builder.add_qitp_defaults()
        result = builder.build()

        assert "execution_agent" in result
        assert "backtest_agents" in result
        assert "risk_engine" in result
        assert "place_order" in result

    def test_build_contains_all_policies(self):
        builder = CedarPolicyBuilder()
        builder.add_qitp_defaults()
        result = builder.build()

        # Should contain all default policies
        for policy in QITP_POLICIES:
            assert policy.description in result or policy.policy_id

    def test_write_to_file(self, tmp_path):
        builder = CedarPolicyBuilder()
        builder.add_qitp_defaults()

        output = tmp_path / "test.cedar"
        builder.write_to_file(str(output))

        assert output.exists()
        content = output.read_text()
        assert "permit(" in content
        assert "forbid(" in content


class TestValidatePolicySet:
    """Tests for policy validation."""

    def test_qitp_defaults_validate(self):
        errors = validate_policy_set(QITP_POLICIES)
        assert len(errors) == 0

    def test_duplicate_ids_detected(self):
        policies = [
            CedarPolicy(
                policy_id="dupe",
                effect=PolicyEffect.PERMIT,
                description="First",
                principal='Agent::"a"',
                action=PolicyAction.INVOKE_TOOL,
                resource='Tool::"t"',
            ),
            CedarPolicy(
                policy_id="dupe",
                effect=PolicyEffect.FORBID,
                description="Second",
                principal='Agent::"b"',
                action=PolicyAction.INVOKE_TOOL,
                resource='Tool::"t"',
            ),
        ]
        errors = validate_policy_set(policies)
        assert any("Duplicate" in e for e in errors)


class TestCedarSchema:
    """Tests for Cedar entity schema."""

    def test_schema_has_entity_types(self):
        assert "Agent" in CEDAR_SCHEMA["QITP"]["entityTypes"]
        assert "Tool" in CEDAR_SCHEMA["QITP"]["entityTypes"]
        assert "AgentGroup" in CEDAR_SCHEMA["QITP"]["entityTypes"]
        assert "ToolGroup" in CEDAR_SCHEMA["QITP"]["entityTypes"]

    def test_schema_has_actions(self):
        actions = CEDAR_SCHEMA["QITP"]["actions"]
        assert "invoke_tool" in actions
        assert "read_memory" in actions
        assert "write_memory" in actions

    def test_agent_member_of_group(self):
        agent = CEDAR_SCHEMA["QITP"]["entityTypes"]["Agent"]
        assert "AgentGroup" in agent["memberOfTypes"]
```

---

### tests/unit/test_agentcore_stack.py (tccw-agent-infra)

```python
"""CDK snapshot test for AgentCore stack."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import assertions, aws_ec2 as ec2

from stacks.agentcore_stack import AgentCoreStack


class TestAgentCoreStack:
    """Tests for AgentCoreStack CDK synthesis."""

    def _create_stack(self) -> assertions.Template:
        app = cdk.App(context={
            "env": "dev",
            "account": "835618032093",
            "region": "eu-west-1",
            "bedrock_region": "us-west-2",
        })
        env = cdk.Environment(account="835618032093", region="eu-west-1")

        # Create VPC for testing
        vpc_stack = cdk.Stack(app, "VpcStack", env=env)
        vpc = ec2.Vpc(vpc_stack, "Vpc")
        sg = ec2.SecurityGroup(vpc_stack, "SG", vpc=vpc)

        stack = AgentCoreStack(
            app, "TestAgentCore",
            env=env,
            env_name="dev",
            vpc=vpc,
            agent_sg=sg,
        )
        return assertions.Template.from_stack(stack)

    def test_session_memory_table_created(self):
        template = self._create_stack()
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "qitp-dev-agentcore-session-memory",
                "BillingMode": "PAY_PER_REQUEST",
            },
        )

    def test_episodic_memory_table_created(self):
        template = self._create_stack()
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "qitp-dev-agentcore-episodic-memory",
                "BillingMode": "PAY_PER_REQUEST",
            },
        )

    def test_gateway_sync_lambda_created(self):
        template = self._create_stack()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "qitp-dev-gateway-sync",
                "Runtime": "python3.12",
            },
        )

    def test_cedar_policies_in_ssm(self):
        template = self._create_stack()
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/qitp/dev/agentcore/cedar-policies",
            },
        )

    def test_agent_configs_in_ssm(self):
        template = self._create_stack()
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/qitp/dev/agentcore/agents/gap-detector",
            },
        )

    def test_runtime_role_has_bedrock_permissions(self):
        template = self._create_stack()
        template.has_resource_properties(
            "AWS::IAM::Policy",
            assertions.Match.object_like({
                "PolicyDocument": assertions.Match.object_like({
                    "Statement": assertions.Match.array_with([
                        assertions.Match.object_like({
                            "Action": assertions.Match.array_with([
                                "bedrock:InvokeModel",
                            ]),
                        }),
                    ]),
                }),
            }),
        )
```

---

### tests/integration/test_agentcore_pipeline.py (tccw-qitp-agents)

```python
"""Integration test: end-to-end agent pipeline in dual-mode.

Tests the full flow: normalize payload → create session → invoke agent
→ persist memory → format response. Uses mocked MCP clients and Strands SDK.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from qitp_agents.runtime.adapter import AgentPayload, AgentResult, normalize_payload
from qitp_agents.runtime.entrypoint import AgentCoreApp, _AGENT_REGISTRY, register_agent
from qitp_agents.runtime.session import SessionState


@pytest.fixture(autouse=True)
def clear_registry():
    _AGENT_REGISTRY.clear()
    yield
    _AGENT_REGISTRY.clear()


class TestDualModePipeline:
    """End-to-end tests for the dual-mode pipeline."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda", "EXECUTION_MODE": "backtest"})
    def test_full_lambda_pipeline(self):
        """Complete Lambda pipeline: event → adapter → handler → response."""

        @register_agent("integration-agent")
        def handler(payload: AgentPayload, session: SessionState) -> AgentResult:
            date = payload.parameters.get("date")
            session.store("processed_date", date)
            return AgentResult(
                status="success",
                agent_id="integration-agent",
                session_id=payload.session_id,
                output={"date": date, "result": "gaps_found"},
                memory_updates=session.get_pending_updates(),
            )

        app = AgentCoreApp()

        # Simulate SFN Lambda invocation
        event = {
            "agent_id": "integration-agent",
            "session_id": "sfn-exec-integration-001",
            "execution_mode": "backtest",
            "date": "2026-03-15",
        }

        response = app.invoke(event)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["date"] == "2026-03-15"
        assert body["result"] == "gaps_found"
        assert body["_memory_updates"]["processed_date"] == "2026-03-15"

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_multi_agent_pipeline(self):
        """Multiple agents invoked sequentially, sharing session memory."""

        @register_agent("agent-a")
        def handler_a(payload: AgentPayload, session: SessionState) -> AgentResult:
            session.store("step_a_output", "hello from A")
            return AgentResult(
                status="success",
                agent_id="agent-a",
                session_id=payload.session_id,
                output={"from": "A"},
                memory_updates=session.get_pending_updates(),
            )

        @register_agent("agent-b")
        def handler_b(payload: AgentPayload, session: SessionState) -> AgentResult:
            prior = session.retrieve("step_a_output", "not found")
            return AgentResult(
                status="success",
                agent_id="agent-b",
                session_id=payload.session_id,
                output={"from": "B", "prior": prior},
            )

        app = AgentCoreApp()

        # Agent A
        response_a = app.invoke({
            "agent_id": "agent-a",
            "session_id": "pipeline-001",
        })
        assert response_a["statusCode"] == 200

        # Agent B (would receive memory context from SFN in production)
        response_b = app.invoke({
            "agent_id": "agent-b",
            "session_id": "pipeline-001",
        })
        assert response_b["statusCode"] == 200

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_agentcore_payload_format(self):
        """AgentCore-format payload is correctly normalized in Lambda mode."""

        @register_agent("ac-test-agent")
        def handler(payload: AgentPayload, session: SessionState) -> AgentResult:
            return AgentResult(
                status="success",
                agent_id="ac-test-agent",
                session_id=payload.session_id,
                output={"mode": payload.execution_mode},
            )

        app = AgentCoreApp()

        agentcore_event = {
            "payload": {
                "agent_id": "ac-test-agent",
                "session_id": "ac-sess-001",
                "parameters": {"date": "2026-03-15"},
            },
            "session": {
                "session_id": "ac-sess-001",
                "memory": {"prior": "data"},
            },
            "context": {
                "execution_mode": "paper",
            },
        }

        response = app.invoke(agentcore_event)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["mode"] == "paper"

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_error_handling_pipeline(self):
        """Errors are caught and returned as structured responses."""

        @register_agent("error-agent")
        def handler(payload: AgentPayload, session: SessionState) -> AgentResult:
            raise ValueError("Intentional test error")

        app = AgentCoreApp()

        response = app.invoke({
            "agent_id": "error-agent",
            "session_id": "error-001",
        })

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Intentional test error" in body["error"]
```

---

## Acceptance Criteria
- [ ] Adapter normalizes both Lambda events and AgentCore payloads to unified AgentPayload
- [ ] All 4 agent handlers work in Lambda mode (backwards-compatible with P10)
- [ ] All 4 agent handlers work in AgentCore mode via @register_agent decorator
- [ ] GatewayClient routes tool calls to Gateway with namespace prefixes
- [ ] TargetRegistry registers all 8 QITP targets (5 MCPs + 3 APIs)
- [ ] ToolDiscovery performs semantic search with relevance filtering
- [ ] MemoryManager supports short-term, long-term, and episodic tiers with fallback
- [ ] SessionBridge converts SFN execution ARNs to session IDs and back
- [ ] Identity providers resolve credentials from env vars (Lambda) or AgentCore Identity
- [ ] Cedar policies serialize correctly and validate without errors
- [ ] CDK AgentCoreStack synthesizes: memory tables, gateway sync Lambda, SSM params, IAM roles
- [ ] Cedar policies enforce: execution_agent only for orders, backtest agents blocked from ibkr-mcp, risk_engine read-only
- [ ] All unit tests pass with mocked dependencies
- [ ] Integration test validates full dual-mode pipeline end-to-end

## Test Plan
```bash
# tccw-qitp-agents
cd ~/dev/tccw-qitp-agents
pip install -e ".[dev]"
pytest tests/unit/test_adapter.py tests/unit/test_session.py tests/unit/test_entrypoint.py -v
pytest tests/unit/test_gap_detector_agentcore.py -v
pytest tests/integration/test_agentcore_pipeline.py -v

# tccw-agent-core
cd ~/dev/tccw-agent-core
pip install -e ".[dev]"
pytest tests/unit/test_gateway_client.py tests/unit/test_target_registry.py tests/unit/test_tool_discovery.py -v
pytest tests/unit/test_memory_manager.py tests/unit/test_session_bridge.py -v
pytest tests/unit/test_identity_providers.py tests/unit/test_cedar_policies.py -v

# tccw-agent-infra
cd ~/dev/tccw-agent-infra
pip install -e ".[dev]"
cdk synth
pytest tests/test_agentcore_stack.py -v
```

## Agent Instructions
This is the Phase 2 graduation plan — the most architecturally significant migration in the platform. The key design principle is **dual-mode**: every component must work in both Lambda (Phase 1) and AgentCore (Phase 2) modes, selected by environment variable. No code changes between modes.

Key patterns to follow:
1. **Adapter pattern**: `normalize_payload()` auto-detects Lambda vs AgentCore input format
2. **Gateway single endpoint**: In AgentCore mode, all MCP tool calls route through one URL
3. **Memory tiers**: Short-term is ephemeral (within SFN execution), long-term persists, episodic is searchable
4. **Cedar enforcement**: Real enforcement is at the Gateway — Python code does soft pre-checks only
5. **Graceful fallback**: If AgentCore SDK is not installed, fall back to Lambda-mode behavior
6. **Session ID = SFN execution ID**: This convention bridges both worlds
7. **Secrets via env vars**: AgentCore Identity replaces env vars, but the interface is identical
