data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  name_prefix = "${var.resource_prefix}-${var.environment}"
  ssm_prefix  = var.ssm_root_path

  tags = merge(var.tags, {
    Environment = var.environment
    Project     = var.resource_prefix
    ManagedBy   = "terraform"
  })
}
