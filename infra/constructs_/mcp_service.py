"""McpServiceConstruct -- reusable CDK construct for Fargate MCP services."""
from aws_cdk import (
    Duration,
    RemovalPolicy,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecr as ecr,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_servicediscovery as sd,
)
from constructs import Construct


class McpServiceConstruct(Construct):
    """Provisions an ECR repo and ECS Fargate service for one MCP.

    Features:
    - ECR image from repo
    - ECS task definition with health check
    - Service Discovery A record
    - CloudWatch log group
    - Configurable container port
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        mcp_name: str,
        cluster: ecs.ICluster,
        namespace: sd.INamespace,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
        resource_prefix: str = "platform",
        container_port: int = 8000,
        cpu: int = 256,
        memory_limit_mib: int = 512,
    ) -> None:
        super().__init__(scope, construct_id)

        self.mcp_name = mcp_name
        self.container_port = container_port
        prefix = resource_prefix
        removal = RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN

        # -- ECR Repository ------------------------------------------------

        self.repository = ecr.Repository(
            self,
            "Repo",
            repository_name=f"{prefix}-{env_name}-mcp-{mcp_name}",
            removal_policy=removal,
            empty_on_delete=(env_name == "dev"),
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    max_image_count=10,
                    description="Keep last 10 images",
                )
            ],
        )

        # -- Log Group -----------------------------------------------------

        self.log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=f"/ecs/{prefix}-{env_name}-mcp-{mcp_name}",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # -- Task Definition -----------------------------------------------

        self.task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            family=f"{prefix}-{env_name}-mcp-{mcp_name}",
            cpu=cpu,
            memory_limit_mib=memory_limit_mib,
        )

        self.container = self.task_definition.add_container(
            "Container",
            container_name=mcp_name,
            image=ecs.ContainerImage.from_ecr_repository(
                self.repository, tag="latest"
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=mcp_name,
                log_group=self.log_group,
            ),
            environment={
                "ENV_NAME": env_name,
                "MCP_NAME": mcp_name,
                "PORT": str(container_port),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", f"curl -f http://localhost:{container_port}/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        self.container.add_port_mappings(
            ecs.PortMapping(container_port=container_port, protocol=ecs.Protocol.TCP)
        )

        # -- Fargate Service -----------------------------------------------

        desired_count = 1 if env_name == "dev" else 2

        self.service = ecs.FargateService(
            self,
            "Service",
            service_name=f"{prefix}-{env_name}-mcp-{mcp_name}",
            cluster=cluster,
            task_definition=self.task_definition,
            desired_count=desired_count,
            security_groups=[security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            assign_public_ip=False,
            cloud_map_options=ecs.CloudMapOptions(
                name=mcp_name,
                cloud_map_namespace=namespace,
                dns_record_type=sd.DnsRecordType.A,
                dns_ttl=Duration.seconds(30),
            ),
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=True,
            ),
            enable_execute_command=True,
        )
