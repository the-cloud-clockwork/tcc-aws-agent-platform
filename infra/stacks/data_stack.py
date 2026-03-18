"""Data stack: S3 buckets, DynamoDB tables, SQS queues."""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from aws_cdk import (
    aws_ssm as ssm,
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
