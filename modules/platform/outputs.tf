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
  name  = "${local.ssm_prefix}/security/platform-artifacts-key-arn"
  type  = "String"
  value = module.security.platform_artifacts_kms_key_arn
  tags  = local.tags
}

resource "aws_ssm_parameter" "kms_domain_artifacts" {
  name  = "${local.ssm_prefix}/security/domain-artifacts-key-arn"
  type  = "String"
  value = module.security.domain_artifacts_kms_key_arn
  tags  = local.tags
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

# Network (derived from data sources)
output "vpc_id" {
  value = module.data_sources.vpc_id
}

output "vpc_cidr_block" {
  value = module.data_sources.vpc_cidr_block
}

output "public_subnet_ids" {
  value = module.data_sources.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.data_sources.private_subnet_ids
}

output "agent_security_group_id" {
  value = module.security.agent_security_group_id
}

output "mcp_security_group_id" {
  value = module.security.mcp_security_group_id
}

# Security
output "platform_artifacts_kms_key_arn" {
  value = module.security.platform_artifacts_kms_key_arn
}

output "domain_artifacts_kms_key_arn" {
  value = module.security.domain_artifacts_kms_key_arn
}

output "data_kms_key_arn" {
  value = module.security.data_kms_key_arn
}

output "storage_kms_key_arn" {
  value = module.security.storage_kms_key_arn
}

output "waf_acl_arn" {
  value = module.security.waf_acl_arn
}

# Data
output "table_names" {
  value = module.data.table_names
}

output "table_arns" {
  value = module.data.table_arns
}

output "artifacts_bucket_name" {
  value = module.data.artifacts_bucket_name
}

output "artifacts_bucket_arn" {
  value = module.data.artifacts_bucket_arn
}

output "codebuild_source_bucket" {
  description = "S3 bucket name for CodeBuild source code uploads. Pass to modules/agents codebuild_source_bucket variable."
  value       = module.data.codebuild_source_bucket_name
}

output "bucket_names" {
  value = module.data.bucket_names
}

output "cloudfront_domain" {
  value = module.data.cloudfront_domain
}

output "cloudfront_distribution_arn" {
  value = module.data.cloudfront_distribution_arn
}

output "artifact_queue_url" {
  value = module.data.artifact_queue_url
}

# AgentCore
output "gateway_id" {
  value = module.agentcore.gateway_id
}

output "gateway_url" {
  value = module.agentcore.gateway_url
}

output "gateway_arn" {
  value = module.agentcore.gateway_arn
}

output "gateway_role_arn" {
  value = module.agentcore.gateway_role_arn
}

output "memory_id" {
  value = module.agentcore.memory_id
}

output "memory_arn" {
  value = module.agentcore.memory_arn
}

output "code_interpreter_id" {
  value = module.agentcore.code_interpreter_id
}

output "browser_id" {
  value = module.agentcore.browser_id
}

output "cognito_user_pool_id" {
  value = module.agentcore.cognito_user_pool_id
}

output "cognito_client_id" {
  value = module.agentcore.cognito_client_id
}

output "mcp_oauth2_provider_arn" {
  value = module.agentcore.mcp_oauth2_provider_arn
}

output "mcp_oauth2_scopes" {
  value = module.agentcore.mcp_oauth2_scopes
}

output "mcp_oauth2_discovery_url" {
  value = module.agentcore.mcp_oauth2_discovery_url
}

output "mcp_oauth2_allowed_clients" {
  value = module.agentcore.mcp_oauth2_allowed_clients
}

# Observability
output "alert_topic_arn" {
  value = module.observability.alert_topic_arn
}

output "pipeline_log_group_name" {
  value = module.observability.pipeline_log_group_name
}

# API
output "api_url" {
  value = module.api.api_url
}

output "prompt_registry_url" {
  value = module.prompt_registry.prompt_registry_url
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
