# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Locals
#
# Parses blueprint YAML files and derives per-agent configuration maps
# consumed by all other resource files in this module.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Read all YAML files from blueprint directory
  blueprint_files = fileset(var.blueprint_dir, "*.yaml")

  # Decode each blueprint into a map keyed by agent ID
  blueprints = {
    for f in local.blueprint_files :
    yamldecode(file("${var.blueprint_dir}/${f}")).id => yamldecode(file("${var.blueprint_dir}/${f}"))
  }

  # Read gateway targets file if provided
  # NOTE: yamldecode wraps the conditional to avoid Terraform tuple length mismatch
  # between decoded YAML (variable-length tuple) and the empty fallback.
  gateway_targets = yamldecode(var.gateway_targets_file != "" ? file(var.gateway_targets_file) : "targets: []")

  # Flatten memory strategies across all agents
  agent_memory_strategies = flatten([
    for agent_id, bp in local.blueprints : [
      for strategy in try(bp.memory.strategies, []) : {
        key       = "${agent_id}-${strategy.name}"
        agent_id  = agent_id
        type      = upper(strategy.type)
        name      = strategy.name
        namespace = try(strategy.namespace, "")
      }
    ]
  ])

  # Flatten identity credentials across all agents -- API key type
  agent_api_key_credentials = flatten([
    for agent_id, bp in local.blueprints : [
      for cred in try(bp.identity.credentials, []) : {
        key              = "${agent_id}-${cred.name}"
        agent_id         = agent_id
        name             = cred.name
        api_key_ssm_path = try(cred.api_key_ssm_path, "${var.ssm_root_path}/agents/${agent_id}/credentials/${cred.name}/api-key")
      }
      if try(cred.type, "") == "api_key"
    ]
  ])

  # Flatten identity credentials across all agents -- OAuth types
  agent_oauth_credentials = flatten([
    for agent_id, bp in local.blueprints : [
      for cred in try(bp.identity.credentials, []) : {
        key                    = "${agent_id}-${cred.name}"
        agent_id               = agent_id
        name                   = cred.name
        provider               = try(cred.provider, cred.name)
        scopes                 = try(cred.scopes, [])
        auth_flow              = try(cred.auth_flow, "M2M")
        discovery_url          = try(cred.discovery_url, "")
        client_id_ssm_path     = try(cred.client_id_ssm_path, "${var.ssm_root_path}/agents/${agent_id}/oauth/${cred.name}/client-id")
        client_secret_ssm_path = try(cred.client_secret_ssm_path, "${var.ssm_root_path}/agents/${agent_id}/oauth/${cred.name}/client-secret")
      }
      if contains(["oauth_3lo", "oauth2", "m2m"], try(cred.type, ""))
    ]
  ])

  # Per-agent OTEL env vars (mirrors SDK generate_otel_env output)
  otel_env_vars = var.observability_enabled ? {
    AGENT_OBSERVABILITY_ENABLED = "true"
    OTEL_PYTHON_DISTRO          = "aws_distro"
    OTEL_PYTHON_CONFIGURATOR    = "aws_configurator"
    OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
    OTEL_TRACES_EXPORTER        = "otlp"
    OTEL_METRICS_EXPORTER       = "otlp"
    OTEL_LOGS_EXPORTER          = "otlp"
    # Bridge Python stdlib `logging` records into the OTel logs pipeline.
    # Without this the LOGS exporter is enabled but no LoggingHandler is
    # attached, so agent `logger.*` output never produces log records (Bug G).
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED = "true"
  } : {}

  name_prefix = "${var.resource_prefix}-${var.environment}"

  tags = merge(var.tags, {
    Module = "agents"
  })
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
