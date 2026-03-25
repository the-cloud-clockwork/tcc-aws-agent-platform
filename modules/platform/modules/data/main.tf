# ──────────────────────────────────────────────────────────────────────────────
# Data Sub-Module -- DynamoDB Tables & SQS Queues
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
      range_key = null
      ttl_field = null
      gsis = [
        { name = "type-created_at-index", hash_key = "type", range_key = "created_at" },
        { name = "agent_id-created_at-index", hash_key = "agent_id", range_key = "created_at" },
        { name = "execution_id-agent_id-index", hash_key = "execution_id", range_key = "agent_id" }
      ]
    }
    audit_log = {
      hash_key  = "event_id"
      range_key = "timestamp"
      ttl_field = null
      gsis = [
        { name = "agent_id-timestamp-index", hash_key = "agent_id", range_key = "timestamp" }
      ]
    }
    prompt_registry = {
      hash_key  = "prompt_key"
      range_key = "version"
      ttl_field = null
      gsis      = []
    }
    run_history = {
      hash_key  = "run_id"
      range_key = "started_at"
      ttl_field = null
      gsis = [
        { name = "agent_id-started_at-index", hash_key = "agent_id", range_key = "started_at" },
        { name = "status-started_at-index", hash_key = "status", range_key = "started_at" }
      ]
    }
    idempotency = {
      hash_key  = "idempotency_key"
      range_key = null
      ttl_field = "expires_at"
      gsis      = []
    }
  }

  is_provisioned = var.dynamodb_billing_mode == "PROVISIONED"

  # Collect all unique attribute names per table (table keys + GSI keys).
  # DynamoDB requires each attribute used in any key to be defined exactly once.
  table_attributes = {
    for table_key, table in local.tables :
    table_key => distinct(concat(
      [table.hash_key],
      table.range_key != null ? [table.range_key] : [],
      flatten([for gsi in table.gsis : [gsi.hash_key, gsi.range_key]])
    ))
  }
}

# ── DynamoDB Tables ──────────────────────────────────────────────────────────

resource "aws_dynamodb_table" "tables" {
  for_each = local.tables

  name         = "${var.resource_prefix}-${var.environment}-${each.key}"
  billing_mode = var.dynamodb_billing_mode

  # Provisioned capacity (ignored when PAY_PER_REQUEST)
  read_capacity  = local.is_provisioned ? var.dynamodb_read_capacity : null
  write_capacity = local.is_provisioned ? var.dynamodb_write_capacity : null

  # Hash key (partition key) -- always a string
  hash_key = each.value.hash_key

  # Range key (sort key) -- optional
  range_key = each.value.range_key

  # Attribute definitions -- one per unique key attribute (table + GSIs)
  dynamic "attribute" {
    for_each = local.table_attributes[each.key]
    content {
      name = attribute.value
      type = "S"
    }
  }

  # Global Secondary Indexes
  dynamic "global_secondary_index" {
    for_each = each.value.gsis
    content {
      name            = global_secondary_index.value.name
      hash_key        = global_secondary_index.value.hash_key
      range_key       = global_secondary_index.value.range_key
      projection_type = "ALL"
      read_capacity   = local.is_provisioned ? var.dynamodb_read_capacity : null
      write_capacity  = local.is_provisioned ? var.dynamodb_write_capacity : null
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

  # Point-in-time recovery -- always enabled
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

# ── SQS -- Artifact Notification Dead-Letter Queue ───────────────────────────

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

# ── SQS -- Artifact Notification Queue ───────────────────────────────────────

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
