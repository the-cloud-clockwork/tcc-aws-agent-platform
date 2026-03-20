"""Network stack: VPC, subnets, security groups."""
from __future__ import annotations

from aws_cdk import (
    Stack,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from constructs import Construct


class NetworkStack(Stack):
    """Provisions VPC and security groups for the agent platform."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")

        # -- VPC -----------------------------------------------------------

        vpc_config = config.get("vpc", {})

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=f"{prefix}-{env_name}-vpc",
            max_azs=vpc_config.get("max_azs", 2),
            nat_gateways=vpc_config.get("nat_gateways", 1),
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

        # VPC Endpoints moved to SecurityStack via VpcEndpointsConstruct

        # -- Security Groups -----------------------------------------------

        self.agent_sg = ec2.SecurityGroup(
            self,
            "AgentSG",
            vpc=self.vpc,
            security_group_name=f"{prefix}-{env_name}-agent-sg",
            description="Security group for agent Lambda functions",
            allow_all_outbound=True,
        )

        self.mcp_sg = ec2.SecurityGroup(
            self,
            "McpSG",
            vpc=self.vpc,
            security_group_name=f"{prefix}-{env_name}-mcp-sg",
            description="Security group for MCP Fargate services",
            allow_all_outbound=True,
        )

        # Allow agents to reach MCPs on port 8080
        self.mcp_sg.add_ingress_rule(
            peer=self.agent_sg,
            connection=ec2.Port.tcp(8080),
            description="Allow agent Lambdas to call MCP services (port 8080)",
        )

        # -- SSM Parameters ------------------------------------------------

        ssm.StringParameter(
            self,
            "SSM-vpc-id",
            parameter_name=f"{ssm_root}/network/vpc-id",
            string_value=self.vpc.vpc_id,
        )
