# tccw-mcp-artifacts — Project Structure

## Root

| File | Purpose |
|---|---|
| `pyproject.toml` | Package `mcp-artifacts` v0.1.0. Deps: `mcp[server]`, `boto3`, `pydantic`, `uvicorn`. Entry point: `mcp-artifacts → mcp_artifacts.server:main` |
| `CLAUDE.md` | Agent instructions — plan ref P04, claim-check pattern, idempotency |
| `README.md` | Full docs: 4 tools, 6 artifact types, DynamoDB schema, S3 key convention, deployment |
| `Dockerfile` | Production image: `python:3.11-slim`, exposes 8080, runs `mcp-artifacts` |
| `docker-compose.yml` | Local dev: `artifacts-mcp` service + LocalStack (S3 + DynamoDB on 4566) |

## CI/CD (`.github/workflows/`)

| File | Purpose |
|---|---|
| `ci.yml` | Lint, type check, test on every push/PR |
| `sonar-scan.yml` | Coverage + analysis → SonarQube |

---

## `src/mcp_artifacts/`

**`schemas.py`** — All shared types in one place. `ArtifactType` enum defines six types (chart/report/simulation_result/recommendation/image/data_export) with their file extensions and content types. `ArtifactMeta` is the full DynamoDB item shape. `CreateResult` and `ArtifactResult` are response envelopes. Helper functions handle content encoding (base64 for images, UTF-8 for everything else) and filename/content-type mapping.

**`server.py`** — MCP server entrypoint. Defines all 4 tool JSON schemas (`create_artifact`, `get_artifact`, `poll_artifact`, `list_artifacts`), wires the request dispatcher, and provides the `main()` stdio entry point. Keeps tool implementations decoupled from MCP protocol wiring — tools are plain async functions, not MCP-aware.

**`storage.py`** — S3 abstraction layer. `ArtifactStorage` handles object upload, pre-signed URL generation (1-hour TTL, generated on-demand per retrieval), and existence checks. Accepts injected S3 client for moto testing.

**`catalog.py`** — DynamoDB metadata catalog. `ArtifactCatalog` handles CRUD for artifact metadata with smart GSI-aware query routing: type filter → GSI1 (`type-created_at-index`), agent_id filter → GSI2 (`agent_id-created_at-index`), no filter → table scan. Includes `ensure_table()` for bootstrapping in tests and local dev. Idempotency key support for duplicate detection.

### `tools/` — One file per tool

**`create.py`** — Write path for the claim-check pattern. Checks idempotency key first (returns existing artifact on retry), creates DynamoDB entry with `status="processing"`, uploads to S3, then updates status to `"ready"` (or `"error"` on failure). This processing→ready/error lifecycle is what `poll_artifact` watches.

**`get.py`** — Single-shot retrieval. Looks up the catalog entry, generates a pre-signed URL if the artifact is ready.

**`poll.py`** — Blocking poll loop for async artifact readiness. Polls every 2 seconds until the artifact reaches a terminal state or the timeout (default 60s) expires. Used when an agent needs to wait for another agent's output.

**`list_artifacts.py`** — Filtered listing of artifact metadata without signed URLs. Supports type, agent_id, date, and limit filters. Lightweight discovery endpoint.

---

## `tests/` — 19 tests

| File | Coverage |
|---|---|
| `conftest.py` | Shared fixtures: moto-mocked S3 bucket + DynamoDB table, pre-wired `ArtifactStorage` and `ArtifactCatalog` instances |
| `test_create.py` | 7 tests — all 6 artifact types (verifies extensions: .md, .jsx, .json, .png, .csv), image from base64, invalid type rejection |
| `test_get.py` | 6 tests — get ready (has signed_url), not_found, processing (no url), poll ready/not_found/error |
| `test_catalog.py` | 6 tests — list by type (GSI1), by agent_id (GSI2), with limit, no filters (scan), CRUD roundtrip, status transitions |
