#!/usr/bin/env python3
"""CDK app entrypoint for the agent deployment platform.

Loads environment-specific config from config/{env}.yaml.
Usage: cdk deploy -c env=dev|staging|production
"""
from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
import yaml
from stacks.agent_stack import AgentStack
from stacks.data_stack import DataStack
from stacks.mcp_stack import McpStack
from stacks.network_stack import NetworkStack
from stacks.observability_stack import ObservabilityStack
from stacks.security_stack import SecurityStack


def load_config(env_name: str) -> dict:
    """Load environment config from YAML file."""
    config_path = Path(__file__).parent / "config" / f"{env_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Valid environments: dev, staging, production"
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


app = cdk.App()

# -- Load Environment Config ------------------------------------------------

env_name = app.node.try_get_context("env") or "dev"
config = load_config(env_name)

account = config.get("account", "835618032093")
region = config.get("region", "eu-west-1")
resource_prefix = config.get("resource_prefix", "platform")

cdk_env = cdk.Environment(account=account, region=region)
prefix = f"{resource_prefix}-{env_name}"

# Apply tags to all resources in the app
for tag_key, tag_value in config.get("tags", {}).items():
    cdk.Tags.of(app).add(tag_key, str(tag_value))

# -- Core Stacks -----------------------------------------------------------

data = DataStack(
    app,
    f"{prefix}-data",
    env=cdk_env,
    env_name=env_name,
    config=config,
)

network = NetworkStack(
    app,
    f"{prefix}-network",
    env=cdk_env,
    env_name=env_name,
    config=config,
)

# -- Security Stack --------------------------------------------------------

security = SecurityStack(
    app,
    f"{prefix}-security",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
)

# -- Agent Stack -----------------------------------------------------------

agents = AgentStack(
    app,
    f"{prefix}-agents",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    agent_sg=network.agent_sg,
    data_stack=data,
    security_stack=security,
)

# -- MCP Stack -------------------------------------------------------------

mcps = McpStack(
    app,
    f"{prefix}-mcps",
    env=cdk_env,
    env_name=env_name,
    config=config,
    vpc=network.vpc,
    mcp_sg=network.mcp_sg,
)

# -- Observability Stack ---------------------------------------------------

observability = ObservabilityStack(
    app,
    f"{prefix}-observability",
    env=cdk_env,
    env_name=env_name,
    config=config,
    agent_functions=agents.functions,
    mcp_services=mcps.services,
)

app.synth()
