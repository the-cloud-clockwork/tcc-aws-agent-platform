# P17 — Full Production Infrastructure

> **Self-contained plan.** A fresh Claude Code agent reads ONLY this file and can execute everything.

## Metadata

| Field | Value |
|---|---|
| Plan ID | P17 |
| Plane Tickets | ROOT-61 (extended) |
| Target Repo | `~/dev/tccw-agent-infra` |
| Depends On | P11 (base CDK stacks), P14 (ibkr-mcp), P15 (2FA gate), P16 (risk engine) |
| Batch | Phase 2 |

## Objective

Upgrade P11 CDK stacks from dev/POC to production-ready. Add multi-environment deployment (dev/paper/live) via config YAML files, VPC endpoints for Bedrock, WAF on API Gateway, Secrets Manager for credentials, KMS encryption, auto-scaling for Fargate services and Lambda provisioned concurrency, new stacks for Phase 2 components (risk engine, 2FA, IBKR), and cost optimization (S3 Intelligent-Tiering, DynamoDB capacity modes).

---

## What Changes from P11

| Area | P11 (POC) | P17 (Production) |
|---|---|---|
| Environments | `env_name` string, manual per-stack | Config YAML per env, loaded by CDK context |
| VPC Endpoints | S3, DynamoDB, SQS, ECR, CloudWatch Logs | + Bedrock Runtime, Secrets Manager, KMS, STS |
| Security | Basic SGs, S3 encryption | WAF on API GW, Secrets Manager, KMS CMKs, rotation |
| Scaling | Fixed `desired_count` | Auto-scaling 1-5 tasks, Lambda provisioned concurrency |
| New Stacks | None | security_stack, risk_engine_stack, twofa_stack, ibkr_stack |
| Cost | Default everything | S3 Intelligent-Tiering, DDB on-demand vs provisioned, reserved tags |
| app.py | Hardcoded values | Loads config YAML, environment-aware routing |

---

## Target File Structure

```
tccw-agent-infra/
├── app.py                              # MODIFIED: environment-aware, loads config YAML
├── config/
│   ├── dev.yaml                        # Dev environment config
│   ├── paper.yaml                      # Paper trading config
│   └── live.yaml                       # Live trading config
├── stacks/
│   ├── security_stack.py               # NEW: WAF, Secrets Manager, KMS keys
│   ├── risk_engine_stack.py            # NEW: Risk Engine Lambda + EventBridge trailing stop
│   ├── twofa_stack.py                  # NEW: 2FA MCP Fargate + Telegram webhook
│   └── ibkr_stack.py                   # NEW: IBKR MCP Fargate + session mgmt
├── constructs_/
│   ├── vpc_endpoints.py                # NEW: VPC endpoints construct
│   ├── waf_rules.py                    # NEW: WAF WebACL for API Gateway
│   └── auto_scaling.py                 # NEW: Fargate + Lambda scaling construct
└── tests/
    ├── test_security_stack.py          # NEW: security stack tests
    └── test_multi_env.py               # NEW: multi-env config tests
```

---

## Agent Instructions

You are upgrading the QITP CDK infrastructure from POC to production-ready.

1. `cd ~/dev/tccw-agent-infra`
2. Create every file listed below with the EXACT content provided.
3. Modify `app.py` to replace the P11 version with the new environment-aware version.
4. Run the acceptance criteria commands at the end.
5. Fix any issues until all checks pass.
6. Commit with a descriptive message.

**Rules:**
- Use `from __future__ import annotations` in ALL `.py` files.
- Use `aws-cdk-lib` v2 — no v1 imports.
- All type hints must be modern (use `X | None` not `Optional[X]`).
- Local constructs directory is `constructs_/` (trailing underscore) to avoid collision with `constructs` PyPI package.
- All secrets referenced by name only — never embed actual credential values.
- Mark any values that need real tuning with `# TODO: tune for production`.

---

## File Contents

---

### `config/dev.yaml`

```yaml
# Dev environment configuration
# Usage: cdk deploy -c env=dev

environment: dev
account: "123456789012"
region: eu-west-1
bedrock_region: us-west-2

execution_mode: backtest

vpc:
  max_azs: 2
  nat_gateways: 1

scaling:
  fargate:
    min_tasks: 1
    max_tasks: 2
    target_cpu_percent: 70
  lambda:
    provisioned_concurrency: 0  # No provisioned concurrency in dev

dynamodb:
  billing_mode: PAY_PER_REQUEST  # On-demand for dev (unpredictable usage)

s3:
  intelligent_tiering: false  # Not worth it for dev
  removal_policy: DESTROY

logs:
  retention_days: 14

mcp_services:
  cpu: 256
  memory_mib: 512
  desired_count: 1

lambda_agents:
  memory_size: 1024
  timeout_minutes: 15

waf:
  enabled: false  # No WAF in dev

secrets:
  rotation_days: 0  # No rotation in dev

tags:
  Environment: dev
  Project: qitp
  CostCenter: qitp-dev
```

---

### `config/paper.yaml`

```yaml
# Paper trading environment configuration
# Usage: cdk deploy -c env=paper

environment: paper
account: "123456789012"
region: eu-west-1
bedrock_region: us-west-2

execution_mode: paper

vpc:
  max_azs: 2
  nat_gateways: 1

scaling:
  fargate:
    min_tasks: 1
    max_tasks: 3
    target_cpu_percent: 65
  lambda:
    provisioned_concurrency: 1  # Warm start for key agents

dynamodb:
  billing_mode: PAY_PER_REQUEST  # On-demand for paper

s3:
  intelligent_tiering: true
  removal_policy: RETAIN

logs:
  retention_days: 30

mcp_services:
  cpu: 512
  memory_mib: 1024
  desired_count: 1

lambda_agents:
  memory_size: 1024
  timeout_minutes: 15

waf:
  enabled: true
  rate_limit: 1000  # Requests per 5 min per IP
  ip_whitelist: []  # No IP restriction for paper

secrets:
  rotation_days: 90

tags:
  Environment: paper
  Project: qitp
  CostCenter: qitp-paper
```

---

### `config/live.yaml`

```yaml
# Live trading environment configuration
# Usage: cdk deploy -c env=live
# WARNING: This deploys real-money trading infrastructure.

environment: live
account: "123456789012"
region: eu-west-1
bedrock_region: us-west-2

execution_mode: live

vpc:
  max_azs: 2
  nat_gateways: 2  # HA: one per AZ

scaling:
  fargate:
    min_tasks: 2    # Always-on for live
    max_tasks: 5
    target_cpu_percent: 60
  lambda:
    provisioned_concurrency: 2  # Warm start for gap_detector + portfolio_recommender

dynamodb:
  billing_mode: PROVISIONED
  read_capacity: 25   # TODO: tune for production
  write_capacity: 10  # TODO: tune for production
  auto_scaling:
    min_capacity: 5
    max_capacity: 100
    target_utilization: 70

s3:
  intelligent_tiering: true
  removal_policy: RETAIN

logs:
  retention_days: 90  # 3 months for live

mcp_services:
  cpu: 512
  memory_mib: 1024
  desired_count: 2  # HA: minimum 2 tasks

lambda_agents:
  memory_size: 2048  # More memory for live
  timeout_minutes: 15

waf:
  enabled: true
  rate_limit: 500      # Stricter rate limiting
  ip_whitelist:        # Restrict to known IPs in live
    - "0.0.0.0/0"     # TODO: replace with actual IP ranges

secrets:
  rotation_days: 30  # Monthly rotation for live

tags:
  Environment: live
  Project: qitp
  CostCenter: qitp-live
  Compliance: mifid-ii
```

---

### `app.py`

```python
#!/usr/bin/env python3
"""CDK app entrypoint for the QITP platform.

Loads environment-specific config from config/{env}.yaml.
Usage: cdk deploy -c env=dev|paper|live
"""
from __future__ import annotations

from pathlib import Path

import yaml
import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.agent_stack import AgentStack
from stacks.mcp_stack import McpStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.observability_stack import ObservabilityStack
from stacks.security_stack import SecurityStack
from stacks.risk_engine_stack import RiskEngineStack
from stacks.twofa_stack import TwoFaStack
from stacks.ibkr_stack import IbkrStack


def load_config(env_name: str) -> dict:
    """Load environment config from YAML file."""
    config_path = Path(__file__).parent / "config" / f"{env_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Valid environments: dev, paper, live"
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


app = cdk.App()

# ── Load Environment Config ──────────────────────────────────────

env_name = app.node.try_get_context("env") or "dev"
config = load_config(env_name)

account = config.get("account", "123456789012")
region = config.get("region", "eu-west-1")

cdk_env = cdk.Environment(account=account, region=region)
prefix = f"qitp-{env_name}"

# Apply tags to all resources in the app
for tag_key, tag_value in config.get("tags", {}).items():
    cdk.Tags.of(app).add(tag_key, str(tag_value))

# ── Core Stacks (from P11, now config-driven) ────────────────────

data = DataStack(
    app,
    f"{prefix}-data",
    env=cdk_env,
    env_name=env_name,
    config=config,
)

network = NetworkStack(
    app,
    f"{prefix}-network",
    env=cdk_env,
    env_name=env_name,
    config=config,
)

# ── Security Stack (P17: WAF, Secrets, KMS) ──────────────────────

security = SecurityStack(
    app,
    f"{prefix}-security",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
)

# ── Agent Stack ──────────────────────────────────────────────────

agents = AgentStack(
    app,
    f"{prefix}-agents",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    agent_sg=network.agent_sg,
    data_stack=data,
    security_stack=security,
)

# ── MCP Stacks ───────────────────────────────────────────────────

mcps = McpStack(
    app,
    f"{prefix}-mcps",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    mcp_sg=network.mcp_sg,
)

# ── Phase 2 Stacks ──────────────────────────────────────────────

risk_engine = RiskEngineStack(
    app,
    f"{prefix}-risk-engine",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    agent_sg=network.agent_sg,
    data_stack=data,
    security_stack=security,
)

twofa = TwoFaStack(
    app,
    f"{prefix}-2fa",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    mcp_sg=network.mcp_sg,
    security_stack=security,
    mcp_cluster=mcps.cluster,
    mcp_namespace=mcps.namespace,
)

ibkr = IbkrStack(
    app,
    f"{prefix}-ibkr",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    mcp_sg=network.mcp_sg,
    security_stack=security,
    mcp_cluster=mcps.cluster,
    mcp_namespace=mcps.namespace,
)

# ── Orchestration Stack ──────────────────────────────────────────

orchestration = OrchestrationStack(
    app,
    f"{prefix}-orchestration",
    env=cdk_env,
    env_name=env_name,
)

# ── Observability Stack ──────────────────────────────────────────

observability = ObservabilityStack(
    app,
    f"{prefix}-observability",
    env=cdk_env,
    env_name=env_name,
    agent_functions=agents.functions,
    mcp_services=mcps.services,
)

app.synth()
```

---

### `constructs_/vpc_endpoints.py`

```python
"""VPC Endpoints construct — reduces NAT Gateway costs and improves security."""
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    aws_ec2 as ec2,
)


class VpcEndpointsConstruct(Construct):
    """Provisions VPC endpoints for AWS services used by QITP.

    Gateway endpoints (free):
    - S3
    - DynamoDB

    Interface endpoints (cost per hour + per GB):
    - SQS
    - ECR (+ ECR Docker)
    - CloudWatch Logs
    - Bedrock Runtime (us-west-2 cross-region — only if same region)
    - Secrets Manager
    - KMS
    - STS
    - SSM

    Interface endpoints are only created when the service is in the same
    region as the VPC. Bedrock Runtime is in us-west-2, so we skip it
    for eu-west-1 VPCs (cross-region VPC endpoints are not supported).
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        env_name: str,
    ) -> None:
        super().__init__(scope, construct_id)

        self.vpc = vpc
        self.env_name = env_name

        # ── Gateway Endpoints (free, always create) ──────────────────

        self.s3_endpoint = vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        self.dynamodb_endpoint = vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
        )

        # ── Interface Endpoints ──────────────────────────────────────

        # SQS — used by artifact notifications, 2FA approval queue
        self.sqs_endpoint = vpc.add_interface_endpoint(
            "SQSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SQS,
            private_dns_enabled=True,
        )

        # ECR — pull container images for MCP services
        self.ecr_endpoint = vpc.add_interface_endpoint(
            "ECREndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            private_dns_enabled=True,
        )
        self.ecr_docker_endpoint = vpc.add_interface_endpoint(
            "ECRDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            private_dns_enabled=True,
        )

        # CloudWatch Logs — all Lambda and ECS log shipping
        self.logs_endpoint = vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            private_dns_enabled=True,
        )

        # Secrets Manager — credential retrieval
        self.secrets_endpoint = vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            private_dns_enabled=True,
        )

        # KMS — encryption/decryption for Secrets Manager + S3 SSE-KMS
        self.kms_endpoint = vpc.add_interface_endpoint(
            "KMSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.KMS,
            private_dns_enabled=True,
        )

        # STS — IAM role assumption for cross-account/cross-region
        self.sts_endpoint = vpc.add_interface_endpoint(
            "STSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.STS,
            private_dns_enabled=True,
        )

        # SSM Parameter Store — config retrieval
        self.ssm_endpoint = vpc.add_interface_endpoint(
            "SSMEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
            private_dns_enabled=True,
        )

        # Note: Bedrock Runtime is in us-west-2 but VPC is in eu-west-1.
        # Cross-region VPC endpoints are NOT supported. Bedrock calls
        # go through NAT Gateway. This is acceptable because Bedrock
        # calls are infrequent (agent invocations) and the NAT cost
        # is minimal compared to Bedrock inference cost.
```

---

### `constructs_/waf_rules.py`

```python
"""WAF WebACL construct for API Gateway protection."""
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    aws_wafv2 as wafv2,
)


class WafWebAcl(Construct):
    """Creates a WAF WebACL with rate limiting, IP whitelist, and managed rule groups.

    Attach to API Gateway or ALB via web_acl_arn.

    Rules (in priority order):
    1. IP whitelist — allow known IPs (live env only)
    2. Rate limiting — block IPs exceeding request threshold
    3. AWS Managed Rules: Common Rule Set — SQL injection, XSS, etc.
    4. AWS Managed Rules: Known Bad Inputs — Log4j, etc.
    5. Default action: ALLOW
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        rate_limit: int = 1000,
        ip_whitelist: list[str] | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        self.env_name = env_name
        rules: list[wafv2.CfnWebACL.RuleProperty] = []
        priority = 0

        # ── Rule 1: IP Whitelist (live env only) ─────────────────────

        if ip_whitelist and env_name == "live":
            # Create IP set for whitelisted addresses
            self.ip_set = wafv2.CfnIPSet(
                self,
                "WhitelistIPSet",
                name=f"qitp-{env_name}-whitelist",
                scope="REGIONAL",
                ip_address_version="IPV4",
                addresses=ip_whitelist,
            )

            rules.append(
                wafv2.CfnWebACL.RuleProperty(
                    name="IPWhitelist",
                    priority=priority,
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        allow=wafv2.CfnWebACL.AllowActionProperty(),
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        ip_set_reference_statement=wafv2.CfnWebACL.IPSetReferenceStatementProperty(
                            arn=self.ip_set.attr_arn,
                        ),
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"qitp-{env_name}-ip-whitelist",
                        sampled_requests_enabled=True,
                    ),
                )
            )
            priority += 1

        # ── Rule 2: Rate Limiting ────────────────────────────────────

        rules.append(
            wafv2.CfnWebACL.RuleProperty(
                name="RateLimit",
                priority=priority,
                action=wafv2.CfnWebACL.RuleActionProperty(
                    block=wafv2.CfnWebACL.BlockActionProperty(),
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                        limit=rate_limit,
                        aggregate_key_type="IP",
                    ),
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"qitp-{env_name}-rate-limit",
                    sampled_requests_enabled=True,
                ),
            )
        )
        priority += 1

        # ── Rule 3: AWS Managed Rules — Common Rule Set ──────────────

        rules.append(
            wafv2.CfnWebACL.RuleProperty(
                name="AWSManagedRulesCommonRuleSet",
                priority=priority,
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    none={}
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesCommonRuleSet",
                    ),
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"qitp-{env_name}-common-rules",
                    sampled_requests_enabled=True,
                ),
            )
        )
        priority += 1

        # ── Rule 4: AWS Managed Rules — Known Bad Inputs ─────────────

        rules.append(
            wafv2.CfnWebACL.RuleProperty(
                name="AWSManagedRulesKnownBadInputs",
                priority=priority,
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    none={}
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesKnownBadInputsRuleSet",
                    ),
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"qitp-{env_name}-known-bad-inputs",
                    sampled_requests_enabled=True,
                ),
            )
        )

        # ── WebACL ───────────────────────────────────────────────────

        self.web_acl = wafv2.CfnWebACL(
            self,
            "WebACL",
            name=f"qitp-{env_name}-web-acl",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow=wafv2.CfnWebACL.AllowActionProperty(),
            ),
            rules=rules,
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"qitp-{env_name}-web-acl",
                sampled_requests_enabled=True,
            ),
        )

        self.web_acl_arn = self.web_acl.attr_arn
```

---

### `constructs_/auto_scaling.py`

```python
"""Auto-scaling construct for Fargate services and Lambda provisioned concurrency."""
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    Duration,
    aws_ecs as ecs,
    aws_applicationautoscaling as appscaling,
    aws_lambda as lambda_,
)


class FargateAutoScaling(Construct):
    """Configures auto-scaling for an ECS Fargate service.

    Scales based on:
    - CPU utilization (primary)
    - Memory utilization (secondary, scale-out only)

    Scale-in cooldown is longer than scale-out to prevent flapping.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        service: ecs.FargateService,
        min_tasks: int = 1,
        max_tasks: int = 5,
        target_cpu_percent: int = 70,
    ) -> None:
        super().__init__(scope, construct_id)

        self.scalable_target = service.auto_scale_task_count(
            min_capacity=min_tasks,
            max_capacity=max_tasks,
        )

        # Scale on CPU utilization
        self.scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=target_cpu_percent,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2),
        )

        # Scale on memory utilization (higher threshold — memory is less volatile)
        self.scalable_target.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2),
        )


class LambdaProvisionedConcurrency(Construct):
    """Configures provisioned concurrency for a Lambda function.

    Creates an alias ("live") with provisioned concurrency.
    Use this for hot-path agents that need sub-second cold starts:
    - gap_detector (runs on schedule, latency-sensitive)
    - portfolio_recommender (extended thinking, expensive cold start)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        function: lambda_.Function,
        provisioned_concurrent_executions: int,
        alias_name: str = "live",
    ) -> None:
        super().__init__(scope, construct_id)

        if provisioned_concurrent_executions <= 0:
            # No-op: skip provisioned concurrency (dev env)
            self.alias = None
            return

        # Create a version from the current function code
        self.version = function.current_version

        # Create alias with provisioned concurrency
        self.alias = lambda_.Alias(
            self,
            "Alias",
            alias_name=alias_name,
            version=self.version,
            provisioned_concurrent_executions=provisioned_concurrent_executions,
        )
```

---

### `stacks/security_stack.py`

```python
"""Security stack: WAF, Secrets Manager, KMS customer-managed keys."""
from __future__ import annotations

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_kms as kms,
    aws_secretsmanager as secretsmanager,
    aws_ec2 as ec2,
    aws_ssm as ssm,
)

from constructs_.waf_rules import WafWebAcl
from constructs_.vpc_endpoints import VpcEndpointsConstruct


class SecurityStack(Stack):
    """Provisions security infrastructure for the QITP platform.

    Components:
    - KMS customer-managed keys (CMKs) for encryption at rest
    - Secrets Manager secrets for external service credentials
    - WAF WebACL for API Gateway protection (paper/live only)
    - VPC Endpoints for secure, cost-effective AWS service access
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        vpc: ec2.IVpc,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.config = config
        removal = RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN

        # ── VPC Endpoints ────────────────────────────────────────────

        self.vpc_endpoints = VpcEndpointsConstruct(
            self,
            "VpcEndpoints",
            vpc=vpc,
            env_name=env_name,
        )

        # ── KMS Customer-Managed Keys ────────────────────────────────

        # Primary encryption key for DynamoDB, SQS, and general use
        self.data_key = kms.Key(
            self,
            "DataKey",
            alias=f"alias/qitp-{env_name}-data",
            description=f"QITP {env_name} data encryption key (DynamoDB, SQS)",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # Separate key for S3 objects (artifacts, historical data)
        self.storage_key = kms.Key(
            self,
            "StorageKey",
            alias=f"alias/qitp-{env_name}-storage",
            description=f"QITP {env_name} storage encryption key (S3)",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # Separate key for secrets encryption
        self.secrets_key = kms.Key(
            self,
            "SecretsKey",
            alias=f"alias/qitp-{env_name}-secrets",
            description=f"QITP {env_name} secrets encryption key",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # ── Secrets Manager Secrets ──────────────────────────────────

        rotation_days = config.get("secrets", {}).get("rotation_days", 0)

        # IBKR credentials (username, password, account ID)
        self.ibkr_secret = secretsmanager.Secret(
            self,
            "IbkrSecret",
            secret_name=f"qitp/{env_name}/ibkr-credentials",
            description="Interactive Brokers API credentials",
            encryption_key=self.secrets_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"PLACEHOLDER","account_id":"PLACEHOLDER"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        # Polygon.io API key
        self.polygon_secret = secretsmanager.Secret(
            self,
            "PolygonSecret",
            secret_name=f"qitp/{env_name}/polygon-api-key",
            description="Polygon.io market data API key",
            encryption_key=self.secrets_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"provider":"polygon"}',
                generate_string_key="api_key",
                exclude_punctuation=True,
            ),
        )

        # Telegram bot token (for 2FA approval gateway)
        self.telegram_secret = secretsmanager.Secret(
            self,
            "TelegramSecret",
            secret_name=f"qitp/{env_name}/telegram-bot-token",
            description="Telegram bot token for 2FA approval notifications",
            encryption_key=self.secrets_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"chat_id":"PLACEHOLDER"}',
                generate_string_key="bot_token",
                exclude_punctuation=True,
            ),
        )

        # Langfuse API key (observability)
        self.langfuse_secret = secretsmanager.Secret(
            self,
            "LangfuseSecret",
            secret_name=f"qitp/{env_name}/langfuse-api-key",
            description="Langfuse observability API key",
            encryption_key=self.secrets_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"host":"https://cloud.langfuse.com"}',
                generate_string_key="secret_key",
                exclude_punctuation=True,
            ),
        )

        self.secrets = {
            "ibkr": self.ibkr_secret,
            "polygon": self.polygon_secret,
            "telegram": self.telegram_secret,
            "langfuse": self.langfuse_secret,
        }

        # ── WAF WebACL (paper/live only) ─────────────────────────────

        waf_config = config.get("waf", {})
        self.web_acl: WafWebAcl | None = None

        if waf_config.get("enabled", False):
            self.web_acl = WafWebAcl(
                self,
                "WafWebAcl",
                env_name=env_name,
                rate_limit=waf_config.get("rate_limit", 1000),
                ip_whitelist=waf_config.get("ip_whitelist"),
            )

        # ── SSM Parameters ───────────────────────────────────────────

        ssm.StringParameter(
            self,
            "SSM-data-key-arn",
            parameter_name=f"/qitp/{env_name}/security/data-key-arn",
            string_value=self.data_key.key_arn,
        )
        ssm.StringParameter(
            self,
            "SSM-storage-key-arn",
            parameter_name=f"/qitp/{env_name}/security/storage-key-arn",
            string_value=self.storage_key.key_arn,
        )

        for secret_name, secret in self.secrets.items():
            ssm.StringParameter(
                self,
                f"SSM-secret-{secret_name}-arn",
                parameter_name=f"/qitp/{env_name}/secrets/{secret_name}/arn",
                string_value=secret.secret_arn,
            )

        if self.web_acl:
            ssm.StringParameter(
                self,
                "SSM-waf-acl-arn",
                parameter_name=f"/qitp/{env_name}/security/waf-acl-arn",
                string_value=self.web_acl.web_acl_arn,
            )
```

---

### `stacks/risk_engine_stack.py`

```python
"""Risk Engine stack: Lambda function, DynamoDB risk state, EventBridge for trailing stops."""
from __future__ import annotations

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_ssm as ssm,
)

from stacks.data_stack import DataStack
from stacks.security_stack import SecurityStack
from constructs_.auto_scaling import LambdaProvisionedConcurrency


class RiskEngineStack(Stack):
    """Provisions the Risk Engine Lambda and EventBridge trailing stop monitor.

    The Risk Engine is a plain Lambda (not Strands agent) that enforces
    hard risk limits before any order submission:
    - Max open positions (5)
    - Max single position size (20% NAV)
    - Max sector concentration (40%)
    - Daily loss breaker (-3% portfolio)
    - Drawdown breaker (-10% from peak)
    - Trailing stop mandatory check

    EventBridge rule runs every 5 minutes during market hours to check
    trailing stop conditions and trigger adjustments.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        vpc: ec2.IVpc,
        agent_sg: ec2.ISecurityGroup,
        data_stack: DataStack,
        security_stack: SecurityStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # ── Log Group ────────────────────────────────────────────────

        log_group = logs.LogGroup(
            self,
            "RiskEngineLogGroup",
            log_group_name=f"/aws/lambda/qitp-{env_name}-risk-engine",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── IAM Role ────────────────────────────────────────────────

        risk_role = iam.Role(
            self,
            "RiskEngineRole",
            role_name=f"qitp-{env_name}-risk-engine-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # DynamoDB: read/write risk_state, read-only for watchlist and audit_log
        risk_role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBRiskState",
                actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"],
                resources=[
                    data_stack.risk_state_table.table_arn,
                    f"{data_stack.risk_state_table.table_arn}/index/*",
                ],
            )
        )
        risk_role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBReadOnly",
                actions=["dynamodb:GetItem", "dynamodb:Query"],
                resources=[
                    data_stack.watchlist_table.table_arn,
                    data_stack.audit_log_table.table_arn,
                    f"{data_stack.audit_log_table.table_arn}/index/*",
                ],
            )
        )

        # Secrets Manager: read IBKR credentials (for position queries)
        risk_role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsRead",
                actions=["secretsmanager:GetSecretValue"],
                resources=[security_stack.ibkr_secret.secret_arn],
            )
        )

        # KMS: decrypt secrets
        security_stack.secrets_key.grant_decrypt(risk_role)

        # X-Ray tracing
        risk_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracing",
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )

        # ── Risk Engine Lambda ───────────────────────────────────────

        lambda_config = config.get("lambda_agents", {})

        self.risk_engine_function = lambda_.Function(
            self,
            "RiskEngineFunction",
            function_name=f"qitp-{env_name}-risk-engine",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda/risk_engine"),
            timeout=Duration.seconds(30),  # Risk checks must be fast
            memory_size=512,
            role=risk_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[agent_sg],
            tracing=lambda_.Tracing.ACTIVE,
            log_group=log_group,
            environment={
                "ENV_NAME": env_name,
                "EXECUTION_MODE": config.get("execution_mode", "backtest"),
                "RISK_STATE_TABLE": data_stack.risk_state_table.table_name,
                "WATCHLIST_TABLE": data_stack.watchlist_table.table_name,
                "AUDIT_LOG_TABLE": data_stack.audit_log_table.table_name,
                "IBKR_SECRET_ARN": security_stack.ibkr_secret.secret_arn,
                # Risk limits (configurable via env vars)
                "MAX_OPEN_POSITIONS": "5",
                "MAX_POSITION_SIZE_PCT": "20",
                "MAX_SECTOR_CONCENTRATION_PCT": "40",
                "DAILY_LOSS_BREAKER_PCT": "3",
                "DRAWDOWN_BREAKER_PCT": "10",
            },
        )

        # ── Provisioned Concurrency (live only) ─────────────────────

        provisioned = config.get("scaling", {}).get("lambda", {}).get(
            "provisioned_concurrency", 0
        )
        if provisioned > 0 and env_name == "live":
            LambdaProvisionedConcurrency(
                self,
                "RiskEnginePC",
                function=self.risk_engine_function,
                provisioned_concurrent_executions=1,  # Risk engine: 1 is enough
            )

        # ── EventBridge: Trailing Stop Monitor ───────────────────────
        # Runs every 5 minutes during US market hours (14:30-21:00 UTC)
        # Only in paper/live modes — backtest doesn't need real-time monitoring

        if env_name in ("paper", "live"):
            self.trailing_stop_rule = events.Rule(
                self,
                "TrailingStopMonitorRule",
                rule_name=f"qitp-{env_name}-trailing-stop-monitor",
                description="Check trailing stop conditions every 5 minutes during market hours",
                schedule=events.Schedule.cron(
                    minute="*/5",
                    hour="14-21",  # US market hours in UTC
                    week_day="MON-FRI",
                ),
                enabled=env_name == "live",  # Disabled for paper by default
            )

            self.trailing_stop_rule.add_target(
                events_targets.LambdaFunction(
                    self.risk_engine_function,
                    event=events.RuleTargetInput.from_object({
                        "action": "check_trailing_stops",
                        "execution_mode": config.get("execution_mode", "paper"),
                    }),
                    retry_attempts=2,
                )
            )

        # ── SSM Parameters ───────────────────────────────────────────

        ssm.StringParameter(
            self,
            "SSM-risk-engine-arn",
            parameter_name=f"/qitp/{env_name}/risk-engine/function-arn",
            string_value=self.risk_engine_function.function_arn,
        )
```

---

### `stacks/twofa_stack.py`

```python
"""2FA stack: Telegram approval gateway as ECS Fargate + API Gateway webhook."""
from __future__ import annotations

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_iam as iam,
    aws_apigateway as apigw,
    aws_servicediscovery as sd,
    aws_ssm as ssm,
    aws_sqs as sqs,
)

from stacks.security_stack import SecurityStack
from constructs_.auto_scaling import FargateAutoScaling


class TwoFaStack(Stack):
    """Provisions the 2FA approval gateway.

    Architecture:
    1. Step Functions waitForTaskToken → SQS approval queue
    2. 2FA MCP (Fargate) polls SQS, sends Telegram notification
    3. Telegram webhook → API Gateway → 2FA MCP → sends task success/failure
    4. Step Functions resumes with approval/rejection

    Components:
    - ECS Fargate service for 2FA MCP (port 8007)
    - API Gateway for Telegram webhook callback
    - IAM permissions for SFN SendTaskSuccess/SendTaskFailure
    - WAF association on API Gateway (if enabled)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        vpc: ec2.IVpc,
        mcp_sg: ec2.ISecurityGroup,
        security_stack: SecurityStack,
        mcp_cluster: ecs.ICluster,
        mcp_namespace: sd.INamespace,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        mcp_config = config.get("mcp_services", {})
        scaling_config = config.get("scaling", {}).get("fargate", {})

        # ── Log Group ────────────────────────────────────────────────

        log_group = logs.LogGroup(
            self,
            "TwoFaLogGroup",
            log_group_name=f"/ecs/qitp-{env_name}-mcp-2fa",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Task Definition ──────────────────────────────────────────

        task_role = iam.Role(
            self,
            "TwoFaTaskRole",
            role_name=f"qitp-{env_name}-2fa-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Allow sending task success/failure to Step Functions
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsCallback",
                actions=[
                    "states:SendTaskSuccess",
                    "states:SendTaskFailure",
                    "states:SendTaskHeartbeat",
                ],
                resources=["*"],  # SFN ARN not known at deploy time
            )
        )

        # Allow reading Telegram bot token from Secrets Manager
        security_stack.telegram_secret.grant_read(task_role)
        security_stack.secrets_key.grant_decrypt(task_role)

        # Allow SQS operations on approval queue
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="SQSApprovalQueue",
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:SendMessage",
                ],
                resources=[
                    f"arn:aws:sqs:{self.region}:{self.account}:qitp-{env_name}-2fa-approval-queue",
                ],
            )
        )

        task_def = ecs.FargateTaskDefinition(
            self,
            "TwoFaTaskDef",
            family=f"qitp-{env_name}-mcp-2fa",
            cpu=mcp_config.get("cpu", 256),
            memory_limit_mib=mcp_config.get("memory_mib", 512),
            task_role=task_role,
        )

        container = task_def.add_container(
            "TwoFaContainer",
            container_name="2fa-mcp",
            image=ecs.ContainerImage.from_registry(
                f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/"
                f"qitp-{env_name}-mcp-2fa:latest"
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="2fa",
                log_group=log_group,
            ),
            environment={
                "ENV_NAME": env_name,
                "MCP_NAME": "2fa",
                "PORT": "8007",
                "EXECUTION_MODE": config.get("execution_mode", "backtest"),
                "APPROVAL_QUEUE_URL": (
                    f"https://sqs.{self.region}.amazonaws.com/"
                    f"{self.account}/qitp-{env_name}-2fa-approval-queue"
                ),
            },
            secrets={
                "TELEGRAM_BOT_TOKEN": ecs.Secret.from_secrets_manager(
                    security_stack.telegram_secret, "bot_token"
                ),
                "TELEGRAM_CHAT_ID": ecs.Secret.from_secrets_manager(
                    security_stack.telegram_secret, "chat_id"
                ),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8007/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=8007, protocol=ecs.Protocol.TCP)
        )

        # ── Fargate Service ──────────────────────────────────────────

        desired_count = mcp_config.get("desired_count", 1)

        self.service = ecs.FargateService(
            self,
            "TwoFaService",
            service_name=f"qitp-{env_name}-mcp-2fa",
            cluster=mcp_cluster,
            task_definition=task_def,
            desired_count=desired_count,
            security_groups=[mcp_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            assign_public_ip=False,
            cloud_map_options=ecs.CloudMapOptions(
                name="2fa",
                cloud_map_namespace=mcp_namespace,
                dns_record_type=sd.DnsRecordType.A,
                dns_ttl=Duration.seconds(30),
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            enable_execute_command=True,
        )

        # ── Auto-scaling ─────────────────────────────────────────────

        if scaling_config.get("max_tasks", 1) > 1:
            FargateAutoScaling(
                self,
                "TwoFaScaling",
                service=self.service,
                min_tasks=scaling_config.get("min_tasks", 1),
                max_tasks=scaling_config.get("max_tasks", 3),
                target_cpu_percent=scaling_config.get("target_cpu_percent", 70),
            )

        # ── API Gateway for Telegram Webhook ─────────────────────────

        self.api = apigw.RestApi(
            self,
            "TwoFaWebhookApi",
            rest_api_name=f"qitp-{env_name}-2fa-webhook",
            description="Telegram webhook endpoint for 2FA approval callbacks",
            deploy_options=apigw.StageOptions(
                stage_name=env_name,
                throttling_rate_limit=10,
                throttling_burst_limit=20,
                tracing_enabled=True,
                logging_level=apigw.MethodLoggingLevel.INFO,
            ),
        )

        # Webhook resource: POST /webhook/telegram
        webhook_resource = self.api.root.add_resource("webhook").add_resource("telegram")

        # VPC Link for private integration with Fargate
        vpc_link = apigw.VpcLink(
            self,
            "TwoFaVpcLink",
            vpc_link_name=f"qitp-{env_name}-2fa-vpc-link",
            targets=[],  # Will be configured with NLB in production
            description="VPC Link for 2FA MCP webhook",
        )

        # For now, use a mock integration (real integration needs NLB/ALB)
        # In production, replace with HTTP_PROXY integration through VPC Link
        webhook_resource.add_method(
            "POST",
            apigw.MockIntegration(
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                        response_templates={"application/json": '{"status": "ok"}'},
                    )
                ],
                request_templates={"application/json": '{"statusCode": 200}'},
            ),
            method_responses=[
                apigw.MethodResponse(status_code="200"),
            ],
        )

        # ── WAF Association ──────────────────────────────────────────

        if security_stack.web_acl:
            cdk.aws_wafv2.CfnWebACLAssociation(
                self,
                "WafAssociation",
                resource_arn=self.api.deployment_stage.stage_arn,
                web_acl_arn=security_stack.web_acl.web_acl_arn,
            )

        # ── SSM Parameters ───────────────────────────────────────────

        ssm.StringParameter(
            self,
            "SSM-2fa-endpoint",
            parameter_name=f"/qitp/{env_name}/mcps/2fa/endpoint",
            string_value="2fa.qitp.local",
        )
        ssm.StringParameter(
            self,
            "SSM-2fa-webhook-url",
            parameter_name=f"/qitp/{env_name}/mcps/2fa/webhook-url",
            string_value=self.api.url,
        )
```

---

### `stacks/ibkr_stack.py`

```python
"""IBKR stack: Interactive Brokers MCP as ECS Fargate with session management."""
from __future__ import annotations

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_servicediscovery as sd,
    aws_ssm as ssm,
)

from stacks.security_stack import SecurityStack
from constructs_.auto_scaling import FargateAutoScaling


class IbkrStack(Stack):
    """Provisions the Interactive Brokers MCP Fargate service.

    The IBKR MCP manages:
    - IBKR Client Portal API gateway session
    - Position queries (read-only for risk engine)
    - Order submission (write, 2FA-gated)
    - Trailing stop management
    - Account summary queries

    Session management:
    - IBKR sessions stored in DynamoDB (session tokens, expiry)
    - Session refresh runs on a schedule (keep-alive)
    - Credentials from Secrets Manager (never in env vars)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        vpc: ec2.IVpc,
        mcp_sg: ec2.ISecurityGroup,
        security_stack: SecurityStack,
        mcp_cluster: ecs.ICluster,
        mcp_namespace: sd.INamespace,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        mcp_config = config.get("mcp_services", {})
        scaling_config = config.get("scaling", {}).get("fargate", {})
        removal = RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN

        # ── IBKR Session Table ───────────────────────────────────────

        self.session_table = dynamodb.Table(
            self,
            "IbkrSessionTable",
            table_name=f"qitp_{env_name}_ibkr_sessions",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl",
        )

        # ── Log Group ────────────────────────────────────────────────

        log_group = logs.LogGroup(
            self,
            "IbkrLogGroup",
            log_group_name=f"/ecs/qitp-{env_name}-mcp-ibkr",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Task Role ────────────────────────────────────────────────

        task_role = iam.Role(
            self,
            "IbkrTaskRole",
            role_name=f"qitp-{env_name}-ibkr-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # IBKR credentials from Secrets Manager
        security_stack.ibkr_secret.grant_read(task_role)
        security_stack.secrets_key.grant_decrypt(task_role)

        # DynamoDB session table access
        self.session_table.grant_read_write_data(task_role)

        # X-Ray tracing
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracing",
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )

        # ── Task Definition ──────────────────────────────────────────

        task_def = ecs.FargateTaskDefinition(
            self,
            "IbkrTaskDef",
            family=f"qitp-{env_name}-mcp-ibkr",
            cpu=mcp_config.get("cpu", 256),
            memory_limit_mib=mcp_config.get("memory_mib", 512),
            task_role=task_role,
        )

        container = task_def.add_container(
            "IbkrContainer",
            container_name="ibkr-mcp",
            image=ecs.ContainerImage.from_registry(
                f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/"
                f"qitp-{env_name}-mcp-ibkr:latest"
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ibkr",
                log_group=log_group,
            ),
            environment={
                "ENV_NAME": env_name,
                "MCP_NAME": "ibkr",
                "PORT": "8001",
                "EXECUTION_MODE": config.get("execution_mode", "backtest"),
                "SESSION_TABLE": self.session_table.table_name,
            },
            secrets={
                "IBKR_USERNAME": ecs.Secret.from_secrets_manager(
                    security_stack.ibkr_secret, "username"
                ),
                "IBKR_ACCOUNT_ID": ecs.Secret.from_secrets_manager(
                    security_stack.ibkr_secret, "account_id"
                ),
                "IBKR_PASSWORD": ecs.Secret.from_secrets_manager(
                    security_stack.ibkr_secret, "password"
                ),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8001/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(90),  # IBKR session init takes longer
            ),
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=8001, protocol=ecs.Protocol.TCP)
        )

        # ── Fargate Service ──────────────────────────────────────────

        desired_count = mcp_config.get("desired_count", 1)

        self.service = ecs.FargateService(
            self,
            "IbkrService",
            service_name=f"qitp-{env_name}-mcp-ibkr",
            cluster=mcp_cluster,
            task_definition=task_def,
            desired_count=desired_count,
            security_groups=[mcp_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            assign_public_ip=False,
            cloud_map_options=ecs.CloudMapOptions(
                name="ibkr",
                cloud_map_namespace=mcp_namespace,
                dns_record_type=sd.DnsRecordType.A,
                dns_ttl=Duration.seconds(30),
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            enable_execute_command=True,
        )

        # ── Auto-scaling ─────────────────────────────────────────────

        if scaling_config.get("max_tasks", 1) > 1:
            FargateAutoScaling(
                self,
                "IbkrScaling",
                service=self.service,
                min_tasks=scaling_config.get("min_tasks", 1),
                max_tasks=scaling_config.get("max_tasks", 3),
                target_cpu_percent=scaling_config.get("target_cpu_percent", 70),
            )

        # ── SSM Parameters ───────────────────────────────────────────

        ssm.StringParameter(
            self,
            "SSM-ibkr-endpoint",
            parameter_name=f"/qitp/{env_name}/mcps/ibkr/endpoint",
            string_value="ibkr.qitp.local",
        )
        ssm.StringParameter(
            self,
            "SSM-ibkr-session-table",
            parameter_name=f"/qitp/{env_name}/mcps/ibkr/session-table",
            string_value=self.session_table.table_name,
        )
```

---

### `tests/test_security_stack.py`

```python
"""Tests for the SecurityStack — WAF, Secrets Manager, KMS, VPC Endpoints."""
from __future__ import annotations

import pytest
import aws_cdk as cdk
from aws_cdk import assertions

from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack


def _make_config(env_name: str, waf_enabled: bool = False) -> dict:
    """Build a minimal config dict for testing."""
    return {
        "environment": env_name,
        "account": "123456789012",
        "region": "eu-west-1",
        "execution_mode": "backtest" if env_name == "dev" else env_name,
        "vpc": {"max_azs": 2, "nat_gateways": 1},
        "scaling": {"fargate": {"min_tasks": 1, "max_tasks": 2, "target_cpu_percent": 70}, "lambda": {"provisioned_concurrency": 0}},
        "dynamodb": {"billing_mode": "PAY_PER_REQUEST"},
        "s3": {"intelligent_tiering": False, "removal_policy": "DESTROY"},
        "logs": {"retention_days": 14},
        "mcp_services": {"cpu": 256, "memory_mib": 512, "desired_count": 1},
        "lambda_agents": {"memory_size": 1024, "timeout_minutes": 15},
        "waf": {"enabled": waf_enabled, "rate_limit": 1000, "ip_whitelist": []},
        "secrets": {"rotation_days": 0},
        "tags": {"Environment": env_name},
    }


@pytest.fixture
def app():
    return cdk.App(context={"env": "dev"})


@pytest.fixture
def cdk_env():
    return cdk.Environment(account="123456789012", region="eu-west-1")


class TestKmsKeys:
    def test_creates_three_kms_keys(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # 3 CMKs: data, storage, secrets
        template.resource_count_is("AWS::KMS::Key", 3)

    def test_kms_key_rotation_enabled(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet2", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity2", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::KMS::Key",
            {"EnableKeyRotation": True},
        )


class TestSecretsManager:
    def test_creates_four_secrets(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet3", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity3", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # 4 secrets: ibkr, polygon, telegram, langfuse
        template.resource_count_is("AWS::SecretsManager::Secret", 4)

    def test_ibkr_secret_name(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet4", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity4", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "qitp/dev/ibkr-credentials"},
        )

    def test_secrets_encrypted_with_cmk(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet5", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity5", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # All secrets should reference a KMS key
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"KmsKeyId": assertions.Match.any_value()},
        )


class TestWaf:
    def test_no_waf_in_dev(self, app, cdk_env):
        config = _make_config("dev", waf_enabled=False)
        network = NetworkStack(app, "TestNet6", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity6", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # No WAF resources in dev
        template.resource_count_is("AWS::WAFv2::WebACL", 0)

    def test_waf_created_when_enabled(self, app, cdk_env):
        config = _make_config("paper", waf_enabled=True)
        network = NetworkStack(app, "TestNet7", env=cdk_env, env_name="paper", config=config)
        stack = SecurityStack(
            app, "TestSecurity7", env=cdk_env, env_name="paper", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::WAFv2::WebACL", 1)

    def test_waf_has_rate_limit_rule(self, app, cdk_env):
        config = _make_config("paper", waf_enabled=True)
        network = NetworkStack(app, "TestNet8", env=cdk_env, env_name="paper", config=config)
        stack = SecurityStack(
            app, "TestSecurity8", env=cdk_env, env_name="paper", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::WAFv2::WebACL",
            {
                "Rules": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Name": "RateLimit",
                        "Statement": {
                            "RateBasedStatement": {
                                "Limit": 1000,
                                "AggregateKeyType": "IP",
                            },
                        },
                    }),
                ]),
            },
        )

    def test_waf_has_managed_rules(self, app, cdk_env):
        config = _make_config("live", waf_enabled=True)
        network = NetworkStack(app, "TestNet9", env=cdk_env, env_name="live", config=config)
        stack = SecurityStack(
            app, "TestSecurity9", env=cdk_env, env_name="live", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::WAFv2::WebACL",
            {
                "Rules": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Name": "AWSManagedRulesCommonRuleSet",
                    }),
                    assertions.Match.object_like({
                        "Name": "AWSManagedRulesKnownBadInputs",
                    }),
                ]),
            },
        )


class TestVpcEndpoints:
    def test_creates_gateway_endpoints(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet10", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity10", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # S3 and DynamoDB gateway endpoints
        template.resource_count_is("AWS::EC2::VPCEndpoint", assertions.Match.any_value())

    def test_creates_interface_endpoints(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet11", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity11", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # Should have multiple VPC endpoints (interface + gateway)
        # Exact count depends on CDK synthesis — just verify > 0
        resources = template.find_resources("AWS::EC2::VPCEndpoint")
        assert len(resources) > 0


class TestSsmParameters:
    def test_exports_key_arns(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet12", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity12", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/qitp/dev/security/data-key-arn"},
        )
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/qitp/dev/security/storage-key-arn"},
        )

    def test_exports_secret_arns(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet13", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity13", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        for secret_name in ("ibkr", "polygon", "telegram", "langfuse"):
            template.has_resource_properties(
                "AWS::SSM::Parameter",
                {"Name": f"/qitp/dev/secrets/{secret_name}/arn"},
            )
```

---

### `tests/test_multi_env.py`

```python
"""Tests for multi-environment configuration loading and stack behavior."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
import aws_cdk as cdk
from aws_cdk import assertions

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack
from stacks.risk_engine_stack import RiskEngineStack
from stacks.twofa_stack import TwoFaStack
from stacks.ibkr_stack import IbkrStack
from stacks.mcp_stack import McpStack


CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_config(env_name: str) -> dict:
    """Load config YAML for testing."""
    config_path = CONFIG_DIR / f"{env_name}.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


class TestConfigFiles:
    """Verify that all config YAMLs exist and have required keys."""

    @pytest.mark.parametrize("env_name", ["dev", "paper", "live"])
    def test_config_file_exists(self, env_name):
        config_path = CONFIG_DIR / f"{env_name}.yaml"
        assert config_path.exists(), f"Missing config: {config_path}"

    @pytest.mark.parametrize("env_name", ["dev", "paper", "live"])
    def test_config_has_required_keys(self, env_name):
        config = _load_config(env_name)
        required_keys = [
            "environment",
            "account",
            "region",
            "execution_mode",
            "vpc",
            "scaling",
            "dynamodb",
            "s3",
            "logs",
            "mcp_services",
            "lambda_agents",
            "waf",
            "secrets",
            "tags",
        ]
        for key in required_keys:
            assert key in config, f"Missing key '{key}' in {env_name}.yaml"

    @pytest.mark.parametrize("env_name", ["dev", "paper", "live"])
    def test_config_environment_matches_filename(self, env_name):
        config = _load_config(env_name)
        assert config["environment"] == env_name

    def test_dev_execution_mode_is_backtest(self):
        config = _load_config("dev")
        assert config["execution_mode"] == "backtest"

    def test_paper_execution_mode_is_paper(self):
        config = _load_config("paper")
        assert config["execution_mode"] == "paper"

    def test_live_execution_mode_is_live(self):
        config = _load_config("live")
        assert config["execution_mode"] == "live"

    def test_dev_waf_disabled(self):
        config = _load_config("dev")
        assert config["waf"]["enabled"] is False

    def test_live_waf_enabled(self):
        config = _load_config("live")
        assert config["waf"]["enabled"] is True

    def test_live_has_higher_nat_gateways(self):
        dev_config = _load_config("dev")
        live_config = _load_config("live")
        assert live_config["vpc"]["nat_gateways"] >= dev_config["vpc"]["nat_gateways"]

    def test_live_has_higher_fargate_min_tasks(self):
        dev_config = _load_config("dev")
        live_config = _load_config("live")
        assert live_config["scaling"]["fargate"]["min_tasks"] > dev_config["scaling"]["fargate"]["min_tasks"]

    def test_live_has_provisioned_concurrency(self):
        config = _load_config("live")
        assert config["scaling"]["lambda"]["provisioned_concurrency"] > 0

    def test_live_has_mifid_tag(self):
        config = _load_config("live")
        assert config["tags"].get("Compliance") == "mifid-ii"


class TestMultiEnvStacks:
    """Verify stacks synthesize correctly for each environment."""

    @pytest.fixture(params=["dev", "paper", "live"])
    def env_name(self, request):
        return request.param

    @pytest.fixture
    def config(self, env_name):
        return _load_config(env_name)

    @pytest.fixture
    def cdk_env(self):
        return cdk.Environment(account="123456789012", region="eu-west-1")

    def test_network_stack_nat_gateways(self, env_name, config, cdk_env):
        app = cdk.App()
        stack = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        template = assertions.Template.from_stack(stack)

        expected_nats = config["vpc"]["nat_gateways"]
        template.resource_count_is("AWS::EC2::NatGateway", expected_nats)

    def test_security_stack_waf_by_env(self, env_name, config, cdk_env):
        app = cdk.App()
        network = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        stack = SecurityStack(
            app, f"TestSec-{env_name}", env=cdk_env, env_name=env_name, config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        expected_waf_count = 1 if config["waf"]["enabled"] else 0
        template.resource_count_is("AWS::WAFv2::WebACL", expected_waf_count)

    def test_risk_engine_stack_synths(self, env_name, config, cdk_env):
        app = cdk.App()
        data = DataStack(app, f"TestData-{env_name}", env=cdk_env, env_name=env_name, config=config)
        network = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        security = SecurityStack(
            app, f"TestSec-{env_name}", env=cdk_env, env_name=env_name, config=config, vpc=network.vpc,
        )
        stack = RiskEngineStack(
            app,
            f"TestRisk-{env_name}",
            env=cdk_env,
            env_name=env_name,
            config=config,
            vpc=network.vpc,
            agent_sg=network.agent_sg,
            data_stack=data,
            security_stack=security,
        )
        template = assertions.Template.from_stack(stack)

        # Risk engine Lambda always exists
        template.resource_count_is("AWS::Lambda::Function", 1)

        # EventBridge rule only for paper/live
        if env_name in ("paper", "live"):
            template.resource_count_is("AWS::Events::Rule", 1)
        else:
            template.resource_count_is("AWS::Events::Rule", 0)

    def test_ibkr_stack_synths(self, env_name, config, cdk_env):
        app = cdk.App()
        network = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        security = SecurityStack(
            app, f"TestSec-{env_name}", env=cdk_env, env_name=env_name, config=config, vpc=network.vpc,
        )
        mcps = McpStack(
            app,
            f"TestMcps-{env_name}",
            env=cdk_env,
            env_name=env_name,
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        stack = IbkrStack(
            app,
            f"TestIbkr-{env_name}",
            env=cdk_env,
            env_name=env_name,
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
            security_stack=security,
            mcp_cluster=mcps.cluster,
            mcp_namespace=mcps.namespace,
        )
        template = assertions.Template.from_stack(stack)

        # IBKR Fargate service + session DynamoDB table
        template.resource_count_is("AWS::ECS::Service", 1)
        template.resource_count_is("AWS::DynamoDB::Table", 1)

    def test_twofa_stack_synths(self, env_name, config, cdk_env):
        app = cdk.App()
        network = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        security = SecurityStack(
            app, f"TestSec-{env_name}", env=cdk_env, env_name=env_name, config=config, vpc=network.vpc,
        )
        mcps = McpStack(
            app,
            f"TestMcps-{env_name}",
            env=cdk_env,
            env_name=env_name,
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        stack = TwoFaStack(
            app,
            f"TestTwoFa-{env_name}",
            env=cdk_env,
            env_name=env_name,
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
            security_stack=security,
            mcp_cluster=mcps.cluster,
            mcp_namespace=mcps.namespace,
        )
        template = assertions.Template.from_stack(stack)

        # 2FA Fargate service + API Gateway
        template.resource_count_is("AWS::ECS::Service", 1)
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)

    def test_risk_engine_env_vars_match_config(self, env_name, config, cdk_env):
        app = cdk.App()
        data = DataStack(app, f"TestData-{env_name}", env=cdk_env, env_name=env_name, config=config)
        network = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        security = SecurityStack(
            app, f"TestSec-{env_name}", env=cdk_env, env_name=env_name, config=config, vpc=network.vpc,
        )
        stack = RiskEngineStack(
            app,
            f"TestRisk-{env_name}",
            env=cdk_env,
            env_name=env_name,
            config=config,
            vpc=network.vpc,
            agent_sg=network.agent_sg,
            data_stack=data,
            security_stack=security,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": {
                    "Variables": assertions.Match.object_like({
                        "ENV_NAME": env_name,
                        "EXECUTION_MODE": config["execution_mode"],
                        "MAX_OPEN_POSITIONS": "5",
                    }),
                },
            },
        )
```

---

## Modifications to Existing P11 Stacks

The following P11 stacks need minor modifications to accept the `config` dict parameter. These are **not** full rewrites — just signature changes.

### Changes to `stacks/network_stack.py`

Add `config: dict` parameter. Use config for NAT gateway count instead of hardcoded conditional:

```python
# In __init__ signature, add:
#   config: dict,

# Replace:
#   nat_gateways=1 if env_name == "dev" else 2,
# With:
#   nat_gateways=config.get("vpc", {}).get("nat_gateways", 1),

# Remove VPC endpoints from network_stack (moved to security_stack via VpcEndpointsConstruct)
# Delete the add_gateway_endpoint and add_interface_endpoint calls.
```

### Changes to `stacks/data_stack.py`

Add `config: dict` parameter. Use config for DynamoDB billing mode:

```python
# In __init__ signature, add:
#   config: dict,

# For live environment with provisioned billing:
# Replace all:
#   billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
# With:
#   billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
#       if config.get("dynamodb", {}).get("billing_mode") == "PAY_PER_REQUEST"
#       else dynamodb.BillingMode.PROVISIONED,

# For S3 buckets in live, add intelligent tiering:
# After bucket creation, if config["s3"]["intelligent_tiering"]:
#   add lifecycle rule for intelligent tiering transition
```

### Changes to `stacks/agent_stack.py`

Add `config: dict` and `security_stack: SecurityStack` parameters:

```python
# In __init__ signature, add:
#   config: dict,
#   security_stack: SecurityStack,

# Use config for Lambda memory_size:
#   memory_size=config.get("lambda_agents", {}).get("memory_size", 1024),

# Grant secrets read to agent role:
#   for secret in security_stack.secrets.values():
#       secret.grant_read(fn.role)

# Add provisioned concurrency for hot agents (gap_detector, portfolio_recommender):
#   provisioned = config.get("scaling", {}).get("lambda", {}).get("provisioned_concurrency", 0)
#   if provisioned > 0 and agent_name in ("research", "portfolio"):
#       LambdaProvisionedConcurrency(self, f"PC-{agent_name}", ...)
```

### Changes to `stacks/mcp_stack.py`

Add `config: dict` parameter. Use config for Fargate sizing and auto-scaling:

```python
# In __init__ signature, add:
#   config: dict,

# Pass config to McpServiceConstruct:
#   cpu=config.get("mcp_services", {}).get("cpu", 256),
#   memory_mib=config.get("mcp_services", {}).get("memory_mib", 512),

# After service creation, add auto-scaling:
#   scaling_config = config.get("scaling", {}).get("fargate", {})
#   if scaling_config.get("max_tasks", 1) > 1:
#       FargateAutoScaling(self, f"Scaling-{mcp_name}", service=mcp.service, ...)

# Expose cluster and namespace for Phase 2 stacks:
#   self.cluster  (already exposed)
#   self.namespace (already exposed)
```

---

## Acceptance Criteria

- [ ] All 3 config YAMLs exist and validate: `dev.yaml`, `paper.yaml`, `live.yaml`
- [ ] `app.py` loads config by CDK context `-c env=dev|paper|live`
- [ ] `cdk synth -c env=dev` succeeds with no WAF, minimal scaling
- [ ] `cdk synth -c env=live` succeeds with WAF, auto-scaling, provisioned concurrency
- [ ] SecurityStack creates 3 KMS CMKs with rotation enabled
- [ ] SecurityStack creates 4 Secrets Manager secrets (ibkr, polygon, telegram, langfuse)
- [ ] WAF WebACL has rate limiting + AWS Managed Rules (paper/live only)
- [ ] VPC Endpoints created: S3, DynamoDB (gateway) + SQS, ECR, CloudWatch, Secrets Manager, KMS, STS, SSM (interface)
- [ ] RiskEngineStack creates Lambda with correct risk limit env vars
- [ ] RiskEngineStack creates EventBridge rule for trailing stop monitoring (paper/live only)
- [ ] TwoFaStack creates Fargate service + API Gateway webhook
- [ ] IbkrStack creates Fargate service + DynamoDB session table
- [ ] Auto-scaling configured on Fargate services when max_tasks > 1
- [ ] Lambda provisioned concurrency configured for hot agents (live only)
- [ ] All SSM Parameters exported for cross-stack references
- [ ] All tests pass: `pytest tests/test_security_stack.py tests/test_multi_env.py -v`

---

## Test Plan

```bash
cd ~/dev/tccw-agent-infra

# Install dependencies
pip install -e ".[dev]"

# Run new tests
pytest tests/test_security_stack.py -v
pytest tests/test_multi_env.py -v

# Run all tests (including P11 tests)
pytest -v

# Synth for each environment
cdk synth -c env=dev 2>&1 | tail -5
cdk synth -c env=paper 2>&1 | tail -5
cdk synth -c env=live 2>&1 | tail -5
```

---

## Key Implementation Notes

1. **Config YAML is the single source of truth for environment differences.** Never use `if env_name == "live"` in stack code when the value can come from config. The config YAML is what changes between environments; the stack code should be environment-agnostic.

2. **VPC Endpoints moved from NetworkStack to SecurityStack.** P11 had VPC endpoints inline in network_stack.py. P17 extracts them into a reusable `VpcEndpointsConstruct` and creates them in SecurityStack (which owns all security/cost optimization concerns). Remove the VPC endpoint code from network_stack.py to avoid duplicates.

3. **Secrets Manager secrets are placeholders.** The `generate_secret_string` creates dummy values. After deployment, the operator must update each secret with real credentials via AWS Console or CLI. Never commit real credentials.

4. **WAF is REGIONAL scope.** API Gateway WebACLs must use REGIONAL scope (not CLOUDFRONT). The WAF construct is configured for this.

5. **Auto-scaling cooldowns.** Scale-out cooldown (2 min) is shorter than scale-in cooldown (5 min) to prevent flapping. This is intentional — we want to scale out fast and scale in slowly.

6. **IBKR MCP health check start period is 90s** (vs 60s for other MCPs) because IBKR Client Portal session initialization takes longer.

7. **EventBridge trailing stop rule is disabled for paper env** by default. Set `enabled=True` manually when testing paper trading to avoid unexpected behavior.

8. **Cross-region Bedrock calls go through NAT Gateway.** VPC endpoints don't support cross-region, so Bedrock Runtime calls from eu-west-1 to us-west-2 traverse the NAT Gateway. This is acceptable for the call frequency and volume involved.

9. **Lambda provisioned concurrency creates an alias.** Step Functions and EventBridge targets must be updated to invoke the alias ARN (not the function ARN) when provisioned concurrency is enabled. The construct returns the alias for this purpose.

10. **DynamoDB provisioned mode for live.** The live config uses PROVISIONED billing with auto-scaling (min 5, max 100, target 70%). This provides more predictable costs at scale. Dev and paper use PAY_PER_REQUEST for simplicity.
