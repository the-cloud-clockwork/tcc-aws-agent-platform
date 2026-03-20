"""REST API stack for artifact retrieval.

Provides API Gateway + Lambda endpoints for the dashboard:
  GET /api/artifacts          — List artifacts with filters
  GET /api/artifacts/{id}     — Get artifact metadata + signed URL
  GET /api/runs               — List pipeline runs
  GET /api/runs/{execution_id} — Get manifest for a run
"""
from __future__ import annotations

from aws_cdk import (
    Duration,
    Stack,
)
from aws_cdk import (
    aws_apigateway as apigw,
)
from aws_cdk import (
    aws_ec2 as ec2,
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

from stacks.data_stack import DataStack
from stacks.security_stack import SecurityStack


class ApiStack(Stack):
    """Provisions REST API Gateway + Lambda for artifact/run retrieval."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        vpc: ec2.IVpc,
        data_stack: DataStack,
        security_stack: SecurityStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        api_config = config.get("api", {})

        # Resolve data resources
        artifacts_table = data_stack.tables.get("artifacts")
        artifacts_bucket = data_stack.buckets.get("artifacts")

        artifacts_table_name = artifacts_table.table_name if artifacts_table else ""
        artifacts_bucket_name = artifacts_bucket.bucket_name if artifacts_bucket else ""

        # -- Lambda Handler ------------------------------------------------

        code_path = "lambda/agents/dist"
        import os
        if not os.path.isdir(os.path.join(os.path.dirname(__file__), "..", code_path)):
            code_path = "lambda/agents/example"

        log_group = logs.LogGroup(
            self, "ApiLogGroup",
            log_group_name=f"/aws/lambda/{prefix}-{env_name}-artifacts-api",
            retention=logs.RetentionDays.TWO_WEEKS if env_name == "dev" else logs.RetentionDays.THREE_MONTHS,
            removal_policy=Stack.of(self).removal_policy if hasattr(Stack.of(self), "removal_policy") else None,
        )

        self.api_handler = lambda_.Function(
            self, "ArtifactsApiHandler",
            function_name=f"{prefix}-{env_name}-artifacts-api",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="agent_core.api.artifacts_api.handler",
            code=lambda_.Code.from_asset(code_path),
            memory_size=512,
            timeout=Duration.seconds(30),
            environment={
                "ENV_NAME": env_name,
                "ARTIFACTS_TABLE": artifacts_table_name,
                "ARTIFACTS_BUCKET": artifacts_bucket_name,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            tracing=lambda_.Tracing.ACTIVE,
            log_group=log_group,
        )

        # Grant read access to data resources
        if artifacts_table:
            artifacts_table.grant_read_data(self.api_handler)
        if artifacts_bucket:
            artifacts_bucket.grant_read(self.api_handler)

        # Grant KMS decrypt for reading encrypted artifacts
        security_stack.platform_artifacts_key.grant_decrypt(self.api_handler)
        security_stack.domain_artifacts_key.grant_decrypt(self.api_handler)

        # -- API Gateway ---------------------------------------------------

        cors_origins = api_config.get("cors_origins", ["*"])
        stage = api_config.get("stage", env_name)

        self.api = apigw.RestApi(
            self, "ArtifactsApi",
            rest_api_name=f"{prefix}-{env_name}-artifacts-api",
            description="REST API for artifact and pipeline run retrieval",
            deploy_options=apigw.StageOptions(
                stage_name=stage,
                throttling_rate_limit=api_config.get("throttle_rate", 100),
                throttling_burst_limit=api_config.get("throttle_burst", 200),
                tracing_enabled=True,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=cors_origins,
                allow_methods=["GET", "OPTIONS"],
            ),
        )

        # Lambda proxy integration
        integration = apigw.LambdaIntegration(self.api_handler)

        # /api resource
        api_resource = self.api.root.add_resource("api")

        # /api/artifacts
        artifacts = api_resource.add_resource("artifacts")
        artifacts.add_method("GET", integration, authorization_type=apigw.AuthorizationType.IAM)

        # /api/artifacts/{artifact_id}
        artifact_by_id = artifacts.add_resource("{artifact_id}")
        artifact_by_id.add_method("GET", integration, authorization_type=apigw.AuthorizationType.IAM)

        # /api/artifacts/{artifact_id}/data
        artifact_data = artifact_by_id.add_resource("data")
        artifact_data.add_method("GET", integration, authorization_type=apigw.AuthorizationType.IAM)

        # /api/runs
        runs = api_resource.add_resource("runs")
        runs.add_method("GET", integration, authorization_type=apigw.AuthorizationType.IAM)

        # /api/runs/{execution_id}
        run_by_id = runs.add_resource("{execution_id}")
        run_by_id.add_method("GET", integration, authorization_type=apigw.AuthorizationType.IAM)

        # /api/runs/{execution_id}/{agent}
        run_agent = run_by_id.add_resource("{agent}")
        run_agent.add_method("GET", integration, authorization_type=apigw.AuthorizationType.IAM)

        # -- SSM Parameters ------------------------------------------------

        ssm.StringParameter(
            self, "SSM-api-url",
            parameter_name=f"{ssm_root}/api/artifacts-api-url",
            string_value=self.api.url,
        )
