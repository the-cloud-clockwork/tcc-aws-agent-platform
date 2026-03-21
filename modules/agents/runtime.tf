# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — AgentCore Runtime
#
# Per-agent AgentCore Runtime resources. Each agent blueprint produces one
# Runtime with container configuration pointing at the agent's ECR image,
# environment variables wired to platform outputs, and network/protocol
# settings from the blueprint.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  for_each = local.blueprints

  agent_runtime_name = "${local.name_prefix}-${each.key}"
  description        = try(each.value.description, "Agent runtime for ${each.key}")
  role_arn           = aws_iam_role.agent[each.key].arn

  # Container image from the agent's ECR repository
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent[each.key].repository_url}:latest"
    }
  }

  # Environment variables — merge platform wiring with optional artifact config
  environment_variables = merge(
    {
      AGENTCORE_GATEWAY_URL = var.gateway_url
      AGENTCORE_MEMORY_ID   = var.memory_id
      EXECUTION_MODE        = var.environment
      AGENT_ID              = each.key
      AWS_DEFAULT_REGION    = var.aws_region
      SSM_ROOT_PATH         = var.ssm_root_path
    },
    var.bedrock_region != "" ? { BEDROCK_REGION = var.bedrock_region } : {},
    var.artifacts_bucket_name != "" ? { ARTIFACTS_BUCKET = var.artifacts_bucket_name } : {},
  )

  # Network configuration — PUBLIC or PRIVATE (with VPC)
  network_configuration {
    network_mode = try(each.value.runtime.network_mode, "PUBLIC")

    dynamic "vpc_configuration" {
      for_each = try(each.value.runtime.network_mode, "PUBLIC") == "PRIVATE" ? [1] : []
      content {
        vpc_id             = var.vpc_id
        subnet_ids         = var.private_subnet_ids
        security_group_ids = [var.agent_security_group_id]
      }
    }
  }

  # Protocol — HTTP or MCP
  protocol_configuration {
    protocol = try(each.value.runtime.protocol, "HTTP")
  }

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-${each.key}"
    Component = "runtime"
    AgentId   = each.key
    Version   = try(each.value.version, "0.0.0")
  })
}
