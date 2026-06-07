# Contributing to AWS Agent Platform

Thank you for your interest in contributing. AWS Agent Platform is a
configuration-driven, domain-agnostic runtime for declaring AI agents in YAML
and deploying them on AWS — built over the
[Strands Agents SDK](https://github.com/strands-agents/sdk-python) and
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/).

- **Documentation:** <https://the-cloud-clockwork.github.io/tcc-aws-agent-platform>
- **Code of Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- **License:** Apache-2.0

All contributions are accepted under the project's
[Apache-2.0 license](LICENSE) (inbound = outbound). By submitting a pull
request you certify that you have the right to submit the contribution under
that license.

---

## Table of Contents

1. [The #1 Rule — Zero Domain Contamination](#the-1-rule--zero-domain-contamination)
2. [Setting Up a Development Environment](#setting-up-a-development-environment)
3. [Contribution Workflow](#contribution-workflow)
4. [Commit Message Convention](#commit-message-convention)
5. [Code Style](#code-style)
6. [Running Tests](#running-tests)
7. [CI Requirements](#ci-requirements)
8. [Reporting Issues and Security Vulnerabilities](#reporting-issues-and-security-vulnerabilities)

---

## The #1 Rule — Zero Domain Contamination

**Platform code must never contain domain-specific knowledge.**

The `scripts/domain-scan.sh` scanner enforces this automatically. A clean
contribution has zero hits from that script. Specifically, platform code must
not reference:

- Business domain branding, ticker symbols, or regulatory identifiers of any
  consumer application.
- Internal hostnames, account IDs, or file-system paths belonging to any
  particular deployment.
- Any hard-coded model name, sampling rate, temperature, or other
  deployment-varying value that should come from a blueprint or environment
  variable.

Run the scanner before every pull request:

```bash
./scripts/domain-scan.sh          # HARD terms — must return zero hits
./scripts/domain-scan.sh --full   # HARD + SOFT terms — review in context
```

If you are unsure whether something belongs in the platform or in a domain
repo, the answer is almost always: put it in the blueprint YAML or an
environment variable.

---

## Setting Up a Development Environment

### Prerequisites

- Python 3.11 or later
- `git`

### Clone and install

```bash
git clone https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git
cd tcc-aws-agent-platform
```

Each Python package is independently installable. Install the ones relevant to
your change — or install all four for a full local environment:

```bash
# Core runtime, blueprint engine, hooks, observability, MCP base classes
pip install -e "core/[dev]"

# Versioned prompt management (S3 + DynamoDB)
pip install -e "prompts/[dev]"

# Artifact store — claim-check pattern (S3 + DynamoDB + signed URLs)
pip install -e "artifacts/[dev]"

# CLI — blueprint validation, prompt management, graph rendering
pip install -e "cli/[dev]"
```

The `[dev]` extras install the full test and linting toolchain (`pytest`,
`ruff`, `mypy`, and associated plugins) for that package.

### Verify your setup

```bash
# Lint check — must be clean
ruff check .

# Format check — must be clean
ruff format --check .
```

---

## Contribution Workflow

1. **Fork** the repository on GitHub.
2. **Create a feature branch** from `main` in your fork:

   ```bash
   git checkout -b feat/your-descriptive-name
   ```

3. **Make your changes.** Keep commits focused and logically grouped. See
   [Commit Message Convention](#commit-message-convention) below.
4. **Run linting, formatting, and tests locally** before pushing (see
   [Running Tests](#running-tests)).
5. **Open an issue or Discussion** before starting significant work, so the
   approach can be agreed on before implementation.
6. **Push** your branch to your fork and open a **pull request against
   `main`** in this repository.
7. Fill in the pull request template. Include:
   - A clear description of what changed and why.
   - The result of `./scripts/domain-scan.sh` (must be zero hits).
   - Which packages and test suites are affected.
8. **CI must pass** before a maintainer will review (see
   [CI Requirements](#ci-requirements)).
9. Address review feedback in additional commits on the same branch. Do not
   force-push after review begins unless asked by a maintainer.

### Terraform module changes

If your change touches any module under `modules/`, note that these modules are
consumed by downstream domain repositories — they are not deployed standalone.
Describe any interface changes in the PR so maintainers can assess
compatibility. All new variables must be added to `dev.tfvars`, `staging.tfvars`,
and `production.tfvars` reference files. Sub-module interfaces are locked:
update all consumers in the same PR when changing a module's interface.

---

## Commit Message Convention

This project follows
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

```
<type>(<scope>): <short summary in imperative mood>

[optional body — explain the why, not the what]

[optional footer — breaking changes, issue refs]
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`

**Scopes** (optional but encouraged): `core`, `prompts`, `artifacts`, `cli`,
`modules`, `loader`, `observability`, `graph`, `policy`, `evaluation`

**Examples:**

```
feat(core): add vertex provider to model config dispatcher

fix(loader): remove StructuredOutputEnforcer fallback for Strands native

docs: add development environment setup to CONTRIBUTING

chore(ci): pin ruff version across all package workflows
```

Breaking changes must include a `BREAKING CHANGE:` footer:

```
feat(modules/agents)!: rename blueprint_path variable to blueprint_dir

BREAKING CHANGE: domain repos must rename blueprint_path to blueprint_dir
in all calls to module.agents.
```

---

## Code Style

### Formatting and linting

All Python code is formatted and linted with [Ruff](https://docs.astral.sh/ruff/).
Configuration lives in each package's `pyproject.toml`.

```bash
ruff format .        # apply formatting
ruff check . --fix   # apply safe auto-fixes
```

Pull requests that fail `ruff check .` or `ruff format --check .` will not
be merged.

### Type annotations

- **Required** on all public function and method signatures.
- Optional on local variables, private helpers, and test utilities.
- Type-check with mypy before submitting:

  ```bash
  mypy core/src/agent_core
  ```

### General conventions

| Convention | Rule |
|------------|------|
| File paths | Use `pathlib.Path`, not `os.path` |
| String formatting | f-strings; avoid `.format()` and `%` |
| Imports | stdlib → third-party → local, separated by blank lines |
| Configuration | All deployment-varying values from blueprints or environment variables — never hard-coded |
| Blueprints | Use `.yaml` extension (not `.yml`) — Terraform `fileset()` matches `*.yaml` only |
| Blueprint `id` field | kebab-case, required at top level of every blueprint file |
| No backward compatibility | Build for the current vision; do not add shim layers for removed APIs |

---

## Running Tests

Tests are written with `pytest`. Each package has its own `tests/` directory
and `pyproject.toml` test configuration.

### Run a single package's tests

```bash
pytest core/tests/

pytest prompts/tests/

pytest artifacts/tests/

pytest cli/tests/
```

### Run with coverage

```bash
pytest core/tests/ --cov=agent_core --cov-report=term-missing
```

### Scope to a file, class, or single test

```bash
pytest core/tests/test_loader.py                          # single file
pytest core/tests/test_loader.py::test_litellm_provider   # single test
pytest core/tests/ -k "observability"                     # keyword filter
```

### Notes

- Tests use [moto](https://github.com/getmoto/moto) to mock AWS services and
  `pytest-asyncio` for async fixtures. Both are installed by `[dev]` extras.
- Local runs are for fast iteration. The authoritative test run is the CI
  pipeline — see [CI Requirements](#ci-requirements).

---

## CI Requirements

Every pull request must pass the following GitHub Actions workflows before it
can be merged:

| Workflow | Checks |
|----------|--------|
| `ci-core.yml` | `ruff check`, `ruff format --check`, `mypy`, `pytest` for `core/` and `cli/` |
| `ci-prompts.yml` | `ruff check`, `ruff format --check`, `pytest` for `prompts/` |
| `ci-artifacts.yml` | `ruff check`, `ruff format --check`, `pytest` for `artifacts/` |

All checks must be green before a reviewer is assigned. Investigate a failing
run before requesting review:

```bash
gh run list --repo The-Cloud-Clockwork/tcc-aws-agent-platform --limit 10
gh run view <run-id> --log-failed
```

---

## Reporting Issues and Security Vulnerabilities

**Bugs and feature requests:** open a
[GitHub Issue](https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform/issues)
using the appropriate template. Search existing issues before opening a new one.

**Security vulnerabilities:** do **not** open a public issue. Use
[GitHub private vulnerability reporting](https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform/security/advisories/new)
to disclose security issues confidentially. A maintainer will respond and
coordinate disclosure.

---

## Questions

If you have a question not answered by the
[documentation](https://the-cloud-clockwork.github.io/tcc-aws-agent-platform)
or this guide, open a
[GitHub Discussion](https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform/discussions)
or a draft pull request with your question in the description.
