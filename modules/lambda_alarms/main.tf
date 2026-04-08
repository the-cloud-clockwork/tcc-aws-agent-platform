# ── Lambda Alarm Factory ──────────────────────────────────────────────────────
# Generates Error + Duration (p99 at 75% timeout) alarms per Lambda function.

resource "aws_cloudwatch_metric_alarm" "errors" {
  for_each = var.lambdas

  alarm_name          = "${var.resource_prefix}-${each.key}-errors"
  alarm_description   = "Errors detected in ${each.value.function_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    FunctionName = each.value.function_name
  }

  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${each.key}-errors"
  })
}

resource "aws_cloudwatch_metric_alarm" "duration" {
  for_each = var.lambdas

  alarm_name          = "${var.resource_prefix}-${each.key}-duration"
  alarm_description   = "p99 duration exceeds 75%% of timeout for ${each.value.function_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  extended_statistic  = "p99"
  threshold           = each.value.timeout * 750
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    FunctionName = each.value.function_name
  }

  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${each.key}-duration"
  })
}
