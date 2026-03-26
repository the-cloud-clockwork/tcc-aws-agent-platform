# ──────────────────────────────────────────────────────────────────────────────
# Data Sources Sub-Module
#
# Looks up a pre-existing VPC and its associated subnets by tag convention.
# Input: vpc_id. Everything else is derived.
#
# Expected subnet tags (set by the networking module):
#   Tier = "Public"   → public subnets
#   Tier = "Private"  → private subnets (NAT egress)
# ──────────────────────────────────────────────────────────────────────────────

data "aws_vpc" "main" {
  id = var.vpc_id
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  tags = {
    Tier = "Public"
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  tags = {
    Tier = "Private"
  }
}
