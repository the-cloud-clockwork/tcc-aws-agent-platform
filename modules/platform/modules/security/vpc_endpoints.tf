# ──────────────────────────────────────────────────────────────────────────────
# Security Sub-Module -- VPC Endpoints
#
# Gateway endpoints (free): S3, DynamoDB
# Interface endpoints: SQS, ECR API, ECR DKR, CloudWatch Logs,
#                      Secrets Manager, KMS, STS, SSM, Bedrock, Bedrock Runtime
#
# Each interface endpoint gets a dedicated security group allowing HTTPS (443)
# inbound from the VPC CIDR block.
# ──────────────────────────────────────────────────────────────────────────────

# ── Route tables for gateway endpoints ───────────────────────────────────────

data "aws_route_tables" "private" {
  vpc_id = var.vpc_id

  filter {
    name   = "association.subnet-id"
    values = var.private_subnet_ids
  }
}

# ── Gateway Endpoints (free) ─────────────────────────────────────────────────

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.private.ids
  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.environment}-s3-endpoint"
  })
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${local.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.private.ids
  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.environment}-dynamodb-endpoint"
  })
}

# ── Interface Endpoints ──────────────────────────────────────────────────────

locals {
  interface_endpoints = {
    sqs               = "com.amazonaws.${local.region}.sqs"
    ecr_api           = "com.amazonaws.${local.region}.ecr.api"
    ecr_dkr           = "com.amazonaws.${local.region}.ecr.dkr"
    logs              = "com.amazonaws.${local.region}.logs"
    secretsmanager    = "com.amazonaws.${local.region}.secretsmanager"
    kms               = "com.amazonaws.${local.region}.kms"
    sts               = "com.amazonaws.${local.region}.sts"
    ssm               = "com.amazonaws.${local.region}.ssm"
    bedrock           = "com.amazonaws.${local.region}.bedrock"
    bedrock_runtime   = "com.amazonaws.${local.region}.bedrock-runtime"
    bedrock_agentcore = "com.amazonaws.${local.region}.bedrock-agentcore"
  }
}

resource "aws_security_group" "vpc_endpoint" {
  for_each = local.interface_endpoints

  name        = "${var.resource_prefix}-${var.environment}-vpce-${each.key}"
  description = "Allow HTTPS from VPC CIDR to ${each.key} VPC endpoint"
  vpc_id      = var.vpc_id
  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.environment}-vpce-${each.key}"
  })

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = var.vpc_id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]

  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.environment}-${each.key}-endpoint"
  })
}
