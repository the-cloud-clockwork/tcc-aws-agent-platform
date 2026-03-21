# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module — Memory
#
# Creates the AgentCore Memory resource with an IAM execution role.
# Memory provides three-tier persistence (short-term, long-term, episodic)
# for agents, with automatic event expiry and KMS encryption.
# ──────────────────────────────────────────────────────────────────────────────

# ── IAM Role: Memory Execution ───────────────────────────────────────────────

data "aws_iam_policy_document" "memory_trust" {
  statement {
    sid     = "AllowBedrockAgentCoreAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.aws_region}:${var.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "memory" {
  name               = "${local.prefix}-${local.env}-memory"
  assume_role_policy = data.aws_iam_policy_document.memory_trust.json

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-memory"
    Module    = "agentcore"
    Component = "memory"
  })
}

# ── AgentCore Memory ─────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_memory" "this" {
  name = "${local.prefix}-${local.env}-memory"

  description = var.memory_description != "" ? var.memory_description : null

  # Event expiry — duration in days
  event_expiry_duration = var.memory_event_expiry_days

  # KMS encryption — only set when a key ARN is provided
  encryption_key_arn = var.memory_kms_key_arn != "" ? var.memory_kms_key_arn : null

  # Execution role for Memory service operations
  memory_execution_role_arn = aws_iam_role.memory.arn

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-memory"
    Module    = "agentcore"
    Component = "memory"
  })
}
