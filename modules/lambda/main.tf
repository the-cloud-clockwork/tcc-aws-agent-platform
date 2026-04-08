# ── Reusable Lambda Module ────────────────────────────────────────────────────
# Generates: archive_file, lambda_function, iam_role, 2× managed policy
# attachments, optional inline policies, and cloudwatch log group.

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.root}/.build/${var.resource_prefix}-${var.function_name}.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${var.resource_prefix}-${var.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = var.vpc_enabled ? "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole" : "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "xray" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

resource "aws_iam_role_policy" "additional" {
  for_each = { for i, p in var.additional_policies : "policy-${i}" => p }

  name   = "${var.resource_prefix}-${var.function_name}-${each.key}"
  role   = aws_iam_role.lambda.id
  policy = each.value
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.resource_prefix}-${var.function_name}"
  role             = aws_iam_role.lambda.arn
  handler          = var.handler
  runtime          = var.runtime
  memory_size      = var.memory_size
  timeout          = var.timeout
  architectures    = var.architectures
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }

  dynamic "vpc_config" {
    for_each = var.vpc_enabled ? [1] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = var.security_group_ids
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.function_name}"
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.this.function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn != "" ? var.kms_key_arn : null

  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.function_name}-logs"
  })
}
