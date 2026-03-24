# ──────────────────────────────────────────────────────────────────────────────
# Prompt Registry Sub-Module
#
# Deploys the Prompt Registry Lambda with a Function URL.
# Provides versioned, mode-gated prompt management (AI-DLC practice).
#
# The Lambda ships with placeholder.zip — real handler code is deployed via
# CodeBuild (same pattern as modules/api). lifecycle { ignore_changes }
# prevents Terraform from reverting the deployed code on subsequent applies.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# --- IAM Role ---

resource "aws_iam_role" "prompt_registry" {
  name = "${var.resource_prefix}-${var.environment}-prompt-registry-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "prompt_registry_basic" {
  role       = aws_iam_role.prompt_registry.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "prompt_registry_data" {
  name = "${var.resource_prefix}-${var.environment}-prompt-registry-data"
  role = aws_iam_role.prompt_registry.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          var.prompt_table_arn,
          "${var.prompt_table_arn}/index/*",
        ]
      },
      {
        Sid    = "S3Access"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ]
        Resource = [
          var.prompt_bucket_arn,
          "${var.prompt_bucket_arn}/*",
        ]
      },
      {
        Sid      = "KMSDecrypt"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = var.storage_kms_key_arn != "" ? [var.storage_kms_key_arn] : ["*"]
      },
    ]
  })
}

# --- Lambda Function ---

resource "aws_lambda_function" "prompt_registry" {
  function_name = "${var.resource_prefix}-${var.environment}-prompt-registry"
  description   = "Prompt Registry API — versioned prompt lifecycle management (AI-DLC)"
  role          = aws_iam_role.prompt_registry.arn
  handler       = "prompt_registry.handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 30
  filename      = "${path.module}/placeholder.zip"

  environment {
    variables = {
      DYNAMODB_TABLE = var.prompt_table_name
      S3_BUCKET      = var.prompt_bucket_name
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [filename]
  }
}

# --- Lambda Function URL (IAM-authed, internal use) ---

resource "aws_lambda_function_url" "prompt_registry" {
  function_name      = aws_lambda_function.prompt_registry.function_name
  authorization_type = "AWS_IAM"
}
