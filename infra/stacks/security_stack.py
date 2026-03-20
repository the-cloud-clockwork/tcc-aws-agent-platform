"""Security stack: WAF, Secrets Manager, KMS customer-managed keys."""
from __future__ import annotations

from aws_cdk import (
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_kms as kms,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from constructs import Construct
from constructs_.vpc_endpoints import VpcEndpointsConstruct
from constructs_.waf_rules import WafWebAcl


class SecurityStack(Stack):
    """Provisions security infrastructure for the agent platform.

    Components:
    - KMS customer-managed keys (CMKs) for encryption at rest
    - Secrets Manager secrets for external service credentials
    - WAF WebACL for API Gateway protection (staging/production only)
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
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        removal = RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN

        # -- VPC Endpoints -------------------------------------------------

        self.vpc_endpoints = VpcEndpointsConstruct(
            self,
            "VpcEndpoints",
            vpc=vpc,
            env_name=env_name,
        )

        # -- KMS Customer-Managed Keys ------------------------------------

        # Primary encryption key for DynamoDB, SQS, and general use
        self.data_key = kms.Key(
            self,
            "DataKey",
            alias=f"alias/{prefix}-{env_name}-data",
            description=f"{prefix} {env_name} data encryption key (DynamoDB, SQS)",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # Separate key for S3 objects (artifacts, historical data)
        self.storage_key = kms.Key(
            self,
            "StorageKey",
            alias=f"alias/{prefix}-{env_name}-storage",
            description=f"{prefix} {env_name} storage encryption key (S3)",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # Separate key for secrets encryption
        self.secrets_key = kms.Key(
            self,
            "SecretsKey",
            alias=f"alias/{prefix}-{env_name}-secrets",
            description=f"{prefix} {env_name} secrets encryption key",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # Platform artifacts KMS key — all platform services can use
        self.platform_artifacts_key = kms.Key(
            self,
            "PlatformArtifactsKey",
            alias=f"alias/{config.get('kms', {}).get('platform_artifacts_key_alias', 'platform-artifacts')}",
            description="Encrypts platform-tier artifacts (operational metadata, manifests)",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # Domain artifacts KMS key — restricted to authorized services only
        self.domain_artifacts_key = kms.Key(
            self,
            "DomainArtifactsKey",
            alias=f"alias/{config.get('kms', {}).get('domain_artifacts_key_alias', 'qitp-domain-artifacts')}",
            description="Encrypts domain-tier artifacts (financial data, recommendations)",
            enable_key_rotation=True,
            removal_policy=removal,
        )

        # -- Secrets Manager Secrets (generic placeholders) ----------------

        _rotation_days = config.get("secrets", {}).get("rotation_days", 0)

        # Observability API key (e.g. Langfuse)
        self.observability_secret = secretsmanager.Secret(
            self,
            "ObservabilitySecret",
            secret_name=f"{prefix}/{env_name}/observability-api-key",
            description="Observability platform API key",
            encryption_key=self.secrets_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"host":"https://observability.example.com"}',
                generate_string_key="secret_key",
                exclude_punctuation=True,
            ),
        )

        self.secrets = {
            "observability": self.observability_secret,
        }

        # -- WAF WebACL (staging/production only) ----------------------------------

        waf_config = config.get("waf", {})
        self.web_acl: WafWebAcl | None = None

        if waf_config.get("enabled", False):
            self.web_acl = WafWebAcl(
                self,
                "WafWebAcl",
                env_name=env_name,
                rate_limit=waf_config.get("rate_limit", 1000),
                ip_whitelist=waf_config.get("ip_whitelist"),
                resource_prefix=prefix,
            )

        # -- SSM Parameters ------------------------------------------------

        ssm.StringParameter(
            self,
            "SSM-data-key-arn",
            parameter_name=f"{ssm_root}/security/data-key-arn",
            string_value=self.data_key.key_arn,
        )
        ssm.StringParameter(
            self,
            "SSM-storage-key-arn",
            parameter_name=f"{ssm_root}/security/storage-key-arn",
            string_value=self.storage_key.key_arn,
        )
        ssm.StringParameter(
            self,
            "SSM-platform-artifacts-key-arn",
            parameter_name=f"{ssm_root}/security/platform-artifacts-key-arn",
            string_value=self.platform_artifacts_key.key_arn,
        )
        ssm.StringParameter(
            self,
            "SSM-domain-artifacts-key-arn",
            parameter_name=f"{ssm_root}/security/domain-artifacts-key-arn",
            string_value=self.domain_artifacts_key.key_arn,
        )

        for secret_name, secret in self.secrets.items():
            ssm.StringParameter(
                self,
                f"SSM-secret-{secret_name}-arn",
                parameter_name=f"{ssm_root}/secrets/{secret_name}/arn",
                string_value=secret.secret_arn,
            )

        if self.web_acl:
            ssm.StringParameter(
                self,
                "SSM-waf-acl-arn",
                parameter_name=f"{ssm_root}/security/waf-acl-arn",
                string_value=self.web_acl.web_acl_arn,
            )
