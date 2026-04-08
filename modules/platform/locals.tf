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
# JWT validation moved to gateway resource precondition (hard error, not warning).

check "api_throttle_burst_gt_rate" {
  assert {
    condition     = var.api_throttle_burst > var.api_throttle_rate
    error_message = "api_throttle_burst must be > api_throttle_rate. Burst absorbs traffic spikes above the steady-state rate — they must not be equal."
  }
}
