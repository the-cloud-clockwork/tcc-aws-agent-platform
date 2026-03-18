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
from stacks.security_stack import SecurityStack
from constructs_.auto_scaling import LambdaProvisionedConcurrency


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

        # Build agent name list from config or context
        agent_configs = config.get("agents", [])
        agent_names: list[str] = self.node.try_get_context("agents") or [
            a["name"] for a in agent_configs
        ] or ["research", "strategy", "recommender"]

        # -- Strands SDK Layer ---------------------------------------------

        strands_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "StrandsLayer",
            layer_version_arn=(
                f"arn:aws:lambda:{self.region}:856699698935"
                f":layer:strands-agents-py312-arm64:1"
            ),
        )

        # -- Shared IAM Policy --------------------------------------------

        agent_policy = iam.ManagedPolicy(
            self,
            "AgentPolicy",
            managed_policy_name=f"{prefix}-{env_name}-agent-policy",
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
                        f"arn:aws:ssm:{self.region}:{self.account}:parameter{ssm_root}/*"
                    ],
                ),
            ],
        )

        # -- Lambda Functions ----------------------------------------------

        self.functions: dict[str, lambda_.Function] = {}

        for agent_name in agent_names:
            log_group = logs.LogGroup(
                self,
                f"LogGroup-{agent_name}",
                log_group_name=f"/aws/lambda/{prefix}-{env_name}-agent-{agent_name}",
                retention=logs.RetentionDays.TWO_WEEKS
                if env_name == "dev"
                else logs.RetentionDays.THREE_MONTHS,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )

            fn = lambda_.Function(
                self,
                f"AgentFn-{agent_name}",
                function_name=f"{prefix}-{env_name}-agent-{agent_name}",
                runtime=lambda_.Runtime.PYTHON_3_12,
                architecture=lambda_.Architecture.ARM_64,
                handler="handler.lambda_handler",
                code=lambda_.Code.from_asset("lambda/agents/example"),
                timeout=Duration.minutes(15),
                memory_size=config.get("lambda_agents", {}).get("memory_size", 1024),
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
                    "EXECUTION_MODE": config.get("execution_mode", "simulation"),
                    "BEDROCK_REGION": bedrock_region,
                    "ARTIFACTS_TABLE": data_stack.tables.get("artifacts", data_stack.tables.get(list(data_stack.tables.keys())[0] if data_stack.tables else "artifacts")).table_name if data_stack.tables else "",
                    "ARTIFACTS_BUCKET": data_stack.buckets.get("artifacts", list(data_stack.buckets.values())[0] if data_stack.buckets else None).bucket_name if data_stack.buckets else "",
                    "ARTIFACT_QUEUE_URL": data_stack.artifact_queue.queue_url,
                    "SERVICE_DISCOVERY_NAMESPACE": sd_namespace,
                },
            )

            fn.role.add_managed_policy(agent_policy)
            self.functions[agent_name] = fn

            # Grant secrets read to agent role
            fn.role.add_to_policy(
                iam.PolicyStatement(
                    sid='SecretsRead',
                    actions=['secretsmanager:GetSecretValue'],
                    resources=[s.secret_arn for s in security_stack.secrets.values()],
                )
            )
            fn.role.add_to_policy(
                iam.PolicyStatement(
                    sid='KMSDecryptSecrets',
                    actions=['kms:Decrypt'],
                    resources=[security_stack.secrets_key.key_arn],
                )
            )

            # SSM export for cross-stack reference
            ssm.StringParameter(
                self,
                f"SSM-agent-{agent_name}-arn",
                parameter_name=f"{ssm_root}/agents/{agent_name}/arn",
                string_value=fn.function_arn,
            )

            # Add provisioned concurrency for hot agents (production only)
            provisioned = config.get("scaling", {}).get("lambda", {}).get("provisioned_concurrency", 0)
            if provisioned > 0 and agent_name in ("research", "recommender"):
                LambdaProvisionedConcurrency(
                    self,
                    f"PC-{agent_name}",
                    function=fn,
                    provisioned_concurrent_executions=provisioned,
                )
