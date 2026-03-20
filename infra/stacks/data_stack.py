"""Data stack: S3 buckets, DynamoDB tables, SQS queues, scheduled sync Lambdas."""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as events_targets,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from aws_cdk import (
    aws_cloudfront as cloudfront,
)
from aws_cdk import (
    aws_cloudfront_origins as origins,
)
from aws_cdk import (
    aws_iam as iam,
)
from constructs import Construct


class DataStack(Stack):
    """Provisions all data stores for the agent platform."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict | None = None,
        security_stack=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        config = config or {}
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        s3_config = config.get("s3", {})
        removal_str = s3_config.get("removal_policy", "DESTROY" if env_name == "dev" else "RETAIN")
        removal = RemovalPolicy.DESTROY if removal_str == "DESTROY" else RemovalPolicy.RETAIN

        # -- DynamoDB Tables (config-driven) --------------------------------

        table_configs = config.get("tables", {})
        self.tables: dict[str, dynamodb.Table] = {}

        for table_key, table_def in table_configs.items():
            pk_name = table_def.get("partition_key", "id")
            sk_name = table_def.get("sort_key")

            kwargs_table: dict = {
                "partition_key": dynamodb.Attribute(
                    name=pk_name, type=dynamodb.AttributeType.STRING
                ),
                "billing_mode": dynamodb.BillingMode.PAY_PER_REQUEST,
                "removal_policy": removal,
                "point_in_time_recovery": True,
            }
            if sk_name:
                kwargs_table["sort_key"] = dynamodb.Attribute(
                    name=sk_name, type=dynamodb.AttributeType.STRING
                )

            table = dynamodb.Table(
                self,
                f"Table-{table_key}",
                table_name=f"{prefix}_{env_name}_{table_key}",
                **kwargs_table,
            )

            # Enable TTL if configured
            ttl_attr = table_def.get("ttl_attribute")
            if ttl_attr:
                table.node.default_child.add_property_override(
                    "TimeToLiveSpecification",
                    {"AttributeName": ttl_attr, "Enabled": True},
                )

            self.tables[table_key] = table

        # -- S3 Buckets (config-driven) ------------------------------------

        bucket_names = config.get("buckets", ["artifacts"])
        self.buckets: dict[str, s3.Bucket] = {}
        for name in bucket_names:
            bucket = s3.Bucket(
                self,
                f"Bucket-{name}",
                bucket_name=f"{prefix}-{env_name}-{name}-{self.account}",
                versioned=True,
                encryption=s3.BucketEncryption.S3_MANAGED,
                removal_policy=removal,
                auto_delete_objects=(env_name == "dev"),
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
            )
            self.buckets[name] = bucket

        # -- S3 Bucket Policy (KMS enforcement by prefix) -----------------

        artifacts_bucket = self.buckets.get("artifacts")
        if artifacts_bucket and security_stack is not None:
            platform_key_arn = security_stack.platform_artifacts_key.key_arn
            domain_key_arn = security_stack.domain_artifacts_key.key_arn

            # Deny PutObject to platform/ without platform KMS key
            artifacts_bucket.add_to_resource_policy(iam.PolicyStatement(
                sid="DenyPlatformWithoutPlatformKey",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:PutObject"],
                resources=[f"{artifacts_bucket.bucket_arn}/platform/*"],
                conditions={
                    "StringNotEquals": {
                        "s3:x-amz-server-side-encryption-aws-kms-key-id": platform_key_arn,
                    },
                },
            ))

            # Deny PutObject to domain/ without domain KMS key
            artifacts_bucket.add_to_resource_policy(iam.PolicyStatement(
                sid="DenyDomainWithoutDomainKey",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:PutObject"],
                resources=[f"{artifacts_bucket.bucket_arn}/domain/*"],
                conditions={
                    "StringNotEquals": {
                        "s3:x-amz-server-side-encryption-aws-kms-key-id": domain_key_arn,
                    },
                },
            ))

        # -- CloudFront Distribution (optional) ----------------------------

        self.artifacts_distribution = None
        if config.get("cloudfront", {}).get("enabled", False) and artifacts_bucket:
            oac = cloudfront.CfnOriginAccessControl(
                self, "ArtifactsOAC",
                origin_access_control_config={
                    "name": f"{prefix}-{env_name}-artifacts-oac",
                    "originAccessControlOriginType": "s3",
                    "signingBehavior": "always",
                    "signingProtocol": "sigv4",
                },
            )

            self.artifacts_distribution = cloudfront.Distribution(
                self, "ArtifactsDistribution",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_control(artifacts_bucket),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                ),
                comment=f"{prefix}-{env_name} artifact delivery",
            )

        # -- SQS Queues ----------------------------------------------------

        self.artifact_dlq = sqs.Queue(
            self,
            "ArtifactDLQ",
            queue_name=f"{prefix}-{env_name}-artifact-notifications-dlq",
            retention_period=Duration.days(14),
        )
        self.artifact_queue = sqs.Queue(
            self,
            "ArtifactQueue",
            queue_name=f"{prefix}-{env_name}-artifact-notifications",
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, queue=self.artifact_dlq
            ),
        )

        self.queues = {
            "artifact-notifications": self.artifact_queue,
        }

        # -- CNMV Ban List Sync Lambda + EventBridge -----------------------

        risk_state_table = self.tables.get("risk_state")
        if risk_state_table is not None:
            # SNS topic for sync failure alerts
            self.cnmv_alert_topic = sns.Topic(
                self,
                "CNMVSyncAlertTopic",
                topic_name=f"{prefix}-{env_name}-cnmv-sync-alerts",
                display_name="CNMV Ban List Sync Alerts",
            )

            # DLQ for failed Lambda invocations
            cnmv_dlq = sqs.Queue(
                self,
                "CNMVSyncDLQ",
                queue_name=f"{prefix}-{env_name}-cnmv-sync-dlq",
                retention_period=Duration.days(14),
            )

            # Lambda function — code packaged from QITP risk module
            import os as _os

            cnmv_code_path = "lambda/risk/dist"
            if not _os.path.isdir(
                _os.path.join(_os.path.dirname(__file__), "..", cnmv_code_path)
            ):
                cnmv_code_path = "lambda/risk/example"

            self.cnmv_sync_lambda = lambda_.Function(
                self,
                "CNMVBanSync",
                function_name=f"{prefix}-{env_name}-cnmv-ban-sync",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="qitp_risk_engine.cnmv_sync.handler",
                code=lambda_.Code.from_asset(cnmv_code_path),
                memory_size=512,
                timeout=Duration.seconds(60),
                dead_letter_queue=cnmv_dlq,
                environment={
                    "RISK_STATE_TABLE": risk_state_table.table_name,
                    "ALERT_TOPIC_ARN": self.cnmv_alert_topic.topic_arn,
                },
            )

            # Grant write to risk_state table
            risk_state_table.grant_write_data(self.cnmv_sync_lambda)
            # Grant publish to SNS alert topic
            self.cnmv_alert_topic.grant_publish(self.cnmv_sync_lambda)

            # EventBridge rule: 07:00 CET = 05:00 UTC, weekdays only
            events.Rule(
                self,
                "CNMVSyncSchedule",
                rule_name=f"{prefix}-{env_name}-cnmv-ban-sync-schedule",
                schedule=events.Schedule.expression("cron(0 5 ? * MON-FRI *)"),
                targets=[events_targets.LambdaFunction(self.cnmv_sync_lambda)],
            )

        # -- SSM Parameters (for cross-stack references) -------------------

        for table_key, table in self.tables.items():
            ssm.StringParameter(
                self,
                f"SSM-table-{table_key}",
                parameter_name=f"{ssm_root}/tables/{table_key}/name",
                string_value=table.table_name,
            )
            ssm.StringParameter(
                self,
                f"SSM-table-{table_key}-arn",
                parameter_name=f"{ssm_root}/tables/{table_key}/arn",
                string_value=table.table_arn,
            )

        for bucket_key, bucket in self.buckets.items():
            ssm.StringParameter(
                self,
                f"SSM-bucket-{bucket_key}",
                parameter_name=f"{ssm_root}/buckets/{bucket_key}/name",
                string_value=bucket.bucket_name,
            )

        for queue_key, queue in self.queues.items():
            ssm.StringParameter(
                self,
                f"SSM-queue-{queue_key}",
                parameter_name=f"{ssm_root}/queues/{queue_key}/url",
                string_value=queue.queue_url,
            )
