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


# MCP URI environment variable mapping
# Key: env var name, Value: (mcp_name, default_port)
MCP_ENV_VARS = {
    "MARKET_DATA_MCP_URI": ("market-data", 8080),
    "SENTIMENT_MCP_URI": ("sentiment", 8080),
    "ARTIFACTS_MCP_URI": ("artifacts", 8080),
    "BACKTEST_MCP_URI": ("backtest", 8080),
    "CHARTING_MCP_URI": ("charting", 8080),
    "IBKR_MCP_URI": ("ibkr", 8080),
    "TWO_FA_MCP_URI": ("twofa", 8080),
    "ML_PREDICT_MCP_URI": ("ml-predict", 8080),
    "TECHNICAL_MCP_URI": ("technical", 8080),
}


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
        mcp_endpoints: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.config = config
        self.mcp_endpoints = mcp_endpoints or {}
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        sd_namespace = config.get("service_discovery_namespace", f"{prefix}.local")
        bedrock_region = config.get("bedrock_region", "us-west-2")

        agent_configs = self._resolve_agent_configs(config)
        agent_policy = self._create_agent_policy(prefix, env_name, data_stack, ssm_root)

        self.functions: dict[str, lambda_.Function] = {}

        for agent_cfg in agent_configs:
            agent_name = agent_cfg["name"]
            handler = agent_cfg.get("handler", "handler.lambda_handler")
            memory = agent_cfg.get("memory", config.get("lambda_agents", {}).get("memory_size", 1024))

            fn = self._create_agent_function(
                agent_name, handler, memory, prefix, env_name, config,
                bedrock_region, vpc, agent_sg,
                data_stack, security_stack, sd_namespace,
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
            if provisioned > 0 and agent_name in ("portfolio-recommender",):
                LambdaProvisionedConcurrency(
                    self, f"PC-{agent_name}", function=fn,
                    provisioned_concurrent_executions=provisioned,
                )

        # -- Manifest Lambda -----------------------------------------------

        artifacts_table_name = self._resolve_table_name(data_stack, "artifacts")
        artifacts_bucket_name = self._resolve_bucket_name(data_stack, "artifacts")

        code_path = "lambda/agents/dist"
        import os as _os
        if not _os.path.isdir(_os.path.join(_os.path.dirname(__file__), "..", code_path)):
            code_path = "lambda/agents/example"

        self.manifest_lambda = lambda_.Function(
            self, "StoreManifestFunction",
            function_name=f"{prefix}-{env_name}-store-manifest",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="agent_core.runtime.manifest.handler",
            code=lambda_.Code.from_asset(code_path),
            memory_size=512,
            timeout=Duration.seconds(60),
            environment={
                "ENV_NAME": env_name,
                "ARTIFACTS_BUCKET": artifacts_bucket_name,
                "ARTIFACTS_TABLE": artifacts_table_name,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            tracing=lambda_.Tracing.ACTIVE,
        )

        # Grant manifest Lambda S3 write + DynamoDB write
        artifacts_bucket = data_stack.buckets.get("artifacts")
        if artifacts_bucket:
            artifacts_bucket.grant_write(self.manifest_lambda)
        artifacts_table = data_stack.tables.get("artifacts")
        if artifacts_table:
            artifacts_table.grant_write_data(self.manifest_lambda)

        # -- KMS Grants for agent Lambdas ----------------------------------

        for fn in self.functions.values():
            security_stack.platform_artifacts_key.grant_encrypt_decrypt(fn)
            security_stack.domain_artifacts_key.grant_encrypt_decrypt(fn)

        # Also grant KMS to manifest Lambda
        security_stack.platform_artifacts_key.grant_encrypt_decrypt(self.manifest_lambda)
        security_stack.domain_artifacts_key.grant_encrypt_decrypt(self.manifest_lambda)

    def _resolve_agent_configs(self, config: dict) -> list[dict]:
        agent_configs = config.get("agents", [])
        context_agents = self.node.try_get_context("agents")
        if context_agents:
            return [{"name": n} for n in context_agents]
        if agent_configs:
            return agent_configs
        return [
            {"name": "gap-detector"},
            {"name": "sentiment-analyzer"},
            {"name": "strategy-evaluator"},
        ]


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

    def _build_mcp_env_vars(self, sd_namespace: str) -> dict[str, str]:
        """Build MCP URI environment variables from Cloud Map DNS or passed endpoints."""
        env_vars = {}
        for env_key, (mcp_name, default_port) in MCP_ENV_VARS.items():
            if mcp_name in self.mcp_endpoints:
                env_vars[env_key] = self.mcp_endpoints[mcp_name]
            else:
                env_vars[env_key] = f"http://{mcp_name}.{sd_namespace}:{default_port}"
        return env_vars

    def _create_agent_function(
        self, agent_name: str, handler: str, memory: int,
        prefix: str, env_name: str, config: dict,
        bedrock_region: str,
        vpc: ec2.IVpc, agent_sg: ec2.ISecurityGroup,
        data_stack: DataStack, security_stack: SecurityStack,
        sd_namespace: str,
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

        # Build environment variables
        env = {
            "ENV_NAME": env_name,
            "AGENT_ID": agent_name,
            "EXECUTION_MODE": config.get("execution_mode", "simulation"),
            "BEDROCK_REGION": bedrock_region,
            "BLUEPRINTS_DIR": "blueprints",
            "PROMPTS_DIR": "prompts",
            "ARTIFACTS_TABLE": self._resolve_table_name(data_stack, "artifacts"),
            "ARTIFACTS_BUCKET": self._resolve_bucket_name(data_stack, "artifacts"),
            "ARTIFACT_QUEUE_URL": data_stack.artifact_queue.queue_url,
            "SERVICE_DISCOVERY_NAMESPACE": sd_namespace,
            # P27.1 — Idempotency table for check-before-write pattern
            "IDEMPOTENCY_TABLE": self._resolve_table_name(data_stack, "idempotency"),
            # P27.4 — Missing Lambda env vars
            "AUDIT_TABLE": self._resolve_table_name(data_stack, "audit_log"),
            "RUN_HISTORY_TABLE": self._resolve_table_name(data_stack, "run_history"),
            "PROMPT_REGISTRY_TABLE": self._resolve_table_name(data_stack, "prompt_registry"),
            "PROMPT_REGISTRY_BUCKET": self._resolve_bucket_name(data_stack, "prompt-registry"),
            "HISTORICAL_DATA_BUCKET": self._resolve_bucket_name(data_stack, "historical-data"),
            # P27.2 — KMS key ARN env vars for runtime alias resolution
            "KMS_KEY_ARN_PLATFORM_ARTIFACTS": security_stack.platform_artifacts_key.key_arn,
            "KMS_KEY_ARN_QITP_DOMAIN_ARTIFACTS": security_stack.domain_artifacts_key.key_arn,
        }
        # Add MCP URI env vars
        env.update(self._build_mcp_env_vars(sd_namespace))

        # Use packaged ZIP if dist directory exists, else stub
        code_path = "lambda/agents/dist"
        import os
        if not os.path.isdir(os.path.join(os.path.dirname(__file__), "..", code_path)):
            code_path = "lambda/agents/example"

        return lambda_.Function(
            self, f"AgentFn-{agent_name}",
            function_name=f"{prefix}-{env_name}-agent-{agent_name}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler=handler,
            code=lambda_.Code.from_asset(code_path),
            timeout=Duration.minutes(15),
            memory_size=memory,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[agent_sg],
            tracing=lambda_.Tracing.ACTIVE,
            log_group=log_group,
            environment=env,
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
