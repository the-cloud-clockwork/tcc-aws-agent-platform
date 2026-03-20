# Deployment Notes — tccw-aws-agent-platform

## CDK Stacks

The platform deploys 8 stacks via `cdk deploy --all -c env=<env>`:

| Stack | Purpose |
|-------|---------|
| `{prefix}-network` | VPC, subnets, security groups |
| `{prefix}-security` | KMS keys, IAM roles |
| `{prefix}-data` | DynamoDB tables, S3 buckets |
| `{prefix}-mcps` | ECS Fargate services for MCP servers |
| `{prefix}-agents` | Lambda functions for agents |
| `{prefix}-workflows` | Step Functions state machines |
| `{prefix}-observability` | CloudWatch dashboards, X-Ray tracing group, SNS alerts, metric alarms |
| `{prefix}-api` | API Gateway for dashboard artifact retrieval |

Where `{prefix}` = `{resource_prefix}-{env}` (e.g., `platform-dev`).

## ObservabilityStack

The ObservabilityStack (`infra/stacks/observability_stack.py`) is fully implemented and wired into `infra/app.py`. It creates:

- CloudWatch dashboard with agent and MCP widgets
- SNS topic for alerts
- X-Ray tracing group
- Metric alarms for agent errors and MCP latency

It is deployed as part of `cdk deploy --all`. No additional steps required.

## CodeArtifact

Packages are published to:
- **Domain**: `tccw`
- **Repository**: `tccw-python`
- **Region**: `eu-west-1`
- **Owner**: `123456789012`

Published packages: `agent-core`, `prompt-registry`.

## Dependency Lock Files

Run `./scripts/lock-deps.sh` to generate `requirements.lock` for each module. Requires `pip-tools`.
