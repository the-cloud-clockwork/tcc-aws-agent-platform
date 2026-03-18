# P01 — Repo Scaffold & CI/CD Bootstrap

## Objective
Create all 12 QITP repos in ~/dev/ with standard structure, CI/CD pipelines, and CLAUDE.md files pointing back to the specs repo.

## Plane Tickets
ROOT-66

## Target Repos
All 12 repos created in ~/dev/:

### Python Libraries (pip installable)
1. `tccw-agent-core` — Blueprint engine, schemas, hooks, execution modes
2. `tccw-qitp-simulation` — Backtest engine, financial metrics

### MCP Servers (Docker + Fargate)
3. `tccw-qitp-mcp-market-data` — Unified market data
4. `tccw-qitp-mcp-sentiment` — Sentiment scoring
5. `tccw-mcp-artifacts` — S3 artifact store
6. `tccw-qitp-mcp-backtest` — Simulation engine MCP wrapper

### Phase 2 MCP Servers (skeleton only)
7. `tccw-qitp-mcp-ibkr` — Interactive Brokers (Phase 2)
8. `tccw-qitp-mcp-charting` — Chart generation (Phase 2)

### Applications
9. `tccw-qitp-agents` — All Strands agents (subdirectory per agent)
10. `tccw-prompt-registry` — Lambda API service for versioned prompts
11. `tccw-agent-cli` — `qitp` CLI tool
12. `tccw-agent-infra` — CDK Python stacks

## Dependencies
None — this is the first plan.

## Repo Structure Templates

For EACH repo type, the EXACT file tree and the FULL content of every file is provided below.

### Template A: Python Library (tccw-agent-core, tccw-qitp-simulation)
```
tccw-qitp-{name}/
├── pyproject.toml
├── src/
│   └── qitp_{name}/
│       ├── __init__.py
│       └── py.typed
├── tests/
│   ├── __init__.py
│   └── conftest.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── .python-version
├── CLAUDE.md
└── README.md
```

### Template B: MCP Server (tccw-qitp-mcp-*)
```
tccw-qitp-mcp-{name}/
├── pyproject.toml
├── src/
│   └── qitp_mcp_{name}/
│       ├── __init__.py
│       ├── server.py          # MCP server entrypoint
│       ├── tools/
│       │   └── __init__.py
│       └── py.typed
├── tests/
│   ├── __init__.py
│   └── conftest.py
├── Dockerfile
├── docker-compose.yml
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── .python-version
├── CLAUDE.md
└── README.md
```

### Template C: Agents Repo (tccw-qitp-agents)
```
tccw-qitp-agents/
├── pyproject.toml
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
│   └── integration/
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── .python-version
├── CLAUDE.md
└── README.md
```

### Template D: CDK Infra (tccw-agent-infra)
```
tccw-agent-infra/
├── pyproject.toml
├── app.py
├── stacks/
│   ├── __init__.py
│   ├── data_stack.py
│   ├── network_stack.py
│   ├── agent_stack.py
│   ├── mcp_stack.py
│   ├── orchestration_stack.py
│   └── observability_stack.py
├── constructs/
│   ├── __init__.py
│   ├── strands_agent.py
│   ├── mcp_service.py
│   └── sfn_workflow.py
├── tests/
│   └── __init__.py
├── cdk.json
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── CLAUDE.md
└── README.md
```

### Template E: Prompt Registry Service
```
tccw-prompt-registry/
├── pyproject.toml
├── src/
│   └── prompt_registry/
│       ├── __init__.py
│       ├── handler.py         # Lambda handler
│       ├── models.py          # Pydantic models
│       └── storage.py         # S3 + DynamoDB ops
├── tests/
│   └── __init__.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── .python-version
├── CLAUDE.md
└── README.md
```

### Template F: CLI Tool
```
tccw-agent-cli/
├── pyproject.toml
├── src/
│   └── agent_cli/
│       ├── __init__.py
│       ├── main.py
│       ├── prompt.py
│       ├── strategy.py
│       ├── blueprint.py
│       └── graph.py
├── tests/
│   └── __init__.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── .python-version
├── CLAUDE.md
└── README.md
```

## Implementation Details — Full File Contents

### 1. pyproject.toml Files

#### Template A: tccw-agent-core/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-core"
version = "0.1.0"
description = "QITP Core Engine — Blueprint loader, schemas, hooks, execution modes"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "strands-agents>=1.0",
    "boto3>=1.35",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/agent_core"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template A: tccw-qitp-simulation/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-simulation"
version = "0.1.0"
description = "QITP Simulation — Backtest engine, financial metrics, Monte Carlo analysis"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "agent-core>=0.1.0",
    "pandas>=2.0",
    "numpy>=1.26",
    "pyarrow>=15.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_simulation"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template B: tccw-qitp-mcp-market-data/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-market-data"
version = "0.1.0"
description = "QITP Market Data MCP Server — Unified market data access"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "fastmcp>=0.1",
    "agent-core>=0.1.0",
    "boto3>=1.35",
    "pandas>=2.0",
    "pyarrow>=15.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_market_data"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template B: tccw-qitp-mcp-sentiment/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-sentiment"
version = "0.1.0"
description = "QITP Sentiment MCP Server — Sentiment scoring and analysis"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "fastmcp>=0.1",
    "agent-core>=0.1.0",
    "boto3>=1.35",
    "pandas>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_sentiment"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template B: tccw-mcp-artifacts/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mcp-artifacts"
version = "0.1.0"
description = "QITP Artifacts MCP Server — S3 artifact store for run outputs"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "fastmcp>=0.1",
    "agent-core>=0.1.0",
    "boto3>=1.35",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/mcp_artifacts"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template B: tccw-qitp-mcp-backtest/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-backtest"
version = "0.1.0"
description = "QITP Backtest MCP Server — Simulation engine MCP wrapper"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "fastmcp>=0.1",
    "agent-core>=0.1.0",
    "qitp-simulation>=0.1.0",
    "boto3>=1.35",
    "pandas>=2.0",
    "pyarrow>=15.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_backtest"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template B: tccw-qitp-mcp-ibkr/pyproject.toml (Phase 2 skeleton)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-ibkr"
version = "0.1.0"
description = "QITP IBKR MCP Server — Interactive Brokers integration (Phase 2)"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "fastmcp>=0.1",
    "agent-core>=0.1.0",
    "boto3>=1.35",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_ibkr"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template B: tccw-qitp-mcp-charting/pyproject.toml (Phase 2 skeleton)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-charting"
version = "0.1.0"
description = "QITP Charting MCP Server — Chart generation (Phase 2)"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "fastmcp>=0.1",
    "agent-core>=0.1.0",
    "boto3>=1.35",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_charting"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template C: tccw-qitp-agents/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-agents"
version = "0.1.0"
description = "QITP Agents — All Strands-based trading agents"
requires-python = ">=3.12"
dependencies = [
    "agent-core>=0.1.0",
    "strands-agents>=1.0",
    "boto3>=1.35",
    "pydantic>=2.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_agents"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template D: tccw-agent-infra/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-infra"
version = "0.1.0"
description = "QITP Infrastructure — CDK Python stacks for AWS deployment"
requires-python = ">=3.12"
dependencies = [
    "aws-cdk-lib>=2.170.0",
    "constructs>=10.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template E: tccw-prompt-registry/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "prompt-registry"
version = "0.1.0"
description = "QITP Prompt Registry — Lambda API for versioned prompt management"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "boto3>=1.35",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/prompt_registry"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
```

#### Template F: tccw-agent-cli/pyproject.toml
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-cli"
version = "0.1.0"
description = "QITP CLI — Command-line interface for QITP platform operations"
requires-python = ">=3.12"
dependencies = [
    "click>=8.0",
    "rich>=13.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "boto3>=1.35",
]

[project.scripts]
qitp = "agent_cli.main:cli"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/agent_cli"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
```

### 2. Dockerfile (MCP Servers)

One Dockerfile per MCP server — adjust the CMD module name per repo.

#### tccw-qitp-mcp-market-data/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "qitp_mcp_market_data.server"]
```

#### tccw-qitp-mcp-sentiment/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "qitp_mcp_sentiment.server"]
```

#### tccw-mcp-artifacts/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "mcp_artifacts.server"]
```

#### tccw-qitp-mcp-backtest/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "qitp_mcp_backtest.server"]
```

#### tccw-qitp-mcp-ibkr/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "qitp_mcp_ibkr.server"]
```

#### tccw-qitp-mcp-charting/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV EXECUTION_MODE=backtest
ENV AWS_DEFAULT_REGION=eu-west-1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "qitp_mcp_charting.server"]
```

### 3. docker-compose.yml (MCP Servers)

#### tccw-qitp-mcp-market-data/docker-compose.yml
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8002}:8000"
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
    volumes:
      - ./src:/app/src
```

#### tccw-qitp-mcp-sentiment/docker-compose.yml
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8003}:8000"
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
    volumes:
      - ./src:/app/src
```

#### tccw-mcp-artifacts/docker-compose.yml
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8004}:8000"
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
    volumes:
      - ./src:/app/src
```

#### tccw-qitp-mcp-backtest/docker-compose.yml
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8005}:8000"
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
    volumes:
      - ./src:/app/src
```

#### tccw-qitp-mcp-ibkr/docker-compose.yml
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8006}:8000"
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
    volumes:
      - ./src:/app/src
```

#### tccw-qitp-mcp-charting/docker-compose.yml
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8007}:8000"
    environment:
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
    volumes:
      - ./src:/app/src
```

### 4. .github/workflows/ci.yml (shared across ALL repos)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Lint
        run: ruff check . && ruff format --check .
      - name: Type check
        run: mypy src/
      - name: Test
        run: pytest -v
```

### 5. .gitignore (shared across ALL repos)

```
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
.env
.env.*
*.parquet
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.log
.DS_Store
```

### 6. .python-version (shared across ALL repos except tccw-agent-infra)

```
3.12
```

### 7. CLAUDE.md Files (one per repo — adjust name, description, and plan reference)

#### tccw-agent-core/CLAUDE.md
```markdown
# tccw-agent-core

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P02-core-engine.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Blueprint engine, schemas, hooks, execution modes. This is the foundational library that all other QITP components depend on.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy

## Commands
```bash
pip install -e ".[dev]"   # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                 # Type check
pytest -v                 # Test
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-simulation/CLAUDE.md
```markdown
# tccw-qitp-simulation

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P03-simulation.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Backtest engine, financial metrics, Monte Carlo analysis. Provides simulation capabilities for strategy evaluation.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy

## Commands
```bash
pip install -e ".[dev]"   # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                 # Type check
pytest -v                 # Test
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-mcp-market-data/CLAUDE.md
```markdown
# tccw-qitp-mcp-market-data

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P04-mcp-servers.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Unified market data MCP server. Provides tools for fetching OHLCV data, screening stocks, and accessing financial data.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: Docker / Fargate

## Commands
```bash
pip install -e ".[dev]"        # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                      # Type check
pytest -v                      # Test
docker compose up              # Run locally
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-mcp-sentiment/CLAUDE.md
```markdown
# tccw-qitp-mcp-sentiment

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P04-mcp-servers.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Sentiment scoring MCP server. Analyzes news, social media, and market sentiment for trading signals.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: Docker / Fargate

## Commands
```bash
pip install -e ".[dev]"        # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                      # Type check
pytest -v                      # Test
docker compose up              # Run locally
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-mcp-artifacts/CLAUDE.md
```markdown
# tccw-mcp-artifacts

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P04-mcp-servers.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
S3 artifact store MCP server. Manages storage and retrieval of run outputs, backtest results, and agent artifacts.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: Docker / Fargate

## Commands
```bash
pip install -e ".[dev]"        # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                      # Type check
pytest -v                      # Test
docker compose up              # Run locally
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-mcp-backtest/CLAUDE.md
```markdown
# tccw-qitp-mcp-backtest

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P04-mcp-servers.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Simulation engine MCP wrapper. Exposes backtest capabilities as MCP tools for agent consumption.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: Docker / Fargate

## Commands
```bash
pip install -e ".[dev]"        # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                      # Type check
pytest -v                      # Test
docker compose up              # Run locally
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-mcp-ibkr/CLAUDE.md
```markdown
# tccw-qitp-mcp-ibkr

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P04-mcp-servers.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Interactive Brokers MCP server (Phase 2). Will provide order execution and portfolio management tools.

**STATUS: Phase 2 skeleton only — no tools implemented yet.**

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: Docker / Fargate

## Commands
```bash
pip install -e ".[dev]"        # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                      # Type check
pytest -v                      # Test
docker compose up              # Run locally
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-mcp-charting/CLAUDE.md
```markdown
# tccw-qitp-mcp-charting

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P04-mcp-servers.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Chart generation MCP server (Phase 2). Will generate technical analysis charts and visualizations.

**STATUS: Phase 2 skeleton only — no tools implemented yet.**

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: Docker / Fargate

## Commands
```bash
pip install -e ".[dev]"        # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                      # Type check
pytest -v                      # Test
docker compose up              # Run locally
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-qitp-agents/CLAUDE.md
```markdown
# tccw-qitp-agents

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P05-agents.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
All Strands-based trading agents: gap detector, sentiment analyzer, strategy evaluator, portfolio recommender. Blueprints define agent configuration; handlers implement the agent logic.

## Agents
- **gap_detector** — Scans for gap trading opportunities
- **sentiment_analyzer** — Scores market sentiment signals
- **strategy_evaluator** — Evaluates strategy performance
- **portfolio_recommender** — Generates portfolio recommendations

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy

## Commands
```bash
pip install -e ".[dev]"   # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                 # Type check
pytest -v                 # Test
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-prompt-registry/CLAUDE.md
```markdown
# tccw-prompt-registry

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P06-prompt-registry.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
Lambda API service for versioned prompt management. Stores, retrieves, and versions prompts used by all QITP agents.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- Runtime: AWS Lambda

## Commands
```bash
pip install -e ".[dev]"   # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                 # Type check
pytest -v                 # Test
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-agent-cli/CLAUDE.md
```markdown
# tccw-agent-cli

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P07-cli.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
The `qitp` CLI tool. Provides commands for prompt management, strategy operations, blueprint handling, and graph visualization.

## Stack
- Python 3.12+
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy
- CLI framework: click + rich

## Commands
```bash
pip install -e ".[dev]"   # Install with dev deps
ruff check . && ruff format .  # Lint
mypy src/                 # Type check
pytest -v                 # Test
qitp --help               # Run the CLI
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

#### tccw-agent-infra/CLAUDE.md
```markdown
# tccw-agent-infra

> Part of the QITP platform. Specs and plans live in `~/tccw-strand-package/`.

## Quick Reference
- **Specs repo**: `~/tccw-strand-package/` (design docs, plans, master CLAUDE.md)
- **This plan**: `~/tccw-strand-package/plans/P08-infra.md`
- **Architecture**: `~/tccw-strand-package/QITP_Doc1_Architecture.md`

## What This Repo Does
CDK Python stacks for all QITP AWS infrastructure: data layer, networking, agent deployment, MCP services, orchestration, and observability.

## Stacks
- **DataStack** — DynamoDB tables, S3 buckets
- **NetworkStack** — VPC, subnets, security groups
- **AgentStack** — Lambda functions for agents
- **McpStack** — Fargate services for MCP servers
- **OrchestrationStack** — Step Functions workflows
- **ObservabilityStack** — CloudWatch, X-Ray, dashboards

## Stack
- Python 3.12+
- CDK v2
- Build: hatchling
- Lint: ruff
- Test: pytest
- Type check: mypy

## Commands
```bash
pip install -e ".[dev]"         # Install with dev deps
ruff check . && ruff format .   # Lint
mypy stacks/ constructs/        # Type check
pytest -v                       # Test
cdk synth                       # Synthesize CloudFormation
cdk deploy --all                # Deploy all stacks
```

## Constraints
- Never hardcode prompts — load from Prompt Registry
- Never bypass 2FA gate in live mode
- EXECUTION_MODE env var controls all mode switching
- All tool side-effects must be idempotent
```

### 8. MCP server.py Skeletons

#### tccw-qitp-mcp-market-data/src/qitp_mcp_market_data/server.py
```python
"""QITP Market Data MCP Server."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "backtest")

app = Server("qitp-market-data-mcp")


@app.list_tools()
async def list_tools():
    return []  # TODO: implement tools


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

#### tccw-qitp-mcp-sentiment/src/qitp_mcp_sentiment/server.py
```python
"""QITP Sentiment MCP Server."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "backtest")

app = Server("qitp-sentiment-mcp")


@app.list_tools()
async def list_tools():
    return []  # TODO: implement tools


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

#### tccw-mcp-artifacts/src/mcp_artifacts/server.py
```python
"""QITP Artifacts MCP Server."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "backtest")

app = Server("qitp-artifacts-mcp")


@app.list_tools()
async def list_tools():
    return []  # TODO: implement tools


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

#### tccw-qitp-mcp-backtest/src/qitp_mcp_backtest/server.py
```python
"""QITP Backtest MCP Server."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "backtest")

app = Server("qitp-backtest-mcp")


@app.list_tools()
async def list_tools():
    return []  # TODO: implement tools


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

#### tccw-qitp-mcp-ibkr/src/qitp_mcp_ibkr/server.py
```python
"""QITP IBKR MCP Server (Phase 2 — skeleton only)."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "backtest")

app = Server("qitp-ibkr-mcp")


@app.list_tools()
async def list_tools():
    return []  # Phase 2: not yet implemented


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

#### tccw-qitp-mcp-charting/src/qitp_mcp_charting/server.py
```python
"""QITP Charting MCP Server (Phase 2 — skeleton only)."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "backtest")

app = Server("qitp-charting-mcp")


@app.list_tools()
async def list_tools():
    return []  # Phase 2: not yet implemented


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

### 9. CDK Files

#### tccw-agent-infra/cdk.json
```json
{
  "app": "python app.py",
  "context": {
    "env": "dev",
    "account": "123456789012",
    "region": "eu-west-1"
  }
}
```

#### tccw-agent-infra/app.py
```python
#!/usr/bin/env python3
"""QITP Infrastructure — CDK app entrypoint."""

import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack

app = cdk.App()
env_name = app.node.try_get_context("env") or "dev"
env = cdk.Environment(account="123456789012", region="eu-west-1")

data = DataStack(app, f"Data-{env_name}", env=env)
network = NetworkStack(app, f"Network-{env_name}", env=env)

app.synth()
```

#### tccw-agent-infra/stacks/__init__.py
```python
```

#### tccw-agent-infra/stacks/data_stack.py
```python
"""QITP Data Stack — DynamoDB tables, S3 buckets."""

import aws_cdk as cdk
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: define DynamoDB tables and S3 buckets
```

#### tccw-agent-infra/stacks/network_stack.py
```python
"""QITP Network Stack — VPC, subnets, security groups."""

import aws_cdk as cdk
from constructs import Construct


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: define VPC and networking
```

#### tccw-agent-infra/stacks/agent_stack.py
```python
"""QITP Agent Stack — Lambda functions for agents."""

import aws_cdk as cdk
from constructs import Construct


class AgentStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: define agent Lambda functions
```

#### tccw-agent-infra/stacks/mcp_stack.py
```python
"""QITP MCP Stack — Fargate services for MCP servers."""

import aws_cdk as cdk
from constructs import Construct


class McpStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: define Fargate services for MCP servers
```

#### tccw-agent-infra/stacks/orchestration_stack.py
```python
"""QITP Orchestration Stack — Step Functions workflows."""

import aws_cdk as cdk
from constructs import Construct


class OrchestrationStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: define Step Functions workflows
```

#### tccw-agent-infra/stacks/observability_stack.py
```python
"""QITP Observability Stack — CloudWatch, X-Ray, dashboards."""

import aws_cdk as cdk
from constructs import Construct


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # TODO: define observability resources
```

#### tccw-agent-infra/constructs/__init__.py
```python
```

#### tccw-agent-infra/constructs/strands_agent.py
```python
"""Strands Agent construct — reusable Lambda-based agent deployment."""

from constructs import Construct


class StrandsAgentConstruct(Construct):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id)
        # TODO: define reusable agent construct
```

#### tccw-agent-infra/constructs/mcp_service.py
```python
"""MCP Service construct — reusable Fargate-based MCP server deployment."""

from constructs import Construct


class McpServiceConstruct(Construct):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id)
        # TODO: define reusable MCP service construct
```

#### tccw-agent-infra/constructs/sfn_workflow.py
```python
"""Step Functions Workflow construct — reusable orchestration pattern."""

from constructs import Construct


class SfnWorkflowConstruct(Construct):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id)
        # TODO: define reusable Step Functions construct
```

### 10. Python __init__.py and Skeleton Files

#### Shared: __init__.py (for all src packages)
```python
"""QITP {Component}."""
```

Use appropriate module docstring per repo:
- `agent_core`: `"""QITP Core Engine."""`
- `qitp_simulation`: `"""QITP Simulation Engine."""`
- `qitp_mcp_market_data`: `"""QITP Market Data MCP Server."""`
- `qitp_mcp_sentiment`: `"""QITP Sentiment MCP Server."""`
- `mcp_artifacts`: `"""QITP Artifacts MCP Server."""`
- `qitp_mcp_backtest`: `"""QITP Backtest MCP Server."""`
- `qitp_mcp_ibkr`: `"""QITP IBKR MCP Server."""`
- `qitp_mcp_charting`: `"""QITP Charting MCP Server."""`
- `qitp_agents`: `"""QITP Agents."""`
- `prompt_registry`: `"""QITP Prompt Registry."""`
- `agent_cli`: `"""QITP CLI."""`

#### MCP tools/__init__.py
```python
"""MCP tool definitions."""
```

#### Shared: tests/__init__.py
```python
```

#### Shared: tests/conftest.py (for repos that have it)
```python
"""Shared test fixtures."""
```

#### Shared: py.typed
Empty file (marker for PEP 561 type stubs).

#### Shared: README.md
```markdown
# tccw-qitp-{name}

Part of the QITP platform. See `~/tccw-strand-package/` for specs and plans.
```

### 11. Agents Repo — Blueprint and Handler Skeletons

#### blueprints/agents/gap_detector.yaml
```yaml
name: gap_detector
description: Scans pre-market data for gap trading opportunities
version: "0.1.0"
model: us.anthropic.claude-sonnet-4-20250514
execution_mode: "${EXECUTION_MODE}"
tools:
  - market_data.screen_gaps
  - market_data.get_ohlcv
  - artifacts.store_result
prompt_key: agent.gap_detector.system
```

#### blueprints/agents/sentiment_analyzer.yaml
```yaml
name: sentiment_analyzer
description: Scores market sentiment from multiple data sources
version: "0.1.0"
model: us.anthropic.claude-sonnet-4-20250514
execution_mode: "${EXECUTION_MODE}"
tools:
  - sentiment.score_ticker
  - sentiment.get_news
  - artifacts.store_result
prompt_key: agent.sentiment_analyzer.system
```

#### blueprints/agents/strategy_evaluator.yaml
```yaml
name: strategy_evaluator
description: Evaluates trading strategies via backtesting
version: "0.1.0"
model: us.anthropic.claude-sonnet-4-20250514
execution_mode: "${EXECUTION_MODE}"
tools:
  - backtest.run_simulation
  - backtest.get_metrics
  - artifacts.store_result
prompt_key: agent.strategy_evaluator.system
```

#### blueprints/agents/portfolio_recommender.yaml
```yaml
name: portfolio_recommender
description: Generates portfolio recommendations from evaluated strategies
version: "0.1.0"
model: us.anthropic.claude-sonnet-4-20250514
execution_mode: "${EXECUTION_MODE}"
tools:
  - market_data.get_ohlcv
  - backtest.get_metrics
  - artifacts.store_result
prompt_key: agent.portfolio_recommender.system
```

#### blueprints/strategies/gap_momentum_up.yaml
```yaml
name: gap_momentum_up
description: Long momentum play on upward gaps with volume confirmation
version: "0.1.0"
entry_conditions:
  gap_pct_min: 2.0
  volume_ratio_min: 1.5
  direction: up
exit_conditions:
  stop_loss_pct: 1.5
  take_profit_pct: 4.0
  max_hold_minutes: 120
```

#### blueprints/strategies/mean_reversion_gap.yaml
```yaml
name: mean_reversion_gap
description: Fade large gaps expecting mean reversion
version: "0.1.0"
entry_conditions:
  gap_pct_min: 4.0
  volume_ratio_min: 1.2
  direction: either
exit_conditions:
  stop_loss_pct: 2.0
  take_profit_pct: 3.0
  max_hold_minutes: 180
```

#### blueprints/strategies/gap_continuation.yaml
```yaml
name: gap_continuation
description: Ride gap continuation when trend aligns
version: "0.1.0"
entry_conditions:
  gap_pct_min: 1.5
  trend_alignment: true
  volume_ratio_min: 1.3
exit_conditions:
  stop_loss_pct: 1.0
  take_profit_pct: 3.5
  max_hold_minutes: 240
```

#### blueprints/strategies/sentiment_driven.yaml
```yaml
name: sentiment_driven
description: Trade based on sentiment divergence from price action
version: "0.1.0"
entry_conditions:
  sentiment_score_min: 0.7
  price_sentiment_divergence: true
exit_conditions:
  stop_loss_pct: 2.0
  take_profit_pct: 5.0
  max_hold_minutes: 360
```

#### blueprints/strategies/gap_etf_momentum.yaml
```yaml
name: gap_etf_momentum
description: ETF-level gap momentum trading
version: "0.1.0"
entry_conditions:
  gap_pct_min: 1.0
  asset_type: etf
  volume_ratio_min: 1.4
exit_conditions:
  stop_loss_pct: 1.0
  take_profit_pct: 2.5
  max_hold_minutes: 120
```

#### src/qitp_agents/gap_detector/handler.py
```python
"""Gap Detector agent handler."""


async def handle() -> None:
    """Run the gap detector agent."""
    # TODO: implement gap detection logic
    raise NotImplementedError
```

#### src/qitp_agents/sentiment_analyzer/handler.py
```python
"""Sentiment Analyzer agent handler."""


async def handle() -> None:
    """Run the sentiment analyzer agent."""
    # TODO: implement sentiment analysis logic
    raise NotImplementedError
```

#### src/qitp_agents/strategy_evaluator/handler.py
```python
"""Strategy Evaluator agent handler."""


async def handle() -> None:
    """Run the strategy evaluator agent."""
    # TODO: implement strategy evaluation logic
    raise NotImplementedError
```

#### src/qitp_agents/portfolio_recommender/handler.py
```python
"""Portfolio Recommender agent handler."""


async def handle() -> None:
    """Run the portfolio recommender agent."""
    # TODO: implement portfolio recommendation logic
    raise NotImplementedError
```

### 12. Prompt Registry — Skeleton Files

#### src/prompt_registry/handler.py
```python
"""Lambda handler for Prompt Registry API."""


def lambda_handler(event: dict, context: object) -> dict:
    """Handle API Gateway requests for prompt operations."""
    # TODO: implement CRUD for prompts
    return {"statusCode": 501, "body": "Not implemented"}
```

#### src/prompt_registry/models.py
```python
"""Pydantic models for Prompt Registry."""

from pydantic import BaseModel


class PromptVersion(BaseModel):
    """A versioned prompt template."""

    key: str
    version: str
    template: str
    metadata: dict = {}
```

#### src/prompt_registry/storage.py
```python
"""S3 + DynamoDB storage operations for Prompt Registry."""


class PromptStorage:
    """Manages prompt storage in S3 and DynamoDB."""

    def __init__(self) -> None:
        # TODO: initialize boto3 clients
        pass

    async def get_prompt(self, key: str, version: str | None = None) -> dict:
        """Retrieve a prompt by key and optional version."""
        raise NotImplementedError

    async def put_prompt(self, key: str, template: str, metadata: dict | None = None) -> dict:
        """Store a new prompt version."""
        raise NotImplementedError
```

### 13. CLI — Skeleton Files

#### src/agent_cli/main.py
```python
"""QITP CLI entrypoint."""

import click


@click.group()
def cli() -> None:
    """QITP Platform CLI."""


if __name__ == "__main__":
    cli()
```

#### src/agent_cli/prompt.py
```python
"""Prompt management CLI commands."""

import click


@click.group()
def prompt() -> None:
    """Manage prompts in the Prompt Registry."""


@prompt.command()
@click.argument("key")
def get(key: str) -> None:
    """Get a prompt by key."""
    # TODO: implement
    click.echo(f"Getting prompt: {key}")
```

#### src/agent_cli/strategy.py
```python
"""Strategy CLI commands."""

import click


@click.group()
def strategy() -> None:
    """Manage trading strategies."""


@strategy.command()
def list_strategies() -> None:
    """List all available strategies."""
    # TODO: implement
    click.echo("Listing strategies...")
```

#### src/agent_cli/blueprint.py
```python
"""Blueprint CLI commands."""

import click


@click.group()
def blueprint() -> None:
    """Manage agent blueprints."""


@blueprint.command()
def validate() -> None:
    """Validate all blueprints."""
    # TODO: implement
    click.echo("Validating blueprints...")
```

#### src/agent_cli/graph.py
```python
"""Graph visualization CLI commands."""

import click


@click.group()
def graph() -> None:
    """Visualize QITP graphs and workflows."""


@graph.command()
def show() -> None:
    """Show the agent orchestration graph."""
    # TODO: implement
    click.echo("Showing graph...")
```

## Agent Instructions

You are creating 12 repos. For each repo:

1. `mkdir -p ~/dev/tccw-qitp-{name}`
2. `cd ~/dev/tccw-qitp-{name} && git init`
3. Create all files using the appropriate template (A-F) above
4. Adjust pyproject.toml name, description, and dependencies per repo type
5. Adjust CLAUDE.md with the correct plan reference
6. For MCP servers: adjust Dockerfile CMD, docker-compose port, and server.py module name
7. For Phase 2 repos (ibkr, charting): create skeleton only (no tools implemented, just the structure)
8. `git add -A && git commit -m "P01: scaffold {repo-name}"`

Do NOT create GitHub remote repos or configure branch protection — that will be done manually.

### Execution Order

```bash
# 1. Python Libraries
# tccw-agent-core (Template A)
# tccw-qitp-simulation (Template A)

# 2. Phase 1 MCP Servers
# tccw-qitp-mcp-market-data (Template B)
# tccw-qitp-mcp-sentiment (Template B)
# tccw-mcp-artifacts (Template B)
# tccw-qitp-mcp-backtest (Template B)

# 3. Phase 2 MCP Servers (skeleton)
# tccw-qitp-mcp-ibkr (Template B)
# tccw-qitp-mcp-charting (Template B)

# 4. Applications
# tccw-qitp-agents (Template C)
# tccw-prompt-registry (Template E)
# tccw-agent-cli (Template F)

# 5. Infrastructure
# tccw-agent-infra (Template D)
```

## Acceptance Criteria

- [ ] All 12 repos exist in ~/dev/ with correct directory structure
- [ ] Every repo has pyproject.toml, .gitignore, CLAUDE.md, tests/, CI workflow
- [ ] MCP repos have Dockerfile + docker-compose.yml + server.py skeleton
- [ ] CDK repo has cdk.json + app.py + stacks/ + constructs/
- [ ] Agents repo has blueprints/ + 4 agent subdirectories
- [ ] `pip install -e ".[dev]"` succeeds in every repo (no import errors)
- [ ] `ruff check .` passes in every repo
- [ ] `pytest` runs (0 tests collected is fine at this stage)
- [ ] Each repo has an initial git commit

## Test Plan

```bash
# For each repo:
cd ~/dev/tccw-qitp-{name}
pip install -e ".[dev]"
ruff check .
pytest -v
```
