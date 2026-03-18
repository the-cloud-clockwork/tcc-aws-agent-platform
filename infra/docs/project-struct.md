# tccw-agent-infra — Project Structure

## Root

| File | Purpose |
|---|---|
| `pyproject.toml` | Package `tccw-agent-infra` v0.2.0. Deps: `aws-cdk-lib>=2.170`, `constructs`, `pyyaml`. Packages: `stacks/` and `constructs_/` |
| `cdk.json` | CDK app config: `python3 app.py`. Default context: `env=dev`, account `835618032093`, region `eu-west-1` |
| `app.py` | CDK entrypoint. Loads `config/{env}.yaml`, instantiates all 6 stacks in dependency order, applies global tags. Environment selected via `cdk deploy -c env=staging` |
| `CLAUDE.md` | Agent instructions |
| `README.md` | Stack descriptions, deployment guide, multi-env config reference |

## CI/CD (`.github/workflows/`)

| File | Purpose |
|---|---|
| `ci.yml` | Lint, type check, test on every push/PR |
| `sonar-scan.yml` | Coverage + analysis → SonarQube |

---

## `config/` — Environment-specific configuration

Three YAML files (`dev.yaml`, `staging.yaml`, `production.yaml`) sharing the same structure but differing in scaling, security, and cost:

- **dev** — WAF off, 1 NAT, Fargate min 1, DynamoDB on-demand, S3 auto-delete, 14-day logs
- **staging** — WAF on (rate limit 1000), secrets rotation 90d, S3 RETAIN, 30-day logs
- **production** — WAF on (rate limit 500 + IP whitelist), 2 NATs (HA), Fargate min 2/max 5, DynamoDB provisioned with auto-scaling, 90-day logs, Lambda provisioned concurrency

All configs define the same tables, buckets, agents, and MCPs. `resource_prefix` is `"platform"` everywhere — no domain-specific naming.

---

## `stacks/` — CDK Stacks

**`data_stack.py`** — All data stores. Iterates config to create DynamoDB tables (configurable keys, billing, PITR), S3 buckets (versioned, SSL-enforced, public-access-blocked), and SQS queues (artifact notification + DLQ). Exports all resource names/ARNs to SSM parameters. Other stacks reference these via cross-stack attributes.

**`network_stack.py`** — VPC with three subnet tiers (public, private-with-egress, isolated) and two security groups: Agent SG (all outbound) and MCP SG (all outbound + ingress from Agent SG on port 8000).

**`security_stack.py`** — Three KMS CMKs with rotation (data, storage, secrets), a Secrets Manager placeholder, VPC endpoints (2 gateway + 8 interface to reduce NAT costs), and WAF WebACL (enabled only in staging/production, delegates to `WafWebAcl` construct).

**`agent_stack.py`** — Lambda functions for all Strands agents. References the public Strands SDK Lambda Layer. Creates a shared IAM policy (Bedrock, DynamoDB, S3, SQS, X-Ray, SSM). Each agent gets Python 3.12, ARM64, 15-min timeout, private subnet, X-Ray tracing, and secrets access. Provisioned concurrency applied in staging/production.

**`mcp_stack.py`** — ECS Fargate cluster with Container Insights, Cloud Map private DNS namespace (agents discover MCPs at `{name}.platform.local:8000`), and one `McpServiceConstruct` per MCP in config with optional auto-scaling.

**`observability_stack.py`** — CloudWatch dashboard (`{prefix}-{env}-overview`), SNS alert topic, X-Ray tracing group, per-agent alarms (errors, p99 duration), per-MCP alarms (CPU), and custom metrics (TokenCostUSD, pipeline events, agent latency).

---

## `constructs_/` — Reusable CDK Constructs

**`mcp_service.py`** — `McpServiceConstruct` provisions everything for a single MCP server: ECR repo (scan on push, lifecycle keeping 10 images), Fargate task definition, container with health check on port 8000, Cloud Map A-record registration, deployment circuit breaker with rollback.

**`strands_agent.py`** — `StrandsAgentTask` wraps a Lambda as a Step Functions task implementing the claim-check pattern. Result selector extracts only `artifact_id`, `success`, `s3_key` (keeping payloads under 256KB). Retries with exponential backoff and FULL jitter. Catches all failures → explicit Fail state.

**`sfn_workflow.py`** — `SfnWorkflow` converts a workflow blueprint YAML into a Step Functions state machine. Parses `agent:` steps into `StrandsAgentTask` and `parallel:` steps into branches.

**`auto_scaling.py`** — `FargateAutoScaling` (CPU + memory targets with cooldown periods) and `LambdaProvisionedConcurrency` (creates alias with provisioned concurrency, no-op when set to 0).

**`vpc_endpoints.py`** — `VpcEndpointsConstruct` creates 2 gateway endpoints (S3, DynamoDB — free) and 8 interface endpoints (SQS, ECR, Logs, Secrets Manager, KMS, STS, SSM). Reduces NAT costs and keeps AWS API calls within the VPC.

**`waf_rules.py`** — `WafWebAcl` creates a WAF v2 WebACL with four rules by priority: IP whitelist (production only), rate limiting, AWS Managed Rules Common (SQLi/XSS), AWS Managed Rules Known Bad Inputs (Log4j).

---

## `lambda/`

**`lambda/agents/example/handler.py`** — Stub handler returning 200. Placeholder so CDK synthesizes valid Lambda functions. Real agent code lives in separate repos.

---

## `tests/` — 43+ tests

| File | Coverage |
|---|---|
| `test_stacks.py` | 10 tests — DataStack (4 tables, 3 buckets, 2 queues), NetworkStack (VPC, 2 SGs), AgentStack (3 Lambdas, runtime/arch/timeout), McpStack (2 ECS services, Cloud Map namespace) |
| `test_multi_env.py` | ~17 tests — config validation across all 3 envs: required keys, mode correctness, WAF disabled in dev, production has higher scaling, no "qitp" in config, `resource_prefix` is "platform" everywhere. Stack synthesis: NAT count and WAF WebACL count match config |
| `test_observability_stack.py` | 5 tests — SNS topic, dashboard, X-Ray group naming, log group, SSM parameter |
| `test_security_stack.py` | 11 tests — 3 KMS keys with rotation, Secrets Manager with CMK, WAF rules (rate limit, managed rules), VPC endpoints (≥8), SSM exports |
