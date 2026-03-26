# ──────────────────────────────────────────────────────────────────────────────
# Data Sources Sub-Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "VPC ID (pass-through)."
  value       = data.aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = data.aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets (Tier=Public)."
  value       = data.aws_subnets.public.ids
}

output "private_subnet_ids" {
  description = "IDs of private subnets with NAT egress (Tier=Private)."
  value       = data.aws_subnets.private.ids
}
