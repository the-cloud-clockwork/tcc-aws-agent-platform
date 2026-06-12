# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- AgentCore Runtime
#
# Per-agent AgentCore Runtime resources. Each agent blueprint produces one
# Runtime with container configuration pointing at the agent's ECR image,
# environment variables wired to platform outputs, and network/protocol
# settings from the blueprint.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_ecr_image" "agent" {
  for_each        = local.blueprints
  repository_name = aws_ecr_repository.agent[each.key].name
  image_tag       = "latest"
}

# Recreate-on-change sentinel for MCP runtimes — RE-ARMED 2026-06-11.
#
# An in-place UpdateAgentRuntime on an MCP runtime can leave the Gateway with a
# STALE BINDING: the gateway still completes `initialize` and `tools/list`, but
# never forwards `tools/call` — every tool invocation fails with an opaque
# internal error while all Terraform-visible config looks correct (observed
# twice on 2026-06-11, once after an image update and once after an env-only
# update; intermittent — other runtimes survived the same applies). A REPLACE
# gives the runtime a new endpoint, forcing the gateway target to re-bind in
# the same apply, which clears the wedge deterministically.
#
# History: this sentinel originally guarded the provider <6.46.0 bug that
# dropped authorizer_configuration on in-place updates (fixed upstream; we pin
# >=6.49.0) and was dormant 2026-06-09..11 — which exposed the stale-binding
# failure the recreate had been masking. The input now covers BOTH signals
# that would otherwise apply in-place: the image digest AND the env-var
# inputs (hashed — only the digest enters state).
locals {
  # Change-signal over every module input that feeds the runtime
  # environment_variables merge (values only, order-stable, hashed).
  # Per-key env parts (AGENT_ID, OTEL service.name) are constant for a given
  # runtime and deliberately excluded. KEEP IN SYNC: adding a new env input
  # to the merge in the runtime resource means adding its source here, or an
  # env-only change of it will in-place-update MCP runtimes again.
  runtime_env_signal = sha256(jsonencode([
    var.gateway_url, var.gateway_id, var.memory_id, var.execution_mode,
    var.environment, var.aws_region, var.ssm_root_path, var.bedrock_region,
    var.litellm_base_url, var.litellm_api_key, var.anthropic_api_key,
    var.cf_access_client_id, var.cf_access_client_secret,
    var.model_pricing, var.model_default_pricing,
    var.artifacts_bucket_name, var.artifacts_table_name,
    var.domain_artifacts_kms_key_arn, var.platform_artifacts_kms_key_arn,
    var.prompt_registry_url, var.prompt_registry_function_name,
    var.idempotency_table_name,
    var.gateway_direct_mcp, var.mcp_direct_urls,
    var.cognito_token_url, var.cognito_mcp_client_id,
    var.cognito_mcp_client_secret, var.cognito_mcp_scopes,
    local.otel_env_vars,
    var.observability_enabled, var.observability_log_group_prefix,
    var.observability_metric_namespace,
    var.langfuse_host, var.langfuse_public_key, var.langfuse_secret_key,
    var.guardrail_id, var.guardrail_version,
    var.evaluation_table_name,
    var.extra_environment_variables,
  ]))
}

resource "terraform_data" "mcp_authorizer_replace" {
  for_each = local.blueprints
  input = (
    upper(try(each.value.runtime.protocol, "HTTP")) == "MCP" &&
    var.mcp_oauth2_discovery_url != ""
  ) ? "${data.aws_ecr_image.agent[each.key].image_digest}:${local.runtime_env_signal}" : "non-mcp"
}

# Replacement-safe runtime naming (2026-06-12). A runtime REPLACE must never
# fight a wedged predecessor for its name: on 2026-06-11 three runtimes sat in
# AWS-side DELETING for >9h (ConflictException on every delete retry, no
# force-delete exists, StopRuntimeSession refused on DELETING) and held their
# names hostage — same-name creates were impossible and the fleet stayed down.
# The name now carries a generation component, and the runtime uses
# create_before_destroy: a replacement CREATES under a fresh name first (the
# fleet never goes down), then destroys the old runtime — and if that delete
# wedges, the deposed ghost is retried on later applies while everything runs.
#   - MCP runtimes: generation = short hash of (image digest + env signal) —
#     the name changes exactly when the recreate sentinel fires, which now
#     drives replacement directly (replace_triggered_by no longer needed).
#   - HTTP runtimes: generation from var.runtime_name_generation (operator-
#     bumped per agent, e.g. {"ml-predictor" = "r2"}); empty = original name.
locals {
  runtime_name = {
    for key, bp in local.blueprints : key => format(
      "%s_%s%s",
      replace(local.name_prefix, "-", "_"),
      replace(key, "-", "_"),
      (
        upper(try(bp.runtime.protocol, "HTTP")) == "MCP" &&
        var.mcp_oauth2_discovery_url != ""
      ) ? "_${substr(sha256("${data.aws_ecr_image.agent[key].image_digest}:${local.runtime_env_signal}"), 0, 6)}"
      : (lookup(var.runtime_name_generation, key, "") != "" ? "_${lookup(var.runtime_name_generation, key, "")}" : "")
    )
  }
}

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  for_each = local.blueprints

  agent_runtime_name = local.runtime_name[each.key]
  description        = try(each.value.description, "Agent runtime for ${each.key}")
  role_arn           = aws_iam_role.agent[each.key].arn

  # Container image from the agent's ECR repository
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent[each.key].repository_url}@${data.aws_ecr_image.agent[each.key].image_digest}"
    }
  }

  # Environment variables -- merge platform wiring with optional artifact config.
  # NOTE: container_uri is pinned to the ECR image *digest* (see agent_runtime_artifact
  # above), so Terraform already detects a new image without any timestamp nonce. The
  # old `DEPLOY_TIMESTAMP = timestamp()` forced an in-place UpdateAgentRuntime on EVERY
  # apply — and an in-place update is exactly when the AWS provider silently drops
  # authorizer_configuration from MCP runtimes (the JWT authorizer the direct-MCP path
  # depends on). Removed: the digest-pinned container_uri is the change signal, and MCP
  # runtimes are force-recreated on image/env change via the generation-suffixed
  # runtime NAME (local.runtime_name) so the authorizer is always re-applied on Create.
  environment_variables = merge(
    {
      AGENTCORE_GATEWAY_URL = var.gateway_url
      AGENTCORE_GATEWAY_ARN = "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:gateway/${var.gateway_id}"
      AGENTCORE_MEMORY_ID   = var.memory_id
      EXECUTION_MODE        = var.execution_mode != "" ? var.execution_mode : var.environment
      AGENT_ID              = each.key
      AWS_DEFAULT_REGION    = var.aws_region
      SSM_ROOT_PATH         = var.ssm_root_path
    },
    var.bedrock_region != "" ? { BEDROCK_REGION = var.bedrock_region } : {},
    var.litellm_base_url != "" ? { LITELLM_BASE_URL = var.litellm_base_url } : {},
    var.litellm_api_key != "" ? { LITELLM_API_KEY = var.litellm_api_key } : {},
    var.anthropic_api_key != "" ? { ANTHROPIC_API_KEY = var.anthropic_api_key } : {},
    var.cf_access_client_id != "" ? { CF_ACCESS_CLIENT_ID = var.cf_access_client_id } : {},
    var.cf_access_client_secret != "" ? { CF_ACCESS_CLIENT_SECRET = var.cf_access_client_secret } : {},
    var.model_pricing != "" ? { MODEL_PRICING = var.model_pricing } : {},
    var.model_default_pricing != "" ? { MODEL_DEFAULT_PRICING = var.model_default_pricing } : {},
    var.artifacts_bucket_name != "" ? { ARTIFACTS_BUCKET = var.artifacts_bucket_name } : {},
    var.artifacts_table_name != "" ? { ARTIFACTS_TABLE = var.artifacts_table_name } : {},
    var.domain_artifacts_kms_key_arn != "" ? { DOMAIN_ARTIFACTS_KMS_KEY_ARN = var.domain_artifacts_kms_key_arn } : {},
    var.platform_artifacts_kms_key_arn != "" ? { PLATFORM_ARTIFACTS_KMS_KEY_ARN = var.platform_artifacts_kms_key_arn } : {},
    var.prompt_registry_url != "" ? { PROMPT_REGISTRY_URL = var.prompt_registry_url } : {},
    var.prompt_registry_function_name != "" ? { PROMPT_REGISTRY_FUNCTION = var.prompt_registry_function_name } : {},
    var.idempotency_table_name != "" ? { IDEMPOTENCY_TABLE = var.idempotency_table_name } : {},
    # MCP transport -- required for Gateway HTTP connectivity to MCP Runtimes
    try(upper(each.value.runtime.protocol), "HTTP") == "MCP" ? {
      MCP_TRANSPORT = "http"
      MCP_HOST      = "0.0.0.0"
      MCP_PORT      = "8000"
    } : {},
    # A2A port -- inter-agent communication via A2A protocol on port 9000
    try(each.value.runtime.a2a_port, null) != null ? {
      A2A_PORT = tostring(each.value.runtime.a2a_port)
    } : {},
    # WORKAROUND: Direct MCP bypass (AWS Issue #809) — see KNOWN_ISSUES.md KI-001
    var.gateway_direct_mcp ? {
      GATEWAY_DIRECT_MCP        = "true"
      MCP_DIRECT_URLS           = jsonencode(var.mcp_direct_urls)
      COGNITO_TOKEN_URL         = var.cognito_token_url
      COGNITO_MCP_CLIENT_ID     = var.cognito_mcp_client_id
      COGNITO_MCP_CLIENT_SECRET = var.cognito_mcp_client_secret
      COGNITO_MCP_SCOPES        = var.cognito_mcp_scopes
    } : {},
    # OTEL observability -- mirrors SDK generate_otel_env()
    local.otel_env_vars,
    var.observability_enabled ? {
      OTEL_RESOURCE_ATTRIBUTES        = "service.name=${each.key},aws.log.group.names=${var.observability_log_group_prefix}${each.key}"
      OTEL_EXPORTER_OTLP_LOGS_HEADERS = "x-aws-log-group=${var.observability_log_group_prefix}${each.key},x-aws-log-stream=runtime-logs,x-aws-metric-namespace=${var.observability_metric_namespace}"
    } : {},
    # Langfuse -- SDK direct via LangfuseHook (reads LANGFUSE_* env vars)
    # OTEL path requires Langfuse Cloud or v3+ with /api/public/otel endpoint
    var.langfuse_host != "" ? {
      LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
      LANGFUSE_SECRET_KEY = var.langfuse_secret_key
      LANGFUSE_HOST       = var.langfuse_host
      LANGFUSE_ENABLED    = "true"
    } : {},
    # Guardrail -- Bedrock content filtering
    var.guardrail_id != "" ? {
      BEDROCK_GUARDRAIL_ID      = var.guardrail_id
      BEDROCK_GUARDRAIL_VERSION = var.guardrail_version
    } : {},
    # Evaluation persistence
    var.evaluation_table_name != "" ? { EVALUATION_TABLE = var.evaluation_table_name } : {},
    var.extra_environment_variables,
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

    # Replacement is driven by the NAME (see local.runtime_name): for MCP
    # runtimes the name embeds the (digest + env signal) hash, so any image or
    # env change forces a clean REPLACE — which keeps the Gateway binding fresh
    # (in-place UpdateAgentRuntime intermittently wedges it: initialize/
    # tools-list succeed, tools/call is never forwarded). create_before_destroy
    # means the successor exists under its new name before the old runtime is
    # destroyed: zero downtime, and a delete wedged in AWS's DELETING state
    # becomes a harmless deposed ghost instead of blocking the fleet.
    create_before_destroy = true

    # Fail loud if an MCP Runtime would ship without an inbound JWT authorizer
    # while the consumer expects direct Runtime-to-Runtime MCP calls. Without
    # this check, the authorizer dynamic block silently skips, the Runtime
    # comes up accepting only SigV4, and every agent call fails with 403.
    precondition {
      condition = !(
        upper(try(each.value.runtime.protocol, "HTTP")) == "MCP" &&
        var.gateway_direct_mcp &&
        var.mcp_oauth2_discovery_url == ""
      )
      error_message = "MCP Runtime '${each.key}' requires a JWT authorizer (gateway_direct_mcp=true) but mcp_oauth2_discovery_url is empty. Either enable Cognito on the platform module, or set gateway_direct_mcp=false."
    }
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

  # Follows the runtime's create-before-destroy: the endpoint on the successor
  # runtime is created first (endpoint names are scoped per runtime — no
  # conflict); destroying the old endpoint on a DELETING ghost fails harmlessly
  # and is retried as deposed on later applies.
  lifecycle {
    create_before_destroy = true
  }
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

  depends_on = [
    aws_cloudwatch_log_delivery_source.agent,
    aws_cloudwatch_log_delivery_destination.agent,
  ]

  # When a runtime is replaced its ARN changes, forcing the delivery SOURCE
  # (resource_arn = runtime ARN) to be replaced too. The CloudWatch Logs API
  # DeleteDeliverySource returns ConflictException while a delivery still binds
  # the source; the AWS-prescribed teardown order is: delete the Delivery first,
  # THEN the DeliverySource. Coupling this delivery's replacement to its source
  # (plus the depends_on above) makes Terraform destroy the delivery before the
  # source in the destroy phase (reverse dependency order), clearing the binding
  # so the source delete succeeds. Without this, a runtime recreate wedges every
  # subsequent apply on ConflictException.
  lifecycle {
    replace_triggered_by = [aws_cloudwatch_log_delivery_source.agent[each.key]]
  }
}
