---
title: Artifacts
parent: Concepts
nav_order: 12
---

# Artifact Store

The Artifact Store is an MCP server (`mcp-artifacts`) that implements the claim-check pattern for large agent outputs. Instead of passing full data through agent pipelines, agents store artifacts in S3 and pass lightweight references (artifact IDs) through the system.

## Why Claim-Check

Agent outputs can be large -- charts, reports, simulation results, data exports. Passing these through Step Functions, agent-to-agent calls, or memory systems creates problems:

- **Step Functions payload limits** -- SFN has a 256 KB payload limit per state
- **Memory bloat** -- storing raw outputs in memory makes retrieval slow and expensive
- **Serialization overhead** -- large objects slow down every inter-agent call

The claim-check pattern solves this: store the artifact in S3, register metadata in DynamoDB, and pass only the artifact ID. Consumers retrieve the full artifact via a signed URL when they actually need it.

## Storage Architecture

- **S3** stores artifact content (text, JSON, images, exports)
- **DynamoDB** stores the catalog: artifact ID (partition key), type, status, S3 key, agent ID, execution ID, timestamps, and metadata
- **Three GSIs** enable efficient queries: by type + created_at, by agent_id + created_at, and by execution_id + agent_id

## Artifact Types

The store supports these artifact types:

- `chart` -- generated visualizations
- `report` -- structured text reports
- `simulation_result` -- output from simulation runs
- `recommendation` -- agent recommendations
- `image` -- generated or processed images (base64 encoded)
- `data_export` -- exported datasets
- `pipeline_run` -- pipeline execution manifests

## MCP Server Interface

The artifact store runs as an MCP server built on `BaseMCPServer`. It exposes 8 tools:

| Tool | Purpose |
|------|---------|
| `create_artifact` | Store content to S3 and register in catalog |
| `get_artifact` | Retrieve metadata and signed URL |
| `poll_artifact` | Wait until artifact status is ready |
| `list_artifacts` | List artifacts with type/agent/date filters |
| `get_pipeline_run` | Retrieve a pipeline run manifest |
| `get_latest_run` | Get the most recent pipeline run |
| `get_agent_result` | Get a specific agent's result from a pipeline |
| `search_artifacts` | Search with date range, agent, type, and tier filters |

## Signed URLs

Artifact retrieval uses pre-signed URLs rather than direct S3 access. The store supports two URL strategies:

1. **S3 pre-signed URLs** -- default, 1-hour expiry
2. **CloudFront signed URLs** -- when `CLOUDFRONT_DOMAIN` is configured, provides CDN-cached delivery with 14-day expiry and private key signing via Secrets Manager

The `get_best_url()` method automatically picks CloudFront if configured, falling back to S3.

## Tiered Storage

Artifacts belong to either the `platform` or `domain` tier. Platform artifacts use the platform KMS key for encryption; domain artifacts use the domain KMS key. This separation ensures that platform-level outputs (pipeline manifests, evaluation results) are encrypted separately from domain-specific data.

## Idempotency

The `create_artifact` tool accepts an optional `idempotency_key`. If a previous artifact with the same key exists, the store returns the existing artifact instead of creating a duplicate. This prevents duplicate artifacts when agent steps are retried.
