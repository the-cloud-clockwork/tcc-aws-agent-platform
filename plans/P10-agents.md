# P10 — Agents

## Objective
Build all 4 POC agents + 5 strategy YAML blueprints in one repo. Agents: Gap Detection (single), Sentiment Analysis (Swarm), Strategy Evaluation (Graph), Portfolio Recommender (single, extended thinking).

## Plane Tickets
ROOT-54 (Gap Detection), ROOT-55 (Sentiment), ROOT-56 (Strategy Library), ROOT-59 (Portfolio Recommender)

## Target Repo
`~/dev/tccw-qitp-agents`

## Dependencies
P02 (core engine), P05 (market-data-mcp), P06 (artifacts-mcp), P07 (sentiment-mcp), P08 (backtest-mcp)

## Repo Structure
```
tccw-qitp-agents/
├── blueprints/
│   ├── agents/
│   │   ├── gap_detector.yaml
│   │   ├── sentiment_analyzer.yaml
│   │   ├── strategy_evaluator.yaml
│   │   └── portfolio_recommender.yaml
│   └── strategies/
│       ├── gap_momentum_up.yaml
│       ├── mean_reversion_gap.yaml
│       ├── gap_continuation.yaml
│       ├── sentiment_driven.yaml
│       └── gap_etf_momentum.yaml
├── src/
│   └── qitp_agents/
│       ├── __init__.py
│       ├── gap_detector/
│       │   ├── __init__.py
│       │   └── handler.py
│       ├── sentiment_analyzer/
│       │   ├── __init__.py
│       │   └── handler.py
│       ├── strategy_evaluator/
│       │   ├── __init__.py
│       │   └── handler.py
│       └── portfolio_recommender/
│           ├── __init__.py
│           └── handler.py
├── tests/
│   ├── unit/
│   │   ├── test_gap_detector.py
│   │   ├── test_sentiment_analyzer.py
│   │   ├── test_strategy_evaluator.py
│   │   └── test_portfolio_recommender.py
│   ├── integration/
│   │   └── test_pipeline.py
│   └── conftest.py
└── pyproject.toml
```

## Agent Architecture

Each agent follows the Lambda handler pattern:
- Initialize `BlueprintLoader` and `EXECUTION_MODE` OUTSIDE handler (warm start)
- MCP clients created per invocation with context managers
- Agent built from blueprint via `LOADER.build_strands_agent(agent_id, mcp_clients)`
- Output marshaled to JSON, truncated to <256KB (claim-check for larger)

---

## Implementation

### pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-agents"
version = "0.1.0"
description = "QITP POC agents — gap detection, sentiment analysis, strategy evaluation, portfolio recommendation"
requires-python = ">=3.11"
dependencies = [
    "strands-agents>=0.1.0",
    "strands-agents-tools>=0.1.0",
    "agent-core>=0.1.0",
    "pyyaml>=6.0.1",
    "pydantic>=2.6.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
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

### src/qitp_agents/__init__.py

```python
"""QITP Agents — POC agent handlers for the Quantitative Investment Trading Platform."""

__version__ = "0.1.0"
```

---

## Agent 1: Gap Detection (Single Strands Agent)

### blueprints/agents/gap_detector.yaml

```yaml
agent_id: gap-detector
name: Gap Detection Agent
version: "1.0.0"
description: >
  Identifies and ranks price gaps in a watchlist of symbols.
  Uses market data MCP for OHLCV and volume profiles, then creates
  a GapDetectionOutput artifact via artifacts MCP.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 4096
  temperature: 0.1

system_prompt_id: gap-detector-system-v1

tools:
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_watchlist_gaps
      - get_ohlcv
      - get_volume_profile
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact
      - get_artifact

execution:
  timeout_seconds: 60
  max_tool_calls: 50
  retry_policy:
    max_retries: 2
    backoff_base: 1.0

output_schema: GapDetectionOutput

tags:
  - gap-detection
  - market-data
  - phase-1
```

### src/qitp_agents/gap_detector/__init__.py

```python
"""Gap Detection Agent — identifies and ranks price gaps."""
```

### src/qitp_agents/gap_detector/handler.py

```python
"""Gap Detection Agent Lambda handler.

Input:  {"date": "2026-03-15", "threshold_pct": 2.0, "watchlist_id": "default"}
Output: GapDetectionOutput JSON artifact with ranked_gaps list.

Architecture:
- Single Strands agent (no multi-agent pattern)
- Tools: market-data-mcp (get_watchlist_gaps, get_ohlcv, get_volume_profile)
- Tools: artifacts-mcp (create_artifact)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "lambda"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "gap-detector"
MAX_OUTPUT_BYTES = 256 * 1024  # 256KB claim-check threshold


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Gap Detection Agent.

    Args:
        event: Input payload with date, threshold_pct, watchlist_id.
        context: Lambda context (optional).

    Returns:
        JSON response with gap detection results or claim-check reference.
    """
    logger.info("Gap detector invoked", extra={"event_keys": list(event.keys())})

    date = event.get("date")
    threshold_pct = event.get("threshold_pct", 2.0)
    watchlist_id = event.get("watchlist_id", "default")

    if not date:
        return _error_response("Missing required field: date")

    try:
        # Build MCP client map for this invocation
        mcp_clients = _create_mcp_clients()

        # Build agent from blueprint
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Construct the agent prompt
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
        )

        # Invoke the agent
        result = agent(prompt)

        # Marshal output
        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Gap detector failed")
        return _error_response(str(e))
    finally:
        # MCP clients are cleaned up via context managers in _create_mcp_clients
        pass


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation.

    Returns a dict of {tool_name: mcp_client} ready for the agent builder.
    """
    from agent_core.mcp import create_mcp_client

    clients = {}

    market_data_uri = os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8001")
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=market_data_uri,
    )

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8002")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict.

    If output exceeds MAX_OUTPUT_BYTES, stores to S3 and returns claim-check.
    """
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)

    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        # Claim-check: store in artifacts and return reference
        logger.warning("Output exceeds 256KB, storing claim-check reference")
        output = {
            "claim_check": True,
            "message": "Output exceeded 256KB. Full result stored as artifact.",
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "body": json.dumps(data),
    }


def _error_response(message: str) -> dict[str, Any]:
    return {
        "statusCode": 500,
        "body": json.dumps({"error": message}),
    }
```

---

## Agent 2: Sentiment Analysis (Strands Swarm)

### blueprints/agents/sentiment_analyzer.yaml

```yaml
agent_id: sentiment-analyzer
name: Sentiment Analysis Agent
version: "1.0.0"
description: >
  Swarm pattern agent that spawns one sub-agent per symbol to gather
  sentiment scores in parallel. Merges results into a SentimentReport artifact.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 4096
  temperature: 0.1

system_prompt_id: sentiment-analyzer-system-v1

tools:
  - name: sentiment-mcp
    type: mcp
    uri: "${SENTIMENT_MCP_URI}"
    operations:
      - get_composite_sentiment
      - get_news_sentiment
      - get_social_sentiment
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact

multi_agent:
  pattern: swarm
  coordinator:
    agent_ref: sentiment-coordinator
    description: "Dispatches per-symbol sentiment agents and merges results"
  worker:
    agent_ref: sentiment-worker
    description: "Analyzes sentiment for a single symbol"
    spawn_per: symbol
  config:
    execution_timeout: 90
    node_timeout: 30
    max_handoffs: 20
    merge_strategy: aggregate

execution:
  timeout_seconds: 120
  max_tool_calls: 100
  retry_policy:
    max_retries: 2
    backoff_base: 1.0

output_schema: SentimentReport

tags:
  - sentiment
  - swarm
  - phase-1
```

### src/qitp_agents/sentiment_analyzer/__init__.py

```python
"""Sentiment Analysis Agent — Swarm pattern for parallel per-symbol sentiment scoring."""
```

### src/qitp_agents/sentiment_analyzer/handler.py

```python
"""Sentiment Analysis Agent Lambda handler.

Input:  {"symbols": ["AAPL", "TSLA", ...], "date": "2026-03-15", "gap_results_artifact_id": "..."}
Output: SentimentReport JSON artifact with per-symbol sentiment scores.

Architecture:
- Strands Swarm pattern: coordinator dispatches one worker per symbol
- Each worker calls sentiment-mcp get_composite_sentiment
- Coordinator merges results into SentimentReport
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "lambda"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "sentiment-analyzer"
MAX_OUTPUT_BYTES = 256 * 1024


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Sentiment Analysis Agent.

    Args:
        event: Input with symbols list, date, and optional gap_results_artifact_id.
        context: Lambda context (optional).

    Returns:
        JSON response with sentiment report or claim-check reference.
    """
    logger.info("Sentiment analyzer invoked", extra={"symbol_count": len(event.get("symbols", []))})

    symbols = event.get("symbols", [])
    date = event.get("date")
    gap_artifact_id = event.get("gap_results_artifact_id")

    if not symbols:
        return _error_response("Missing required field: symbols")
    if not date:
        return _error_response("Missing required field: date")

    try:
        mcp_clients = _create_mcp_clients()

        # Build the swarm agent from blueprint
        # The Strands SDK Swarm pattern handles coordinator + worker spawning
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Construct coordinator prompt
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

        # The Swarm pattern in Strands will:
        # 1. Coordinator parses symbol list
        # 2. Spawns one worker agent per symbol (up to max_handoffs)
        # 3. Each worker calls sentiment-mcp tools
        # 4. Coordinator merges results
        result = agent(prompt)

        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Sentiment analyzer failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    sentiment_uri = os.environ.get("SENTIMENT_MCP_URI", "http://localhost:8003")
    clients["sentiment-mcp"] = create_mcp_client(
        name="sentiment-mcp",
        uri=sentiment_uri,
    )

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8002")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check for large outputs."""
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


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(data)}


def _error_response(message: str) -> dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": message})}
```

---

## Agent 3: Strategy Evaluation (Strands Graph)

### blueprints/agents/strategy_evaluator.yaml

```yaml
agent_id: strategy-evaluator
name: Strategy Evaluation Agent
version: "1.0.0"
description: >
  Graph pattern agent with deterministic routing between specialist nodes.
  Evaluates which trading strategies apply to detected gaps using
  gap analysis, technical analysis, sentiment analysis, and final evaluation.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.1

system_prompt_id: strategy-evaluator-system-v1

tools:
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_ohlcv
      - get_volume_profile
      - get_technical_indicators
  - name: sentiment-mcp
    type: mcp
    uri: "${SENTIMENT_MCP_URI}"
    operations:
      - get_composite_sentiment
  - name: backtest-mcp
    type: mcp
    uri: "${BACKTEST_MCP_URI}"
    operations:
      - run_backtest
      - get_backtest_results
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact
      - get_artifact

multi_agent:
  pattern: graph
  nodes:
    - id: gap_analysis
      agent_ref: gap-analysis-specialist
      type: agent
      description: "Analyze gap characteristics — magnitude, volume, historical patterns"
      system_prompt_id: gap-analysis-specialist-v1
    - id: technical_analysis
      agent_ref: technical-analysis-specialist
      type: agent
      description: "Compute technical indicators — RSI, MACD, Bollinger, support/resistance"
      system_prompt_id: technical-analysis-specialist-v1
    - id: sentiment_analysis
      agent_ref: sentiment-analysis-specialist
      type: agent
      description: "Evaluate sentiment alignment with gap direction"
      system_prompt_id: sentiment-analysis-specialist-v1
    - id: signal_gate
      type: gate
      description: "Circuit breaker — requires minimum signal count before proceeding"
      trip_condition: "lambda state: state.get('signal_count', 0) < state.get('required_signals', 2)"
      fallback: "return_partial"
    - id: strategy_eval
      agent_ref: strategy-evaluation-specialist
      type: agent
      description: "Match signals to strategy library, score and rank applicable strategies"
      system_prompt_id: strategy-evaluation-specialist-v1
  edges:
    - from: gap_analysis
      to: technical_analysis
      label: "gap_characterized"
      condition: "lambda state: state.get('gap_data') is not None"
    - from: gap_analysis
      to: sentiment_analysis
      label: "gap_characterized"
      condition: "lambda state: state.get('gap_data') is not None"
    - from: technical_analysis
      to: signal_gate
      label: "technicals_ready"
      condition: "lambda state: 'technical_signals' in state"
    - from: sentiment_analysis
      to: signal_gate
      label: "sentiment_ready"
      condition: "lambda state: 'sentiment_score' in state"
    - from: signal_gate
      to: strategy_eval
      label: "gate_passed"
      condition: "lambda state: state.get('signal_count', 0) >= state.get('required_signals', 2)"

execution:
  timeout_seconds: 180
  max_tool_calls: 100
  retry_policy:
    max_retries: 2
    backoff_base: 1.5

output_schema: StrategyEvaluationOutput

tags:
  - strategy-evaluation
  - graph
  - phase-1
```

### src/qitp_agents/strategy_evaluator/__init__.py

```python
"""Strategy Evaluation Agent — Graph pattern with deterministic edge routing."""
```

### src/qitp_agents/strategy_evaluator/handler.py

```python
"""Strategy Evaluation Agent Lambda handler.

Input:  {
    "symbol": "AAPL",
    "date": "2026-03-15",
    "gap_data": {...},           # from gap detector
    "sentiment_data": {...},     # from sentiment analyzer
    "strategies_dir": "blueprints/strategies/"
}
Output: StrategyEvaluationOutput with ranked strategies for this symbol.

Architecture:
- Strands Graph pattern with 5 nodes: gap_analysis -> technical_analysis + sentiment_analysis -> signal_gate -> strategy_eval
- Deterministic routing via Python lambda conditions on edges
- signal_gate is a circuit breaker requiring minimum signal count
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "lambda"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "strategy-evaluator"
MAX_OUTPUT_BYTES = 256 * 1024


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Strategy Evaluation Agent.

    Args:
        event: Input with symbol, date, gap_data, sentiment_data, strategies_dir.
        context: Lambda context (optional).

    Returns:
        JSON response with ranked strategy evaluations.
    """
    logger.info("Strategy evaluator invoked", extra={"symbol": event.get("symbol")})

    symbol = event.get("symbol")
    date = event.get("date")
    gap_data = event.get("gap_data", {})
    sentiment_data = event.get("sentiment_data", {})

    if not symbol:
        return _error_response("Missing required field: symbol")
    if not date:
        return _error_response("Missing required field: date")

    try:
        mcp_clients = _create_mcp_clients()

        # Build graph agent from blueprint
        # The Strands SDK Graph pattern handles node execution and edge routing
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Construct initial prompt with context from prior pipeline stages
        prompt = (
            f"Evaluate trading strategies for {symbol} on {date}.\n\n"
            f"## Gap Data (from gap detector)\n"
            f"{json.dumps(gap_data, indent=2)}\n\n"
            f"## Sentiment Data (from sentiment analyzer)\n"
            f"{json.dumps(sentiment_data, indent=2)}\n\n"
            f"## Instructions\n"
            f"The graph will route through these stages:\n"
            f"1. **gap_analysis**: Deep-dive into gap characteristics using get_ohlcv and get_volume_profile.\n"
            f"2. **technical_analysis**: Compute RSI, MACD, Bollinger bands via get_technical_indicators.\n"
            f"3. **sentiment_analysis**: Cross-reference sentiment with gap direction.\n"
            f"4. **signal_gate**: Proceed only if we have >= 2 confirmed signals.\n"
            f"5. **strategy_eval**: Load strategies from library, match entry conditions to signals, "
            f"   run backtest via backtest-mcp if historical data available, and rank strategies.\n\n"
            f"Output a StrategyEvaluationOutput with:\n"
            f"- symbol, date\n"
            f"- evaluated_strategies: list of (strategy_id, score, matched_conditions, backtest_summary)\n"
            f"- recommended_strategy_id: top-ranked strategy\n"
            f"- confidence: 0.0-1.0\n"
            f"- signals_used: list of signal names that contributed\n"
        )

        # The Graph pattern handles:
        # 1. Start at gap_analysis node
        # 2. Route to technical_analysis AND sentiment_analysis (parallel fan-out)
        # 3. Both converge at signal_gate
        # 4. Gate checks signal count, routes to strategy_eval if passed
        result = agent(prompt)

        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Strategy evaluator failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8001"),
    )
    clients["sentiment-mcp"] = create_mcp_client(
        name="sentiment-mcp",
        uri=os.environ.get("SENTIMENT_MCP_URI", "http://localhost:8003"),
    )
    clients["backtest-mcp"] = create_mcp_client(
        name="backtest-mcp",
        uri=os.environ.get("BACKTEST_MCP_URI", "http://localhost:8004"),
    )
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8002"),
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
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


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(data)}


def _error_response(message: str) -> dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": message})}
```

---

## Agent 4: Portfolio Recommender (Single, Extended Thinking)

### blueprints/agents/portfolio_recommender.yaml

```yaml
agent_id: portfolio-recommender
name: Portfolio Recommender Agent
version: "1.0.0"
description: >
  Synthesizes gap scores, sentiment scores, and strategy evaluations
  to produce final portfolio recommendations. Uses extended thinking
  for deeper reasoning about position sizing and risk management.

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 16384
  temperature: 0.1
  extended_thinking:
    enabled: true
    budget_tokens: 10000

system_prompt_id: portfolio-recommender-system-v1

tools:
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact
      - get_artifact
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_ohlcv
      - get_portfolio_exposure

execution:
  timeout_seconds: 120
  max_tool_calls: 30
  retry_policy:
    max_retries: 2
    backoff_base: 1.0

portfolio_constraints:
  max_positions: 10
  max_sector_concentration_pct: 30
  max_single_position_pct: 10
  min_confidence_threshold: 0.6

scoring_weights:
  gap_score: 0.45
  sentiment_score: 0.35
  technical_score: 0.20

output_schema: PortfolioRecommendation

tags:
  - portfolio
  - extended-thinking
  - phase-1
```

### src/qitp_agents/portfolio_recommender/__init__.py

```python
"""Portfolio Recommender Agent — extended thinking for synthesis and portfolio construction."""
```

### src/qitp_agents/portfolio_recommender/handler.py

```python
"""Portfolio Recommender Agent Lambda handler.

Input:  {
    "date": "2026-03-15",
    "gap_results_artifact_id": "...",
    "sentiment_report_artifact_id": "...",
    "strategy_evaluations": [
        {"symbol": "AAPL", "strategy_id": "gap_momentum_up", "score": 0.85, ...},
        ...
    ],
    "portfolio_constraints": {...}   # optional override
}
Output: PortfolioRecommendation JSON with recommendations + no_action_symbols.

Architecture:
- Single Strands agent with model.extended_thinking=true
- Synthesizes outputs from all prior pipeline stages
- Applies portfolio constraints (max positions, sector concentration)
- Composite score: gap(45%) + sentiment(35%) + technical(20%) for Phase 1 (no ML)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "lambda"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "portfolio-recommender"
MAX_OUTPUT_BYTES = 256 * 1024

# Default portfolio constraints (overridable via event)
DEFAULT_CONSTRAINTS = {
    "max_positions": 10,
    "max_sector_concentration_pct": 30,
    "max_single_position_pct": 10,
    "min_confidence_threshold": 0.6,
}

# Phase 1 scoring weights (no ML — simple weighted composite)
SCORING_WEIGHTS = {
    "gap_score": 0.45,
    "sentiment_score": 0.35,
    "technical_score": 0.20,
}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for Portfolio Recommender Agent.

    Args:
        event: Input with date, artifact IDs, strategy evaluations, constraints.
        context: Lambda context (optional).

    Returns:
        JSON response with portfolio recommendations.
    """
    logger.info("Portfolio recommender invoked", extra={"date": event.get("date")})

    date = event.get("date")
    gap_artifact_id = event.get("gap_results_artifact_id")
    sentiment_artifact_id = event.get("sentiment_report_artifact_id")
    strategy_evaluations = event.get("strategy_evaluations", [])
    constraints = {**DEFAULT_CONSTRAINTS, **event.get("portfolio_constraints", {})}

    if not date:
        return _error_response("Missing required field: date")
    if not strategy_evaluations:
        return _error_response("Missing required field: strategy_evaluations")

    try:
        mcp_clients = _create_mcp_clients()

        # Build agent with extended thinking enabled
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Construct detailed prompt for extended thinking
        prompt = (
            f"You are the Portfolio Recommender. Today is {date}.\n\n"
            f"## Scoring Weights (Phase 1 — no ML)\n"
            f"- Gap score weight: {SCORING_WEIGHTS['gap_score']}\n"
            f"- Sentiment score weight: {SCORING_WEIGHTS['sentiment_score']}\n"
            f"- Technical score weight: {SCORING_WEIGHTS['technical_score']}\n\n"
            f"## Portfolio Constraints\n"
            f"- Max positions: {constraints['max_positions']}\n"
            f"- Max sector concentration: {constraints['max_sector_concentration_pct']}%\n"
            f"- Max single position: {constraints['max_single_position_pct']}%\n"
            f"- Min confidence threshold: {constraints['min_confidence_threshold']}\n\n"
            f"## Strategy Evaluations from Pipeline\n"
            f"{json.dumps(strategy_evaluations, indent=2)}\n\n"
        )

        if gap_artifact_id:
            prompt += (
                f"## Additional Data\n"
                f"Retrieve gap detection results from artifact: {gap_artifact_id}\n"
                f"Retrieve sentiment report from artifact: {sentiment_artifact_id}\n\n"
            )

        prompt += (
            f"## Your Task\n"
            f"Use extended thinking to reason through the following:\n"
            f"1. For each symbol with a strategy evaluation, compute the composite score:\n"
            f"   composite = gap_score * {SCORING_WEIGHTS['gap_score']} + "
            f"sentiment_score * {SCORING_WEIGHTS['sentiment_score']} + "
            f"technical_score * {SCORING_WEIGHTS['technical_score']}\n"
            f"2. Filter out symbols below confidence threshold ({constraints['min_confidence_threshold']}).\n"
            f"3. Rank remaining symbols by composite score.\n"
            f"4. Apply portfolio constraints:\n"
            f"   - Take top {constraints['max_positions']} positions.\n"
            f"   - Check sector concentration — no sector > {constraints['max_sector_concentration_pct']}%.\n"
            f"   - Cap each position at {constraints['max_single_position_pct']}% of portfolio.\n"
            f"5. For each recommended symbol, include:\n"
            f"   symbol, strategy_id, composite_score, gap_score, sentiment_score, technical_score,\n"
            f"   suggested_position_size_pct, entry_price, stop_loss, take_profit.\n"
            f"6. List symbols that were analyzed but NOT recommended (no_action_symbols) with reason.\n"
            f"7. Create a PortfolioRecommendation artifact with all results.\n\n"
            f"Output the final PortfolioRecommendation JSON."
        )

        result = agent(prompt)

        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("Portfolio recommender failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8002"),
    )
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8001"),
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
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


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(data)}


def _error_response(message: str) -> dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": message})}
```

---

## Strategy Blueprints

### blueprints/strategies/gap_momentum_up.yaml

```yaml
strategy_id: gap-momentum-up
name: Gap Momentum Up
version: "1.0.0"
description: >
  Trades upward gap momentum. Enters on confirmed gap-up with strong volume
  and bullish sentiment, rides momentum with trailing stop.
status: draft

entry_conditions:
  - type: gap_up
    threshold_pct: 2.0
    description: "Gap up >= 2% from previous close"
  - type: volume_confirmation
    min_ratio: 1.5
    description: "Volume >= 1.5x average daily volume"
  - type: sentiment_alignment
    min_score: 0.2
    direction: bullish
    description: "Composite sentiment > 0.2 (bullish)"

exit_conditions:
  - type: trailing_stop
    activation_pct: 1.5
    trail_pct: 1.0
    description: "Trailing stop: activate at +1.5%, trail by 1.0%"
  - type: stop_loss
    pct: -2.0
    description: "Hard stop loss at -2.0% from entry"
  - type: take_profit
    pct: 5.0
    description: "Take profit at +5.0% from entry"
  - type: time_stop
    bars: 10
    description: "Exit after 10 bars if no target hit"

trailing_stop:
  activation_pct: 1.5
  trail_pct: 1.0
  reference: high

position_sizing:
  method: fixed_fraction
  fraction: 0.02
  max_position_pct: 10.0
  description: "Risk 2% of portfolio per trade, max 10% position"

risk_management:
  max_daily_loss_pct: 5.0
  max_concurrent_positions: 5
  correlation_check: true

required_agents:
  - gap-detector
  - sentiment-analyzer

required_mcps:
  - market-data-mcp
  - sentiment-mcp
  - artifacts-mcp

backtest_config:
  lookback_days: 252
  min_trades: 20
  min_win_rate: 0.55
  min_sharpe: 1.0

tags:
  - momentum
  - gap-up
  - phase-1
```

### blueprints/strategies/mean_reversion_gap.yaml

```yaml
strategy_id: mean-reversion-gap
name: Mean Reversion Gap
version: "1.0.0"
description: >
  Fades exhaustion gaps that are likely to fill. Enters counter-trend
  when gap shows signs of overextension and sentiment divergence.
status: draft

entry_conditions:
  - type: gap_up
    threshold_pct: 3.0
    description: "Large gap up >= 3% (overextension signal)"
  - type: volume_divergence
    max_ratio: 0.8
    description: "Volume < 0.8x average (weak conviction gap)"
  - type: rsi_overbought
    threshold: 75
    period: 14
    description: "RSI(14) > 75 indicating overbought"
  - type: sentiment_divergence
    max_score: 0.1
    description: "Sentiment is neutral/negative despite gap-up (divergence)"

exit_conditions:
  - type: gap_fill
    fill_pct: 80
    description: "Exit when 80% of gap is filled"
  - type: stop_loss
    pct: -1.5
    description: "Hard stop at -1.5% (gap continues instead of filling)"
  - type: take_profit
    pct: 3.0
    description: "Take profit at +3.0%"
  - type: time_stop
    bars: 5
    description: "Exit after 5 bars — mean reversion is fast or it fails"

trailing_stop:
  activation_pct: 1.0
  trail_pct: 0.5
  reference: low

position_sizing:
  method: fixed_fraction
  fraction: 0.015
  max_position_pct: 8.0
  description: "Risk 1.5% per trade — counter-trend is riskier"

risk_management:
  max_daily_loss_pct: 3.0
  max_concurrent_positions: 3
  correlation_check: true

required_agents:
  - gap-detector
  - sentiment-analyzer

required_mcps:
  - market-data-mcp
  - sentiment-mcp
  - artifacts-mcp

backtest_config:
  lookback_days: 252
  min_trades: 15
  min_win_rate: 0.60
  min_sharpe: 0.8

tags:
  - mean-reversion
  - gap-fade
  - counter-trend
  - phase-1
```

### blueprints/strategies/gap_continuation.yaml

```yaml
strategy_id: gap-continuation
name: Gap Continuation
version: "1.0.0"
description: >
  Breakaway gap strategy. Identifies gaps that signal trend continuation
  with strong volume and momentum confirmation. Wider stops, bigger targets.
status: draft

entry_conditions:
  - type: gap_up
    threshold_pct: 1.5
    description: "Gap up >= 1.5%"
  - type: volume_confirmation
    min_ratio: 2.0
    description: "Volume >= 2x average — strong conviction"
  - type: trend_alignment
    sma_period: 20
    direction: above
    description: "Price above 20-day SMA (uptrend)"
  - type: macd_bullish
    signal: crossover
    description: "MACD bullish crossover or already positive"

exit_conditions:
  - type: trailing_stop
    activation_pct: 2.0
    trail_pct: 1.5
    description: "Trailing stop: activate at +2.0%, trail by 1.5%"
  - type: stop_loss
    pct: -3.0
    description: "Wider stop at -3.0% — breakaway gaps need room"
  - type: take_profit
    pct: 8.0
    description: "Larger target at +8.0%"
  - type: time_stop
    bars: 20
    description: "Hold up to 20 bars for trend to develop"

trailing_stop:
  activation_pct: 2.0
  trail_pct: 1.5
  reference: high

position_sizing:
  method: volatility_adjusted
  atr_multiplier: 1.5
  max_position_pct: 10.0
  description: "Position size inversely proportional to ATR"

risk_management:
  max_daily_loss_pct: 5.0
  max_concurrent_positions: 5
  correlation_check: true

required_agents:
  - gap-detector

required_mcps:
  - market-data-mcp
  - artifacts-mcp

backtest_config:
  lookback_days: 504
  min_trades: 25
  min_win_rate: 0.50
  min_sharpe: 1.2

tags:
  - momentum
  - breakaway-gap
  - trend-following
  - phase-1
```

### blueprints/strategies/sentiment_driven.yaml

```yaml
strategy_id: sentiment-driven
name: Sentiment Driven
version: "1.0.0"
description: >
  Sentiment-first strategy. Enters when composite sentiment strongly aligns
  with a modest gap, betting on continued momentum from news/social catalysts.
status: draft

entry_conditions:
  - type: gap_up
    threshold_pct: 1.0
    description: "Even a modest gap >= 1.0% qualifies"
  - type: sentiment_strong
    min_score: 0.5
    description: "Composite sentiment > 0.5 (strongly bullish)"
  - type: news_catalyst
    min_sources: 3
    description: "At least 3 news sources covering the catalyst"
  - type: social_momentum
    min_social_score: 0.4
    description: "Social sentiment > 0.4 (retail interest)"

exit_conditions:
  - type: sentiment_reversal
    threshold: -0.1
    description: "Exit if sentiment flips negative"
  - type: trailing_stop
    activation_pct: 1.0
    trail_pct: 0.8
    description: "Tight trailing stop — sentiment plays are volatile"
  - type: stop_loss
    pct: -1.5
    description: "Hard stop at -1.5%"
  - type: take_profit
    pct: 4.0
    description: "Take profit at +4.0%"
  - type: time_stop
    bars: 5
    description: "Short holding period — sentiment decays fast"

trailing_stop:
  activation_pct: 1.0
  trail_pct: 0.8
  reference: high

position_sizing:
  method: fixed_fraction
  fraction: 0.015
  max_position_pct: 8.0
  description: "Conservative sizing — sentiment is noisy"

risk_management:
  max_daily_loss_pct: 4.0
  max_concurrent_positions: 4
  correlation_check: true

required_agents:
  - gap-detector
  - sentiment-analyzer

required_mcps:
  - market-data-mcp
  - sentiment-mcp
  - artifacts-mcp

backtest_config:
  lookback_days: 126
  min_trades: 15
  min_win_rate: 0.55
  min_sharpe: 0.9

tags:
  - sentiment
  - news-driven
  - social-momentum
  - phase-1
```

### blueprints/strategies/gap_etf_momentum.yaml

```yaml
strategy_id: gap-etf-momentum
name: Gap ETF Momentum
version: "1.0.0"
description: >
  Sector rotation via ETFs. When multiple stocks in a sector gap up,
  trade the sector ETF for broader exposure with lower single-stock risk.
status: draft

entry_conditions:
  - type: sector_gap_breadth
    min_stocks_gapping: 3
    sector_threshold_pct: 1.5
    description: "At least 3 stocks in sector gap up >= 1.5%"
  - type: etf_volume_confirmation
    min_ratio: 1.3
    description: "Sector ETF volume >= 1.3x average"
  - type: sector_sentiment
    min_score: 0.2
    description: "Average sector sentiment > 0.2"

exit_conditions:
  - type: trailing_stop
    activation_pct: 1.5
    trail_pct: 1.0
    description: "Trailing stop on ETF"
  - type: stop_loss
    pct: -2.0
    description: "Hard stop at -2.0%"
  - type: take_profit
    pct: 4.0
    description: "Take profit at +4.0%"
  - type: breadth_deterioration
    min_stocks_holding: 2
    description: "Exit if fewer than 2 stocks still holding gaps"
  - type: time_stop
    bars: 15
    description: "Hold up to 15 bars"

trailing_stop:
  activation_pct: 1.5
  trail_pct: 1.0
  reference: high

position_sizing:
  method: fixed_fraction
  fraction: 0.025
  max_position_pct: 15.0
  description: "Larger position OK — ETFs have lower single-stock risk"

risk_management:
  max_daily_loss_pct: 5.0
  max_concurrent_positions: 3
  correlation_check: true

required_agents:
  - gap-detector
  - sentiment-analyzer

required_mcps:
  - market-data-mcp
  - sentiment-mcp
  - artifacts-mcp

backtest_config:
  lookback_days: 252
  min_trades: 10
  min_win_rate: 0.55
  min_sharpe: 1.0

tags:
  - etf
  - sector-rotation
  - momentum
  - phase-1
```

---

## Tests

### tests/conftest.py

```python
"""Shared test fixtures for qitp-agents."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set default environment variables for testing."""
    monkeypatch.setenv("EXECUTION_MODE", "test")
    monkeypatch.setenv("BLUEPRINTS_DIR", "blueprints")
    monkeypatch.setenv("MARKET_DATA_MCP_URI", "http://localhost:8001")
    monkeypatch.setenv("ARTIFACTS_MCP_URI", "http://localhost:8002")
    monkeypatch.setenv("SENTIMENT_MCP_URI", "http://localhost:8003")
    monkeypatch.setenv("BACKTEST_MCP_URI", "http://localhost:8004")


@pytest.fixture
def mock_blueprint_loader():
    """Mock BlueprintLoader that returns a mock agent."""
    with patch("agent_core.blueprint.BlueprintLoader") as mock_cls:
        loader = MagicMock()
        mock_cls.return_value = loader

        mock_agent = MagicMock()
        mock_agent.return_value = {"status": "success", "data": {}}
        loader.build_strands_agent.return_value = mock_agent

        yield loader, mock_agent


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client factory."""
    with patch("agent_core.mcp.create_mcp_client") as mock_create:
        client = MagicMock()
        mock_create.return_value = client
        yield client


@pytest.fixture
def sample_gap_data() -> dict[str, Any]:
    """Sample gap detection output for testing."""
    return {
        "ranked_gaps": [
            {
                "symbol": "AAPL",
                "gap_pct": 3.2,
                "direction": "up",
                "volume_ratio": 2.1,
                "previous_close": 185.50,
                "open_price": 191.44,
                "confidence": 0.87,
            },
            {
                "symbol": "TSLA",
                "gap_pct": 4.5,
                "direction": "up",
                "volume_ratio": 1.8,
                "previous_close": 245.00,
                "open_price": 256.02,
                "confidence": 0.79,
            },
            {
                "symbol": "NVDA",
                "gap_pct": 2.1,
                "direction": "up",
                "volume_ratio": 1.6,
                "previous_close": 890.00,
                "open_price": 908.69,
                "confidence": 0.72,
            },
        ],
        "date": "2026-03-15",
        "threshold_pct": 2.0,
        "total_scanned": 50,
    }


@pytest.fixture
def sample_sentiment_data() -> dict[str, Any]:
    """Sample sentiment report for testing."""
    return {
        "symbols": {
            "AAPL": {
                "composite_score": 0.65,
                "news_score": 0.7,
                "social_score": 0.55,
                "source_count": 12,
                "dominant_theme": "earnings_beat",
            },
            "TSLA": {
                "composite_score": 0.4,
                "news_score": 0.3,
                "social_score": 0.6,
                "source_count": 25,
                "dominant_theme": "product_launch",
            },
            "NVDA": {
                "composite_score": 0.55,
                "news_score": 0.6,
                "social_score": 0.45,
                "source_count": 8,
                "dominant_theme": "ai_demand",
            },
        },
        "overall_market_sentiment": 0.53,
        "date": "2026-03-15",
    }


@pytest.fixture
def sample_strategy_evaluations() -> list[dict[str, Any]]:
    """Sample strategy evaluation results for testing."""
    return [
        {
            "symbol": "AAPL",
            "strategy_id": "gap-momentum-up",
            "score": 0.85,
            "gap_score": 0.87,
            "sentiment_score": 0.65,
            "technical_score": 0.90,
            "matched_conditions": ["gap_up", "volume_confirmation", "sentiment_alignment"],
            "confidence": 0.85,
        },
        {
            "symbol": "TSLA",
            "strategy_id": "sentiment-driven",
            "score": 0.72,
            "gap_score": 0.79,
            "sentiment_score": 0.40,
            "technical_score": 0.75,
            "matched_conditions": ["gap_up", "social_momentum"],
            "confidence": 0.68,
        },
        {
            "symbol": "NVDA",
            "strategy_id": "gap-continuation",
            "score": 0.78,
            "gap_score": 0.72,
            "sentiment_score": 0.55,
            "technical_score": 0.88,
            "matched_conditions": ["gap_up", "volume_confirmation", "trend_alignment"],
            "confidence": 0.75,
        },
    ]
```

### tests/unit/test_gap_detector.py

```python
"""Unit tests for Gap Detection Agent handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestGapDetectorHandler:
    """Tests for gap_detector.handler.handler()."""

    @patch("qitp_agents.gap_detector.handler._create_mcp_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    def test_handler_success(self, mock_loader, mock_mcp, sample_gap_data):
        """Handler returns ranked gaps on valid input."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_gap_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {"market-data-mcp": MagicMock(), "artifacts-mcp": MagicMock()}

        from qitp_agents.gap_detector.handler import handler

        result = handler({"date": "2026-03-15", "threshold_pct": 2.0})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "ranked_gaps" in body

    @patch("qitp_agents.gap_detector.handler._create_mcp_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    def test_handler_missing_date(self, mock_loader, mock_mcp):
        """Handler returns error when date is missing."""
        from qitp_agents.gap_detector.handler import handler

        result = handler({"threshold_pct": 2.0})

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
        assert "date" in body["error"]

    @patch("qitp_agents.gap_detector.handler._create_mcp_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    def test_handler_default_threshold(self, mock_loader, mock_mcp, sample_gap_data):
        """Handler uses default threshold_pct when not provided."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_gap_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.gap_detector.handler import handler

        result = handler({"date": "2026-03-15"})
        assert result["statusCode"] == 200

    @patch("qitp_agents.gap_detector.handler._create_mcp_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    def test_handler_agent_exception(self, mock_loader, mock_mcp):
        """Handler returns error when agent throws exception."""
        mock_agent = MagicMock()
        mock_agent.side_effect = RuntimeError("MCP connection failed")
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.gap_detector.handler import handler

        result = handler({"date": "2026-03-15"})
        assert result["statusCode"] == 500

    @patch("qitp_agents.gap_detector.handler._create_mcp_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    def test_handler_claim_check_large_output(self, mock_loader, mock_mcp):
        """Handler returns claim-check when output exceeds 256KB."""
        large_data = {"ranked_gaps": [{"symbol": f"SYM{i}", "data": "x" * 1000} for i in range(300)]}
        mock_agent = MagicMock()
        mock_agent.return_value = large_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.gap_detector.handler import handler

        result = handler({"date": "2026-03-15"})
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body.get("claim_check") is True
```

### tests/unit/test_sentiment_analyzer.py

```python
"""Unit tests for Sentiment Analysis Agent handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestSentimentAnalyzerHandler:
    """Tests for sentiment_analyzer.handler.handler()."""

    @patch("qitp_agents.sentiment_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.sentiment_analyzer.handler.LOADER")
    def test_handler_success(self, mock_loader, mock_mcp, sample_sentiment_data):
        """Handler returns sentiment report on valid input."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_sentiment_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.sentiment_analyzer.handler import handler

        result = handler({
            "symbols": ["AAPL", "TSLA", "NVDA"],
            "date": "2026-03-15",
        })

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "symbols" in body

    @patch("qitp_agents.sentiment_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.sentiment_analyzer.handler.LOADER")
    def test_handler_missing_symbols(self, mock_loader, mock_mcp):
        """Handler returns error when symbols list is missing."""
        from qitp_agents.sentiment_analyzer.handler import handler

        result = handler({"date": "2026-03-15"})

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "symbols" in body["error"]

    @patch("qitp_agents.sentiment_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.sentiment_analyzer.handler.LOADER")
    def test_handler_missing_date(self, mock_loader, mock_mcp):
        """Handler returns error when date is missing."""
        from qitp_agents.sentiment_analyzer.handler import handler

        result = handler({"symbols": ["AAPL"]})

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "date" in body["error"]

    @patch("qitp_agents.sentiment_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.sentiment_analyzer.handler.LOADER")
    def test_handler_with_gap_artifact(self, mock_loader, mock_mcp, sample_sentiment_data):
        """Handler accepts optional gap_results_artifact_id for cross-reference."""
        mock_agent = MagicMock()
        mock_agent.return_value = sample_sentiment_data
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.sentiment_analyzer.handler import handler

        result = handler({
            "symbols": ["AAPL"],
            "date": "2026-03-15",
            "gap_results_artifact_id": "artifact-123",
        })

        assert result["statusCode"] == 200

    @patch("qitp_agents.sentiment_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.sentiment_analyzer.handler.LOADER")
    def test_handler_agent_exception(self, mock_loader, mock_mcp):
        """Handler returns error when swarm agent throws."""
        mock_agent = MagicMock()
        mock_agent.side_effect = RuntimeError("Swarm coordination failed")
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.sentiment_analyzer.handler import handler

        result = handler({"symbols": ["AAPL"], "date": "2026-03-15"})
        assert result["statusCode"] == 500
```

### tests/unit/test_strategy_evaluator.py

```python
"""Unit tests for Strategy Evaluation Agent handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestStrategyEvaluatorHandler:
    """Tests for strategy_evaluator.handler.handler()."""

    @patch("qitp_agents.strategy_evaluator.handler._create_mcp_clients")
    @patch("qitp_agents.strategy_evaluator.handler.LOADER")
    def test_handler_success(self, mock_loader, mock_mcp, sample_gap_data, sample_sentiment_data):
        """Handler returns strategy evaluations on valid input."""
        eval_result = {
            "symbol": "AAPL",
            "evaluated_strategies": [
                {"strategy_id": "gap-momentum-up", "score": 0.85, "matched_conditions": ["gap_up", "volume"]},
            ],
            "recommended_strategy_id": "gap-momentum-up",
            "confidence": 0.85,
            "signals_used": ["gap_up", "volume_confirmation", "sentiment_alignment"],
        }
        mock_agent = MagicMock()
        mock_agent.return_value = eval_result
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.strategy_evaluator.handler import handler

        result = handler({
            "symbol": "AAPL",
            "date": "2026-03-15",
            "gap_data": sample_gap_data["ranked_gaps"][0],
            "sentiment_data": sample_sentiment_data["symbols"]["AAPL"],
        })

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "evaluated_strategies" in body

    @patch("qitp_agents.strategy_evaluator.handler._create_mcp_clients")
    @patch("qitp_agents.strategy_evaluator.handler.LOADER")
    def test_handler_missing_symbol(self, mock_loader, mock_mcp):
        """Handler returns error when symbol is missing."""
        from qitp_agents.strategy_evaluator.handler import handler

        result = handler({"date": "2026-03-15"})
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "symbol" in body["error"]

    @patch("qitp_agents.strategy_evaluator.handler._create_mcp_clients")
    @patch("qitp_agents.strategy_evaluator.handler.LOADER")
    def test_handler_missing_date(self, mock_loader, mock_mcp):
        """Handler returns error when date is missing."""
        from qitp_agents.strategy_evaluator.handler import handler

        result = handler({"symbol": "AAPL"})
        assert result["statusCode"] == 500

    @patch("qitp_agents.strategy_evaluator.handler._create_mcp_clients")
    @patch("qitp_agents.strategy_evaluator.handler.LOADER")
    def test_handler_graph_exception(self, mock_loader, mock_mcp):
        """Handler returns error when graph execution fails."""
        mock_agent = MagicMock()
        mock_agent.side_effect = RuntimeError("Signal gate tripped")
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.strategy_evaluator.handler import handler

        result = handler({"symbol": "AAPL", "date": "2026-03-15"})
        assert result["statusCode"] == 500
```

### tests/unit/test_portfolio_recommender.py

```python
"""Unit tests for Portfolio Recommender Agent handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestPortfolioRecommenderHandler:
    """Tests for portfolio_recommender.handler.handler()."""

    @patch("qitp_agents.portfolio_recommender.handler._create_mcp_clients")
    @patch("qitp_agents.portfolio_recommender.handler.LOADER")
    def test_handler_success(self, mock_loader, mock_mcp, sample_strategy_evaluations):
        """Handler returns portfolio recommendation on valid input."""
        recommendation = {
            "date": "2026-03-15",
            "recommendations": [
                {
                    "symbol": "AAPL",
                    "strategy_id": "gap-momentum-up",
                    "composite_score": 0.82,
                    "suggested_position_size_pct": 8.0,
                },
            ],
            "no_action_symbols": [
                {"symbol": "TSLA", "reason": "Below confidence threshold"},
            ],
        }
        mock_agent = MagicMock()
        mock_agent.return_value = recommendation
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.portfolio_recommender.handler import handler

        result = handler({
            "date": "2026-03-15",
            "strategy_evaluations": sample_strategy_evaluations,
        })

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "recommendations" in body
        assert "no_action_symbols" in body

    @patch("qitp_agents.portfolio_recommender.handler._create_mcp_clients")
    @patch("qitp_agents.portfolio_recommender.handler.LOADER")
    def test_handler_missing_date(self, mock_loader, mock_mcp, sample_strategy_evaluations):
        """Handler returns error when date is missing."""
        from qitp_agents.portfolio_recommender.handler import handler

        result = handler({"strategy_evaluations": sample_strategy_evaluations})
        assert result["statusCode"] == 500

    @patch("qitp_agents.portfolio_recommender.handler._create_mcp_clients")
    @patch("qitp_agents.portfolio_recommender.handler.LOADER")
    def test_handler_missing_evaluations(self, mock_loader, mock_mcp):
        """Handler returns error when strategy_evaluations is missing."""
        from qitp_agents.portfolio_recommender.handler import handler

        result = handler({"date": "2026-03-15"})
        assert result["statusCode"] == 500

    @patch("qitp_agents.portfolio_recommender.handler._create_mcp_clients")
    @patch("qitp_agents.portfolio_recommender.handler.LOADER")
    def test_handler_custom_constraints(self, mock_loader, mock_mcp, sample_strategy_evaluations):
        """Handler accepts custom portfolio constraints override."""
        mock_agent = MagicMock()
        mock_agent.return_value = {"recommendations": [], "no_action_symbols": []}
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.portfolio_recommender.handler import handler

        result = handler({
            "date": "2026-03-15",
            "strategy_evaluations": sample_strategy_evaluations,
            "portfolio_constraints": {
                "max_positions": 5,
                "min_confidence_threshold": 0.8,
            },
        })

        assert result["statusCode"] == 200

    @patch("qitp_agents.portfolio_recommender.handler._create_mcp_clients")
    @patch("qitp_agents.portfolio_recommender.handler.LOADER")
    def test_handler_extended_thinking_invoked(self, mock_loader, mock_mcp, sample_strategy_evaluations):
        """Verify agent is built from blueprint (which has extended_thinking enabled)."""
        mock_agent = MagicMock()
        mock_agent.return_value = {"recommendations": []}
        mock_loader.build_strands_agent.return_value = mock_agent
        mock_mcp.return_value = {}

        from qitp_agents.portfolio_recommender.handler import handler

        handler({
            "date": "2026-03-15",
            "strategy_evaluations": sample_strategy_evaluations,
        })

        # Verify the loader was asked to build the portfolio-recommender agent
        mock_loader.build_strands_agent.assert_called_once()
        call_args = mock_loader.build_strands_agent.call_args
        assert call_args[0][0] == "portfolio-recommender"
```

### tests/integration/test_pipeline.py

```python
"""Integration test: full pipeline from gap detection -> portfolio recommendation.

This test mocks all MCP tools but exercises the handler wiring end-to-end.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestFullPipeline:
    """End-to-end pipeline integration test with mocked MCPs."""

    @patch("qitp_agents.gap_detector.handler._create_mcp_clients")
    @patch("qitp_agents.gap_detector.handler.LOADER")
    @patch("qitp_agents.sentiment_analyzer.handler._create_mcp_clients")
    @patch("qitp_agents.sentiment_analyzer.handler.LOADER")
    @patch("qitp_agents.strategy_evaluator.handler._create_mcp_clients")
    @patch("qitp_agents.strategy_evaluator.handler.LOADER")
    @patch("qitp_agents.portfolio_recommender.handler._create_mcp_clients")
    @patch("qitp_agents.portfolio_recommender.handler.LOADER")
    def test_pipeline_end_to_end(
        self,
        pr_loader, pr_mcp,
        se_loader, se_mcp,
        sa_loader, sa_mcp,
        gd_loader, gd_mcp,
        sample_gap_data,
        sample_sentiment_data,
        sample_strategy_evaluations,
    ):
        """Run all 4 handlers sequentially, passing outputs forward."""
        # --- Stage 1: Gap Detection ---
        gd_agent = MagicMock()
        gd_agent.return_value = sample_gap_data
        gd_loader.build_strands_agent.return_value = gd_agent
        gd_mcp.return_value = {}

        from qitp_agents.gap_detector.handler import handler as gd_handler
        gd_result = gd_handler({"date": "2026-03-15", "threshold_pct": 2.0})
        assert gd_result["statusCode"] == 200
        gap_output = json.loads(gd_result["body"])

        # --- Stage 2: Sentiment Analysis ---
        sa_agent = MagicMock()
        sa_agent.return_value = sample_sentiment_data
        sa_loader.build_strands_agent.return_value = sa_agent
        sa_mcp.return_value = {}

        symbols = [g["symbol"] for g in gap_output["ranked_gaps"]]

        from qitp_agents.sentiment_analyzer.handler import handler as sa_handler
        sa_result = sa_handler({"symbols": symbols, "date": "2026-03-15"})
        assert sa_result["statusCode"] == 200
        sentiment_output = json.loads(sa_result["body"])

        # --- Stage 3: Strategy Evaluation (per symbol) ---
        eval_results = []
        for sym_gap in gap_output["ranked_gaps"]:
            sym = sym_gap["symbol"]
            se_agent = MagicMock()
            se_agent.return_value = {
                "symbol": sym,
                "evaluated_strategies": [{"strategy_id": "gap-momentum-up", "score": 0.8}],
                "recommended_strategy_id": "gap-momentum-up",
                "confidence": 0.8,
                "signals_used": ["gap_up"],
                "gap_score": sym_gap["confidence"],
                "sentiment_score": sentiment_output["symbols"].get(sym, {}).get("composite_score", 0),
                "technical_score": 0.75,
            }
            se_loader.build_strands_agent.return_value = se_agent
            se_mcp.return_value = {}

            from qitp_agents.strategy_evaluator.handler import handler as se_handler
            se_result = se_handler({
                "symbol": sym,
                "date": "2026-03-15",
                "gap_data": sym_gap,
                "sentiment_data": sentiment_output["symbols"].get(sym, {}),
            })
            assert se_result["statusCode"] == 200
            eval_results.append(json.loads(se_result["body"]))

        # --- Stage 4: Portfolio Recommendation ---
        pr_agent = MagicMock()
        pr_agent.return_value = {
            "date": "2026-03-15",
            "recommendations": [
                {"symbol": "AAPL", "strategy_id": "gap-momentum-up", "composite_score": 0.82},
                {"symbol": "NVDA", "strategy_id": "gap-continuation", "composite_score": 0.73},
            ],
            "no_action_symbols": [
                {"symbol": "TSLA", "reason": "Sentiment below threshold"},
            ],
        }
        pr_loader.build_strands_agent.return_value = pr_agent
        pr_mcp.return_value = {}

        from qitp_agents.portfolio_recommender.handler import handler as pr_handler
        pr_result = pr_handler({
            "date": "2026-03-15",
            "strategy_evaluations": eval_results,
        })

        assert pr_result["statusCode"] == 200
        final_output = json.loads(pr_result["body"])
        assert "recommendations" in final_output
        assert "no_action_symbols" in final_output
        assert len(final_output["recommendations"]) >= 1
```

---

## Acceptance Criteria
- [ ] All 4 agent handlers instantiate correctly from blueprints
- [ ] Gap detector processes watchlist and produces ranked_gaps
- [ ] Sentiment analyzer runs Swarm pattern with parallel per-ticker agents
- [ ] Strategy evaluator uses Graph pattern with deterministic edge conditions
- [ ] Portfolio recommender produces valid recommendation JSON
- [ ] All 5 strategy YAMLs validate against StrategyBlueprint schema
- [ ] Unit tests pass with mocked MCPs

## Test Plan
```bash
cd ~/dev/tccw-qitp-agents
pip install -e ".[dev]"
pytest tests/unit/ -v
pytest tests/integration/ -v
```

## Agent Instructions
These are the heart of the platform. Each agent is thin -- the logic lives in the Strands SDK and the MCP tools. The agent handler is mostly wiring: load blueprint, connect MCPs, invoke agent, marshal output. Test with mocked MCP responses. The Swarm and Graph patterns use real Strands SDK APIs (from strands.multiagent).

Key patterns to follow:
1. **Warm-start**: LOADER and EXECUTION_MODE initialized outside handler for Lambda reuse
2. **MCP per-invocation**: Create MCP clients inside handler, clean up after
3. **Claim-check**: If output > 256KB, store artifact and return reference
4. **Error handling**: Always return structured JSON with statusCode, never throw unhandled
5. **Blueprint-driven**: All agent config lives in YAML, handler code is generic wiring
