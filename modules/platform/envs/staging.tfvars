environment     = "staging"
resource_prefix = "platform"
aws_region      = "eu-west-1"
bedrock_region  = "us-west-2"
ssm_root_path   = "/platform/staging"

# Network
vpc_cidr          = "10.1.0.0/16"
nat_gateway_count = 1

# Security
kms_key_deletion_window_days = 30
waf_enabled                  = true
waf_rate_limit               = 1000

# Data
dynamodb_billing_mode  = "PAY_PER_REQUEST"
cloudfront_enabled     = true
removal_policy_destroy = false

# AgentCore
gateway_auth_type        = "CUSTOM_JWT"
memory_event_expiry_days = 60
cognito_enabled          = true

# Observability
log_retention_days = 30

# API
api_throttle_rate  = 500
api_throttle_burst = 100

tags = {
  CostCenter = "staging"
}
