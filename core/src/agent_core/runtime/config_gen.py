"""AgentCore Runtime config and Dockerfile generators.

Reads an AgentBlueprint and produces:
  - .bedrock_agentcore.yaml (Runtime deployment config)
  - Dockerfile (ARM64 container with OTEL wrapper)

These are consumed by the deployment pipeline and by
`agentcli generate runtime-config` / `agentcli generate dockerfile`.
"""

from __future__ import annotations

import textwrap

import yaml

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.schemas.identity_config import AuthorizerType
from agent_core.schemas.tool_config import BuiltinToolConfig, BuiltinToolType


def _build_identity_config(blueprint: AgentBlueprint) -> dict:
    """Build identity section from blueprint identity configuration."""
    identity_cfg: dict = {}

    # Inbound: authorizer configuration
    if blueprint.identity.authorizer is not None:
        auth = blueprint.identity.authorizer
        if auth.type == AuthorizerType.CUSTOM_JWT:
            authorizer: dict = {"customJWTAuthorizer": {}}
            if auth.discovery_url:
                authorizer["customJWTAuthorizer"]["discoveryUrl"] = auth.discovery_url
            if auth.allowed_clients:
                authorizer["customJWTAuthorizer"]["allowedClients"] = (
                    auth.allowed_clients
                )
            identity_cfg["authorizer_configuration"] = authorizer

    # Outbound: credential providers
    credential_providers = []
    for cred in blueprint.identity.credentials:
        entry: dict = {
            "name": cred.provider,
            "type": cred.type.value,
        }
        if cred.scopes:
            entry["scopes"] = cred.scopes
        if cred.auth_flow is not None:
            entry["auth_flow"] = cred.auth_flow.value
        credential_providers.append(entry)
    identity_cfg["credential_providers"] = credential_providers

    return identity_cfg


def generate_agentcore_config(
    blueprint: AgentBlueprint,
    *,
    entrypoint_file: str = "app.py",
) -> str:
    """Generate .bedrock_agentcore.yaml from an agent blueprint.

    Args:
        blueprint: Loaded AgentBlueprint instance.
        entrypoint_file: Python entrypoint file name.

    Returns:
        YAML string ready to write to .bedrock_agentcore.yaml.
    """
    config = {
        "agents": {
            blueprint.id: {
                "entrypoint": entrypoint_file,
                "deployment_type": "container",
                "platform": blueprint.runtime.platform,
                "aws": {
                    "network_configuration": {
                        "network_mode": blueprint.runtime.network_mode,
                    },
                    "protocol_configuration": {
                        "server_protocol": blueprint.runtime.protocol,
                    },
                    "observability": {
                        "enabled": blueprint.runtime.observability_enabled,
                    },
                },
                "memory": {
                    "mode": "NO_MEMORY",
                },
                "identity": _build_identity_config(blueprint),
            },
        },
    }
    # Builtin tools (Code Interpreter, Browser)
    builtin_tools = _build_tools_config(blueprint)
    if builtin_tools:
        config["agents"][blueprint.id]["tools"] = builtin_tools

    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _build_tools_config(blueprint: AgentBlueprint) -> list[dict]:
    """Build tools config entries for builtin tools declared in the blueprint."""
    tools: list[dict] = []
    for tool_cfg in blueprint.tools:
        if not isinstance(tool_cfg, BuiltinToolConfig):
            continue
        entry: dict = {"type": tool_cfg.builtin.value}
        if tool_cfg.region:
            entry["region"] = tool_cfg.region
        if tool_cfg.builtin == BuiltinToolType.CODE_INTERPRETER:
            entry["network_mode"] = tool_cfg.network_mode
        tools.append(entry)
    return tools


def generate_dockerfile(
    blueprint: AgentBlueprint,
    *,
    base_image: str = "python:3.12-slim",
    requirements_file: str = "requirements.txt",
) -> str:
    """Generate a Dockerfile for an AgentCore Runtime agent container.

    Produces an ARM64-compatible container with:
      - bedrock_agentcore + strands as mandatory dependencies
      - OTEL auto-instrumentation wrapper (when observability enabled)
      - Health check on /ping
      - Correct port exposure

    Args:
        blueprint: Loaded AgentBlueprint instance.
        base_image: Base Docker image.
        requirements_file: Requirements file to install.

    Returns:
        Dockerfile content as string.
    """
    port = blueprint.runtime.port
    otel_enabled = blueprint.runtime.observability_enabled

    otel_install = ""
    if otel_enabled:
        otel_install = "RUN pip install --no-cache-dir aws-opentelemetry-distro\n"

    if otel_enabled:
        cmd = 'CMD ["opentelemetry-instrument", "python", "-m", "app"]'
    else:
        cmd = 'CMD ["python", "-m", "app"]'

    a2a_expose = ""
    if (
        blueprint.multi_agent is not None
        and blueprint.multi_agent.role == "specialist"
        and blueprint.runtime.a2a_port
    ):
        a2a_expose = f"\nEXPOSE {blueprint.runtime.a2a_port}"

    dockerfile = textwrap.dedent(f"""\
        FROM {base_image}

        WORKDIR /app

        COPY {requirements_file} .
        RUN pip install --no-cache-dir -r {requirements_file}
        {otel_install}
        COPY . .

        EXPOSE {port}{a2a_expose}

        HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
            CMD curl -f http://localhost:{port}/ping || exit 1

        {cmd}
    """)
    return dockerfile
