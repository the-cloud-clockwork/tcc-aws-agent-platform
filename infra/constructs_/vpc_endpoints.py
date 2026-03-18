"""VPC Endpoints construct -- reduces NAT Gateway costs and improves security."""
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    aws_ec2 as ec2,
)


class VpcEndpointsConstruct(Construct):
    """Provisions VPC endpoints for AWS services used by the agent platform.

    Gateway endpoints (free):
    - S3
    - DynamoDB

    Interface endpoints (cost per hour + per GB):
    - SQS
    - ECR (+ ECR Docker)
    - CloudWatch Logs
    - Secrets Manager
    - KMS
    - STS
    - SSM

    Interface endpoints are only created when the service is in the same
    region as the VPC.
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

        # -- Gateway Endpoints (free, always create) -----------------------

        self.s3_endpoint = vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        self.dynamodb_endpoint = vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
        )

        # -- Interface Endpoints -------------------------------------------

        # SQS -- used by artifact notifications
        self.sqs_endpoint = vpc.add_interface_endpoint(
            "SQSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SQS,
            private_dns_enabled=True,
        )

        # ECR -- pull container images for MCP services
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

        # CloudWatch Logs -- all Lambda and ECS log shipping
        self.logs_endpoint = vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            private_dns_enabled=True,
        )

        # Secrets Manager -- credential retrieval
        self.secrets_endpoint = vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            private_dns_enabled=True,
        )

        # KMS -- encryption/decryption for Secrets Manager + S3 SSE-KMS
        self.kms_endpoint = vpc.add_interface_endpoint(
            "KMSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.KMS,
            private_dns_enabled=True,
        )

        # STS -- IAM role assumption for cross-account/cross-region
        self.sts_endpoint = vpc.add_interface_endpoint(
            "STSEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.STS,
            private_dns_enabled=True,
        )

        # SSM Parameter Store -- config retrieval
        self.ssm_endpoint = vpc.add_interface_endpoint(
            "SSMEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
            private_dns_enabled=True,
        )
