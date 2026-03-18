# tccw-prompt-registry — Project Structure

## Root

| File | Purpose |
|---|---|
| `pyproject.toml` | Package `prompt-registry` v0.1.0. Deps: `boto3`, `pydantic`. Published to CodeArtifact |
| `CLAUDE.md` | Agent instructions |
| `README.md` | Full API reference, lifecycle diagram, usage examples |

## CI/CD (`.github/workflows/`)

| File | Purpose |
|---|---|
| `ci.yml` | Lint, type check, test on every push/PR |
| `publish.yml` | Build wheel → publish to CodeArtifact on changes to `src/` or `pyproject.toml` |
| `sonar-scan.yml` | Coverage + analysis → SonarQube |

---

## `src/prompt_registry/`

**`models.py`** — All data contracts in one file. `PromptStatus` enum defines the three-state lifecycle (DRAFT → STABLE → DEPRECATED). `Mode` enum defines execution environments (SIMULATION/DEV/STAGING/PRODUCTION). `DRAFT_ALLOWED_MODES` gates which modes can see drafts (only simulation and dev). Pydantic models cover the DynamoDB item shape (`PromptVersion`), API requests (`PromptCreateRequest`, `PromptPromoteRequest`, `PromptRollbackRequest`), and responses (`PromptResolveResponse`, `PromptVersionListItem`).

**`storage.py`** — S3 content layer. `PromptStorage` reads and writes prompt text to S3 at keys like `{prompt_id}/{version}.txt`. Separates arbitrarily long prompt content (S3) from structured metadata (DynamoDB).

**`registry.py`** — DynamoDB metadata layer. `PromptRegistry` implements the prompt lifecycle state machine. Core invariant: only one version per prompt_id can be STABLE at a time. `promote()` deprecates the current stable and sets the target version; `rollback()` reverses this. Versions are sorted by semver (not lexicographic — `1.2.0 < 1.10.0`).

**`resolver.py`** — Query layer. `parse_prompt_ref()` handles three reference formats: plain name (`gap_detector`), underscore-v (`gap_detector_v1.2`), and at-sign (`gap_detector@1.2.0`). `PromptResolver` combines registry + storage to resolve references to actual text, respecting mode gates — production agents can never see drafts, dev/simulation can fall back to latest draft when no stable exists.

**`handler.py`** — Lambda entry point with built-in regex routing for API Gateway. Six routes: create prompt (POST, 201, checks duplicates), get prompt (GET, with version/mode query params, delegates to resolver), list versions (GET, semver-sorted), promote (POST), rollback (POST), and diff (GET, unified diff between two versions via `difflib`).

---

## `tests/` — 30 tests

| File | Coverage |
|---|---|
| `conftest.py` | Shared fixtures: moto-mocked DynamoDB table (hash: prompt_id, range: version) + S3 bucket, pre-wired registry/storage instances, sample prompt text files |
| `fixtures/sample_prompts/` | Two versions of a gap_detector prompt (v1.0.0 basic, v1.2.0 with percentage thresholds and JSON schema) |
| `test_registry.py` | 8 tests — CRUD, semver sorting, latest stable filtering, promote (deprecates old), rollback (restores + handles missing) |
| `test_resolver.py` | 11 tests — all reference formats, semver padding (1.2 → 1.2.0), draft blocked in production, draft allowed in simulation/dev, latest stable resolution |
| `test_handler.py` | 11 tests — full API surface via Lambda events: create (201/409/400), get (stable/pinned/404), list, promote (200/404), rollback, diff (output/400), unknown route |
