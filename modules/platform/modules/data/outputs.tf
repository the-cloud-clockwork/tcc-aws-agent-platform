# ──────────────────────────────────────────────────────────────────────────────
# Data Sub-Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

# ── DynamoDB Tables ──────────────────────────────────────────────────────────

output "table_names" {
  description = "Map of table key to DynamoDB table name."
  value       = { for k, t in aws_dynamodb_table.tables : k => t.name }
}

output "table_arns" {
  description = "Map of table key to DynamoDB table ARN."
  value       = { for k, t in aws_dynamodb_table.tables : k => t.arn }
}

# ── S3 Buckets -- Artifacts ───────────────────────────────────────────────────

output "artifacts_bucket_name" {
  description = "Name of the artifacts S3 bucket."
  value       = aws_s3_bucket.artifacts.id
}

output "artifacts_bucket_arn" {
  description = "ARN of the artifacts S3 bucket."
  value       = aws_s3_bucket.artifacts.arn
}

output "artifacts_bucket_id" {
  description = "ID (same as name) of the artifacts S3 bucket."
  value       = aws_s3_bucket.artifacts.id
}

# ── S3 Buckets -- Prompt Registry ─────────────────────────────────────────────

output "prompt_registry_bucket_name" {
  description = "Name of the prompt registry S3 bucket."
  value       = aws_s3_bucket.prompt_registry.id
}

output "prompt_registry_bucket_arn" {
  description = "ARN of the prompt registry S3 bucket."
  value       = aws_s3_bucket.prompt_registry.arn
}

# ── S3 Buckets -- Historical Data ─────────────────────────────────────────────

output "historical_data_bucket_name" {
  description = "Name of the historical data S3 bucket."
  value       = aws_s3_bucket.historical_data.id
}

output "historical_data_bucket_arn" {
  description = "ARN of the historical data S3 bucket."
  value       = aws_s3_bucket.historical_data.arn
}

# ── S3 Buckets -- Combined Map ────────────────────────────────────────────────

output "codebuild_source_bucket_name" {
  description = "Name of the S3 bucket for CodeBuild source code uploads."
  value       = aws_s3_bucket.codebuild_source.id
}

output "codebuild_source_bucket_arn" {
  description = "ARN of the S3 bucket for CodeBuild source code uploads."
  value       = aws_s3_bucket.codebuild_source.arn
}

output "bucket_names" {
  description = "Map of bucket key to S3 bucket name."
  value = {
    artifacts        = aws_s3_bucket.artifacts.id
    prompt_registry  = aws_s3_bucket.prompt_registry.id
    historical_data  = aws_s3_bucket.historical_data.id
    codebuild_source = aws_s3_bucket.codebuild_source.id
  }
}

# ── CloudFront ───────────────────────────────────────────────────────────────

output "cloudfront_domain" {
  description = "CloudFront distribution domain name. Empty string if CloudFront is disabled."
  value       = var.cloudfront_enabled ? aws_cloudfront_distribution.artifacts[0].domain_name : ""
}

output "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN. Empty string if CloudFront is disabled."
  value       = var.cloudfront_enabled ? aws_cloudfront_distribution.artifacts[0].arn : ""
}

# ── SQS -- Artifact Notifications ─────────────────────────────────────────────

output "artifact_queue_url" {
  description = "URL of the artifact notifications SQS queue."
  value       = aws_sqs_queue.artifact_notifications.url
}

output "artifact_queue_arn" {
  description = "ARN of the artifact notifications SQS queue."
  value       = aws_sqs_queue.artifact_notifications.arn
}

output "artifact_dlq_url" {
  description = "URL of the artifact notifications dead-letter queue."
  value       = aws_sqs_queue.artifact_dlq.url
}

output "artifact_dlq_arn" {
  description = "ARN of the artifact notifications dead-letter queue."
  value       = aws_sqs_queue.artifact_dlq.arn
}
