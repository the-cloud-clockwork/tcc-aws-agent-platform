environment     = "production"
resource_prefix = "platform"
aws_region      = "eu-west-1"
bedrock_region  = "us-west-2"
ssm_root_path   = "/platform/production"

# Network (VPC and subnets are externally managed — provide IDs from the networking project)
# Security groups (Agent SG, MCP SG) are created by this module.
# Required: vpc_id, private_subnet_ids
# Optional: public_subnet_ids, isolated_subnet_ids
vpc_id             = "vpc-REPLACE_ME"
private_subnet_ids = ["subnet-REPLACE_ME_1", "subnet-REPLACE_ME_2"]

# Security
kms_key_deletion_window_days = 30
waf_enabled                  = true
waf_rate_limit               = 500

# Data
dynamodb_billing_mode   = "PROVISIONED"
dynamodb_read_capacity  = 25
dynamodb_write_capacity = 10
cloudfront_enabled      = true
removal_policy_destroy  = false

# AgentCore
gateway_auth_type        = "CUSTOM_JWT"
memory_event_expiry_days = 90
cognito_enabled          = true

# Observability
log_retention_days = 90

# API
api_throttle_rate  = 500
api_throttle_burst = 500

tags = {
  CostCenter = "production"
}
