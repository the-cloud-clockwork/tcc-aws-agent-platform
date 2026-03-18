# P11 — CDK Infrastructure

## Objective
Build all CDK Python stacks for the QITP platform: data (S3, DynamoDB, SQS), network (VPC, security groups), agents (Lambda functions, Strands SDK layer), MCPs (ECS Fargate services, ECR, Service Discovery), observability (CloudWatch dashboards, X-Ray, alarms). Plus reusable CDK constructs.

## Plane Tickets
ROOT-61

## Target Repo
`~/dev/tccw-agent-infra`

## Dependencies
P05-P08 (MCP Dockerfiles), P10 (agent Lambda packages)

## Repo Structure
```
tccw-agent-infra/
├── app.py                      # CDK app entrypoint
├── cdk.json
├── stacks/
│   ├── __init__.py
│   ├── data_stack.py           # S3 buckets, DynamoDB tables, SQS queues
│   ├── network_stack.py        # VPC, subnets, security groups
│   ├── agent_stack.py          # Lambda functions per agent, Strands Layer, IAM
│   ├── mcp_stack.py            # ECS Fargate per MCP, ECR repos, Service Discovery
│   ├── orchestration_stack.py  # Step Functions, EventBridge (P12 fills this in detail)
│   └── observability_stack.py  # CloudWatch dashboards, X-Ray, log groups, alarms
├── constructs/
│   ├── __init__.py
│   ├── strands_agent.py        # Reusable: Lambda + retry + claim-check for agent tasks
│   ├── mcp_service.py          # Reusable: Fargate service + health check + Service Discovery
│   └── sfn_workflow.py         # Reusable: Blueprint YAML → Step Functions state machine
├── tests/
│   ├── __init__.py
│   └── test_stacks.py          # CDK snapshot tests
└── pyproject.toml
```

---

## Full Inline Code

---

### `pyproject.toml`

```toml
[project]
name = "tccw-agent-infra"
version = "0.1.0"
description = "CDK infrastructure for the QITP platform"
requires-python = ">=3.12"
dependencies = [
    "aws-cdk-lib>=2.170.0,<3.0.0",
    "constructs>=10.0.0,<11.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "syrupy>=4.0",
]

[build-system]
requires = ["setuptools>=75.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

---

### `cdk.json`

```json
{
  "app": "python3 app.py",
  "watch": {
    "include": ["**"],
    "exclude": [
      "README.md",
      "cdk*.json",
      "requirements*.txt",
      "source.bat",
      "**/__pycache__",
      "tests"
    ]
  },
  "context": {
    "env": "dev",
    "account": "835618032093",
    "region": "eu-west-1",
    "bedrock_region": "us-west-2",
    "agents": [
      "research",
      "strategy",
      "risk",
      "execution",
      "portfolio",
      "compliance"
    ],
    "mcps": [
      "artifacts",
      "market-data",
      "broker",
      "notifications"
    ]
  }
}
```

---

### `app.py`

```python
#!/usr/bin/env python3
"""CDK app entrypoint for the QITP platform."""
import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.agent_stack import AgentStack
from stacks.mcp_stack import McpStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.observability_stack import ObservabilityStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"
account = app.node.try_get_context("account") or "835618032093"
region = app.node.try_get_context("region") or "eu-west-1"

cdk_env = cdk.Environment(account=account, region=region)
prefix = f"qitp-{env_name}"

data = DataStack(app, f"{prefix}-data", env=cdk_env, env_name=env_name)
network = NetworkStack(app, f"{prefix}-network", env=cdk_env, env_name=env_name)
agents = AgentStack(
    app,
    f"{prefix}-agents",
    env=cdk_env,
    env_name=env_name,
    vpc=network.vpc,
    agent_sg=network.agent_sg,
    data_stack=data,
)
mcps = McpStack(
    app,
    f"{prefix}-mcps",
    env=cdk_env,
    env_name=env_name,
    vpc=network.vpc,
    mcp_sg=network.mcp_sg,
)
orchestration = OrchestrationStack(
    app,
    f"{prefix}-orchestration",
    env=cdk_env,
    env_name=env_name,
)
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

### `stacks/__init__.py`

```python
```

---

### `stacks/data_stack.py`

```python
"""Data stack: S3 buckets, DynamoDB tables, SQS queues."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_ssm as ssm,
)


class DataStack(Stack):
    """Provisions all data stores for the QITP platform."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        removal = RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN

        # ── DynamoDB Tables ──────────────────────────────────────────

        self.watchlist_table = dynamodb.Table(
            self,
            "WatchlistTable",
            table_name=f"qitp_{env_name}_watchlist",
            partition_key=dynamodb.Attribute(
                name="symbol", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        self.artifacts_table = dynamodb.Table(
            self,
            "ArtifactsTable",
            table_name=f"qitp_{env_name}_artifacts",
            partition_key=dynamodb.Attribute(
                name="artifact_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.artifacts_table.add_global_secondary_index(
            index_name="type-created_at-index",
            partition_key=dynamodb.Attribute(
                name="type", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )
        self.artifacts_table.add_global_secondary_index(
            index_name="agent_id-created_at-index",
            partition_key=dynamodb.Attribute(
                name="agent_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.audit_log_table = dynamodb.Table(
            self,
            "AuditLogTable",
            table_name=f"qitp_{env_name}_audit_log",
            partition_key=dynamodb.Attribute(
                name="audit_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.audit_log_table.add_global_secondary_index(
            index_name="execution_mode-date-index",
            partition_key=dynamodb.Attribute(
                name="execution_mode", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="date", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )
        self.audit_log_table.add_global_secondary_index(
            index_name="symbol-date-index",
            partition_key=dynamodb.Attribute(
                name="symbol", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="date", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.risk_state_table = dynamodb.Table(
            self,
            "RiskStateTable",
            table_name=f"qitp_{env_name}_risk_state",
            partition_key=dynamodb.Attribute(
                name="account_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        self.strategy_registry_table = dynamodb.Table(
            self,
            "StrategyRegistryTable",
            table_name=f"qitp_{env_name}_strategy_registry",
            partition_key=dynamodb.Attribute(
                name="strategy_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="version", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        self.prompt_registry_table = dynamodb.Table(
            self,
            "PromptRegistryTable",
            table_name=f"qitp_{env_name}_prompt_registry",
            partition_key=dynamodb.Attribute(
                name="prompt_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="version", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        self.run_history_table = dynamodb.Table(
            self,
            "RunHistoryTable",
            table_name=f"qitp_{env_name}_run_history",
            partition_key=dynamodb.Attribute(
                name="run_date", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="execution_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        self.tfa_events_table = dynamodb.Table(
            self,
            "TfaEventsTable",
            table_name=f"qitp_{env_name}_2fa_events",
            partition_key=dynamodb.Attribute(
                name="execution_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="event_type", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )

        self.tables = {
            "watchlist": self.watchlist_table,
            "artifacts": self.artifacts_table,
            "audit_log": self.audit_log_table,
            "risk_state": self.risk_state_table,
            "strategy_registry": self.strategy_registry_table,
            "prompt_registry": self.prompt_registry_table,
            "run_history": self.run_history_table,
            "2fa_events": self.tfa_events_table,
        }

        # ── S3 Buckets ──────────────────────────────────────────────

        bucket_names = [
            "artifacts",
            "historical-data",
            "prompt-registry",
            "strategy-blueprints",
        ]
        self.buckets: dict[str, s3.Bucket] = {}
        for name in bucket_names:
            bucket = s3.Bucket(
                self,
                f"Bucket-{name}",
                bucket_name=f"qitp-{env_name}-{name}-{self.account}",
                versioned=True,
                encryption=s3.BucketEncryption.S3_MANAGED,
                removal_policy=removal,
                auto_delete_objects=(env_name == "dev"),
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
            )
            self.buckets[name] = bucket

        # ── SQS Queues ──────────────────────────────────────────────

        self.artifact_dlq = sqs.Queue(
            self,
            "ArtifactDLQ",
            queue_name=f"qitp-{env_name}-artifact-notifications-dlq",
            retention_period=Duration.days(14),
        )
        self.artifact_queue = sqs.Queue(
            self,
            "ArtifactQueue",
            queue_name=f"qitp-{env_name}-artifact-notifications",
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, queue=self.artifact_dlq
            ),
        )

        self.approval_dlq = sqs.Queue(
            self,
            "ApprovalDLQ",
            queue_name=f"qitp-{env_name}-2fa-approval-dlq",
            retention_period=Duration.days(14),
        )
        self.approval_queue = sqs.Queue(
            self,
            "ApprovalQueue",
            queue_name=f"qitp-{env_name}-2fa-approval-queue",
            visibility_timeout=Duration.seconds(900),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, queue=self.approval_dlq
            ),
        )

        self.queues = {
            "artifact-notifications": self.artifact_queue,
            "2fa-approval": self.approval_queue,
        }

        # ── SSM Parameters (for cross-stack references) ──────────────

        for table_key, table in self.tables.items():
            ssm.StringParameter(
                self,
                f"SSM-table-{table_key}",
                parameter_name=f"/qitp/{env_name}/tables/{table_key}/name",
                string_value=table.table_name,
            )
            ssm.StringParameter(
                self,
                f"SSM-table-{table_key}-arn",
                parameter_name=f"/qitp/{env_name}/tables/{table_key}/arn",
                string_value=table.table_arn,
            )

        for bucket_key, bucket in self.buckets.items():
            ssm.StringParameter(
                self,
                f"SSM-bucket-{bucket_key}",
                parameter_name=f"/qitp/{env_name}/buckets/{bucket_key}/name",
                string_value=bucket.bucket_name,
            )

        for queue_key, queue in self.queues.items():
            ssm.StringParameter(
                self,
                f"SSM-queue-{queue_key}",
                parameter_name=f"/qitp/{env_name}/queues/{queue_key}/url",
                string_value=queue.queue_url,
            )
```

---

### `stacks/network_stack.py`

```python
"""Network stack: VPC, subnets, security groups."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ssm as ssm,
)


class NetworkStack(Stack):
    """Provisions VPC and security groups for the QITP platform."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # ── VPC ──────────────────────────────────────────────────────

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=f"qitp-{env_name}-vpc",
            max_azs=2,
            nat_gateways=1 if env_name == "dev" else 2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ── VPC Endpoints (reduce NAT costs) ────────────────────────

        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )
        self.vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
        )
        self.vpc.add_interface_endpoint(
            "SQSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SQS,
        )
        self.vpc.add_interface_endpoint(
            "ECREndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
        )
        self.vpc.add_interface_endpoint(
            "ECRDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
        )
        self.vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        )

        # ── Security Groups ─────────────────────────────────────────

        self.agent_sg = ec2.SecurityGroup(
            self,
            "AgentSG",
            vpc=self.vpc,
            security_group_name=f"qitp-{env_name}-agent-sg",
            description="Security group for agent Lambda functions",
            allow_all_outbound=True,
        )

        self.mcp_sg = ec2.SecurityGroup(
            self,
            "McpSG",
            vpc=self.vpc,
            security_group_name=f"qitp-{env_name}-mcp-sg",
            description="Security group for MCP Fargate services",
            allow_all_outbound=True,
        )

        # Allow agents to reach MCPs on port 8000
        self.mcp_sg.add_ingress_rule(
            peer=self.agent_sg,
            connection=ec2.Port.tcp(8000),
            description="Allow agent Lambdas to call MCP services",
        )

        # ── SSM Parameters ──────────────────────────────────────────

        ssm.StringParameter(
            self,
            "SSM-vpc-id",
            parameter_name=f"/qitp/{env_name}/network/vpc-id",
            string_value=self.vpc.vpc_id,
        )
```

---

### `stacks/agent_stack.py`

```python
"""Agent stack: Lambda functions for each Strands agent."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_logs as logs,
)

from stacks.data_stack import DataStack


class AgentStack(Stack):
    """Provisions Lambda functions for all QITP agents."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        vpc: ec2.IVpc,
        agent_sg: ec2.ISecurityGroup,
        data_stack: DataStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        bedrock_region = self.node.try_get_context("bedrock_region") or "us-west-2"
        agent_names: list[str] = self.node.try_get_context("agents") or [
            "research",
            "strategy",
            "risk",
            "execution",
            "portfolio",
            "compliance",
        ]

        # ── Strands SDK Layer ────────────────────────────────────────

        strands_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "StrandsLayer",
            layer_version_arn=(
                f"arn:aws:lambda:{self.region}:856699698935"
                f":layer:strands-agents-py312-arm64:1"
            ),
        )

        # ── Shared IAM Policy ───────────────────────────────────────

        agent_policy = iam.ManagedPolicy(
            self,
            "AgentPolicy",
            managed_policy_name=f"qitp-{env_name}-agent-policy",
            statements=[
                iam.PolicyStatement(
                    sid="BedrockInvoke",
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="DynamoDBAccess",
                    actions=["dynamodb:*"],
                    resources=[
                        table.table_arn
                        for table in data_stack.tables.values()
                    ]
                    + [
                        f"{table.table_arn}/index/*"
                        for table in data_stack.tables.values()
                    ],
                ),
                iam.PolicyStatement(
                    sid="S3Access",
                    actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                    resources=[
                        bucket.bucket_arn
                        for bucket in data_stack.buckets.values()
                    ]
                    + [
                        f"{bucket.bucket_arn}/*"
                        for bucket in data_stack.buckets.values()
                    ],
                ),
                iam.PolicyStatement(
                    sid="SQSAccess",
                    actions=[
                        "sqs:SendMessage",
                        "sqs:ReceiveMessage",
                        "sqs:DeleteMessage",
                        "sqs:GetQueueAttributes",
                    ],
                    resources=[
                        queue.queue_arn
                        for queue in data_stack.queues.values()
                    ],
                ),
                iam.PolicyStatement(
                    sid="XRayTracing",
                    actions=[
                        "xray:PutTraceSegments",
                        "xray:PutTelemetryRecords",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="SSMRead",
                    actions=["ssm:GetParameter", "ssm:GetParametersByPath"],
                    resources=[
                        f"arn:aws:ssm:{self.region}:{self.account}:parameter/qitp/{env_name}/*"
                    ],
                ),
            ],
        )

        # ── Lambda Functions ─────────────────────────────────────────

        self.functions: dict[str, lambda_.Function] = {}

        for agent_name in agent_names:
            log_group = logs.LogGroup(
                self,
                f"LogGroup-{agent_name}",
                log_group_name=f"/aws/lambda/qitp-{env_name}-agent-{agent_name}",
                retention=logs.RetentionDays.TWO_WEEKS
                if env_name == "dev"
                else logs.RetentionDays.THREE_MONTHS,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )

            fn = lambda_.Function(
                self,
                f"AgentFn-{agent_name}",
                function_name=f"qitp-{env_name}-agent-{agent_name}",
                runtime=lambda_.Runtime.PYTHON_3_12,
                architecture=lambda_.Architecture.ARM_64,
                handler="handler.lambda_handler",
                code=lambda_.Code.from_asset(f"lambda/agents/{agent_name}"),
                timeout=Duration.minutes(15),
                memory_size=1024,
                layers=[strands_layer],
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                ),
                security_groups=[agent_sg],
                tracing=lambda_.Tracing.ACTIVE,
                log_group=log_group,
                environment={
                    "ENV_NAME": env_name,
                    "EXECUTION_MODE": "paper" if env_name != "live" else "live",
                    "PROMPT_REGISTRY_URL": (
                        f"s3://qitp-{env_name}-prompt-registry-{self.account}"
                    ),
                    "BEDROCK_REGION": bedrock_region,
                    "ARTIFACTS_TABLE": data_stack.artifacts_table.table_name,
                    "AUDIT_LOG_TABLE": data_stack.audit_log_table.table_name,
                    "ARTIFACTS_BUCKET": data_stack.buckets["artifacts"].bucket_name,
                    "ARTIFACT_QUEUE_URL": data_stack.artifact_queue.queue_url,
                    "SERVICE_DISCOVERY_NAMESPACE": "qitp.local",
                },
            )

            fn.role.add_managed_policy(agent_policy)
            self.functions[agent_name] = fn

            # SSM export for cross-stack reference
            ssm.StringParameter(
                self,
                f"SSM-agent-{agent_name}-arn",
                parameter_name=f"/qitp/{env_name}/agents/{agent_name}/arn",
                string_value=fn.function_arn,
            )
```

---

### `stacks/mcp_stack.py`

```python
"""MCP stack: ECS Fargate services, ECR repos, Service Discovery."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_logs as logs,
    aws_servicediscovery as sd,
    aws_ssm as ssm,
)

from constructs_.mcp_service import McpServiceConstruct


class McpStack(Stack):
    """Provisions ECS Fargate services for all QITP MCPs."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        vpc: ec2.IVpc,
        mcp_sg: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        mcp_names: list[str] = self.node.try_get_context("mcps") or [
            "artifacts",
            "market-data",
            "broker",
            "notifications",
        ]

        # ── ECS Cluster ──────────────────────────────────────────────

        self.cluster = ecs.Cluster(
            self,
            "McpCluster",
            cluster_name=f"qitp-{env_name}-mcp-cluster",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        # ── Cloud Map Namespace ──────────────────────────────────────

        self.namespace = self.cluster.add_default_cloud_map_namespace(
            name="qitp.local",
            type=sd.NamespaceType.DNS_PRIVATE,
            vpc=vpc,
        )

        # ── MCP Services ─────────────────────────────────────────────

        self.services: dict[str, ecs.FargateService] = {}

        for mcp_name in mcp_names:
            mcp = McpServiceConstruct(
                self,
                f"Mcp-{mcp_name}",
                env_name=env_name,
                mcp_name=mcp_name,
                cluster=self.cluster,
                namespace=self.namespace,
                vpc=vpc,
                security_group=mcp_sg,
            )
            self.services[mcp_name] = mcp.service

            ssm.StringParameter(
                self,
                f"SSM-mcp-{mcp_name}-endpoint",
                parameter_name=f"/qitp/{env_name}/mcps/{mcp_name}/endpoint",
                string_value=f"{mcp_name}.qitp.local",
            )
```

---

### `stacks/orchestration_stack.py`

```python
"""Orchestration stack: Step Functions and EventBridge (placeholder for P12)."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ssm as ssm,
)


class OrchestrationStack(Stack):
    """Placeholder for Step Functions workflows — filled by P12.

    This stack exists so the CDK app can synth without errors.
    P12 will add Step Functions state machines, EventBridge rules,
    and use the StrandsAgentTask and SfnWorkflow constructs.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        ssm.StringParameter(
            self,
            "SSM-orchestration-status",
            parameter_name=f"/qitp/{env_name}/orchestration/status",
            string_value="placeholder",
        )
```

---

### `stacks/observability_stack.py`

```python
"""Observability stack: CloudWatch dashboards, X-Ray, alarms."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_cloudwatch as cw,
    aws_lambda as lambda_,
    aws_ecs as ecs,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_cloudwatch_actions as cw_actions,
)


class ObservabilityStack(Stack):
    """CloudWatch dashboards, alarms, and X-Ray configuration."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        agent_functions: dict[str, lambda_.Function],
        mcp_services: dict[str, ecs.FargateService],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # ── SNS Topic for Alarms ─────────────────────────────────────

        self.alarm_topic = sns.Topic(
            self,
            "AlarmTopic",
            topic_name=f"qitp-{env_name}-alarms",
            display_name=f"QITP {env_name} Alarms",
        )

        # ── Agent Lambda Alarms ──────────────────────────────────────

        agent_widgets: list[cw.IWidget] = []

        for name, fn in agent_functions.items():
            error_alarm = cw.Alarm(
                self,
                f"ErrorAlarm-{name}",
                alarm_name=f"qitp-{env_name}-agent-{name}-errors",
                metric=fn.metric_errors(period=Duration.minutes(5)),
                threshold=3,
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            error_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

            duration_alarm = cw.Alarm(
                self,
                f"DurationAlarm-{name}",
                alarm_name=f"qitp-{env_name}-agent-{name}-duration",
                metric=fn.metric_duration(
                    period=Duration.minutes(5),
                    statistic="p99",
                ),
                threshold=600_000,  # 10 minutes in ms
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            duration_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

            agent_widgets.append(
                cw.GraphWidget(
                    title=f"Agent: {name}",
                    left=[
                        fn.metric_invocations(period=Duration.minutes(5)),
                        fn.metric_errors(period=Duration.minutes(5)),
                    ],
                    right=[
                        fn.metric_duration(period=Duration.minutes(5)),
                    ],
                    width=12,
                )
            )

        # ── MCP Service Alarms ───────────────────────────────────────

        mcp_widgets: list[cw.IWidget] = []

        for name, service in mcp_services.items():
            cpu_alarm = cw.Alarm(
                self,
                f"CpuAlarm-{name}",
                alarm_name=f"qitp-{env_name}-mcp-{name}-cpu",
                metric=service.metric_cpu_utilization(
                    period=Duration.minutes(5),
                ),
                threshold=80,
                evaluation_periods=3,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

            mcp_widgets.append(
                cw.GraphWidget(
                    title=f"MCP: {name}",
                    left=[
                        service.metric_cpu_utilization(
                            period=Duration.minutes(5)
                        ),
                    ],
                    right=[
                        service.metric_memory_utilization(
                            period=Duration.minutes(5)
                        ),
                    ],
                    width=12,
                )
            )

        # ── Dashboard ────────────────────────────────────────────────

        self.dashboard = cw.Dashboard(
            self,
            "Dashboard",
            dashboard_name=f"qitp-{env_name}-overview",
            widgets=[
                [
                    cw.TextWidget(
                        markdown=f"# QITP Platform — {env_name.upper()}",
                        width=24,
                        height=1,
                    )
                ],
                [
                    cw.TextWidget(
                        markdown="## Agent Lambda Functions",
                        width=24,
                        height=1,
                    )
                ],
                agent_widgets,
                [
                    cw.TextWidget(
                        markdown="## MCP Fargate Services",
                        width=24,
                        height=1,
                    )
                ],
                mcp_widgets,
            ],
        )
```

---

### `constructs/__init__.py`

Note: The package is named `constructs_` (with underscore) to avoid colliding with the `constructs` PyPI package.

```python
```

**Important**: Because the PyPI package `constructs` occupies the `constructs` namespace, the local directory must be named `constructs_` to avoid import conflicts. All imports referencing local constructs use `constructs_`.

---

### `constructs/strands_agent.py`

```python
"""StrandsAgentTask — reusable CDK construct for Step Functions agent invocation."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
)


class StrandsAgentTask(Construct):
    """Wraps a Lambda invocation for use in Step Functions.

    Features:
    - LambdaInvoke with exponential backoff + full jitter retry
    - Claim-check pattern: large output → S3, only S3 key in state
    - X-Ray tracing enabled on the underlying function
    - result_selector extracts artifact_id, success, s3_key
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        agent_function: lambda_.IFunction,
        agent_name: str,
        output_bucket_name: str,
        env_name: str,
    ) -> None:
        super().__init__(scope, construct_id)

        self.agent_name = agent_name

        # The Lambda task for Step Functions
        self.task = sfn_tasks.LambdaInvoke(
            self,
            f"Invoke-{agent_name}",
            lambda_function=agent_function,
            payload=sfn.TaskInput.from_json_path_at("$"),
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "success.$": "$.Payload.success",
                "s3_key.$": "$.Payload.s3_key",
                "agent": agent_name,
            },
            result_path=f"$.results.{agent_name}",
            retry_on_service_exceptions=True,
            comment=f"Invoke {agent_name} agent with claim-check pattern",
        )

        # Add retry with exponential backoff + full jitter
        self.task.add_retry(
            errors=["States.TaskFailed", "Lambda.ServiceException"],
            interval=Duration.seconds(2),
            max_attempts=3,
            backoff_rate=2.0,
            jitter_strategy=sfn.JitterType.FULL,
        )

        # Add catch for unrecoverable failures
        self.fail_state = sfn.Fail(
            self,
            f"Fail-{agent_name}",
            cause=f"Agent {agent_name} failed after retries",
            error="AgentExecutionFailed",
        )
        self.task.add_catch(
            handler=self.fail_state,
            errors=["States.ALL"],
            result_path=f"$.errors.{agent_name}",
        )
```

---

### `constructs/mcp_service.py`

```python
"""McpServiceConstruct — reusable CDK construct for Fargate MCP services."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_logs as logs,
    aws_servicediscovery as sd,
)


class McpServiceConstruct(Construct):
    """Provisions an ECR repo and ECS Fargate service for one MCP.

    Features:
    - ECR image from repo
    - ECS task definition with health check
    - Service Discovery A record
    - CloudWatch log group
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        mcp_name: str,
        cluster: ecs.ICluster,
        namespace: sd.INamespace,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
    ) -> None:
        super().__init__(scope, construct_id)

        self.mcp_name = mcp_name
        removal = RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN

        # ── ECR Repository ───────────────────────────────────────────

        self.repository = ecr.Repository(
            self,
            "Repo",
            repository_name=f"qitp-{env_name}-mcp-{mcp_name}",
            removal_policy=removal,
            empty_on_delete=(env_name == "dev"),
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    max_image_count=10,
                    description="Keep last 10 images",
                )
            ],
        )

        # ── Log Group ────────────────────────────────────────────────

        self.log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=f"/ecs/qitp-{env_name}-mcp-{mcp_name}",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Task Definition ──────────────────────────────────────────

        self.task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            family=f"qitp-{env_name}-mcp-{mcp_name}",
            cpu=256,
            memory_limit_mib=512,
        )

        self.container = self.task_definition.add_container(
            "Container",
            container_name=mcp_name,
            image=ecs.ContainerImage.from_ecr_repository(
                self.repository, tag="latest"
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=mcp_name,
                log_group=self.log_group,
            ),
            environment={
                "ENV_NAME": env_name,
                "MCP_NAME": mcp_name,
                "PORT": "8000",
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        self.container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
        )

        # ── Fargate Service ──────────────────────────────────────────

        desired_count = 1 if env_name == "dev" else 2

        self.service = ecs.FargateService(
            self,
            "Service",
            service_name=f"qitp-{env_name}-mcp-{mcp_name}",
            cluster=cluster,
            task_definition=self.task_definition,
            desired_count=desired_count,
            security_groups=[security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            assign_public_ip=False,
            cloud_map_options=ecs.CloudMapOptions(
                name=mcp_name,
                cloud_map_namespace=namespace,
                dns_record_type=sd.DnsRecordType.A,
                dns_ttl=Duration.seconds(30),
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=True,
            ),
            enable_execute_command=True,
        )
```

---

### `constructs/sfn_workflow.py`

```python
"""SfnWorkflow — reusable CDK construct: Blueprint YAML to Step Functions state machine."""
from __future__ import annotations

import yaml
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    aws_stepfunctions as sfn,
    aws_lambda as lambda_,
    aws_logs as logs,
)

from constructs_.strands_agent import StrandsAgentTask


class SfnWorkflow(Construct):
    """Generates a Step Functions state machine from a YAML blueprint.

    The YAML format:
    ```yaml
    name: my-workflow
    steps:
      - agent: research
        next: strategy
      - agent: strategy
        next: risk
      - parallel:
          - agent: execution
          - agent: compliance
        next: portfolio
      - agent: portfolio
    ```

    Each step becomes a StrandsAgentTask. Parallel blocks become
    sfn.Parallel states.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        blueprint_yaml: str,
        agent_functions: dict[str, lambda_.IFunction],
        output_bucket_name: str,
        env_name: str,
    ) -> None:
        super().__init__(scope, construct_id)

        blueprint = yaml.safe_load(blueprint_yaml)
        workflow_name = blueprint["name"]
        steps = blueprint["steps"]

        # Build chain of states
        chain_steps: list[sfn.IChainable] = []

        for step_def in steps:
            if "agent" in step_def:
                agent_name = step_def["agent"]
                task = StrandsAgentTask(
                    self,
                    f"Task-{agent_name}",
                    agent_function=agent_functions[agent_name],
                    agent_name=agent_name,
                    output_bucket_name=output_bucket_name,
                    env_name=env_name,
                )
                chain_steps.append(task.task)

            elif "parallel" in step_def:
                branches = []
                for branch_def in step_def["parallel"]:
                    agent_name = branch_def["agent"]
                    task = StrandsAgentTask(
                        self,
                        f"Task-{agent_name}",
                        agent_function=agent_functions[agent_name],
                        agent_name=agent_name,
                        output_bucket_name=output_bucket_name,
                        env_name=env_name,
                    )
                    branches.append(task.task)

                parallel = sfn.Parallel(
                    self,
                    f"Parallel-{'-'.join(b['agent'] for b in step_def['parallel'])}",
                )
                for branch in branches:
                    parallel.branch(branch)
                chain_steps.append(parallel)

        # Chain all steps together
        definition = chain_steps[0]
        for step in chain_steps[1:]:
            definition = definition.next(step)

        # Log group for state machine
        log_group = logs.LogGroup(
            self,
            "SfnLogGroup",
            log_group_name=f"/aws/stepfunctions/qitp-{env_name}-{workflow_name}",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.state_machine = sfn.StateMachine(
            self,
            "StateMachine",
            state_machine_name=f"qitp-{env_name}-{workflow_name}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(1),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
        )
```

---

### `tests/__init__.py`

```python
```

---

### `tests/test_stacks.py`

```python
"""CDK snapshot tests for all QITP stacks."""
import json
import pytest
import aws_cdk as cdk
from aws_cdk import assertions

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.agent_stack import AgentStack
from stacks.mcp_stack import McpStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.observability_stack import ObservabilityStack


@pytest.fixture
def app():
    app = cdk.App(
        context={
            "env": "dev",
            "account": "835618032093",
            "region": "eu-west-1",
            "bedrock_region": "us-west-2",
            "agents": ["research", "strategy", "risk"],
            "mcps": ["artifacts", "market-data"],
        }
    )
    return app


@pytest.fixture
def env():
    return cdk.Environment(account="835618032093", region="eu-west-1")


class TestDataStack:
    def test_creates_dynamodb_tables(self, app, env):
        stack = DataStack(app, "TestData", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)

        # Should have 8 DynamoDB tables
        template.resource_count_is("AWS::DynamoDB::Table", 8)

    def test_creates_s3_buckets(self, app, env):
        stack = DataStack(app, "TestData", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)

        # Should have 4 S3 buckets
        template.resource_count_is("AWS::S3::Bucket", 4)

    def test_creates_sqs_queues(self, app, env):
        stack = DataStack(app, "TestData", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)

        # 2 main queues + 2 DLQs = 4
        template.resource_count_is("AWS::SQS::Queue", 4)

    def test_artifacts_table_has_gsis(self, app, env):
        stack = DataStack(app, "TestData", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "qitp_dev_artifacts",
                "GlobalSecondaryIndexes": assertions.Match.any_value(),
            },
        )

    def test_snapshot(self, app, env, snapshot):
        stack = DataStack(app, "TestData", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)
        assert template.to_json() == snapshot


class TestNetworkStack:
    def test_creates_vpc(self, app, env):
        stack = NetworkStack(app, "TestNetwork", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_creates_security_groups(self, app, env):
        stack = NetworkStack(app, "TestNetwork", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)

        # Agent SG + MCP SG (VPC endpoints also create SGs)
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {"GroupDescription": "Security group for agent Lambda functions"},
        )
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {"GroupDescription": "Security group for MCP Fargate services"},
        )

    def test_snapshot(self, app, env, snapshot):
        stack = NetworkStack(app, "TestNetwork", env=env, env_name="dev")
        template = assertions.Template.from_stack(stack)
        assert template.to_json() == snapshot


class TestAgentStack:
    def test_creates_lambda_functions(self, app, env):
        data = DataStack(app, "TestData2", env=env, env_name="dev")
        network = NetworkStack(app, "TestNetwork2", env=env, env_name="dev")
        stack = AgentStack(
            app,
            "TestAgents",
            env=env,
            env_name="dev",
            vpc=network.vpc,
            agent_sg=network.agent_sg,
            data_stack=data,
        )
        template = assertions.Template.from_stack(stack)

        # 3 agents in test context
        template.resource_count_is("AWS::Lambda::Function", 3)

    def test_lambda_runtime_and_arch(self, app, env):
        data = DataStack(app, "TestData3", env=env, env_name="dev")
        network = NetworkStack(app, "TestNetwork3", env=env, env_name="dev")
        stack = AgentStack(
            app,
            "TestAgents2",
            env=env,
            env_name="dev",
            vpc=network.vpc,
            agent_sg=network.agent_sg,
            data_stack=data,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Runtime": "python3.12",
                "Architectures": ["arm64"],
                "Timeout": 900,
                "MemorySize": 1024,
            },
        )


class TestMcpStack:
    def test_creates_fargate_services(self, app, env):
        network = NetworkStack(app, "TestNetwork4", env=env, env_name="dev")
        stack = McpStack(
            app,
            "TestMcps",
            env=env,
            env_name="dev",
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        template = assertions.Template.from_stack(stack)

        # 2 MCPs in test context
        template.resource_count_is("AWS::ECS::Service", 2)

    def test_creates_ecr_repositories(self, app, env):
        network = NetworkStack(app, "TestNetwork5", env=env, env_name="dev")
        stack = McpStack(
            app,
            "TestMcps2",
            env=env,
            env_name="dev",
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::ECR::Repository", 2)

    def test_service_discovery(self, app, env):
        network = NetworkStack(app, "TestNetwork6", env=env, env_name="dev")
        stack = McpStack(
            app,
            "TestMcps3",
            env=env,
            env_name="dev",
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ServiceDiscovery::PrivateDnsNamespace",
            {"Name": "qitp.local"},
        )


class TestOrchestrationStack:
    def test_creates_ssm_parameter(self, app, env):
        stack = OrchestrationStack(
            app, "TestOrch", env=env, env_name="dev"
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Type": "String",
                "Value": "placeholder",
            },
        )
```

---

## Acceptance Criteria
- [ ] `cdk synth` succeeds for all stacks
- [ ] All 8 DynamoDB tables created with correct schemas
- [ ] All 4 S3 buckets created (artifacts, historical-data, prompt-registry, strategy-blueprints)
- [ ] 2 SQS queues with DLQs created
- [ ] Lambda functions created per agent with correct runtime (Python 3.12, ARM64) and layers
- [ ] ECS Fargate services created per MCP with Service Discovery
- [ ] StrandsAgentTask construct generates correct Step Functions task with retry and claim-check
- [ ] McpServiceConstruct generates Fargate service with health check and Cloud Map registration
- [ ] SfnWorkflow construct parses YAML blueprints into Step Functions state machines
- [ ] Cross-stack references via SSM Parameter Store
- [ ] Snapshot tests pass

## Test Plan
```bash
cd ~/dev/tccw-agent-infra
pip install -e ".[dev]"
cdk synth
pytest -v  # snapshot tests
```

## Key Implementation Notes

1. **Import path for local constructs**: The local constructs directory is `constructs_/` (with trailing underscore) to avoid collision with the `constructs` PyPI package. Imports look like `from constructs_.mcp_service import McpServiceConstruct`.

2. **Lambda code asset paths**: `agent_stack.py` references `lambda/agents/{agent_name}` — these directories must exist (even as stubs with a `handler.py`) for `cdk synth` to succeed. P10 delivers the actual agent packages there.

3. **ECR image tags**: MCP services reference `tag="latest"` from ECR. The CI/CD pipeline (P05-P08) pushes Docker images. For initial `cdk synth`, ECR repos are empty — the service will fail to start until images are pushed.

4. **Environment strategy**: CDK context `env` drives naming (`qitp-dev-*`, `qitp-paper-*`, `qitp-live-*`), removal policies, replica counts, and log retention.

5. **Cross-stack references**: All stacks export key resource identifiers to SSM Parameter Store under `/qitp/{env}/...` so that any stack can read them without hard dependencies.

## Agent Instructions
Use aws-cdk-lib v2. All constructs in Python. Use CDK context for environment switching. Cross-stack references via SSM Parameter Store or CfnOutput. Keep stacks independent — data_stack has no dependency on agent_stack. The constructs/ directory (actually `constructs_/`) contains reusable patterns that orchestration_stack (P12) will use.
