data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name
  name_prefix = "${var.resource_prefix}-${var.environment}"

  workflow_files = fileset(var.workflow_dir, "*.yaml")

  workflows = {
    for f in local.workflow_files :
    yamldecode(file("${var.workflow_dir}/${f}")).id => yamldecode(file("${var.workflow_dir}/${f}"))
  }

  tags = merge(var.tags, {
    Module = "workflows"
  })
}
