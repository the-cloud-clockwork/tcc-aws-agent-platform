# ──────────────────────────────────────────────────────────────────────────────
# Security Sub-Module -- Outputs
# ──────────────────────────────────────────────────────────────────────────────

# ── KMS: Data Key ────────────────────────────────────────────────────────────

output "data_kms_key_arn" {
  description = "ARN of the data encryption KMS key (DynamoDB, SQS)."
  value       = aws_kms_key.data.arn
}

output "data_kms_key_id" {
  description = "ID of the data encryption KMS key."
  value       = aws_kms_key.data.key_id
}

# ── KMS: Storage Key ────────────────────────────────────────────────────────

output "storage_kms_key_arn" {
  description = "ARN of the storage encryption KMS key (S3)."
  value       = aws_kms_key.storage.arn
}

output "storage_kms_key_id" {
  description = "ID of the storage encryption KMS key."
  value       = aws_kms_key.storage.key_id
}

# ── KMS: Secrets Key ────────────────────────────────────────────────────────

output "secrets_kms_key_arn" {
  description = "ARN of the secrets encryption KMS key (Secrets Manager)."
  value       = aws_kms_key.secrets.arn
}

output "secrets_kms_key_id" {
  description = "ID of the secrets encryption KMS key."
  value       = aws_kms_key.secrets.key_id
}

# ── KMS: Platform Artifacts Key ──────────────────────────────────────────────

output "platform_artifacts_kms_key_arn" {
  description = "ARN of the platform-tier artifact encryption KMS key."
  value       = aws_kms_key.platform_artifacts.arn
}

output "platform_artifacts_kms_key_id" {
  description = "ID of the platform-tier artifact encryption KMS key."
  value       = aws_kms_key.platform_artifacts.key_id
}

# ── KMS: Domain Artifacts Key ────────────────────────────────────────────────

output "domain_artifacts_kms_key_arn" {
  description = "ARN of the domain-tier artifact encryption KMS key."
  value       = aws_kms_key.domain_artifacts.arn
}

output "domain_artifacts_kms_key_id" {
  description = "ID of the domain-tier artifact encryption KMS key."
  value       = aws_kms_key.domain_artifacts.key_id
}

# ── Secrets Manager ──────────────────────────────────────────────────────────

output "observability_secret_arn" {
  description = "ARN of the Secrets Manager secret for the observability API key."
  value       = aws_secretsmanager_secret.observability_api_key.arn
}

# ── WAF ──────────────────────────────────────────────────────────────────────

output "waf_acl_arn" {
  description = "ARN of the WAF Web ACL. Empty string when WAF is disabled."
  value       = var.waf_enabled ? aws_wafv2_web_acl.main[0].arn : ""
}

output "guardrail_id" {
  description = "Bedrock Guardrail ID for PII/content protection. Empty when guardrail disabled."
  value       = var.guardrail_enabled ? aws_bedrock_guardrail.platform[0].guardrail_id : ""
}

output "guardrail_version" {
  description = "Published Bedrock Guardrail version number. Empty when guardrail disabled."
  value       = var.guardrail_enabled ? aws_bedrock_guardrail_version.platform[0].version : ""
}
