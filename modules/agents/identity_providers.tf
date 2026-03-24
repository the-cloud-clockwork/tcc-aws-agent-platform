# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Identity / Credential Providers
#
# Creates AgentCore credential providers extracted from agent blueprints.
# Currently supports API key credential providers via Terraform.
#
# OAuth2 providers (3LO user federation, M2M client credentials) require
# secrets (client_secret, refresh_token) that should be configured via the
# AgentCore Identity SDK or console -- not stored in Terraform state.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Map keyed for for_each from the flattened list
  api_key_credential_map = {
    for c in local.agent_api_key_credentials :
    c.key => c
  }

  oauth_credential_map = {
    for c in local.agent_oauth_credentials :
    c.key => c
  }
}

# ── API Key Credential Providers ───────────────────────────────────────────
#
# API key values are read from SSM SecureString parameters.
# Pre-populate before terraform apply:
#   aws ssm put-parameter --type SecureString \
#     --name "{ssm_root_path}/agents/{agent_id}/credentials/{name}/api-key" \
#     --value "..."
# ──────────────────────────────────────────────────────────────────────────────

data "aws_ssm_parameter" "api_key" {
  for_each = local.api_key_credential_map
  name     = each.value.api_key_ssm_path
}

resource "aws_bedrockagentcore_api_key_credential_provider" "this" {
  for_each = local.api_key_credential_map

  name               = each.value.name
  api_key_wo         = data.aws_ssm_parameter.api_key[each.key].value
  api_key_wo_version = 1

  tags = merge(local.tags, {
    Name      = each.value.name
    Component = "credential-provider"
    Type      = "api_key"
    AgentId   = each.value.agent_id
  })

  lifecycle {
    ignore_changes = [api_key_wo_version]
  }
}

# ── OAuth2 Credential Providers ────────────────────────────────────────────
#
# OAuth2 client_id and client_secret are read from SSM SecureString parameters.
# Pre-populate before terraform apply:
#   aws ssm put-parameter --type SecureString \
#     --name "{ssm_root_path}/agents/{agent_id}/oauth/{name}/client-id" \
#     --value "..."
#   aws ssm put-parameter --type SecureString \
#     --name "{ssm_root_path}/agents/{agent_id}/oauth/{name}/client-secret" \
#     --value "..."
# ──────────────────────────────────────────────────────────────────────────────

data "aws_ssm_parameter" "oauth_client_id" {
  for_each = local.oauth_credential_map
  name     = each.value.client_id_ssm_path
}

data "aws_ssm_parameter" "oauth_client_secret" {
  for_each = local.oauth_credential_map
  name     = each.value.client_secret_ssm_path
}

resource "aws_bedrockagentcore_oauth2_credential_provider" "this" {
  for_each = local.oauth_credential_map

  name                       = each.value.name
  credential_provider_vendor = each.value.provider

  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id_wo                  = data.aws_ssm_parameter.oauth_client_id[each.key].value
      client_secret_wo              = data.aws_ssm_parameter.oauth_client_secret[each.key].value
      client_credentials_wo_version = 1

      dynamic "oauth_discovery" {
        for_each = each.value.discovery_url != "" ? [1] : []
        content {
          discovery_url = each.value.discovery_url
        }
      }
    }
  }

  tags = merge(local.tags, {
    Name      = each.value.name
    Component = "credential-provider"
    Type      = "oauth2"
    AgentId   = each.value.agent_id
  })

  lifecycle {
    ignore_changes = [oauth2_provider_config]
  }
}
