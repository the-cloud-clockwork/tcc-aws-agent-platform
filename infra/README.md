# tccw-agent-infra

> Generic AWS CDK infrastructure for deploying Strands agents and MCP servers

[![CI](https://github.com/The-Cloud-Clock-Work/tccw-agent-infra/actions/workflows/ci.yml/badge.svg)](https://github.com/The-Cloud-Clock-Work/tccw-agent-infra/actions/workflows/ci.yml)

CDK Python stacks that deploy generic agent platform infrastructure into AWS: data layer (DynamoDB, S3, SQS), networking (VPC, security groups), agent Lambda functions, MCP Fargate services, observability (CloudWatch, X-Ray, SNS), and security (KMS, Secrets Manager, WAF, VPC endpoints).

All resource names, table names, bucket names, SSM paths, and service discovery namespaces are driven by `config/{env}.yaml` -- specifically the `resource_prefix` key. No domain-specific logic is hardcoded.

## Architecture

```
AGENTS         ->  Lambda + Strands SDK Layer (AgentStack)
     |
MCP SERVERS    ->  ECS Fargate cluster + Cloud Map (McpStack)
     |
DATA/SECURITY  ->  DataStack | NetworkStack | SecurityStack | ObservabilityStack
```

## CDK Stacks

| Stack | File | Purpose |
|---|---|---|
| `DataStack` | `stacks/data_stack.py` | DynamoDB tables, S3 buckets, SQS queues (all config-driven) |
| `NetworkStack` | `stacks/network_stack.py` | VPC (3 subnet tiers), security groups for agents and MCPs |
| `SecurityStack` | `stacks/security_stack.py` | KMS CMKs, Secrets Manager, WAF WebACL, VPC endpoints |
| `AgentStack` | `stacks/agent_stack.py` | Lambda functions for Strands agents, SDK Layer, IAM policies |
| `McpStack` | `stacks/mcp_stack.py` | ECS Fargate cluster, Cloud Map namespace, ECR repos |
| `ObservabilityStack` | `stacks/observability_stack.py` | CloudWatch dashboard, SNS alerts, X-Ray tracing group |

## Reusable Constructs (`constructs_/`)

| Construct | File | Purpose |
|---|---|---|
| `McpServiceConstruct` | `mcp_service.py` | ECR repo + ECS Fargate service + Service Discovery for one MCP |
| `StrandsAgentTask` | `strands_agent.py` | Step Functions LambdaInvoke wrapper with claim-check pattern |
| `SfnWorkflow` | `sfn_workflow.py` | YAML blueprint to Step Functions state machine |
| `FargateAutoScaling` | `auto_scaling.py` | CPU-based auto-scaling for Fargate services |
| `LambdaProvisionedConcurrency` | `auto_scaling.py` | Provisioned concurrency for hot Lambda functions |
| `WafWebAcl` | `waf_rules.py` | WAF WebACL with rate limiting and IP whitelist |
| `VpcEndpointsConstruct` | `vpc_endpoints.py` | VPC endpoints for S3, DynamoDB, SSM, Secrets Manager, ECR, STS |

## Configuration

All environment configs reside in `config/{env}.yaml`. Key fields:

```yaml
resource_prefix: "platform"                    # Prefix for all resource names
service_discovery_namespace: "platform.local"  # Cloud Map namespace
ssm_root_path: "/platform/dev"                 # SSM parameter path root

tables:           # DynamoDB tables to create
buckets:          # S3 buckets to create
agents:           # Agent Lambda functions to create
mcps:             # MCP Fargate services to create
```

To deploy for a different domain, change `resource_prefix` (and related fields) in the config YAML. All stacks read from config -- no code changes needed.

## Deployment

```bash
# Install
pip install -e ".[dev]"

# Synthesize (no AWS calls)
cdk synth -c env=dev

# Deploy all stacks
cdk deploy --all -c env=dev

# Deploy specific stack
cdk deploy platform-dev-data -c env=dev

# Destroy dev
cdk destroy --all -c env=dev
```

## Development

```bash
pip install -e ".[dev]"

# Lint and format
ruff check .
ruff format .

# Run tests
pytest -v

# Coverage
pytest --cov=stacks --cov=constructs_ --cov-report=term-missing
```

## SSM Parameter Namespace

All cross-stack references use SSM under `/{resource_prefix}/{env}/`. Examples:

```
/platform/dev/tables/artifacts/name
/platform/dev/buckets/artifacts/name
/platform/dev/agents/research/arn
/platform/dev/mcps/data/endpoint
/platform/dev/security/data-key-arn
/platform/dev/alert-topic-arn
```

---

*Part of [The Cloud Clock Work](https://github.com/The-Cloud-Clock-Work)*
