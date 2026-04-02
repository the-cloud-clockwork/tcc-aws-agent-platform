data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  name_prefix = "${var.resource_prefix}-${var.environment}"
  ssm_prefix  = var.ssm_root_path

  # Environment, Project, and ManagedBy are set via default_tags in
  # providers.tf and apply to all resources automatically.
  tags = var.tags
}

# -- Cross-Variable Validations -------------------------------------

check "jwt_config_complete" {
  assert {
    condition     = var.gateway_auth_type != "CUSTOM_JWT" || (var.gateway_jwt_discovery_url != "" && length(var.gateway_jwt_allowed_clients) > 0)
    error_message = "When gateway_auth_type is CUSTOM_JWT, gateway_jwt_discovery_url and gateway_jwt_allowed_clients must be set."
  }
}

check "api_throttle_burst_gte_rate" {
  assert {
    condition     = var.api_throttle_burst >= var.api_throttle_rate
    error_message = "api_throttle_burst must be >= api_throttle_rate. Burst is the max concurrent requests and should be at least as large as the steady-state rate."
  }
}
