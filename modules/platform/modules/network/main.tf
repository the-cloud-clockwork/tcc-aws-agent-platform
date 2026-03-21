## -----------------------------------------------------
## Network Sub-Module — VPC, Subnets, NAT, Security Groups
##
## Replaces: CDK NetworkStack
## Creates a 3-tier VPC: public, private (NAT egress), isolated (no internet).
## -----------------------------------------------------

# -------------------------------------------------------
# Data Sources
# -------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

# -------------------------------------------------------
# Locals
# -------------------------------------------------------

locals {
  # Use provided AZs or auto-discover from the region
  azs      = length(var.availability_zones) > 0 ? var.availability_zones : data.aws_availability_zones.available.names
  az_count = length(local.azs)

  # CIDR allocation — 3 tiers x N AZs
  # /16 split into /20s gives 16 subnets per tier, more than enough for any AZ count.
  # Tier layout: public=[0..N-1], private=[N..2N-1], isolated=[2N..3N-1]
  public_subnets   = { for i, az in local.azs : az => cidrsubnet(var.vpc_cidr, 4, i) }
  private_subnets  = { for i, az in local.azs : az => cidrsubnet(var.vpc_cidr, 4, i + local.az_count) }
  isolated_subnets = { for i, az in local.azs : az => cidrsubnet(var.vpc_cidr, 4, i + local.az_count * 2) }

  # Clamp NAT count to the number of AZs
  nat_count = min(var.nat_gateway_count, local.az_count)

  # Map each private subnet to a NAT gateway index (round-robin)
  nat_az_keys = slice(keys(local.public_subnets), 0, local.nat_count)

  tags = merge(var.tags, {
    Module = "network"
  })
}

# -------------------------------------------------------
# VPC
# -------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-vpc"
  })
}

# -------------------------------------------------------
# Internet Gateway
# -------------------------------------------------------

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-igw"
  })
}

# -------------------------------------------------------
# Public Subnets
# -------------------------------------------------------

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = true

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-public-${each.key}"
    Tier = "public"
  })
}

# -------------------------------------------------------
# Private Subnets (NAT egress)
# -------------------------------------------------------

resource "aws_subnet" "private" {
  for_each = local.private_subnets

  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value
  availability_zone = each.key

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-private-${each.key}"
    Tier = "private"
  })
}

# -------------------------------------------------------
# Isolated Subnets (no internet access)
# -------------------------------------------------------

resource "aws_subnet" "isolated" {
  for_each = local.isolated_subnets

  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value
  availability_zone = each.key

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-isolated-${each.key}"
    Tier = "isolated"
  })
}

# -------------------------------------------------------
# NAT Gateways + Elastic IPs
# -------------------------------------------------------

resource "aws_eip" "nat" {
  for_each = toset(local.nat_az_keys)

  domain = "vpc"

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-nat-eip-${each.key}"
  })
}

resource "aws_nat_gateway" "main" {
  for_each = toset(local.nat_az_keys)

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-nat-${each.key}"
  })

  depends_on = [aws_internet_gateway.main]
}

# -------------------------------------------------------
# Route Tables — Public (→ IGW)
# -------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-rt-public"
    Tier = "public"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# -------------------------------------------------------
# Route Tables — Private (→ NAT)
# One route table per AZ to allow AZ-local NAT routing
# -------------------------------------------------------

resource "aws_route_table" "private" {
  for_each = local.private_subnets

  vpc_id = aws_vpc.main.id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-rt-private-${each.key}"
    Tier = "private"
  })
}

resource "aws_route" "private_nat" {
  for_each = local.private_subnets

  route_table_id         = aws_route_table.private[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  # Round-robin: map each private subnet's AZ to a NAT gateway
  nat_gateway_id = aws_nat_gateway.main[local.nat_az_keys[index(keys(local.private_subnets), each.key) % local.nat_count]].id
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

# -------------------------------------------------------
# Route Tables — Isolated (local only, no internet)
# -------------------------------------------------------

resource "aws_route_table" "isolated" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-rt-isolated"
    Tier = "isolated"
  })
}

# No routes added — only the implicit local route exists

resource "aws_route_table_association" "isolated" {
  for_each = aws_subnet.isolated

  subnet_id      = each.value.id
  route_table_id = aws_route_table.isolated.id
}

# -------------------------------------------------------
# Security Groups
# -------------------------------------------------------

# Agent SG: agents initiate all connections, accept none
resource "aws_security_group" "agent" {
  name_prefix = "${var.resource_prefix}-agent-"
  description = "Agent security group — all outbound, no inbound"
  vpc_id      = aws_vpc.main.id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-agent-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "agent_all_out" {
  security_group_id = aws_security_group.agent.id
  description       = "Allow all outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# MCP SG: accepts inbound on 8080 from agents, all outbound
resource "aws_security_group" "mcp" {
  name_prefix = "${var.resource_prefix}-mcp-"
  description = "MCP service security group — inbound 8080 from agents, all outbound"
  vpc_id      = aws_vpc.main.id

  tags = merge(local.tags, {
    Name = "${var.resource_prefix}-mcp-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "mcp_from_agents" {
  security_group_id            = aws_security_group.mcp.id
  description                  = "Allow TCP 8080 from agent security group"
  from_port                    = 8080
  to_port                      = 8080
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.agent.id
}

resource "aws_vpc_security_group_egress_rule" "mcp_all_out" {
  security_group_id = aws_security_group.mcp.id
  description       = "Allow all outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
