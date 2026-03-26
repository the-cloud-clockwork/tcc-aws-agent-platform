# ──────────────────────────────────────────────────────────────────────────────
# Platform Security Groups
# Agent and MCP security groups for agent-to-service communication.
# ──────────────────────────────────────────────────────────────────────────────

# Agent SG: agents initiate all connections, accept none
resource "aws_security_group" "agent" {
  name_prefix = "${var.resource_prefix}-agent-"
  description = "Agent security group -- all outbound, no inbound"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
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
  description = "MCP service security group -- inbound 8080 from agents, all outbound"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
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
