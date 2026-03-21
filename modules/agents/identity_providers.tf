# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — Identity / Credential Providers
#
# Creates AgentCore credential providers extracted from agent blueprints.
# Currently supports API key credential providers via Terraform.
#
# OAuth2 providers (3LO user federation, M2M client credentials) require
# secrets (client_secret, refresh_token) that should be configured via the
# AgentCore Identity SDK or console — not stored in Terraform state.
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

resource "aws_bedrockagentcore_apikey_credential_provider" "this" {
  for_each = local.api_key_credential_map

  name                       = each.value.name
  credential_provider_vendor = each.value.provider

  tags = merge(local.tags, {
    Name      = each.value.name
    Component = "credential-provider"
    Type      = "api_key"
    AgentId   = each.value.agent_id
  })
}

# ── OAuth2 Credential Providers ────────────────────────────────────────────
#
# OAuth2 providers require client_id, client_secret, and potentially
# authorization_url / token_url which contain sensitive values.
# These should be provisioned via:
#   1. AgentCore Identity SDK (bedrock-agentcore identity create-oauth-provider)
#   2. AWS Console (Bedrock AgentCore → Identity → Credential Providers)
#
# The oauth_credential_map local is available for reference or future
# automation but is not used to create resources here to avoid storing
# secrets in Terraform state.
#
# Tracked credentials from blueprints (informational):
#   for_each = local.oauth_credential_map
#   name      = each.value.name
#   provider  = each.value.provider
#   scopes    = each.value.scopes
#   auth_flow = each.value.auth_flow
# ──────────────────────────────────────────────────────────────────────────────
