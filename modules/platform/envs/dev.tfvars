environment     = "dev"
resource_prefix = "platform"
aws_region      = "eu-west-1"
bedrock_region  = "us-west-2"
ssm_root_path   = "/platform/dev"

# Network (VPC and subnets are externally managed — provide IDs from the networking project)
# Security groups (Agent SG, MCP SG) are created by this module.
# Required: vpc_id, private_subnet_ids
# Optional: public_subnet_ids, isolated_subnet_ids
vpc_id             = "vpc-REPLACE_ME"
private_subnet_ids = ["subnet-REPLACE_ME_1", "subnet-REPLACE_ME_2"]

# Security
kms_key_deletion_window_days = 7
waf_enabled                  = false

# Data
dynamodb_billing_mode  = "PAY_PER_REQUEST"
cloudfront_enabled     = true
removal_policy_destroy = true

# AgentCore
gateway_auth_type        = "AWS_IAM"
memory_event_expiry_days = 30
cognito_enabled          = false

# Observability
log_retention_days = 14
sns_alert_email    = ""

# API
api_throttle_rate  = 100
api_throttle_burst = 200
api_cors_origins   = ["http://localhost:3000"]

tags = {
  CostCenter = "development"
}

guardrail_enabled = false
