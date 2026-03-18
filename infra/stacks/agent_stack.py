"""Agent stack: Lambda functions for each Strands agent."""
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from constructs import Construct
from constructs_.auto_scaling import LambdaProvisionedConcurrency

from stacks.data_stack import DataStack
from stacks.security_stack import SecurityStack


class AgentStack(Stack):
    """Provisions Lambda functions for all agents."""

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
        self.config = config
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        sd_namespace = config.get("service_discovery_namespace", f"{prefix}.local")
        bedrock_region = config.get("bedrock_region", "us-west-2")

        agent_names = self._resolve_agent_names(config)
        strands_layer = self._create_strands_layer()
        agent_policy = self._create_agent_policy(prefix, env_name, data_stack, ssm_root)

        self.functions: dict[str, lambda_.Function] = {}

        for agent_name in agent_names:
            fn = self._create_agent_function(
                agent_name, prefix, env_name, config, bedrock_region,
                strands_layer, vpc, agent_sg, data_stack, sd_namespace,
            )
            fn.role.add_managed_policy(agent_policy)
            self.functions[agent_name] = fn

            self._grant_secrets_access(fn, security_stack)

            ssm.StringParameter(
                self,
                f"SSM-agent-{agent_name}-arn",
                parameter_name=f"{ssm_root}/agents/{agent_name}/arn",
                string_value=fn.function_arn,
            )

            provisioned = config.get("scaling", {}).get("lambda", {}).get("provisioned_concurrency", 0)
            if provisioned > 0 and agent_name in ("research", "recommender"):
                LambdaProvisionedConcurrency(
                    self, f"PC-{agent_name}", function=fn,
                    provisioned_concurrent_executions=provisioned,
                )

    def _resolve_agent_names(self, config: dict) -> list[str]:
        agent_configs = config.get("agents", [])
        return (
            self.node.try_get_context("agents")
            or [a["name"] for a in agent_configs]
            or ["research", "strategy", "recommender"]
        )

    def _create_strands_layer(self) -> lambda_.ILayerVersion:
        return lambda_.LayerVersion.from_layer_version_arn(
            self, "StrandsLayer",
            layer_version_arn=(
                f"arn:aws:lambda:{self.region}:856699698935"
                f":layer:strands-agents-py312-arm64:1"
            ),
        )

    def _create_agent_policy(
        self, prefix: str, env_name: str, data_stack: DataStack, ssm_root: str,
    ) -> iam.ManagedPolicy:
        return iam.ManagedPolicy(
            self, "AgentPolicy",
            managed_policy_name=f"{prefix}-{env_name}-agent-policy",
            statements=[
                iam.PolicyStatement(
                    sid="BedrockInvoke",
                    actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="DynamoDBAccess",
                    actions=["dynamodb:*"],
                    resources=[t.table_arn for t in data_stack.tables.values()]
                    + [f"{t.table_arn}/index/*" for t in data_stack.tables.values()],
                ),
                iam.PolicyStatement(
                    sid="S3Access",
                    actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                    resources=[b.bucket_arn for b in data_stack.buckets.values()]
                    + [f"{b.bucket_arn}/*" for b in data_stack.buckets.values()],
                ),
                iam.PolicyStatement(
                    sid="SQSAccess",
                    actions=["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
                    resources=[q.queue_arn for q in data_stack.queues.values()],
                ),
                iam.PolicyStatement(
                    sid="XRayTracing",
                    actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="SSMRead",
                    actions=["ssm:GetParameter", "ssm:GetParametersByPath"],
                    resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter{ssm_root}/*"],
                ),
            ],
        )

    def _resolve_table_name(self, data_stack: DataStack, key: str) -> str:
        table = data_stack.tables.get(key)
        if table:
            return table.table_name
        tables = list(data_stack.tables.values())
        return tables[0].table_name if tables else ""

    def _resolve_bucket_name(self, data_stack: DataStack, key: str) -> str:
        bucket = data_stack.buckets.get(key)
        if bucket:
            return bucket.bucket_name
        buckets = list(data_stack.buckets.values())
        return buckets[0].bucket_name if buckets else ""

    def _create_agent_function(
        self, agent_name: str, prefix: str, env_name: str, config: dict,
        bedrock_region: str, strands_layer: lambda_.ILayerVersion,
        vpc: ec2.IVpc, agent_sg: ec2.ISecurityGroup,
        data_stack: DataStack, sd_namespace: str,
    ) -> lambda_.Function:
        log_retention = (
            logs.RetentionDays.TWO_WEEKS if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS
        )
        log_group = logs.LogGroup(
            self, f"LogGroup-{agent_name}",
            log_group_name=f"/aws/lambda/{prefix}-{env_name}-agent-{agent_name}",
            retention=log_retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        return lambda_.Function(
            self, f"AgentFn-{agent_name}",
            function_name=f"{prefix}-{env_name}-agent-{agent_name}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda/agents/example"),
            timeout=Duration.minutes(15),
            memory_size=config.get("lambda_agents", {}).get("memory_size", 1024),
            layers=[strands_layer],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[agent_sg],
            tracing=lambda_.Tracing.ACTIVE,
            log_group=log_group,
            environment={
                "ENV_NAME": env_name,
                "EXECUTION_MODE": config.get("execution_mode", "simulation"),
                "BEDROCK_REGION": bedrock_region,
                "ARTIFACTS_TABLE": self._resolve_table_name(data_stack, "artifacts"),
                "ARTIFACTS_BUCKET": self._resolve_bucket_name(data_stack, "artifacts"),
                "ARTIFACT_QUEUE_URL": data_stack.artifact_queue.queue_url,
                "SERVICE_DISCOVERY_NAMESPACE": sd_namespace,
            },
        )

    @staticmethod
    def _grant_secrets_access(fn: lambda_.Function, security_stack: SecurityStack) -> None:
        fn.role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsRead",
                actions=["secretsmanager:GetSecretValue"],
                resources=[s.secret_arn for s in security_stack.secrets.values()],
            )
        )
        fn.role.add_to_policy(
            iam.PolicyStatement(
                sid="KMSDecryptSecrets",
                actions=["kms:Decrypt"],
                resources=[security_stack.secrets_key.key_arn],
            )
        )
