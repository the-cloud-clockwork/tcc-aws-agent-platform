## -----------------------------------------------------
## Platform Module -- Outputs
## SSM parameters + Terraform outputs for cross-module use.
## -----------------------------------------------------

# -- SSM Parameters --------------------------------------------------

resource "aws_ssm_parameter" "vpc_id" {
  name  = "${local.ssm_prefix}/network/vpc-id"
  type  = "String"
  value = var.vpc_id
  tags  = local.tags
}

resource "aws_ssm_parameter" "gateway_url" {
  name  = "${local.ssm_prefix}/agentcore/gateway-url"
  type  = "String"
  value = module.agentcore.gateway_url
  tags  = local.tags
}

resource "aws_ssm_parameter" "gateway_id" {
  name  = "${local.ssm_prefix}/agentcore/gateway-id"
  type  = "String"
  value = module.agentcore.gateway_id
  tags  = local.tags
}

resource "aws_ssm_parameter" "memory_id" {
  name  = "${local.ssm_prefix}/agentcore/memory-id"
  type  = "String"
  value = module.agentcore.memory_id
  tags  = local.tags
}

resource "aws_ssm_parameter" "table_names" {
  for_each = module.data.table_names

  name  = "${local.ssm_prefix}/tables/${each.key}/name"
  type  = "String"
  value = each.value
  tags  = local.tags
}

resource "aws_ssm_parameter" "table_arns" {
  for_each = module.data.table_arns

  name  = "${local.ssm_prefix}/tables/${each.key}/arn"
  type  = "String"
  value = each.value
  tags  = local.tags
}

resource "aws_ssm_parameter" "bucket_names" {
  for_each = module.data.bucket_names

  name  = "${local.ssm_prefix}/buckets/${each.key}/name"
  type  = "String"
  value = each.value
  tags  = local.tags
}

resource "aws_ssm_parameter" "kms_platform_artifacts" {
  name   = "${local.ssm_prefix}/security/platform-artifacts-key-arn"
  type   = "SecureString"
  key_id = module.security.secrets_kms_key_arn
  value  = module.security.platform_artifacts_kms_key_arn
  tags   = local.tags
}

resource "aws_ssm_parameter" "kms_domain_artifacts" {
  name   = "${local.ssm_prefix}/security/domain-artifacts-key-arn"
  type   = "SecureString"
  key_id = module.security.secrets_kms_key_arn
  value  = module.security.domain_artifacts_kms_key_arn
  tags   = local.tags
}

resource "aws_ssm_parameter" "alert_topic_arn" {
  name  = "${local.ssm_prefix}/observability/alert-topic-arn"
  type  = "String"
  value = module.observability.alert_topic_arn
  tags  = local.tags
}

resource "aws_ssm_parameter" "api_url" {
  name  = "${local.ssm_prefix}/api/artifacts-api-url"
  type  = "String"
  value = module.api.api_url
  tags  = local.tags
}

resource "aws_ssm_parameter" "prompt_registry_url" {
  name  = "${local.ssm_prefix}/prompt-registry/url"
  type  = "String"
  value = module.prompt_registry.prompt_registry_url
  tags  = local.tags
}

resource "aws_ssm_parameter" "cloudfront_domain" {
  count = var.cloudfront_enabled ? 1 : 0

  name  = "${local.ssm_prefix}/cdn/cloudfront-domain"
  type  = "String"
  value = module.data.cloudfront_domain
  tags  = local.tags
}

# -- Terraform Outputs -----------------------------------------------

# Network (pass-through from externally managed resources)
output "vpc_id" {
  description = "VPC ID where platform resources are deployed."
  value       = var.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (pass-through from input)."
  value       = var.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs with NAT egress."
  value       = var.private_subnet_ids
}

output "isolated_subnet_ids" {
  description = "Isolated subnet IDs with no internet access."
  value       = var.isolated_subnet_ids
}

output "agent_security_group_id" {
  description = "Security group ID for agent runtimes (all outbound, TCP 9000 A2A inbound)."
  value       = aws_security_group.agent.id
}

output "mcp_security_group_id" {
  description = "Security group ID for MCP servers (TCP 8080 from agents)."
  value       = aws_security_group.mcp.id
}

# Security
output "platform_artifacts_kms_key_arn" {
  description = "KMS key ARN for platform-tier artifact encryption."
  value       = module.security.platform_artifacts_kms_key_arn
}

output "domain_artifacts_kms_key_arn" {
  description = "KMS key ARN for domain-tier artifact encryption."
  value       = module.security.domain_artifacts_kms_key_arn
}

output "data_kms_key_arn" {
  description = "KMS key ARN for DynamoDB and SQS encryption."
  value       = module.security.data_kms_key_arn
}

output "storage_kms_key_arn" {
  description = "KMS key ARN for general S3 storage encryption."
  value       = module.security.storage_kms_key_arn
}

output "waf_acl_arn" {
  description = "WAF Web ACL ARN. Empty when waf_enabled is false."
  value       = module.security.waf_acl_arn
}

# Data
output "table_names" {
  description = "Map of DynamoDB table logical names to physical names."
  value       = module.data.table_names
}

output "table_arns" {
  description = "Map of DynamoDB table logical names to ARNs."
  value       = module.data.table_arns
}

output "artifacts_bucket_name" {
  description = "S3 artifacts bucket name."
  value       = module.data.artifacts_bucket_name
}

output "artifacts_bucket_arn" {
  description = "S3 artifacts bucket ARN."
  value       = module.data.artifacts_bucket_arn
}

output "codebuild_source_bucket" {
  description = "S3 bucket name for CodeBuild source code uploads. Pass to modules/agents codebuild_source_bucket variable."
  value       = module.data.codebuild_source_bucket_name
}

output "bucket_names" {
  description = "Map of S3 bucket logical names to physical names."
  value       = module.data.bucket_names
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name. Empty when cloudfront_enabled is false."
  value       = module.data.cloudfront_domain
}

output "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN. Empty when cloudfront_enabled is false."
  value       = module.data.cloudfront_distribution_arn
}

output "artifact_queue_url" {
  description = "SQS artifact processing queue URL."
  value       = module.data.artifact_queue_url
}

# AgentCore
output "gateway_id" {
  description = "AgentCore Gateway ID."
  value       = module.agentcore.gateway_id
}

output "gateway_url" {
  description = "AgentCore Gateway MCP endpoint URL."
  value       = module.agentcore.gateway_url
}

output "gateway_arn" {
  description = "AgentCore Gateway ARN."
  value       = module.agentcore.gateway_arn
}

output "gateway_role_arn" {
  description = "IAM role ARN used by the AgentCore Gateway."
  value       = module.agentcore.gateway_role_arn
}

output "memory_id" {
  description = "AgentCore Memory resource ID."
  value       = module.agentcore.memory_id
}

output "memory_arn" {
  description = "AgentCore Memory resource ARN."
  value       = module.agentcore.memory_arn
}

output "code_interpreter_id" {
  description = "AgentCore Code Interpreter builtin tool ID. Empty when disabled."
  value       = module.agentcore.code_interpreter_id
}

output "browser_id" {
  description = "AgentCore Browser builtin tool ID. Empty when disabled."
  value       = module.agentcore.browser_id
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID. Empty when cognito_enabled is false."
  value       = module.agentcore.cognito_user_pool_id
}

output "cognito_client_id" {
  description = "Cognito App Client ID. Empty when cognito_enabled is false."
  value       = module.agentcore.cognito_client_id
}

output "mcp_oauth2_provider_arn" {
  description = "AgentCore OAuth2 credential provider ARN for MCP Gateway auth."
  value       = module.agentcore.mcp_oauth2_provider_arn
}

output "mcp_oauth2_scopes" {
  description = "OAuth2 scopes for MCP Gateway authentication."
  value       = module.agentcore.mcp_oauth2_scopes
}

output "mcp_oauth2_discovery_url" {
  description = "OAuth2 discovery URL for MCP Gateway authentication."
  value       = module.agentcore.mcp_oauth2_discovery_url
}

output "mcp_oauth2_allowed_clients" {
  description = "Allowed OAuth2 client IDs for MCP Gateway authentication."
  value       = module.agentcore.mcp_oauth2_allowed_clients
}

# Observability
output "alert_topic_arn" {
  description = "SNS alert topic ARN for operational notifications."
  value       = module.observability.alert_topic_arn
}

output "pipeline_log_group_name" {
  description = "CloudWatch log group name for pipeline logs."
  value       = module.observability.pipeline_log_group_name
}

# API
output "api_url" {
  description = "API Gateway URL for the artifacts REST API."
  value       = module.api.api_url
}

output "prompt_registry_url" {
  description = "Lambda function URL for the prompt registry."
  value       = module.prompt_registry.prompt_registry_url
}

output "prompt_registry_function_arn" {
  description = "ARN of the Prompt Registry Lambda function. Pass to modules/agents for IAM."
  value       = module.prompt_registry.prompt_registry_lambda_arn
}

output "prompt_registry_function_name" {
  description = "Name of the Prompt Registry Lambda function. Pass to modules/agents for direct invocation."
  value       = module.prompt_registry.prompt_registry_lambda_name
}

output "artifacts_mcp_lambda_arn" {
  description = "ARN of the artifacts MCP tools Lambda (for Gateway target registration)"
  value       = module.api.mcp_tools_lambda_arn
}

output "artifacts_mcp_lambda_name" {
  description = "Name of the artifacts MCP tools Lambda"
  value       = module.api.mcp_tools_lambda_name
}


output "guardrail_id" {
  description = "Bedrock Guardrail ID for PII/content protection. Empty when disabled."
  value       = module.security.guardrail_id
}

output "guardrail_version" {
  description = "Published Bedrock Guardrail version number. Empty when disabled."
  value       = module.security.guardrail_version
}

output "secrets_kms_key_arn" {
  description = "KMS key ARN for Secrets Manager encryption."
  value       = module.security.secrets_kms_key_arn
}

# Direct MCP bypass (AWS Issue #809)
output "mcp_m2m_client_id" {
  description = "Cognito M2M client ID for direct MCP auth (AWS Issue #809 workaround)."
  value       = module.agentcore.mcp_m2m_client_id
  sensitive   = true
}
output "mcp_m2m_client_secret" {
  description = "Cognito M2M client secret for direct MCP auth."
  value       = module.agentcore.mcp_m2m_client_secret
  sensitive   = true
}
output "cognito_token_url" {
  description = "Cognito token endpoint URL for M2M OAuth2 flows."
  value       = module.agentcore.cognito_token_url
}
