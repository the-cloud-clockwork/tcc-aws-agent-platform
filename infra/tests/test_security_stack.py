"""Tests for the SecurityStack -- WAF, Secrets Manager, KMS, VPC Endpoints."""
from __future__ import annotations

import pytest
import aws_cdk as cdk
from aws_cdk import assertions

from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack


def _make_config(env_name: str, waf_enabled: bool = False) -> dict:
    """Build a minimal config dict for testing."""
    return {
        "environment": env_name,
        "account": "123456789012",
        "region": "eu-west-1",
        "resource_prefix": "platform",
        "service_discovery_namespace": "platform.local",
        "ssm_root_path": f"/platform/{env_name}",
        "execution_mode": "simulation" if env_name == "dev" else env_name,
        "vpc": {"max_azs": 2, "nat_gateways": 1},
        "scaling": {"fargate": {"min_tasks": 1, "max_tasks": 2, "target_cpu_percent": 70}, "lambda": {"provisioned_concurrency": 0}},
        "dynamodb": {"billing_mode": "PAY_PER_REQUEST"},
        "s3": {"intelligent_tiering": False, "removal_policy": "DESTROY"},
        "logs": {"retention_days": 14},
        "mcp_services": {"cpu": 256, "memory_mib": 512, "desired_count": 1},
        "lambda_agents": {"memory_size": 1024, "timeout_minutes": 15},
        "waf": {"enabled": waf_enabled, "rate_limit": 1000, "ip_whitelist": []},
        "secrets": {"rotation_days": 0},
        "tags": {"Environment": env_name},
    }


@pytest.fixture
def app():
    return cdk.App(context={"env": "dev"})


@pytest.fixture
def cdk_env():
    return cdk.Environment(account="123456789012", region="eu-west-1")


class TestKmsKeys:
    def test_creates_three_kms_keys(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # 3 CMKs: data, storage, secrets
        template.resource_count_is("AWS::KMS::Key", 3)

    def test_kms_key_rotation_enabled(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet2", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity2", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::KMS::Key",
            {"EnableKeyRotation": True},
        )


class TestSecretsManager:
    def test_creates_one_generic_secret(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet3", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity3", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        # 1 generic secret: observability
        template.resource_count_is("AWS::SecretsManager::Secret", 1)

    def test_secret_name_uses_prefix(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet4", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity4", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "platform/dev/observability-api-key"},
        )

    def test_secrets_encrypted_with_cmk(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet5", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity5", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"KmsKeyId": assertions.Match.any_value()},
        )


class TestWaf:
    def test_no_waf_in_dev(self, app, cdk_env):
        config = _make_config("dev", waf_enabled=False)
        network = NetworkStack(app, "TestNet6", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity6", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::WAFv2::WebACL", 0)

    def test_waf_created_when_enabled(self, app, cdk_env):
        config = _make_config("staging", waf_enabled=True)
        network = NetworkStack(app, "TestNet7", env=cdk_env, env_name="staging", config=config)
        stack = SecurityStack(
            app, "TestSecurity7", env=cdk_env, env_name="staging", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.resource_count_is("AWS::WAFv2::WebACL", 1)

    def test_waf_has_rate_limit_rule(self, app, cdk_env):
        config = _make_config("staging", waf_enabled=True)
        network = NetworkStack(app, "TestNet8", env=cdk_env, env_name="staging", config=config)
        stack = SecurityStack(
            app, "TestSecurity8", env=cdk_env, env_name="staging", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::WAFv2::WebACL",
            {
                "Rules": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Name": "RateLimit",
                        "Statement": {
                            "RateBasedStatement": {
                                "Limit": 1000,
                                "AggregateKeyType": "IP",
                            },
                        },
                    }),
                ]),
            },
        )

    def test_waf_has_managed_rules(self, app, cdk_env):
        config = _make_config("production", waf_enabled=True)
        network = NetworkStack(app, "TestNet9", env=cdk_env, env_name="production", config=config)
        stack = SecurityStack(
            app, "TestSecurity9", env=cdk_env, env_name="production", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::WAFv2::WebACL",
            {
                "Rules": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Name": "AWSManagedRulesCommonRuleSet",
                    }),
                    assertions.Match.object_like({
                        "Name": "AWSManagedRulesKnownBadInputs",
                    }),
                ]),
            },
        )


class TestVpcEndpoints:
    def test_creates_gateway_and_interface_endpoints(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet10", env=cdk_env, env_name="dev", config=config)
        SecurityStack(
            app, "TestSecurity10", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(network)

        resources = template.find_resources("AWS::EC2::VPCEndpoint")
        assert len(resources) >= 8, f"Expected >= 8 VPC endpoints, got {len(resources)}"


class TestSsmParameters:
    def test_exports_key_arns(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet12", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity12", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/platform/dev/security/data-key-arn"},
        )
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/platform/dev/security/storage-key-arn"},
        )

    def test_exports_secret_arns(self, app, cdk_env):
        config = _make_config("dev")
        network = NetworkStack(app, "TestNet13", env=cdk_env, env_name="dev", config=config)
        stack = SecurityStack(
            app, "TestSecurity13", env=cdk_env, env_name="dev", config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/platform/dev/secrets/observability/arn"},
        )
