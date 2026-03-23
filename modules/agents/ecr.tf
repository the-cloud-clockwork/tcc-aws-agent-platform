# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- ECR
#
# Per-agent ECR repositories for container images. Each agent gets its own
# repository namespaced under {prefix}/{env}/{agent_id}. Images are scanned
# on push and old images are cleaned up via lifecycle policy.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "agent" {
  for_each = local.blueprints

  name                 = "${var.resource_prefix}/${var.environment}/${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = var.storage_kms_key_arn != "" ? "KMS" : "AES256"
    kms_key         = var.storage_kms_key_arn != "" ? var.storage_kms_key_arn : null
  }

  tags = merge(local.tags, {
    Name      = "${var.resource_prefix}/${var.environment}/${each.key}"
    Component = "ecr"
    AgentId   = each.key
  })
}

resource "aws_ecr_lifecycle_policy" "agent" {
  for_each = local.blueprints

  repository = aws_ecr_repository.agent[each.key].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
