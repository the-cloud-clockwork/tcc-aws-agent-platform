# ──────────────────────────────────────────────────────────────────────────────
# Security Sub-Module — WAF Web ACL (conditional)
#
# Created only when var.waf_enabled is true. Provides:
#   1. Rate limiting (configurable requests per 5-min window)
#   2. AWS Managed Rules — Common Rule Set
#   3. AWS Managed Rules — Known Bad Inputs
#   4. IP whitelist (only when var.waf_ip_whitelist is non-empty)
# ──────────────────────────────────────────────────────────────────────────────

locals {
  waf_ip_whitelist_enabled = var.waf_enabled && length(var.waf_ip_whitelist) > 0
}

# ── IP Set for whitelist ─────────────────────────────────────────────────────

resource "aws_wafv2_ip_set" "whitelist" {
  count              = local.waf_ip_whitelist_enabled ? 1 : 0
  name               = "${var.resource_prefix}-${var.environment}-ip-whitelist"
  description        = "Whitelisted IP ranges for ${var.resource_prefix}-${var.environment}"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = var.waf_ip_whitelist
  tags               = var.tags
}

# ── Web ACL ──────────────────────────────────────────────────────────────────

resource "aws_wafv2_web_acl" "main" {
  count       = var.waf_enabled ? 1 : 0
  name        = "${var.resource_prefix}-${var.environment}-waf"
  description = "WAF Web ACL for ${var.resource_prefix}-${var.environment}"
  scope       = "REGIONAL"
  tags        = var.tags

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.resource_prefix}-${var.environment}-waf"
    sampled_requests_enabled   = true
  }

  # ── Rule 1: Rate Limiting ────────────────────────────────────────────────

  rule {
    name     = "rate-limit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.resource_prefix}-${var.environment}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 2: AWS Managed Rules — Common Rule Set ──────────────────────────

  rule {
    name     = "aws-common-rules"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.resource_prefix}-${var.environment}-common-rules"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 3: AWS Managed Rules — Known Bad Inputs ─────────────────────────

  rule {
    name     = "aws-known-bad-inputs"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.resource_prefix}-${var.environment}-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 4: IP Whitelist (conditional) ───────────────────────────────────

  dynamic "rule" {
    for_each = local.waf_ip_whitelist_enabled ? [1] : []

    content {
      name     = "ip-whitelist"
      priority = 0

      action {
        allow {}
      }

      statement {
        ip_set_reference_statement {
          arn = aws_wafv2_ip_set.whitelist[0].arn
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "${var.resource_prefix}-${var.environment}-ip-whitelist"
        sampled_requests_enabled   = true
      }
    }
  }
}
