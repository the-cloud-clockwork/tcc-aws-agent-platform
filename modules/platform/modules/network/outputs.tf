## -----------------------------------------------------
## Network Sub-Module -- Outputs
## -----------------------------------------------------

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets (one per AZ)"
  value       = [for s in aws_subnet.public : s.id]
}

output "private_subnet_ids" {
  description = "IDs of private subnets with NAT egress (one per AZ)"
  value       = [for s in aws_subnet.private : s.id]
}

output "isolated_subnet_ids" {
  description = "IDs of isolated subnets with no internet access (one per AZ)"
  value       = [for s in aws_subnet.isolated : s.id]
}

output "agent_security_group_id" {
  description = "ID of the agent security group (all outbound, no inbound)"
  value       = aws_security_group.agent.id
}

output "mcp_security_group_id" {
  description = "ID of the MCP service security group (inbound 8080 from agents)"
  value       = aws_security_group.mcp.id
}
