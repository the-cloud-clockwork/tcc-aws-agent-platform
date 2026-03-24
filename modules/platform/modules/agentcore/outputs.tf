# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

# ── Gateway ──────────────────────────────────────────────────────────────────

output "gateway_id" {
  description = "ID of the AgentCore Gateway."
  value       = aws_bedrockagentcore_gateway.this.gateway_id
}

output "gateway_url" {
  description = "URL endpoint of the AgentCore Gateway."
  value       = aws_bedrockagentcore_gateway.this.gateway_url
}

output "gateway_arn" {
  description = "ARN of the AgentCore Gateway."
  value       = aws_bedrockagentcore_gateway.this.gateway_arn
}

output "gateway_role_arn" {
  description = "ARN of the IAM role used by the AgentCore Gateway."
  value       = aws_iam_role.gateway.arn
}

# ── Memory ───────────────────────────────────────────────────────────────────

output "memory_id" {
  description = "ID of the AgentCore Memory resource."
  value       = aws_bedrockagentcore_memory.this.id
}

output "memory_arn" {
  description = "ARN of the AgentCore Memory resource."
  value       = aws_bedrockagentcore_memory.this.arn
}

# ── Builtin Tools ────────────────────────────────────────────────────────────

output "code_interpreter_id" {
  description = "ID of the Code Interpreter builtin tool. Empty string if disabled."
  value       = var.code_interpreter_enabled ? aws_bedrockagentcore_code_interpreter.this[0].code_interpreter_id : ""
}

output "browser_id" {
  description = "ID of the Browser builtin tool. Empty string if disabled."
  value       = var.browser_enabled ? aws_bedrockagentcore_browser.this[0].browser_id : ""
}

# ── Cognito ──────────────────────────────────────────────────────────────────

output "cognito_user_pool_id" {
  description = "ID of the Cognito user pool. Empty string if Cognito is disabled."
  value       = var.cognito_enabled ? aws_cognito_user_pool.agents[0].id : ""
}

output "cognito_client_id" {
  description = "ID of the Cognito user pool client. Empty string if Cognito is disabled."
  value       = var.cognito_enabled ? aws_cognito_user_pool_client.agents[0].id : ""
}

output "cognito_domain" {
  description = "Cognito user pool domain. Empty string if Cognito is disabled."
  value       = var.cognito_enabled ? aws_cognito_user_pool_domain.agents[0].domain : ""
}

# ── OAuth2 MCP Gateway ─────────────────────────────────────────────────────

output "mcp_oauth2_provider_arn" {
  description = "ARN of the OAuth2 credential provider for Gateway-to-MCP-Runtime auth. Empty if Cognito disabled."
  value       = var.cognito_enabled ? aws_bedrockagentcore_oauth2_credential_provider.gateway_mcp[0].credential_provider_arn : ""
}

output "mcp_oauth2_scopes" {
  description = "OAuth2 scopes for MCP Gateway targets. Empty list if Cognito disabled."
  value = var.cognito_enabled ? [
    "${aws_cognito_resource_server.gateway_mcp[0].identifier}/mcp.invoke",
    "${aws_cognito_resource_server.gateway_mcp[0].identifier}/runtime.access",
  ] : []
}

output "mcp_oauth2_discovery_url" {
  description = "OIDC discovery URL for MCP Runtime JWT authorizer. Empty if Cognito disabled."
  value       = var.cognito_enabled ? "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.agents[0].id}/.well-known/openid-configuration" : ""
}

output "mcp_oauth2_allowed_clients" {
  description = "Allowed client IDs for MCP Runtime JWT authorizer (user + M2M). Empty if Cognito disabled."
  value = var.cognito_enabled ? [
    aws_cognito_user_pool_client.agents[0].id,
    aws_cognito_user_pool_client.gateway_m2m[0].id,
  ] : []
}
