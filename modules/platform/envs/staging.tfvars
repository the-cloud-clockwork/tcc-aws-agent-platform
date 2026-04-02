environment     = "staging"
resource_prefix = "platform"
aws_region      = "eu-west-1"
bedrock_region  = "us-west-2"
ssm_root_path   = "/platform/staging"

# Network (externally managed — provide IDs from the networking project)
# Required: vpc_id, private_subnet_ids, agent_security_group_id, mcp_security_group_id
# Optional: public_subnet_ids, isolated_subnet_ids
vpc_id                  = "vpc-REPLACE_ME"
private_subnet_ids      = ["subnet-REPLACE_ME_1", "subnet-REPLACE_ME_2"]
agent_security_group_id = "sg-REPLACE_ME"
mcp_security_group_id   = "sg-REPLACE_ME"

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
