# ──────────────────────────────────────────────────────────────────────────────
# Prompt Registry Sub-Module — Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "prompt_registry_url" {
  description = "Lambda Function URL for the Prompt Registry API."
  value       = aws_lambda_function_url.prompt_registry.function_url
}

output "prompt_registry_lambda_arn" {
  description = "ARN of the Prompt Registry Lambda function."
  value       = aws_lambda_function.prompt_registry.arn
}

output "prompt_registry_lambda_name" {
  description = "Name of the Prompt Registry Lambda function."
  value       = aws_lambda_function.prompt_registry.function_name
}
