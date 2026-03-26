# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- AgentCore Runtime
#
# Per-agent AgentCore Runtime resources. Each agent blueprint produces one
# Runtime with container configuration pointing at the agent's ECR image,
# environment variables wired to platform outputs, and network/protocol
# settings from the blueprint.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  for_each = local.blueprints

  agent_runtime_name = "${replace(local.name_prefix, "-", "_")}_${replace(each.key, "-", "_")}"
  description        = try(each.value.description, "Agent runtime for ${each.key}")
  role_arn           = aws_iam_role.agent[each.key].arn

  # Container image from the agent's ECR repository
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent[each.key].repository_url}:latest"
    }
  }

  # Environment variables -- merge platform wiring with optional artifact config
  environment_variables = merge(
    {
      AGENTCORE_GATEWAY_URL = var.gateway_url
      AGENTCORE_GATEWAY_ARN = "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:gateway/${var.gateway_id}"
      AGENTCORE_MEMORY_ID   = var.memory_id
      EXECUTION_MODE        = var.environment
      AGENT_ID              = each.key
      AWS_DEFAULT_REGION    = var.aws_region
      SSM_ROOT_PATH         = var.ssm_root_path
    },
    var.bedrock_region != "" ? { BEDROCK_REGION = var.bedrock_region } : {},
    var.artifacts_bucket_name != "" ? { ARTIFACTS_BUCKET = var.artifacts_bucket_name } : {},
    var.prompt_registry_url != "" ? { PROMPT_REGISTRY_URL = var.prompt_registry_url } : {},
    var.prompt_registry_function_name != "" ? { PROMPT_REGISTRY_FUNCTION = var.prompt_registry_function_name } : {},
    var.idempotency_table_name != "" ? { IDEMPOTENCY_TABLE = var.idempotency_table_name } : {},
    # MCP transport -- required for Gateway HTTP connectivity to MCP Runtimes
    try(upper(each.value.runtime.protocol), "HTTP") == "MCP" ? {
      MCP_TRANSPORT = "http"
      MCP_HOST      = "0.0.0.0"
      MCP_PORT      = "8000"
    } : {},
    # OTEL observability -- mirrors SDK generate_otel_env()
    local.otel_env_vars,
    var.observability_enabled ? {
      OTEL_RESOURCE_ATTRIBUTES        = "service.name=${each.key},aws.log.group.names=${var.observability_log_group_prefix}${each.key}"
      OTEL_EXPORTER_OTLP_LOGS_HEADERS = "x-aws-log-group=${var.observability_log_group_prefix}${each.key},x-aws-log-stream=runtime-logs,x-aws-metric-namespace=${var.observability_metric_namespace}"
    } : {},
  )

  # Network configuration -- PUBLIC or VPC
  network_configuration {
    network_mode = try(each.value.runtime.network_mode, "PUBLIC")

    dynamic "network_mode_config" {
      for_each = try(each.value.runtime.network_mode, "PUBLIC") == "VPC" ? [1] : []
      content {
        subnets         = var.private_subnet_ids
        security_groups = [var.agent_security_group_id]
      }
    }
  }

  # Protocol -- HTTP, MCP, or A2A
  protocol_configuration {
    server_protocol = each.value.runtime.protocol
  }

  # OAuth2 JWT authorizer -- MCP runtimes must validate incoming OAuth tokens
  # from Gateway. HTTP runtimes use SigV4 (no authorizer needed).
  dynamic "authorizer_configuration" {
    for_each = (
      upper(try(each.value.runtime.protocol, "HTTP")) == "MCP" &&
      var.mcp_oauth2_discovery_url != ""
    ) ? [1] : []
    content {
      custom_jwt_authorizer {
        discovery_url   = var.mcp_oauth2_discovery_url
        allowed_clients = var.mcp_oauth2_allowed_clients
      }
    }
  }

  # Lifecycle timeouts -- from blueprint when specified
  lifecycle_configuration = (
    try(each.value.runtime.max_lifetime, null) != null ||
    try(each.value.runtime.idle_timeout, null) != null
    ) ? [{
      max_lifetime                 = try(each.value.runtime.max_lifetime, null)
      idle_runtime_session_timeout = try(each.value.runtime.idle_timeout, null)
  }] : null

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-${each.key}"
    Component = "runtime"
    AgentId   = each.key
    Version   = try(each.value.version, "0.0.0")
  })

  # Workaround for provider bug #45290: lifecycle_configuration attributes
  # are not marked as Computed, causing drift on subsequent applies.
  lifecycle {
    ignore_changes = [lifecycle_configuration]
  }
}

# ── Runtime Endpoint ───────────────────────────────────────────────────────
#
# Each runtime needs an endpoint to be network-reachable.

resource "aws_bedrockagentcore_agent_runtime_endpoint" "agent" {
  for_each = local.blueprints

  name             = "${replace(local.name_prefix, "-", "_")}_${replace(each.key, "-", "_")}_ep"
  agent_runtime_id = aws_bedrockagentcore_agent_runtime.agent[each.key].agent_runtime_id
  description      = "Endpoint for runtime: ${each.key}"

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-${each.key}-ep"
    Component = "runtime-endpoint"
    AgentId   = each.key
  })
}

# ── CloudWatch Log Group per Agent ─────────────────────────────────────────
#
# The aws_bedrockagentcore_agent_runtime resource has no logging_configuration
# block (provider issue #44742). We use CloudWatch Vended Logs delivery API
# to wire runtime logs to a CloudWatch log group per agent.

resource "aws_cloudwatch_log_group" "agent" {
  for_each = local.blueprints

  name              = "/aws/bedrock-agentcore/runtimes/${each.key}"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-${each.key}-logs"
    Component = "runtime-logs"
    AgentId   = each.key
  })
}

# ── Vended Logs Delivery: Source → Destination → Delivery ──────────────────
#
# AgentCore Runtimes are "vended log" sources. The CloudWatch Logs delivery
# API connects the runtime ARN (source) to a log group (destination).

resource "aws_cloudwatch_log_delivery_source" "agent" {
  for_each = local.blueprints

  name         = "${local.name_prefix}-${each.key}-logs"
  log_type     = "APPLICATION_LOGS"
  resource_arn = aws_bedrockagentcore_agent_runtime.agent[each.key].agent_runtime_arn
}

resource "aws_cloudwatch_log_delivery_destination" "agent" {
  for_each = local.blueprints

  name = "${local.name_prefix}-${each.key}-logs-dst"

  delivery_destination_configuration {
    destination_resource_arn = aws_cloudwatch_log_group.agent[each.key].arn
  }
}

resource "aws_cloudwatch_log_delivery" "agent_logs" {
  for_each = local.blueprints

  delivery_source_name     = aws_cloudwatch_log_delivery_source.agent[each.key].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.agent[each.key].arn
}
