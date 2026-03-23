# ──────────────────────────────────────────────────────────────────────────────
# API Sub-Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "api_url" {
  description = "Full invoke URL of the API Gateway stage"
  value       = aws_api_gateway_stage.main.invoke_url
}

output "api_id" {
  description = "REST API ID"
  value       = aws_api_gateway_rest_api.artifacts.id
}

output "lambda_function_arn" {
  description = "ARN of the artifacts API Lambda function"
  value       = aws_lambda_function.artifacts_api.arn
}

output "lambda_function_name" {
  description = "Name of the artifacts API Lambda function"
  value       = aws_lambda_function.artifacts_api.function_name
}
