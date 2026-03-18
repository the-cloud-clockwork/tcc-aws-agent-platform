# P02 -- Core Engine Library

> **Self-contained plan.** A fresh Claude Code agent reads ONLY this file and can execute everything.

## Metadata

| Field | Value |
|---|---|
| Plan ID | P02 |
| Plane Tickets | ROOT-47 (Blueprint Engine), ROOT-49 (Execution Modes) |
| Target Repo | `~/dev/tccw-agent-core` |
| Depends On | P01 (repo scaffold must exist) |
| Batch | 1 (parallel with P03) |

## Objective

Build the QITP core Python library that ALL other components depend on:

- **Blueprint Engine** -- YAML to Pydantic to Strands Agent
- **Execution Mode system** -- backtest / paper / live
- **Hook framework** -- observability + portfolio constraints
- **Shared Pydantic schemas** -- model config, runtime, tools, outputs
- **Prompt Registry client** -- resolves versioned prompts from Lambda API

---

## Target Repo Structure

```
tccw-agent-core/
├── src/
│   └── agent_core/
│       ├── __init__.py
│       ├── blueprints/
│       │   ├── __init__.py
│       │   ├── loader.py
│       │   ├── agent.py
│       │   ├── workflow.py
│       │   └── strategy.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── model_config.py
│       │   ├── runtime_config.py
│       │   ├── tool_config.py
│       │   ├── execution_modes.py
│       │   └── outputs.py
│       ├── execution/
│       │   ├── __init__.py
│       │   └── mode.py
│       ├── hooks/
│       │   ├── __init__.py
│       │   ├── observability.py
│       │   └── constraints.py
│       ├── prompt/
│       │   ├── __init__.py
│       │   └── client.py
│       └── py.typed
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_loader.py
│   ├── test_agent_blueprint.py
│   ├── test_strategy_blueprint.py
│   ├── test_execution_mode.py
│   ├── test_hooks.py
│   └── test_prompt_client.py
└── pyproject.toml
```

---

## Agent Instructions

You are building the QITP core library. This is the foundation -- every other component depends on it.

1. `cd ~/dev/tccw-agent-core`
2. Create every file listed below with the EXACT content provided.
3. Run the acceptance criteria commands at the end.
4. Fix any issues until all checks pass.
5. Commit with a descriptive message.

**Rules:**
- Use `from __future__ import annotations` in ALL `.py` files.
- Use Pydantic v2 (`model_config = ConfigDict(...)`, not `class Config`).
- All type hints must be modern (use `X | None` not `Optional[X]`).
- Follow the exact field names from the YAML schemas below.

---

## File Contents

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-core"
version = "0.1.0"
description = "QITP Core Engine -- Blueprint Engine, Execution Modes, Hooks, Schemas"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
dependencies = [
    "pydantic>=2.6,<3",
    "pyyaml>=6.0,<7",
    "httpx>=0.27,<1",
    "strands-agents>=0.1.0",
    "strands-agents-tools>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9",
    "pytest-asyncio>=0.23,<1",
    "ruff>=0.4,<1",
    "mypy>=1.10,<2",
    "types-PyYAML>=6.0,<7",
    "respx>=0.21,<1",
]

[tool.hatch.build.targets.wheel]
packages = ["src/agent_core"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "TCH"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["strands.*", "strands_tools.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### `src/agent_core/__init__.py`

```python
"""QITP Core Engine -- Blueprint Engine, Execution Modes, Hooks, Schemas."""
from __future__ import annotations

__version__ = "0.1.0"

# -- Public API re-exports --
from agent_core.blueprints.agent import AgentBlueprint
from agent_core.blueprints.loader import BlueprintLoader
from agent_core.blueprints.strategy import StrategyBlueprint
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.hooks.constraints import PortfolioConstraintHook
from agent_core.hooks.observability import QitpObservabilityHook
from agent_core.prompt.client import PromptRegistryClient
from agent_core.schemas.outputs import (
    GapDetectionOutput,
    PortfolioRecommendation,
    SentimentReport,
)

__all__ = [
    "AgentBlueprint",
    "BlueprintLoader",
    "ExecutionMode",
    "GapDetectionOutput",
    "PortfolioConstraintHook",
    "PortfolioRecommendation",
    "PromptRegistryClient",
    "QitpObservabilityHook",
    "SentimentReport",
    "StrategyBlueprint",
    "WorkflowBlueprint",
    "get_execution_mode",
    "validate_agent_mode",
]
```

---

### `src/agent_core/py.typed`

```
```

*(Empty marker file for PEP 561.)*

---

### `src/agent_core/schemas/__init__.py`

```python
"""Shared Pydantic schemas for QITP."""
from __future__ import annotations
```

---

### `src/agent_core/schemas/model_config.py`

```python
"""ModelConfig schema -- provider-agnostic LLM configuration."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """LLM model configuration extracted from agent blueprints."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["bedrock", "anthropic", "litellm"] = "bedrock"
    model_id: str = Field(
        ...,
        description="Fully qualified model identifier, e.g. us.anthropic.claude-sonnet-4-20250514-v1:0",
    )
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, gt=0)
    cache_prompt: str | None = Field(
        default="default",
        description="Prompt caching strategy: 'default', 'none', or custom key.",
    )
    cache_tools: str | None = Field(
        default="default",
        description="Tool-result caching strategy.",
    )
```

---

### `src/agent_core/schemas/runtime_config.py`

```python
"""RuntimeConfig schema -- agent runtime settings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfig(BaseModel):
    """Runtime configuration for an agent."""

    model_config = ConfigDict(frozen=True)

    type: Literal["agentcore", "lambda", "ecs"] = "agentcore"
    max_iterations: int = Field(default=5, gt=0)
    max_execution_time: int = Field(
        default=120,
        gt=0,
        description="Maximum execution time in seconds.",
    )
```

---

### `src/agent_core/schemas/tool_config.py`

```python
"""ToolConfig schema -- MCP tool declarations for agent blueprints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolConfig(BaseModel):
    """A single MCP tool-group declaration inside an agent blueprint."""

    model_config = ConfigDict(frozen=True)

    mcp: str = Field(..., description="MCP server name, e.g. 'market-data-mcp'.")
    tools: list[str] = Field(
        ...,
        min_length=1,
        description="List of tool names to expose from this MCP.",
    )
```

---

### `src/agent_core/schemas/execution_modes.py`

```python
"""ExecutionModes schema -- per-mode enablement flags."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExecutionModes(BaseModel):
    """Declares which execution modes an agent or strategy supports."""

    model_config = ConfigDict(frozen=True)

    backtest: bool = True
    paper: bool = False
    live: bool = False
```

---

### `src/agent_core/schemas/outputs.py`

```python
"""Output Pydantic models -- structured results from QITP agents."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Gap Detection
# ---------------------------------------------------------------------------

class GapEntry(BaseModel):
    """A single detected price gap."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    gap_pct: float = Field(..., description="Gap percentage (positive = gap-up).")
    direction: Literal["up", "down"]
    friday_close: float
    monday_open: float
    volume_ratio: float = Field(
        ...,
        description="Monday open volume vs 20-day avg.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)


class GapDetectionOutput(BaseModel):
    """Output schema: gap_detection_output_v1."""

    model_config = ConfigDict(frozen=True)

    scan_date: date
    market: str = Field(default="US")
    ranked_gaps: list[GapEntry] = Field(default_factory=list)
    total_symbols_scanned: int = 0
    gaps_found: int = 0
    execution_mode: str = "backtest"
    notes: str | None = None


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

class TickerSentiment(BaseModel):
    """Per-ticker sentiment breakdown."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    news_score: float = Field(..., ge=-1.0, le=1.0)
    analyst_score: float = Field(..., ge=-1.0, le=1.0)
    composite_score: float = Field(..., ge=-1.0, le=1.0)
    article_count: int = 0
    bullish_signals: list[str] = Field(default_factory=list)
    bearish_signals: list[str] = Field(default_factory=list)


class MacroSentiment(BaseModel):
    """Macro-level market sentiment."""

    model_config = ConfigDict(frozen=True)

    vix: float | None = None
    put_call_ratio: float | None = None
    market_breadth: float | None = None
    overall: Literal["bullish", "neutral", "bearish"] = "neutral"


class SentimentReport(BaseModel):
    """Output schema: sentiment_report_v1."""

    model_config = ConfigDict(frozen=True)

    scan_date: date
    macro: MacroSentiment
    per_ticker: list[TickerSentiment] = Field(default_factory=list)
    execution_mode: str = "backtest"


# ---------------------------------------------------------------------------
# Portfolio Recommendation
# ---------------------------------------------------------------------------

class Recommendation(BaseModel):
    """A single portfolio action recommendation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    action: Literal["buy", "sell", "hold"]
    strategy_id: str
    conviction: float = Field(..., ge=0.0, le=1.0)
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    position_size_pct: float | None = Field(
        default=None, ge=0.0, le=100.0, description="Position size as % of portfolio."
    )
    rationale: str = ""


class PortfolioRecommendation(BaseModel):
    """Output schema: portfolio_recommendation_v1."""

    model_config = ConfigDict(frozen=True)

    scan_date: date
    recommendations: list[Recommendation] = Field(default_factory=list)
    no_action_symbols: list[str] = Field(default_factory=list)
    max_concurrent_positions: int = 3
    execution_mode: str = "backtest"
```

---

### `src/agent_core/execution/__init__.py`

```python
"""Execution mode subsystem."""
from __future__ import annotations
```

---

### `src/agent_core/execution/mode.py`

```python
"""ExecutionMode enum and helpers."""
from __future__ import annotations

import os
from enum import Enum

from agent_core.schemas.execution_modes import ExecutionModes


class ExecutionMode(str, Enum):
    """The three execution modes supported by QITP."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


def get_execution_mode() -> ExecutionMode:
    """Read the current execution mode from the ``EXECUTION_MODE`` env var.

    Defaults to ``backtest`` when the variable is unset or empty.
    """
    raw = os.environ.get("EXECUTION_MODE", "backtest").strip().lower()
    try:
        return ExecutionMode(raw)
    except ValueError:
        return ExecutionMode.BACKTEST


def validate_agent_mode(
    execution_modes: ExecutionModes,
    mode: ExecutionMode | None = None,
) -> bool:
    """Return ``True`` if *mode* is enabled in the given execution-modes config.

    When *mode* is ``None`` the current environment mode is used.
    """
    if mode is None:
        mode = get_execution_mode()

    return bool(getattr(execution_modes, mode.value, False))
```

---

### `src/agent_core/blueprints/__init__.py`

```python
"""Blueprint subsystem -- YAML -> Pydantic -> Strands Agent."""
from __future__ import annotations
```

---

### `src/agent_core/blueprints/agent.py`

```python
"""AgentBlueprint Pydantic model."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_core.schemas.execution_modes import ExecutionModes
from agent_core.schemas.model_config import ModelConfig
from agent_core.schemas.runtime_config import RuntimeConfig
from agent_core.schemas.tool_config import ToolConfig


class MultiAgentConfig(BaseModel):
    """Multi-agent orchestration settings."""

    model_config = ConfigDict(frozen=True)

    pattern: str = Field(
        default="swarm",
        description="Orchestration pattern: 'swarm' or 'graph'.",
    )
    execution_timeout: int = Field(default=90, gt=0)
    node_timeout: int = Field(default=30, gt=0)
    max_handoffs: int = Field(default=20, gt=0)


class AgentBlueprint(BaseModel):
    """Full specification for a single QITP agent, loaded from YAML."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str
    name: str
    description: str = ""
    model: ModelConfig
    prompt_ref: str = Field(
        ...,
        description="Reference key for the Prompt Registry (e.g. 'gap_detector_v1.2').",
    )
    tools: list[ToolConfig] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    execution_modes: ExecutionModes = Field(default_factory=ExecutionModes)
    output_schema: str | None = Field(
        default=None,
        description="Name of the output schema (e.g. 'gap_detection_output_v1').",
    )
    hooks: list[str] = Field(default_factory=list)
    multi_agent: MultiAgentConfig | None = None
```

---

### `src/agent_core/blueprints/strategy.py`

```python
"""StrategyBlueprint Pydantic model."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Condition(BaseModel):
    """A single condition in an entry/exit rule."""

    model_config = ConfigDict(frozen=True)

    field: str | None = None
    op: str | None = None
    value: float | str | bool | None = None
    type: str | None = Field(
        default=None,
        description="Special condition type, e.g. 'trailing_stop'.",
    )


class ConditionGroup(BaseModel):
    """A group of conditions joined by logic."""

    model_config = ConfigDict(frozen=True)

    logic: Literal["AND", "OR"] = "AND"
    conditions: list[Condition] = Field(default_factory=list)


class TrailingStopConfig(BaseModel):
    """Trailing stop configuration."""

    model_config = ConfigDict(frozen=True)

    type: Literal["percent", "atr"] = "percent"
    value: float = Field(..., gt=0.0)


class PositionSizingConfig(BaseModel):
    """Position sizing method."""

    model_config = ConfigDict(frozen=True)

    method: Literal["risk_pct", "fixed_dollar", "equal_weight"] = "risk_pct"
    value: float = Field(..., gt=0.0)


class StrategyBlueprint(BaseModel):
    """Full specification for a trading strategy, loaded from YAML."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str
    name: str
    description: str = ""
    asset_types: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    required_signals: list[str] = Field(default_factory=list)
    entry_conditions: ConditionGroup = Field(default_factory=ConditionGroup)
    exit_conditions: ConditionGroup = Field(default_factory=ConditionGroup)
    trailing_stop: TrailingStopConfig | None = None
    position_sizing: PositionSizingConfig | None = None
    max_holding_days: int = Field(default=5, gt=0)
    max_concurrent_positions: int = Field(default=3, gt=0)
    required_agents: list[str] = Field(default_factory=list)
    required_mcps: list[str] = Field(default_factory=list)
```

---

### `src/agent_core/blueprints/workflow.py`

```python
"""WorkflowBlueprint Pydantic model."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TriggerConfig(BaseModel):
    """Trigger configuration for a workflow."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schedule", "event", "manual"] = "schedule"
    schedule: str | None = Field(
        default=None,
        description="Cron expression, e.g. 'cron(30 8 ? * MON *)'.",
    )
    timezone: str | None = Field(default=None, description="IANA timezone.")
    event_pattern: dict[str, Any] | None = None


class ChoiceRule(BaseModel):
    """A single choice rule inside a Choice state."""

    model_config = ConfigDict(frozen=True)

    condition: dict[str, Any] = Field(
        ...,
        description="Condition dict with path, op, value.",
    )
    next: str = Field(..., description="State to transition to if condition is met.")


class WorkflowState(BaseModel):
    """A single state in the workflow state machine."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: Literal["task", "choice", "parallel", "wait", "succeed", "fail"] = "task"
    lambda_ref: str | None = None
    result_path: str | None = None
    next: str | None = None
    choices: list[ChoiceRule] | None = None
    default: str | None = Field(
        default=None,
        description="Default next state for choice type.",
    )
    branches: list[dict[str, Any]] | None = None
    retry: list[dict[str, Any]] | None = None
    catch: list[dict[str, Any]] | None = None


class WorkflowBlueprint(BaseModel):
    """Full specification for an orchestration workflow, loaded from YAML."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str
    name: str
    description: str = ""
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    timeout_minutes: int = Field(default=60, gt=0)
    states: list[WorkflowState] = Field(default_factory=list)
```

---

### `src/agent_core/blueprints/loader.py`

```python
"""BlueprintLoader -- YAML -> Pydantic -> (optionally) Strands Agent."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.blueprints.strategy import StrategyBlueprint
from agent_core.blueprints.workflow import WorkflowBlueprint
from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.prompt.client import PromptRegistryClient

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
    """

    def __init__(
        self,
        blueprints_dir: str | Path,
        prompt_client: PromptRegistryClient | None = None,
    ) -> None:
        self.blueprints_dir = Path(blueprints_dir)
        self.prompt_client = prompt_client or PromptRegistryClient()

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
            raise BlueprintLoadError(f"Expected a mapping in {path}, got {type(data).__name__}")
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
            raise BlueprintLoadError(f"Validation failed for agent '{agent_id}': {exc}") from exc

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

    def load_strategy_from_path(self, path: str | Path) -> StrategyBlueprint:
        """Load a strategy blueprint from an explicit file path."""
        data = self._read_yaml(Path(path))
        try:
            return StrategyBlueprint(**data)
        except Exception as exc:
            raise BlueprintLoadError(f"Validation failed for {path}: {exc}") from exc

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
        from strands import Agent  # type: ignore[import-untyped]

        blueprint = self.load_agent(agent_id)
        current_mode = mode or get_execution_mode()

        # -- mode gate --
        if not validate_agent_mode(blueprint.execution_modes, current_mode):
            raise BlueprintLoadError(
                f"Agent '{agent_id}' is not enabled for mode '{current_mode.value}'."
            )

        # -- resolve prompt --
        system_prompt = self.prompt_client.get(blueprint.prompt_ref)
        logger.info("Resolved prompt for %s (%d chars)", agent_id, len(system_prompt))

        # -- build model kwargs --
        model_kwargs: dict[str, Any] = {
            "model_id": blueprint.model.model_id,
            "temperature": blueprint.model.temperature,
            "max_tokens": blueprint.model.max_tokens,
        }

        # -- collect tools --
        tools: list[Any] = []
        if mcp_clients:
            for tool_cfg in blueprint.tools:
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
                    # Filter to only declared tools.
                    for tname in tool_cfg.tools:
                        if tname in client.tool_names:
                            tools.append(client[tname])
                        else:
                            logger.warning(
                                "Tool '%s' not found in MCP client '%s'",
                                tname,
                                tool_cfg.mcp,
                            )
                else:
                    # If the client doesn't support filtering, add it wholesale.
                    tools.append(client)

        # -- build agent --
        agent = Agent(
            system_prompt=system_prompt,
            tools=tools if tools else None,
            **model_kwargs,
        )
        logger.info("Built Strands Agent '%s' (mode=%s)", agent_id, current_mode.value)
        return agent
```

---

### `src/agent_core/hooks/__init__.py`

```python
"""Hook framework for QITP agents."""
from __future__ import annotations
```

---

### `src/agent_core/hooks/observability.py`

```python
"""QitpObservabilityHook -- structured logging for agent lifecycle events."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("qitp.observability")


@dataclass
class QitpObservabilityHook:
    """Logs agent lifecycle events as structured JSON.

    Captures:
    - ``agent_start`` -- when the agent begins execution.
    - ``tool_end`` -- after each tool call (logs errors prominently).
    - ``agent_end`` -- when the agent finishes (includes elapsed time).

    Usage with Strands (callback-based)::

        hook = QitpObservabilityHook(agent_id="gap_detector")
        agent = Agent(..., callbacks=[hook])

    This hook implements the Strands callback protocol by exposing
    ``on_agent_start``, ``on_tool_end``, and ``on_agent_end`` methods.
    """

    agent_id: str = "unknown"
    execution_mode: str = "backtest"
    _start_time: float = field(default=0.0, init=False, repr=False)
    _tool_calls: int = field(default=0, init=False, repr=False)
    _tool_errors: int = field(default=0, init=False, repr=False)

    # ---- Strands callback protocol ----

    def on_agent_start(self, **kwargs: Any) -> None:
        """Called when the agent starts execution."""
        self._start_time = time.monotonic()
        self._tool_calls = 0
        self._tool_errors = 0
        self._log(
            "agent_start",
            agent_id=self.agent_id,
            execution_mode=self.execution_mode,
        )

    def on_tool_end(
        self,
        tool_name: str = "unknown",
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after each tool invocation completes."""
        self._tool_calls += 1
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "tool_name": tool_name,
        }
        if error:
            self._tool_errors += 1
            payload["error"] = error
            payload["level"] = "ERROR"
        self._log("tool_end", **payload)

    def on_agent_end(self, **kwargs: Any) -> None:
        """Called when the agent finishes execution."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0
        self._log(
            "agent_end",
            agent_id=self.agent_id,
            execution_mode=self.execution_mode,
            elapsed_seconds=round(elapsed, 3),
            tool_calls=self._tool_calls,
            tool_errors=self._tool_errors,
        )

    # ---- Internal ----

    @staticmethod
    def _log(event: str, **data: Any) -> None:
        record = {"event": event, **data}
        logger.info(json.dumps(record, default=str))
```

---

### `src/agent_core/hooks/constraints.py`

```python
"""PortfolioConstraintHook -- enforces position-limit guardrails."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("qitp.constraints")


@dataclass
class PortfolioConstraintHook:
    """Enforces maximum concurrent recommendations after agent invocation.

    If the agent produces more recommendations than ``max_recommendations``,
    the excess entries are truncated and a warning is logged.

    Usage with Strands (callback-based)::

        hook = PortfolioConstraintHook(max_recommendations=3)
        agent = Agent(..., callbacks=[hook])
    """

    max_recommendations: int = 3

    def on_agent_end(self, result: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any] | None:
        """Trim recommendations list if it exceeds the limit."""
        if result is None:
            return None

        recs = result.get("recommendations")
        if isinstance(recs, list) and len(recs) > self.max_recommendations:
            original_count = len(recs)
            result["recommendations"] = recs[: self.max_recommendations]
            logger.warning(
                "PortfolioConstraintHook: trimmed recommendations from %d to %d",
                original_count,
                self.max_recommendations,
            )
        return result
```

---

### `src/agent_core/prompt/__init__.py`

```python
"""Prompt Registry client subsystem."""
from __future__ import annotations
```

---

### `src/agent_core/prompt/client.py`

```python
"""PromptRegistryClient -- resolves versioned prompts from the Lambda API."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("qitp.prompt")

_DEFAULT_REGISTRY_URL = "http://localhost:8080"


class PromptResolutionError(Exception):
    """Raised when a prompt cannot be resolved."""


class PromptRegistryClient:
    """Fetches prompt text from the QITP Prompt Registry API.

    Resolution order:
    1. Call ``GET /prompts/{prompt_ref}`` on the registry API.
    2. If the registry is unavailable, fall back to a local file at
       ``{local_dir}/{prompt_ref}.txt``.

    Parameters
    ----------
    registry_url:
        Base URL for the registry API.  Defaults to ``PROMPT_REGISTRY_URL``
        env var, then ``http://localhost:8080``.
    local_dir:
        Path to a local directory of prompt text files (dev fallback).
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        registry_url: str | None = None,
        local_dir: str | Path | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.registry_url = (
            registry_url
            or os.environ.get("PROMPT_REGISTRY_URL")
            or _DEFAULT_REGISTRY_URL
        )
        self.local_dir = Path(local_dir) if local_dir else None
        self.timeout = timeout

    def get(self, prompt_ref: str) -> str:
        """Resolve *prompt_ref* to prompt text.

        Supports pinned versions (``gap_detector_v1.2``) and latest-stable
        references (``gap_detector``).

        Returns
        -------
        The resolved prompt text as a string.

        Raises
        ------
        PromptResolutionError
            If the prompt cannot be resolved from either the registry or local
            fallback.
        """
        # Try remote registry first.
        try:
            return self._fetch_remote(prompt_ref)
        except Exception as exc:
            logger.warning(
                "Registry fetch failed for '%s': %s -- trying local fallback",
                prompt_ref,
                exc,
            )

        # Fallback to local file.
        return self._fetch_local(prompt_ref)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_remote(self, prompt_ref: str) -> str:
        url = f"{self.registry_url.rstrip('/')}/prompts/{prompt_ref}"
        resp = httpx.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        text = data.get("text") or data.get("prompt_text") or data.get("body")
        if not text:
            raise PromptResolutionError(
                f"Registry returned empty prompt for '{prompt_ref}'"
            )
        return str(text)

    def _fetch_local(self, prompt_ref: str) -> str:
        if self.local_dir is None:
            raise PromptResolutionError(
                f"No local_dir configured and registry unavailable for '{prompt_ref}'"
            )
        path = self.local_dir / f"{prompt_ref}.txt"
        if not path.exists():
            raise PromptResolutionError(
                f"Local prompt file not found: {path}"
            )
        return path.read_text(encoding="utf-8").strip()
```

---

### `tests/__init__.py`

```python
```

---

### `tests/conftest.py`

```python
"""Shared pytest fixtures for agent-core tests."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Sample YAML content
# ---------------------------------------------------------------------------

SAMPLE_AGENT_YAML = textwrap.dedent("""\
    id: gap_detector
    version: "1.2.0"
    name: Gap Detection Agent
    description: Scans watchlist for significant Friday/Monday price gaps
    model:
      provider: bedrock
      model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
      temperature: 0.2
      max_tokens: 4096
      cache_prompt: default
      cache_tools: default
    prompt_ref: gap_detector_v1.2
    tools:
      - mcp: market-data-mcp
        tools: [get_watchlist_gaps, get_ohlcv, get_volume_profile]
      - mcp: artifacts-mcp
        tools: [create_artifact]
    runtime:
      type: agentcore
      max_iterations: 5
      max_execution_time: 120
    execution_modes:
      backtest: true
      paper: true
      live: true
    output_schema: gap_detection_output_v1
    hooks:
      - QitpObservabilityHook
    multi_agent:
      pattern: swarm
      execution_timeout: 90
      node_timeout: 30
      max_handoffs: 20
""")

SAMPLE_STRATEGY_YAML = textwrap.dedent("""\
    id: gap_momentum_up
    version: "1.0.0"
    name: Gap Momentum Up
    description: Buy gap-up symbols with bullish sentiment confirmation
    asset_types: [stock, etf]
    markets: [US, EU, ES]
    required_signals: [gap, sentiment]
    entry_conditions:
      logic: AND
      conditions:
        - field: gap_pct
          op: gte
          value: 2.0
        - field: sentiment_score
          op: gte
          value: 0.60
    exit_conditions:
      logic: OR
      conditions:
        - type: trailing_stop
        - field: holding_days
          op: gte
          value: 5
    trailing_stop:
      type: percent
      value: 3.0
    position_sizing:
      method: risk_pct
      value: 1.0
    max_holding_days: 5
    max_concurrent_positions: 3
    required_agents: [gap_detector, sentiment_analyzer, portfolio_recommender]
    required_mcps: [market-data-mcp, sentiment-mcp, ibkr-mcp]
""")

SAMPLE_WORKFLOW_YAML = textwrap.dedent("""\
    id: weekly_gap_analysis
    version: "1.0.0"
    name: Weekly Gap Analysis Pipeline
    trigger:
      type: schedule
      schedule: "cron(30 8 ? * MON *)"
      timezone: Europe/Madrid
    timeout_minutes: 60
    states:
      - id: ValidateMarketCalendar
        type: task
        lambda_ref: qitp-market-calendar-validator
        result_path: $.calendar
        next: CheckTradingDay
      - id: CheckTradingDay
        type: choice
        choices:
          - condition:
              path: $.calendar.is_trading_day
              op: eq
              value: false
            next: NoOpComplete
        default: FetchWatchlistGaps
""")


@pytest.fixture()
def tmp_blueprints(tmp_path: Path) -> Path:
    """Create a temporary blueprints directory with sample YAML files.

    Directory layout::

        tmp_path/
        ├── agents/
        │   └── gap_detector.yaml
        ├── strategies/
        │   └── gap_momentum_up.yaml
        └── workflows/
            └── weekly_gap_analysis.yaml
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "gap_detector.yaml").write_text(SAMPLE_AGENT_YAML)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    (strategies_dir / "gap_momentum_up.yaml").write_text(SAMPLE_STRATEGY_YAML)

    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "weekly_gap_analysis.yaml").write_text(SAMPLE_WORKFLOW_YAML)

    return tmp_path


@pytest.fixture()
def sample_agent_dict() -> dict:
    """Parsed dict from the sample agent YAML."""
    return yaml.safe_load(SAMPLE_AGENT_YAML)


@pytest.fixture()
def sample_strategy_dict() -> dict:
    """Parsed dict from the sample strategy YAML."""
    return yaml.safe_load(SAMPLE_STRATEGY_YAML)


@pytest.fixture()
def tmp_prompts(tmp_path: Path) -> Path:
    """Create a temp directory with local prompt files."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "gap_detector_v1.2.txt").write_text(
        "You are a gap detection agent. Analyse price gaps."
    )
    (prompts_dir / "gap_detector.txt").write_text(
        "You are a gap detection agent (latest). Analyse price gaps."
    )
    return prompts_dir
```

---

### `tests/test_agent_blueprint.py`

```python
"""Tests for AgentBlueprint model."""
from __future__ import annotations

import pytest
import yaml

from agent_core.blueprints.agent import AgentBlueprint, MultiAgentConfig
from agent_core.schemas.execution_modes import ExecutionModes
from agent_core.schemas.model_config import ModelConfig
from agent_core.schemas.runtime_config import RuntimeConfig
from agent_core.schemas.tool_config import ToolConfig
from tests.conftest import SAMPLE_AGENT_YAML


class TestAgentBlueprint:
    def test_parse_sample_yaml(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.id == "gap_detector"
        assert bp.version == "1.2.0"
        assert bp.name == "Gap Detection Agent"
        assert bp.prompt_ref == "gap_detector_v1.2"

    def test_model_config(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.model.provider == "bedrock"
        assert bp.model.model_id == "us.anthropic.claude-sonnet-4-20250514-v1:0"
        assert bp.model.temperature == 0.2
        assert bp.model.max_tokens == 4096

    def test_tools_parsed(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert len(bp.tools) == 2
        assert bp.tools[0].mcp == "market-data-mcp"
        assert "get_watchlist_gaps" in bp.tools[0].tools
        assert bp.tools[1].mcp == "artifacts-mcp"

    def test_execution_modes(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.execution_modes.backtest is True
        assert bp.execution_modes.paper is True
        assert bp.execution_modes.live is True

    def test_runtime(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.runtime.type == "agentcore"
        assert bp.runtime.max_iterations == 5
        assert bp.runtime.max_execution_time == 120

    def test_multi_agent(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.multi_agent is not None
        assert bp.multi_agent.pattern == "swarm"
        assert bp.multi_agent.execution_timeout == 90
        assert bp.multi_agent.max_handoffs == 20

    def test_hooks(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert "QitpObservabilityHook" in bp.hooks

    def test_output_schema(self, sample_agent_dict: dict) -> None:
        bp = AgentBlueprint(**sample_agent_dict)
        assert bp.output_schema == "gap_detection_output_v1"

    def test_minimal_agent(self) -> None:
        """An agent with only required fields should work."""
        bp = AgentBlueprint(
            id="minimal",
            version="0.1.0",
            name="Minimal Agent",
            model=ModelConfig(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
            prompt_ref="minimal_v1",
        )
        assert bp.id == "minimal"
        assert bp.execution_modes.backtest is True
        assert bp.execution_modes.paper is False
```

---

### `tests/test_strategy_blueprint.py`

```python
"""Tests for StrategyBlueprint model."""
from __future__ import annotations

import pytest

from agent_core.blueprints.strategy import StrategyBlueprint
from tests.conftest import SAMPLE_STRATEGY_YAML


class TestStrategyBlueprint:
    def test_parse_sample_yaml(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.id == "gap_momentum_up"
        assert bp.version == "1.0.0"
        assert bp.name == "Gap Momentum Up"

    def test_entry_conditions(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.entry_conditions.logic == "AND"
        assert len(bp.entry_conditions.conditions) == 2
        assert bp.entry_conditions.conditions[0].field == "gap_pct"
        assert bp.entry_conditions.conditions[0].op == "gte"
        assert bp.entry_conditions.conditions[0].value == 2.0

    def test_exit_conditions(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.exit_conditions.logic == "OR"
        assert len(bp.exit_conditions.conditions) == 2
        # First condition is a special type
        assert bp.exit_conditions.conditions[0].type == "trailing_stop"
        # Second is a field comparison
        assert bp.exit_conditions.conditions[1].field == "holding_days"

    def test_trailing_stop(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.trailing_stop is not None
        assert bp.trailing_stop.type == "percent"
        assert bp.trailing_stop.value == 3.0

    def test_position_sizing(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.position_sizing is not None
        assert bp.position_sizing.method == "risk_pct"
        assert bp.position_sizing.value == 1.0

    def test_required_agents_and_mcps(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert "gap_detector" in bp.required_agents
        assert "market-data-mcp" in bp.required_mcps

    def test_asset_types_and_markets(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.asset_types == ["stock", "etf"]
        assert bp.markets == ["US", "EU", "ES"]

    def test_holding_and_positions(self, sample_strategy_dict: dict) -> None:
        bp = StrategyBlueprint(**sample_strategy_dict)
        assert bp.max_holding_days == 5
        assert bp.max_concurrent_positions == 3
```

---

### `tests/test_loader.py`

```python
"""Tests for BlueprintLoader."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.blueprints.loader import BlueprintLoadError, BlueprintLoader


class TestBlueprintLoader:
    def test_load_agent(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_agent("gap_detector")
        assert bp.id == "gap_detector"
        assert bp.version == "1.2.0"

    def test_load_strategy(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_strategy("gap_momentum_up")
        assert bp.id == "gap_momentum_up"

    def test_load_workflow(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_workflow("weekly_gap_analysis")
        assert bp.id == "weekly_gap_analysis"
        assert len(bp.states) == 2
        assert bp.states[0].id == "ValidateMarketCalendar"

    def test_load_agent_not_found(self, tmp_blueprints: Path) -> None:
        loader = BlueprintLoader(tmp_blueprints)
        with pytest.raises(BlueprintLoadError, match="not found"):
            loader.load_agent("nonexistent_agent")

    def test_load_agent_from_path(self, tmp_blueprints: Path) -> None:
        path = tmp_blueprints / "agents" / "gap_detector.yaml"
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_agent_from_path(path)
        assert bp.id == "gap_detector"

    def test_load_strategy_from_path(self, tmp_blueprints: Path) -> None:
        path = tmp_blueprints / "strategies" / "gap_momentum_up.yaml"
        loader = BlueprintLoader(tmp_blueprints)
        bp = loader.load_strategy_from_path(path)
        assert bp.id == "gap_momentum_up"
```

---

### `tests/test_execution_mode.py`

```python
"""Tests for ExecutionMode enum and helpers."""
from __future__ import annotations

import os

import pytest

from agent_core.execution.mode import ExecutionMode, get_execution_mode, validate_agent_mode
from agent_core.schemas.execution_modes import ExecutionModes


class TestExecutionMode:
    def test_default_is_backtest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EXECUTION_MODE", raising=False)
        assert get_execution_mode() == ExecutionMode.BACKTEST

    def test_read_paper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "paper")
        assert get_execution_mode() == ExecutionMode.PAPER

    def test_read_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "live")
        assert get_execution_mode() == ExecutionMode.LIVE

    def test_invalid_falls_back_to_backtest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "invalid_mode")
        assert get_execution_mode() == ExecutionMode.BACKTEST

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "PAPER")
        assert get_execution_mode() == ExecutionMode.PAPER

    def test_validate_agent_mode_enabled(self) -> None:
        modes = ExecutionModes(backtest=True, paper=True, live=False)
        assert validate_agent_mode(modes, ExecutionMode.BACKTEST) is True
        assert validate_agent_mode(modes, ExecutionMode.PAPER) is True
        assert validate_agent_mode(modes, ExecutionMode.LIVE) is False

    def test_validate_agent_mode_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTION_MODE", "paper")
        modes = ExecutionModes(backtest=True, paper=True, live=False)
        assert validate_agent_mode(modes) is True

    def test_validate_agent_mode_default_only_backtest(self) -> None:
        modes = ExecutionModes()  # backtest=True, paper=False, live=False
        assert validate_agent_mode(modes, ExecutionMode.BACKTEST) is True
        assert validate_agent_mode(modes, ExecutionMode.PAPER) is False
```

---

### `tests/test_hooks.py`

```python
"""Tests for QitpObservabilityHook and PortfolioConstraintHook."""
from __future__ import annotations

import json
import logging

import pytest

from agent_core.hooks.constraints import PortfolioConstraintHook
from agent_core.hooks.observability import QitpObservabilityHook


class TestObservabilityHook:
    def test_lifecycle(self, caplog: pytest.LogCaptureFixture) -> None:
        hook = QitpObservabilityHook(agent_id="test_agent", execution_mode="backtest")

        with caplog.at_level(logging.INFO, logger="qitp.observability"):
            hook.on_agent_start()
            hook.on_tool_end(tool_name="get_ohlcv")
            hook.on_tool_end(tool_name="bad_tool", error="timeout")
            hook.on_agent_end()

        messages = [r.message for r in caplog.records]
        assert len(messages) == 4

        # Verify agent_start
        start = json.loads(messages[0])
        assert start["event"] == "agent_start"
        assert start["agent_id"] == "test_agent"

        # Verify tool_end (success)
        tool_ok = json.loads(messages[1])
        assert tool_ok["event"] == "tool_end"
        assert tool_ok["tool_name"] == "get_ohlcv"
        assert "error" not in tool_ok

        # Verify tool_end (error)
        tool_err = json.loads(messages[2])
        assert tool_err["event"] == "tool_end"
        assert tool_err["error"] == "timeout"
        assert tool_err["level"] == "ERROR"

        # Verify agent_end
        end = json.loads(messages[3])
        assert end["event"] == "agent_end"
        assert end["tool_calls"] == 2
        assert end["tool_errors"] == 1
        assert end["elapsed_seconds"] >= 0

    def test_default_agent_id(self) -> None:
        hook = QitpObservabilityHook()
        assert hook.agent_id == "unknown"


class TestPortfolioConstraintHook:
    def test_trims_excess_recommendations(self) -> None:
        hook = PortfolioConstraintHook(max_recommendations=2)
        result = {
            "recommendations": [
                {"symbol": "AAPL"},
                {"symbol": "GOOGL"},
                {"symbol": "TSLA"},
                {"symbol": "MSFT"},
            ]
        }
        trimmed = hook.on_agent_end(result=result)
        assert trimmed is not None
        assert len(trimmed["recommendations"]) == 2
        assert trimmed["recommendations"][0]["symbol"] == "AAPL"

    def test_no_trim_when_within_limit(self) -> None:
        hook = PortfolioConstraintHook(max_recommendations=5)
        result = {"recommendations": [{"symbol": "AAPL"}]}
        out = hook.on_agent_end(result=result)
        assert out is not None
        assert len(out["recommendations"]) == 1

    def test_none_result(self) -> None:
        hook = PortfolioConstraintHook()
        assert hook.on_agent_end(result=None) is None

    def test_no_recommendations_key(self) -> None:
        hook = PortfolioConstraintHook()
        result: dict = {"other_key": 42}
        out = hook.on_agent_end(result=result)
        assert out == {"other_key": 42}
```

---

### `tests/test_prompt_client.py`

```python
"""Tests for PromptRegistryClient."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from agent_core.prompt.client import PromptRegistryClient, PromptResolutionError


class TestPromptRegistryClient:
    @respx.mock
    def test_fetch_remote_success(self) -> None:
        respx.get("http://test-registry/prompts/gap_detector_v1.2").mock(
            return_value=httpx.Response(
                200,
                json={"text": "You are a gap detection agent."},
            )
        )
        client = PromptRegistryClient(registry_url="http://test-registry")
        result = client.get("gap_detector_v1.2")
        assert result == "You are a gap detection agent."

    @respx.mock
    def test_fetch_remote_prompt_text_key(self) -> None:
        respx.get("http://test-registry/prompts/test_v1").mock(
            return_value=httpx.Response(
                200,
                json={"prompt_text": "Hello from registry."},
            )
        )
        client = PromptRegistryClient(registry_url="http://test-registry")
        assert client.get("test_v1") == "Hello from registry."

    def test_fallback_to_local(self, tmp_prompts: Path) -> None:
        # Use an unreachable URL so remote fails.
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            local_dir=tmp_prompts,
            timeout=0.5,
        )
        result = client.get("gap_detector_v1.2")
        assert "gap detection agent" in result

    def test_local_latest(self, tmp_prompts: Path) -> None:
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            local_dir=tmp_prompts,
            timeout=0.5,
        )
        result = client.get("gap_detector")
        assert "(latest)" in result

    def test_no_local_dir_raises(self) -> None:
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            timeout=0.5,
        )
        with pytest.raises(PromptResolutionError, match="No local_dir"):
            client.get("missing_prompt")

    def test_missing_local_file_raises(self, tmp_prompts: Path) -> None:
        client = PromptRegistryClient(
            registry_url="http://unreachable-host:9999",
            local_dir=tmp_prompts,
            timeout=0.5,
        )
        with pytest.raises(PromptResolutionError, match="not found"):
            client.get("totally_missing_ref")

    @respx.mock
    def test_empty_response_falls_back(self, tmp_prompts: Path) -> None:
        respx.get("http://test-registry/prompts/gap_detector_v1.2").mock(
            return_value=httpx.Response(200, json={})
        )
        client = PromptRegistryClient(
            registry_url="http://test-registry",
            local_dir=tmp_prompts,
        )
        result = client.get("gap_detector_v1.2")
        assert "gap detection agent" in result
```

---

## Acceptance Criteria

```bash
cd ~/dev/tccw-agent-core
pip install -e ".[dev]"
ruff check .
mypy src/
pytest -v
```

- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `ruff check .` passes
- [ ] `mypy src/` passes (or has only minor third-party issues)
- [ ] `pytest -v` passes -- all unit tests green
- [ ] `BlueprintLoader` can load a sample agent YAML and return `AgentBlueprint`
- [ ] `BlueprintLoader` can load a sample strategy YAML and return `StrategyBlueprint`
- [ ] `ExecutionMode` correctly reads from env var
- [ ] Hooks instantiate without errors

## Test Plan

```bash
cd ~/dev/tccw-agent-core
pip install -e ".[dev]"
ruff check .
pytest -v
```

## Commit Message

```
feat: implement QITP core library (ROOT-47, ROOT-49)

Blueprint Engine, Execution Modes, Hook framework, Pydantic schemas,
Prompt Registry client. Full test coverage.
```
