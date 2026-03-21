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
