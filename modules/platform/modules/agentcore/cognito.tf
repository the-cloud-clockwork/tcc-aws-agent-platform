# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module -- Cognito User Pool
#
# Conditionally creates a Cognito user pool for agent identity/authentication.
# When enabled, this provides the OIDC issuer that the Gateway's CUSTOM_JWT
# authorizer validates against.
# ──────────────────────────────────────────────────────────────────────────────

# ── User Pool ────────────────────────────────────────────────────────────────

resource "aws_cognito_user_pool" "agents" {
  count = var.cognito_enabled ? 1 : 0

  name = "${local.prefix}-${local.env}-agents"

  # Password policy
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  # MFA -- optional (users can enable if desired)
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  # Email verification
  auto_verified_attributes = ["email"]

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-agents"
    Module    = "agentcore"
    Component = "cognito"
  })
}

# ── User Pool Client ─────────────────────────────────────────────────────────

resource "aws_cognito_user_pool_client" "agents" {
  count = var.cognito_enabled ? 1 : 0

  name         = "${local.prefix}-${local.env}-agent-client"
  user_pool_id = aws_cognito_user_pool.agents[0].id

  # Auth flows -- SRP for secure password auth, refresh for session renewal
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # No client secret -- public client for agent SDKs
  generate_secret = false

  # Token validity
  access_token_validity  = 1  # hours
  id_token_validity      = 1  # hours
  refresh_token_validity = 30 # days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# ── User Pool Domain ─────────────────────────────────────────────────────────

resource "aws_cognito_user_pool_domain" "agents" {
  count = var.cognito_enabled ? 1 : 0

  domain       = "${local.prefix}-${local.env}-agents"
  user_pool_id = aws_cognito_user_pool.agents[0].id
}

# ── Resource Server (OAuth2 scopes for MCP Gateway targets) ─────────────────

resource "aws_cognito_resource_server" "gateway_mcp" {
  count = var.cognito_enabled ? 1 : 0

  user_pool_id = aws_cognito_user_pool.agents[0].id
  identifier   = "${local.prefix}-${local.env}-agentcore-mcp"
  name         = "${local.prefix}-${local.env} AgentCore MCP Resources"

  scope {
    scope_name        = "mcp.invoke"
    scope_description = "Invoke MCP server tools via Gateway"
  }

  scope {
    scope_name        = "runtime.access"
    scope_description = "Access AgentCore Runtimes"
  }
}

# ── M2M App Client (Gateway→Runtime OAuth2 client_credentials) ──────────────

resource "aws_cognito_user_pool_client" "gateway_m2m" {
  count = var.cognito_enabled ? 1 : 0

  name         = "${local.prefix}-${local.env}-gateway-m2m"
  user_pool_id = aws_cognito_user_pool.agents[0].id

  generate_secret = true # Required for client_credentials grant

  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes = [
    "${aws_cognito_resource_server.gateway_mcp[0].identifier}/mcp.invoke",
    "${aws_cognito_resource_server.gateway_mcp[0].identifier}/runtime.access",
  ]

  access_token_validity = 1
  token_validity_units {
    access_token = "hours"
  }

  depends_on = [aws_cognito_resource_server.gateway_mcp]
}

# ── SSM Parameters (auto-store M2M credentials for OAuth2 provider) ─────────

resource "aws_ssm_parameter" "m2m_client_id" {
  count = var.cognito_enabled ? 1 : 0

  name  = "${var.ssm_root_path}/gateway/oauth/mcp-gateway/client-id"
  type  = "SecureString"
  value = aws_cognito_user_pool_client.gateway_m2m[0].id

  tags = merge(var.tags, {
    Name      = "gateway-m2m-client-id"
    Module    = "agentcore"
    Component = "oauth2"
  })
}

resource "aws_ssm_parameter" "m2m_client_secret" {
  count = var.cognito_enabled ? 1 : 0

  name  = "${var.ssm_root_path}/gateway/oauth/mcp-gateway/client-secret"
  type  = "SecureString"
  value = aws_cognito_user_pool_client.gateway_m2m[0].client_secret

  tags = merge(var.tags, {
    Name      = "gateway-m2m-client-secret"
    Module    = "agentcore"
    Component = "oauth2"
  })
}
