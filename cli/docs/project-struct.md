# agent-cli — Project Structure

## Root

| File | Purpose |
|---|---|
| `pyproject.toml` | Package `agent-cli` v0.1.0. Deps: `typer`, `rich`, `httpx`, `pyyaml`, `agent-core`. Entry point: `agentcli → agent_cli.main:app` |
| `CLAUDE.md` | Agent instructions — plan ref P07 |
| `README.md` | Subcommand reference, examples, env vars |

## CI/CD (`.github/workflows/`)

| File | Purpose |
|---|---|
| `ci.yml` | Lint, type check, test on every push/PR. Authenticates to CodeArtifact for `agent-core` dependency |
| `sonar-scan.yml` | Coverage + analysis → SonarQube |

---

## `src/agent_cli/`

**`main.py`** — Composition root. Creates the `agentcli` Typer app and registers four subcommand groups: `prompt`, `strategy`, `blueprint`, `graph`. Each group lives in its own module. This is the only file that imports the other four.

**`blueprint.py`** — `blueprint lint` and `blueprint validate` subcommands. Auto-detects whether a YAML is an agent blueprint or strategy blueprint (by inspecting top-level keys), then validates it against the Pydantic model from `agent-core`. If `agent-core` isn't installed, falls back to checking required keys — so the CLI works in lightweight CI environments. Prints a Rich tree summary with PASS/FAIL.

**`prompt.py`** — Six subcommands (`push`, `get`, `list`, `diff`, `promote`, `rollback`) that talk to the Prompt Registry API over HTTP using httpx. This is the developer interface to the "no hardcoded prompts" constraint. `push` uploads a template file, `get` renders content with syntax highlighting, `list` shows a version table, `diff` computes unified diffs between versions, `promote`/`rollback` manage the lifecycle. Registry URL comes from `AGENT_REGISTRY_URL` env var.

**`strategy.py`** — `strategy validate`, `strategy list`, and `strategy promote` subcommands. `validate` checks a strategy YAML against the `StrategyBlueprint` model. `list` scans a directory for strategy files and renders a summary table. `promote` validates first (refuses invalid), then writes `status: stable` back into the YAML file — the only CLI command that modifies a file. Strategies directory comes from `AGENT_STRATEGIES_DIR` env var.

**`graph.py`** — `graph render` subcommand. Reads the `multi_agent` section of an agent blueprint and generates a markdown document with an ASCII topology diagram (topologically sorted nodes as boxes, arrows with labels), a node table, an edge table, and a circuit breaker summary for gate nodes. Can output to file (`-o`) or terminal (Rich panel).

---

## `tests/` — 25 tests

| File | Coverage |
|---|---|
| `test_blueprint.py` | 4 tests — valid agent/strategy YAML, file not found, empty YAML |
| `test_prompt.py` | 7 tests — all 6 subcommands with mocked HTTP (push 201, get 200/404, list, diff, promote, rollback) |
| `test_strategy.py` | 5 tests — validate valid/invalid/missing, list with files/empty dir, promote writes `status: stable` |
| `test_graph.py` | 9 tests — render to terminal/file/missing, ASCII diagram helpers (empty, 2-node), node/edge tables, circuit breaker presence/absence |
