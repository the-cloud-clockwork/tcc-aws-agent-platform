# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module — Cognito User Pool
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

  # MFA — optional (users can enable if desired)
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

  # Auth flows — SRP for secure password auth, refresh for session renewal
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # No client secret — public client for agent SDKs
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
