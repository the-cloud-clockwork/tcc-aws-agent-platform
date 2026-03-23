# ──────────────────────────────────────────────────────────────────────────────
# Observability Sub-Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "alert_topic_arn" {
  description = "ARN of the SNS alerts topic"
  value       = aws_sns_topic.alerts.arn
}

output "alert_topic_name" {
  description = "Name of the SNS alerts topic"
  value       = aws_sns_topic.alerts.name
}

output "pipeline_log_group_name" {
  description = "Name of the pipeline CloudWatch log group"
  value       = aws_cloudwatch_log_group.pipeline.name
}

output "pipeline_log_group_arn" {
  description = "ARN of the pipeline CloudWatch log group"
  value       = aws_cloudwatch_log_group.pipeline.arn
}

output "xray_group_name" {
  description = "Name of the X-Ray tracing group"
  value       = aws_xray_group.main.group_name
}

output "dashboard_name" {
  description = "Name of the CloudWatch overview dashboard"
  value       = aws_cloudwatch_dashboard.overview.dashboard_name
}
