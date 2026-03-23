# ──────────────────────────────────────────────────────────────────────────────
# Data Sub-Module -- CloudFront Distribution (Conditional)
#
# Creates a CloudFront distribution for the artifacts bucket when
# cloudfront_enabled = true. Uses Origin Access Control (OAC) with SigV4
# for secure S3 origin access.
# ──────────────────────────────────────────────────────────────────────────────

# ── Origin Access Control ────────────────────────────────────────────────────

resource "aws_cloudfront_origin_access_control" "artifacts" {
  count = var.cloudfront_enabled ? 1 : 0

  name                              = "${var.resource_prefix}-${var.environment}-artifacts-oac"
  description                       = "OAC for artifacts S3 bucket with SigV4 signing"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ── CloudFront Distribution ─────────────────────────────────────────────────

resource "aws_cloudfront_distribution" "artifacts" {
  count = var.cloudfront_enabled ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.resource_prefix}-${var.environment} artifacts distribution"
  default_root_object = ""
  price_class         = "PriceClass_100" # US, Canada, Europe

  # WAF association (conditional on waf_acl_arn being provided)
  web_acl_id = var.waf_acl_arn != "" ? var.waf_acl_arn : null

  # ── Origin: Artifacts S3 Bucket ──────────────────────────────────────────
  origin {
    domain_name              = aws_s3_bucket.artifacts.bucket_regional_domain_name
    origin_id                = "artifacts-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.artifacts[0].id
  }

  # ── Default Cache Behavior ───────────────────────────────────────────────
  default_cache_behavior {
    target_origin_id       = "artifacts-s3"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # Use the CachingOptimized managed cache policy
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # ── Restrictions ─────────────────────────────────────────────────────────
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # ── TLS Certificate ──────────────────────────────────────────────────────
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-artifacts-cdn"
    Module    = "data"
    Component = "cloudfront"
    Role      = "artifacts-distribution"
  })
}
