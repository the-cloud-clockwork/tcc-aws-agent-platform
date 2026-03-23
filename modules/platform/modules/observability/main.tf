# ──────────────────────────────────────────────────────────────────────────────
# Observability Sub-Module
#
# Replaces the CDK ObservabilityStack. Provides:
#   1. CloudWatch log group for pipeline logs
#   2. SNS topic for alerts (with optional email subscription)
#   3. X-Ray sampling group
#   4. CloudWatch dashboard with platform overview widgets
# ──────────────────────────────────────────────────────────────────────────────

# ── CloudWatch Log Group -- Pipeline Logs ─────────────────────────────────────

resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/${var.resource_prefix}/${var.environment}/pipeline"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name      = "/${var.resource_prefix}/${var.environment}/pipeline"
    Module    = "observability"
    Component = "cloudwatch"
    Role      = "pipeline-logs"
  })
}

# ── SNS Topic -- Alerts ──────────────────────────────────────────────────────

resource "aws_sns_topic" "alerts" {
  name              = "${var.resource_prefix}-${var.environment}-alerts"
  kms_master_key_id = var.kms_key_arn != "" ? var.kms_key_arn : null

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-alerts"
    Module    = "observability"
    Component = "sns"
    Role      = "alerts"
  })
}

resource "aws_sns_topic_subscription" "alert_email" {
  count = var.sns_alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}

# ── X-Ray Group ─────────────────────────────────────────────────────────────

resource "aws_xray_group" "main" {
  group_name        = "${var.resource_prefix}-${var.environment}"
  filter_expression = "annotation.environment = \"${var.environment}\""

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}"
    Module    = "observability"
    Component = "xray"
    Role      = "tracing-group"
  })
}

# ── CloudWatch Dashboard -- Platform Overview ─────────────────────────────────

resource "aws_cloudwatch_dashboard" "overview" {
  dashboard_name = "${var.resource_prefix}-${var.environment}-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "# ${var.resource_prefix} ${var.environment} -- Platform Overview"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "Agent Invocations"
          region = data.aws_region.current.name
          metrics = [
            ["${var.resource_prefix}/${var.environment}", "AgentInvocations", { stat = "Sum", period = 300 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "Token Cost"
          region = data.aws_region.current.name
          metrics = [
            ["${var.resource_prefix}/${var.environment}", "TokenCostUSD", { stat = "Sum", period = 300 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "Pipeline Executions"
          region = data.aws_region.current.name
          metrics = [
            ["${var.resource_prefix}/${var.environment}", "PipelineExecutions", { stat = "Sum", period = 300 }],
            ["${var.resource_prefix}/${var.environment}", "PipelineErrors", { stat = "Sum", period = 300 }]
          ]
          view = "timeSeries"
        }
      }
    ]
  })
}

# ── Data Sources ─────────────────────────────────────────────────────────────

data "aws_region" "current" {}
