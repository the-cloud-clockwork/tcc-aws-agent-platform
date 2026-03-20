"""MCP stack: ECS Fargate services, ECR repos, Service Discovery."""
from aws_cdk import (
    Stack,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_servicediscovery as sd,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from constructs import Construct
from constructs_.auto_scaling import FargateAutoScaling
from constructs_.mcp_service import McpServiceConstruct


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
        data_stack=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.config = config
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        sd_namespace = config.get("service_discovery_namespace", f"{prefix}.local")

        # Build MCP config list from config or context
        mcp_configs = config.get("mcps", [])
        if not mcp_configs:
            mcp_configs = [
                {"name": "artifacts", "port": 8004},
                {"name": "market-data", "port": 8002},
            ]

        # Allow context override of MCP names
        context_mcps = self.node.try_get_context("mcps")
        if context_mcps:
            mcp_configs = [{"name": n, "port": 8000} for n in context_mcps]

        # Default MCP resource config
        mcp_defaults = config.get("mcp_services", {})
        default_cpu = mcp_defaults.get("cpu", 256)
        default_memory = mcp_defaults.get("memory_mib", 512)

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
        self.mcp_endpoints: dict[str, str] = {}

        for mcp_cfg in mcp_configs:
            mcp_name = mcp_cfg["name"]
            mcp_port = mcp_cfg.get("port", 8000)
            mcp_cpu = mcp_cfg.get("cpu", default_cpu)
            mcp_memory = mcp_cfg.get("memory", default_memory)

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
                container_port=mcp_port,
                cpu=mcp_cpu,
                memory_limit_mib=mcp_memory,
            )
            self.services[mcp_name] = mcp.service
            self.mcp_endpoints[mcp_name] = f"http://{mcp_name}.{sd_namespace}:{mcp_port}"

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

            # Add CloudFront env vars for artifacts MCP
            if mcp_name == "artifacts":
                cf_config = config.get("cloudfront", {})
                if cf_config.get("enabled", False) and data_stack and hasattr(data_stack, "artifacts_distribution") and data_stack.artifacts_distribution:
                    mcp.container.add_environment("CLOUDFRONT_DOMAIN", data_stack.artifacts_distribution.distribution_domain_name)
                if cf_config.get("key_pair_id"):
                    mcp.container.add_environment("CLOUDFRONT_KEY_PAIR_ID", cf_config["key_pair_id"])
                if cf_config.get("private_key_secret_arn"):
                    mcp.container.add_environment("CLOUDFRONT_PRIVATE_KEY_SECRET_ARN", cf_config["private_key_secret_arn"])

            ssm.StringParameter(
                self,
                f"SSM-mcp-{mcp_name}-endpoint",
                parameter_name=f"{ssm_root}/mcps/{mcp_name}/endpoint",
                string_value=f"{mcp_name}.{sd_namespace}:{mcp_port}",
            )
