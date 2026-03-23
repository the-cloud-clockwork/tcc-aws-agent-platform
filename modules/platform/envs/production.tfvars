environment     = "production"
resource_prefix = "platform"
aws_region      = "eu-west-1"
bedrock_region  = "us-west-2"
ssm_root_path   = "/platform/production"

# Network
vpc_cidr          = "10.2.0.0/16"
nat_gateway_count = 2

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
api_throttle_burst = 100

tags = {
  CostCenter = "production"
}
