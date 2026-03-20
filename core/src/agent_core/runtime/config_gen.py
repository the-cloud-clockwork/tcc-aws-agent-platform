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
                "identity": {
                    "credential_providers": [],
                },
            },
        },
    }
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


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
        otel_install = 'RUN pip install --no-cache-dir aws-opentelemetry-distro\n'

    if otel_enabled:
        cmd = 'CMD ["opentelemetry-instrument", "python", "-m", "app"]'
    else:
        cmd = 'CMD ["python", "-m", "app"]'

    dockerfile = textwrap.dedent(f"""\
        FROM {base_image}

        WORKDIR /app

        COPY {requirements_file} .
        RUN pip install --no-cache-dir -r {requirements_file}
        {otel_install}
        COPY . .

        EXPOSE {port}

        HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
            CMD curl -f http://localhost:{port}/ping || exit 1

        {cmd}
    """)
    return dockerfile
