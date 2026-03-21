# ──────────────────────────────────────────────────────────────────────────────
# Data Sub-Module — DynamoDB Tables & SQS Queues
#
# Replaces CDK DataStack. Creates the five core DynamoDB tables and the
# artifact notification queue with dead-letter queue.
# ──────────────────────────────────────────────────────────────────────────────

# ── Locals ───────────────────────────────────────────────────────────────────

locals {
  # Table definitions: key → schema. Used with for_each to avoid repetition.
  tables = {
    artifacts = {
      hash_key  = "artifact_id"
      range_key = "created_at"
      ttl_field = null
    }
    audit_log = {
      hash_key  = "event_id"
      range_key = "timestamp"
      ttl_field = null
    }
    prompt_registry = {
      hash_key  = "prompt_key"
      range_key = "version"
      ttl_field = null
    }
    run_history = {
      hash_key  = "run_id"
      range_key = "started_at"
      ttl_field = null
    }
    idempotency = {
      hash_key  = "idempotency_key"
      range_key = null
      ttl_field = "expires_at"
    }
  }

  is_provisioned = var.dynamodb_billing_mode == "PROVISIONED"
}

# ── DynamoDB Tables ──────────────────────────────────────────────────────────

resource "aws_dynamodb_table" "tables" {
  for_each = local.tables

  name         = "${var.resource_prefix}-${var.environment}-${each.key}"
  billing_mode = var.dynamodb_billing_mode

  # Provisioned capacity (ignored when PAY_PER_REQUEST)
  read_capacity  = local.is_provisioned ? var.dynamodb_read_capacity : null
  write_capacity = local.is_provisioned ? var.dynamodb_write_capacity : null

  # Hash key (partition key) — always a string
  hash_key = each.value.hash_key

  # Range key (sort key) — optional
  range_key = each.value.range_key

  # Hash key attribute definition
  attribute {
    name = each.value.hash_key
    type = "S"
  }

  # Range key attribute definition (only when present)
  dynamic "attribute" {
    for_each = each.value.range_key != null ? [each.value.range_key] : []
    content {
      name = attribute.value
      type = "S"
    }
  }

  # TTL configuration (only for tables that need it)
  dynamic "ttl" {
    for_each = each.value.ttl_field != null ? [each.value.ttl_field] : []
    content {
      attribute_name = ttl.value
      enabled        = true
    }
  }

  # Point-in-time recovery — always enabled
  point_in_time_recovery {
    enabled = true
  }

  # KMS encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.data_kms_key_arn
  }

  # Deletion protection (disabled only when removal_policy_destroy is true)
  deletion_protection_enabled = !var.removal_policy_destroy

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-${each.key}"
    Module    = "data"
    Component = "dynamodb"
    Table     = each.key
  })
}

# ── SQS — Artifact Notification Dead-Letter Queue ───────────────────────────

resource "aws_sqs_queue" "artifact_dlq" {
  name                      = "${var.resource_prefix}-${var.environment}-artifact-notifications-dlq"
  message_retention_seconds = 1209600 # 14 days

  # KMS encryption
  kms_master_key_id                 = var.data_kms_key_arn
  kms_data_key_reuse_period_seconds = 300

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-artifact-notifications-dlq"
    Module    = "data"
    Component = "sqs"
    Role      = "dead-letter-queue"
  })
}

# ── SQS — Artifact Notification Queue ───────────────────────────────────────

resource "aws_sqs_queue" "artifact_notifications" {
  name                       = "${var.resource_prefix}-${var.environment}-artifact-notifications"
  visibility_timeout_seconds = 300

  # KMS encryption
  kms_master_key_id                 = var.data_kms_key_arn
  kms_data_key_reuse_period_seconds = 300

  # Dead-letter queue redrive policy
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.artifact_dlq.arn
    maxReceiveCount     = 3
  })

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-artifact-notifications"
    Module    = "data"
    Component = "sqs"
    Role      = "artifact-notifications"
  })
}
