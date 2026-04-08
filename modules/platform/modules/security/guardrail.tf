# ── Bedrock Guardrail — PII and content protection ───────────────────────────
# Shared per-environment guardrail for all agent runtimes.
# Gated by var.guardrail_enabled. Agents reference the guardrail via
# BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION env vars.

resource "aws_bedrock_guardrail" "platform" {
  count = var.guardrail_enabled ? 1 : 0

  name                      = "${var.resource_prefix}-${var.environment}-guardrail"
  description               = "Platform PII and content guardrail for all agents (${var.environment})"
  blocked_input_messaging   = "Request blocked by content policy."
  blocked_outputs_messaging = "Response blocked by content policy."

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = var.guardrail_pii_entities
      content {
        type   = pii_entities_config.value.type
        action = pii_entities_config.value.action
      }
    }
  }

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-guardrail"
    Component = "guardrail"
  })
}

resource "aws_bedrock_guardrail_version" "platform" {
  count = var.guardrail_enabled ? 1 : 0

  guardrail_arn = aws_bedrock_guardrail.platform[0].guardrail_arn
  description   = "Version managed by Terraform for ${var.environment}"
}
