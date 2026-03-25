## -----------------------------------------------------
## Platform Module -- Root Composition
## Wires all sub-modules into a single deployable unit.
## Domain repos consume this as:
##   source = "git::repo.git//modules/platform?ref=v1.0.0"
## -----------------------------------------------------

module "network" {
  source = "./modules/network"

  resource_prefix    = var.resource_prefix
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  nat_gateway_count  = var.nat_gateway_count
  tags               = local.tags
}

module "security" {
  source = "./modules/security"

  resource_prefix              = var.resource_prefix
  environment                  = var.environment
  kms_key_deletion_window_days = var.kms_key_deletion_window_days
  waf_enabled                  = var.waf_enabled
  waf_rate_limit               = var.waf_rate_limit
  waf_ip_whitelist             = var.waf_ip_whitelist
  vpc_id                       = module.network.vpc_id
  vpc_cidr_block               = module.network.vpc_cidr_block
  private_subnet_ids           = module.network.private_subnet_ids
  tags                         = local.tags
}

module "data" {
  source = "./modules/data"

  resource_prefix                = var.resource_prefix
  environment                    = var.environment
  account_id                     = local.account_id
  data_kms_key_arn               = module.security.data_kms_key_arn
  storage_kms_key_arn            = module.security.storage_kms_key_arn
  platform_artifacts_kms_key_arn = module.security.platform_artifacts_kms_key_arn
  domain_artifacts_kms_key_arn   = module.security.domain_artifacts_kms_key_arn
  dynamodb_billing_mode          = var.dynamodb_billing_mode
  dynamodb_read_capacity         = var.dynamodb_read_capacity
  dynamodb_write_capacity        = var.dynamodb_write_capacity
  cloudfront_enabled             = var.cloudfront_enabled
  waf_acl_arn                    = module.security.waf_acl_arn
  removal_policy_destroy         = var.removal_policy_destroy
  tags                           = local.tags
}

module "agentcore" {
  source = "./modules/agentcore"

  resource_prefix                 = var.resource_prefix
  environment                     = var.environment
  account_id                      = local.account_id
  aws_region                      = var.aws_region
  gateway_auth_type               = var.gateway_auth_type
  gateway_jwt_discovery_url       = var.gateway_jwt_discovery_url
  gateway_jwt_allowed_clients     = var.gateway_jwt_allowed_clients
  memory_event_expiry_days        = var.memory_event_expiry_days
  memory_description              = var.memory_description
  memory_kms_key_arn              = module.security.data_kms_key_arn
  gateway_kms_key_arn             = module.security.data_kms_key_arn
  ssm_root_path                   = var.ssm_root_path
  cognito_enabled                 = var.cognito_enabled
  code_interpreter_enabled        = var.builtin_code_interpreter_enabled
  browser_enabled                 = var.builtin_browser_enabled
  artifacts_mcp_lambda_arn        = module.api.mcp_tools_lambda_arn
  enable_artifacts_gateway_target = true
  tags                            = local.tags
}

module "observability" {
  source = "./modules/observability"

  resource_prefix    = var.resource_prefix
  environment        = var.environment
  log_retention_days = var.log_retention_days
  sns_alert_email    = var.sns_alert_email
  kms_key_arn        = module.security.data_kms_key_arn
  tags               = local.tags
}

module "api" {
  source = "./modules/api"

  resource_prefix                = var.resource_prefix
  environment                    = var.environment
  artifacts_table_name           = module.data.table_names["artifacts"]
  artifacts_table_arn            = module.data.table_arns["artifacts"]
  artifacts_bucket_name          = module.data.artifacts_bucket_name
  artifacts_bucket_arn           = module.data.artifacts_bucket_arn
  platform_artifacts_kms_key_arn = module.security.platform_artifacts_kms_key_arn
  domain_artifacts_kms_key_arn   = module.security.domain_artifacts_kms_key_arn
  data_kms_key_arn               = module.security.data_kms_key_arn
  api_throttle_rate              = var.api_throttle_rate
  api_throttle_burst             = var.api_throttle_burst
  api_cors_origins               = var.api_cors_origins
  waf_acl_arn                    = module.security.waf_acl_arn
  waf_enabled                    = var.waf_enabled
  artifact_queue_url             = module.data.artifact_queue_url
  artifact_queue_arn             = module.data.artifact_queue_arn
  tags                           = local.tags
}

# -- Prompt Registry (AI-DLC: prompts as first-class artifacts) --

module "prompt_registry" {
  source = "./modules/prompt_registry"

  resource_prefix     = var.resource_prefix
  environment         = var.environment
  prompt_table_name   = module.data.table_names["prompt_registry"]
  prompt_table_arn    = module.data.table_arns["prompt_registry"]
  prompt_bucket_name  = module.data.bucket_names["prompt_registry"]
  prompt_bucket_arn   = module.data.prompt_registry_bucket_arn
  storage_kms_key_arn = module.security.storage_kms_key_arn
  tags                = local.tags
}
