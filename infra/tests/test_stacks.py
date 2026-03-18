"""CDK tests for all generic platform stacks."""
import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from stacks.agent_stack import AgentStack
from stacks.data_stack import DataStack
from stacks.mcp_stack import McpStack
from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack


@pytest.fixture
def app():
    app = cdk.App(
        context={
            "env": "dev",
            "account": "835618032093",
            "region": "eu-west-1",
            "bedrock_region": "us-west-2",
            "agents": ["research", "strategy", "recommender"],
            "mcps": ["artifacts", "data"],
        }
    )
    return app


@pytest.fixture
def env():
    return cdk.Environment(account="835618032093", region="eu-west-1")


def _default_config():
    """Default dev config for tests."""
    return {
        "environment": "dev",
        "account": "835618032093",
        "region": "eu-west-1",
        "bedrock_region": "us-west-2",
        "resource_prefix": "platform",
        "service_discovery_namespace": "platform.local",
        "ssm_root_path": "/platform/dev",
        "execution_mode": "simulation",
        "vpc": {"max_azs": 2, "nat_gateways": 1},
        "scaling": {
            "fargate": {"min_tasks": 1, "max_tasks": 2, "target_cpu_percent": 70},
            "lambda": {"provisioned_concurrency": 0},
        },
        "dynamodb": {"billing_mode": "PAY_PER_REQUEST"},
        "s3": {"intelligent_tiering": False, "removal_policy": "DESTROY"},
        "logs": {"retention_days": 14},
        "mcp_services": {"cpu": 256, "memory_mib": 512, "desired_count": 1},
        "lambda_agents": {"memory_size": 1024, "timeout_minutes": 15},
        "waf": {"enabled": False},
        "secrets": {"rotation_days": 0},
        "tables": {
            "artifacts": {"partition_key": "artifact_id"},
            "audit_log": {"partition_key": "audit_id", "sort_key": "timestamp"},
            "prompt_registry": {"partition_key": "prompt_id", "sort_key": "version"},
            "run_history": {"partition_key": "run_date", "sort_key": "execution_id"},
        },
        "buckets": ["artifacts", "historical-data", "prompt-registry"],
        "agents": [
            {"name": "research", "memory": 1024, "timeout": 900},
            {"name": "strategy", "memory": 1024, "timeout": 900},
            {"name": "recommender", "memory": 1024, "timeout": 900},
        ],
        "mcps": [
            {"name": "artifacts", "port": 8000, "cpu": 256, "memory": 512},
            {"name": "data", "port": 8000, "cpu": 256, "memory": 512},
        ],
        "tags": {"Environment": "dev"},
    }


class TestDataStack:
    def test_creates_dynamodb_tables(self, app, env):
        stack = DataStack(app, "TestData", env=env, env_name="dev", config=_default_config())
        template = assertions.Template.from_stack(stack)

        # Should have 4 DynamoDB tables (config-driven)
        template.resource_count_is("AWS::DynamoDB::Table", 4)

    def test_creates_s3_buckets(self, app, env):
        stack = DataStack(app, "TestData2", env=env, env_name="dev", config=_default_config())
        template = assertions.Template.from_stack(stack)

        # Should have 3 S3 buckets (config-driven)
        template.resource_count_is("AWS::S3::Bucket", 3)

    def test_creates_sqs_queues(self, app, env):
        stack = DataStack(app, "TestData3", env=env, env_name="dev", config=_default_config())
        template = assertions.Template.from_stack(stack)

        # 1 main queue + 1 DLQ = 2
        template.resource_count_is("AWS::SQS::Queue", 2)

    def test_table_names_use_prefix(self, app, env):
        stack = DataStack(app, "TestData4", env=env, env_name="dev", config=_default_config())
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "platform_dev_artifacts"},
        )


class TestNetworkStack:
    def test_creates_vpc(self, app, env):
        stack = NetworkStack(app, "TestNetwork", env=env, env_name="dev", config=_default_config())
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_creates_security_groups(self, app, env):
        stack = NetworkStack(app, "TestNetwork2", env=env, env_name="dev", config=_default_config())
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {"GroupDescription": "Security group for agent Lambda functions"},
        )
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {"GroupDescription": "Security group for MCP Fargate services"},
        )


class TestAgentStack:
    def test_creates_lambda_functions(self, app, env):
        config = _default_config()
        data = DataStack(app, "TestDataA", env=env, env_name="dev", config=config)
        network = NetworkStack(app, "TestNetworkA", env=env, env_name="dev", config=config)
        security = SecurityStack(app, "TestSecA", env=env, env_name="dev", config=config, vpc=network.vpc)
        stack = AgentStack(
            app,
            "TestAgents",
            env=env,
            env_name="dev",
            config=config,
            vpc=network.vpc,
            agent_sg=network.agent_sg,
            data_stack=data,
            security_stack=security,
        )
        template = assertions.Template.from_stack(stack)

        # 3 agents in test context
        template.resource_count_is("AWS::Lambda::Function", 3)

    def test_lambda_runtime_and_arch(self, app, env):
        config = _default_config()
        data = DataStack(app, "TestDataB", env=env, env_name="dev", config=config)
        network = NetworkStack(app, "TestNetworkB", env=env, env_name="dev", config=config)
        security = SecurityStack(app, "TestSecB", env=env, env_name="dev", config=config, vpc=network.vpc)
        stack = AgentStack(
            app,
            "TestAgents2",
            env=env,
            env_name="dev",
            config=config,
            vpc=network.vpc,
            agent_sg=network.agent_sg,
            data_stack=data,
            security_stack=security,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Runtime": "python3.12",
                "Architectures": ["arm64"],
                "Timeout": 900,
                "MemorySize": 1024,
            },
        )


class TestMcpStack:
    def test_creates_fargate_services(self, app, env):
        config = _default_config()
        network = NetworkStack(app, "TestNetworkM", env=env, env_name="dev", config=config)
        stack = McpStack(
            app,
            "TestMcps",
            env=env,
            env_name="dev",
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        template = assertions.Template.from_stack(stack)

        # 2 MCPs in test context
        template.resource_count_is("AWS::ECS::Service", 2)

    def test_creates_ecr_repositories(self, app, env):
        config = _default_config()
        network = NetworkStack(app, "TestNetworkM2", env=env, env_name="dev", config=config)
        stack = McpStack(
            app,
            "TestMcps2",
            env=env,
            env_name="dev",
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::ECR::Repository", 2)

    def test_service_discovery(self, app, env):
        config = _default_config()
        network = NetworkStack(app, "TestNetworkM3", env=env, env_name="dev", config=config)
        stack = McpStack(
            app,
            "TestMcps3",
            env=env,
            env_name="dev",
            config=config,
            vpc=network.vpc,
            mcp_sg=network.mcp_sg,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ServiceDiscovery::PrivateDnsNamespace",
            {"Name": "platform.local"},
        )
