# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module -- Gateway MCP OAuth2 Credential Provider
#
# Creates a single gateway-level OAuth2 credential provider backed by Cognito
# M2M (client_credentials grant). This provider is used by all MCP server
# gateway targets for Gateway→Runtime authentication.
#
# Separate from per-agent OAuth2 providers in modules/agents/identity_providers.tf
# which handle agent→external-service authentication via blueprint credentials.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_oauth2_credential_provider" "gateway_mcp" {
  count = var.cognito_enabled ? 1 : 0

  name                       = "${local.prefix}-${local.env}-gateway-mcp-oauth2"
  credential_provider_vendor = "CustomOauth2"

  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id_wo                  = aws_cognito_user_pool_client.gateway_m2m[0].id
      client_secret_wo              = aws_cognito_user_pool_client.gateway_m2m[0].client_secret
      client_credentials_wo_version = 1

      oauth_discovery {
        discovery_url = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents[0].id}/.well-known/openid-configuration"
      }
    }
  }

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-gateway-mcp-oauth2"
    Module    = "agentcore"
    Component = "oauth2-provider"
  })

  lifecycle {
    ignore_changes = [oauth2_provider_config]
  }

  depends_on = [
    aws_cognito_user_pool_domain.agents,
    aws_cognito_resource_server.gateway_mcp,
    aws_cognito_user_pool_client.gateway_m2m,
  ]
}
