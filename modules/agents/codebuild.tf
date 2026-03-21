# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — CodeBuild
#
# Per-agent CodeBuild projects for building ARM64 Docker images. Each project
# uses an inline buildspec that builds, tags, and pushes to the agent's ECR
# repository. A shared IAM role grants ECR push and CloudWatch Logs access.
# ──────────────────────────────────────────────────────────────────────────────

# ── IAM Role: CodeBuild Execution ──────────────────────────────────────────

data "aws_iam_policy_document" "codebuild_trust" {
  statement {
    sid     = "AllowCodeBuildAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${local.name_prefix}-agent-codebuild-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_trust.json

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-agent-codebuild-role"
    Component = "codebuild"
  })
}

data "aws_iam_policy_document" "codebuild_permissions" {
  # ECR push permissions
  statement {
    sid    = "EcrAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/${var.resource_prefix}/${var.environment}/*"
    ]
  }

  # CloudWatch Logs for build output
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.name_prefix}-build-*",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.name_prefix}-build-*:*",
    ]
  }

  # Conditional: S3 source bucket read (for fetching build source)
  dynamic "statement" {
    for_each = var.codebuild_source_bucket != "" ? [1] : []
    content {
      sid    = "S3SourceRead"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:GetBucketLocation",
      ]
      resources = [
        "arn:aws:s3:::${var.codebuild_source_bucket}",
        "arn:aws:s3:::${var.codebuild_source_bucket}/*",
      ]
    }
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "${local.name_prefix}-agent-codebuild-policy"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild_permissions.json
}

# ── Per-Agent CodeBuild Projects ───────────────────────────────────────────

resource "aws_codebuild_project" "agent" {
  for_each = local.blueprints

  name         = "${local.name_prefix}-build-${each.key}"
  description  = "ARM64 Docker build for agent: ${each.key}"
  service_role = aws_iam_role.codebuild.arn

  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/amazonlinux-aarch64-standard:3.0"
    type            = "ARM_CONTAINER"
    privileged_mode = true

    environment_variable {
      name  = "ECR_REPO_URI"
      value = aws_ecr_repository.agent[each.key].repository_url
    }

    environment_variable {
      name  = "AGENT_ID"
      value = each.key
    }

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = data.aws_region.current.name
    }
  }

  source {
    type      = "NO_SOURCE"
    buildspec = <<-BUILDSPEC
      version: 0.2
      phases:
        pre_build:
          commands:
            - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $ECR_REPO_URI
        build:
          commands:
            - docker build --platform linux/arm64 -t $ECR_REPO_URI:latest -t $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION .
        post_build:
          commands:
            - docker push $ECR_REPO_URI:latest
            - docker push $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION
    BUILDSPEC
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-build-${each.key}"
    Component = "codebuild"
    AgentId   = each.key
  })
}
