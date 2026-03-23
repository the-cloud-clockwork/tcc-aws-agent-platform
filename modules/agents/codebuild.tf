# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- CodeBuild
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
  name               = "${local.name_prefix}-codebuild-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_trust.json

  tags = merge(local.tags, {
    Name      = "${local.name_prefix}-codebuild-role"
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
        "s3:GetObjectVersion",
        "s3:GetBucketLocation",
      ]
      resources = [
        "arn:aws:s3:::${var.codebuild_source_bucket}",
        "arn:aws:s3:::${var.codebuild_source_bucket}/*",
      ]
    }
  }

  # Conditional: KMS decrypt for encrypted S3 source objects
  dynamic "statement" {
    for_each = var.storage_kms_key_arn != "" ? [1] : []
    content {
      sid    = "KmsSourceDecrypt"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
      ]
      resources = [
        var.storage_kms_key_arn,
      ]
    }
  }

  # CodeArtifact authentication for Python package resolution
  statement {
    sid    = "CodeArtifactAuth"
    effect = "Allow"
    actions = [
      "codeartifact:GetAuthorizationToken",
      "codeartifact:ReadFromRepository",
      "codeartifact:GetRepositoryEndpoint",
      "sts:GetServiceBearerToken",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "${local.name_prefix}-codebuild-policy"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild_permissions.json
}

# ── Per-Agent CodeBuild Projects ───────────────────────────────────────────
#
# Build Workflow (NO_SOURCE pattern):
#   1. Domain repo triggers CodeBuild via AWS CLI or SDK:
#        aws codebuild start-build \\
#          --project-name <project-name> \\
#          --source-type-override S3 \\
#          --source-location-override <bucket>/<path>.zip
#
#   2. The source override injects the domain repo's agent source code
#      at build time. The inline buildspec then runs:
#        - docker build → builds the agent container image
#        - docker push → pushes to the agent's ECR repository
#
#   3. The codebuild_source_bucket variable (wired to IAM above) grants
#      read access to the S3 bucket used in sourceLocationOverride.
#      It is intentionally NOT wired to the CodeBuild source block
#      because the source is provided at trigger time, not at definition time.
#
# This pattern decouples the platform (which owns the build pipeline)
# from the domain (which owns the agent source code).

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

      environment_variable {
        name  = "AWS_ACCOUNT_ID"
        value = data.aws_caller_identity.current.account_id
      }

      environment_variable {
        name  = "CODEARTIFACT_DOMAIN"
        value = var.codeartifact_domain
      }

      environment_variable {
        name  = "CODEARTIFACT_REPO"
        value = var.codeartifact_repo
      }
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
            - export CODEARTIFACT_TOKEN=$(aws codeartifact get-authorization-token --domain $CODEARTIFACT_DOMAIN --domain-owner $AWS_ACCOUNT_ID --region $AWS_DEFAULT_REGION --query authorizationToken --output text)
            - export PIP_EXTRA_INDEX_URL="https://aws:$${CODEARTIFACT_TOKEN}@$${CODEARTIFACT_DOMAIN}-$${AWS_ACCOUNT_ID}.d.codeartifact.$${AWS_DEFAULT_REGION}.amazonaws.com/pypi/$${CODEARTIFACT_REPO}/simple/"
        build:
          commands:
            - docker build --platform linux/arm64 --build-arg PIP_EXTRA_INDEX_URL="$PIP_EXTRA_INDEX_URL" -t $ECR_REPO_URI:latest -t $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION .
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
