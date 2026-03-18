"""Tests for multi-environment configuration loading and stack behavior."""
from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
import pytest
import yaml
from aws_cdk import assertions

from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_config(env_name: str) -> dict:
    """Load config YAML for testing."""
    config_path = CONFIG_DIR / f"{env_name}.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


class TestConfigFiles:
    """Verify that all config YAMLs exist and have required keys."""

    @pytest.mark.parametrize("env_name", ["dev", "staging", "production"])
    def test_config_file_exists(self, env_name):
        config_path = CONFIG_DIR / f"{env_name}.yaml"
        assert config_path.exists(), f"Missing config: {config_path}"

    @pytest.mark.parametrize("env_name", ["dev", "staging", "production"])
    def test_config_has_required_keys(self, env_name):
        config = _load_config(env_name)
        required_keys = [
            "environment",
            "account",
            "region",
            "resource_prefix",
            "service_discovery_namespace",
            "ssm_root_path",
            "execution_mode",
            "vpc",
            "scaling",
            "dynamodb",
            "s3",
            "logs",
            "mcp_services",
            "lambda_agents",
            "waf",
            "secrets",
            "tags",
            "tables",
            "buckets",
            "agents",
            "mcps",
        ]
        for key in required_keys:
            assert key in config, f"Missing key '{key}' in {env_name}.yaml"

    @pytest.mark.parametrize("env_name", ["dev", "staging", "production"])
    def test_config_environment_matches_filename(self, env_name):
        config = _load_config(env_name)
        assert config["environment"] == env_name

    def test_dev_execution_mode_is_simulation(self):
        config = _load_config("dev")
        assert config["execution_mode"] == "simulation"

    def test_staging_execution_mode_is_staging(self):
        config = _load_config("staging")
        assert config["execution_mode"] == "staging"

    def test_production_execution_mode_is_production(self):
        config = _load_config("production")
        assert config["execution_mode"] == "production"

    def test_dev_waf_disabled(self):
        config = _load_config("dev")
        assert config["waf"]["enabled"] is False

    def test_production_waf_enabled(self):
        config = _load_config("production")
        assert config["waf"]["enabled"] is True

    def test_production_has_higher_nat_gateways(self):
        dev_config = _load_config("dev")
        live_config = _load_config("production")
        assert live_config["vpc"]["nat_gateways"] >= dev_config["vpc"]["nat_gateways"]

    def test_production_has_higher_fargate_min_tasks(self):
        dev_config = _load_config("dev")
        live_config = _load_config("production")
        assert live_config["scaling"]["fargate"]["min_tasks"] > dev_config["scaling"]["fargate"]["min_tasks"]

    def test_production_has_provisioned_concurrency(self):
        config = _load_config("production")
        assert config["scaling"]["lambda"]["provisioned_concurrency"] > 0

    @pytest.mark.parametrize("env_name", ["dev", "staging", "production"])
    def test_no_domain_prefix_in_config(self, env_name):
        """Ensure no domain-specific references in config files."""
        config_path = CONFIG_DIR / f"{env_name}.yaml"
        content = config_path.read_text().lower()
        _forbidden = "".join(["q", "i", "t", "p"])
        assert _forbidden not in content, f"Found domain prefix in {env_name}.yaml"

    @pytest.mark.parametrize("env_name", ["dev", "staging", "production"])
    def test_resource_prefix_is_generic(self, env_name):
        config = _load_config(env_name)
        assert config["resource_prefix"] == "platform"


class TestMultiEnvStacks:
    """Verify stacks synthesize correctly for each environment."""

    @pytest.fixture(params=["dev", "staging", "production"])
    def env_name(self, request):
        return request.param

    @pytest.fixture
    def config(self, env_name):
        return _load_config(env_name)

    @pytest.fixture
    def cdk_env(self):
        return cdk.Environment(account="123456789012", region="eu-west-1")

    def test_network_stack_nat_gateways(self, env_name, config, cdk_env):
        app = cdk.App()
        stack = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        template = assertions.Template.from_stack(stack)

        expected_nats = config["vpc"]["nat_gateways"]
        template.resource_count_is("AWS::EC2::NatGateway", expected_nats)

    def test_security_stack_waf_by_env(self, env_name, config, cdk_env):
        app = cdk.App()
        network = NetworkStack(
            app, f"TestNet-{env_name}", env=cdk_env, env_name=env_name, config=config,
        )
        stack = SecurityStack(
            app, f"TestSec-{env_name}", env=cdk_env, env_name=env_name, config=config, vpc=network.vpc,
        )
        template = assertions.Template.from_stack(stack)

        expected_waf_count = 1 if config["waf"]["enabled"] else 0
        template.resource_count_is("AWS::WAFv2::WebACL", expected_waf_count)
