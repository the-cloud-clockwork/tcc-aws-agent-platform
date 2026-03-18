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
from constructs_.auto_scaling import FargateAutoScaling


class McpStack(Stack):
    """Provisions ECS Fargate services for all MCP servers."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        vpc: ec2.IVpc,
        mcp_sg: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.config = config
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        sd_namespace = config.get("service_discovery_namespace", f"{prefix}.local")

        # Build MCP name list from config or context
        mcp_configs = config.get("mcps", [])
        mcp_names: list[str] = self.node.try_get_context("mcps") or [
            m["name"] for m in mcp_configs
        ] or ["artifacts", "data"]

        # -- ECS Cluster ---------------------------------------------------

        self.cluster = ecs.Cluster(
            self,
            "McpCluster",
            cluster_name=f"{prefix}-{env_name}-mcp-cluster",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        # -- Cloud Map Namespace -------------------------------------------

        self.namespace = self.cluster.add_default_cloud_map_namespace(
            name=sd_namespace,
            type=sd.NamespaceType.DNS_PRIVATE,
            vpc=vpc,
        )

        # -- MCP Services --------------------------------------------------

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
                resource_prefix=prefix,
            )
            self.services[mcp_name] = mcp.service

            # Add auto-scaling if max_tasks > 1
            scaling_config = config.get("scaling", {}).get("fargate", {})
            if scaling_config.get("max_tasks", 1) > 1:
                FargateAutoScaling(
                    self,
                    f"Scaling-{mcp_name}",
                    service=mcp.service,
                    min_tasks=scaling_config.get("min_tasks", 1),
                    max_tasks=scaling_config.get("max_tasks", 3),
                    target_cpu_percent=scaling_config.get("target_cpu_percent", 70),
                )

            ssm.StringParameter(
                self,
                f"SSM-mcp-{mcp_name}-endpoint",
                parameter_name=f"{ssm_root}/mcps/{mcp_name}/endpoint",
                string_value=f"{mcp_name}.{sd_namespace}",
            )
