# ──────────────────────────────────────────────────────────────────────────────
# API Sub-Module
#
# Replaces the CDK ApiStack. Provides:
#   1. Lambda function for artifacts API
#   2. API Gateway REST API with IAM authorization
#   3. Routes: /api/artifacts, /api/artifacts/{artifact_id},
#              /api/artifacts/{artifact_id}/data, /api/runs,
#              /api/runs/{execution_id}
#   4. CORS support via OPTIONS mock integrations
#   5. Throttling via method settings
#   6. Conditional WAF association
# ──────────────────────────────────────────────────────────────────────────────

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  function_name = "${var.resource_prefix}-${var.environment}-artifacts-api"
  api_name      = "${var.resource_prefix}-${var.environment}-artifacts-api"
  cors_headers  = join(",", var.api_cors_origins)
}

# ═════════════════════════════════════════════════════════════════════════════
# IAM Role -- Lambda Execution
# ═════════════════════════════════════════════════════════════════════════════

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name      = "${local.function_name}-role"
    Module    = "api"
    Component = "iam"
    Role      = "lambda-execution"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_permissions" {
  # DynamoDB read access on artifacts table
  statement {
    sid    = "DynamoDBReadArtifacts"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchGetItem",
    ]

    resources = [
      var.artifacts_table_arn,
      "${var.artifacts_table_arn}/index/*",
    ]
  }

  # S3 read access on artifacts bucket
  statement {
    sid    = "S3ReadArtifacts"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]

    resources = [
      var.artifacts_bucket_arn,
      "${var.artifacts_bucket_arn}/*",
    ]
  }

  # KMS decrypt for both platform and domain artifact keys
  statement {
    sid    = "KMSDecryptArtifactKeys"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]

    resources = [
      var.platform_artifacts_kms_key_arn,
      var.domain_artifacts_kms_key_arn,
      var.data_kms_key_arn,
    ]

  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${local.function_name}-permissions"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ═════════════════════════════════════════════════════════════════════════════
# Lambda Function -- Artifacts API
# ═════════════════════════════════════════════════════════════════════════════

# -- Build: artifacts-api (no external deps, just handler + boto3 from runtime)
data "archive_file" "artifacts_api" {
  type        = "zip"
  output_path = "${path.module}/build/artifacts-api.zip"

  source {
    content  = ""
    filename = "agent_core/__init__.py"
  }
  source {
    content  = ""
    filename = "agent_core/api/__init__.py"
  }
  source {
    content  = file("${path.module}/../../../../core/src/agent_core/api/artifacts_api.py")
    filename = "agent_core/api/artifacts_api.py"
  }
}

resource "aws_lambda_function" "artifacts_api" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda.arn
  handler          = "agent_core.api.artifacts_api.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 512
  timeout          = 30
  filename         = data.archive_file.artifacts_api.output_path
  source_code_hash = data.archive_file.artifacts_api.output_base64sha256

  environment {
    variables = {
      ENV_NAME         = var.environment
      ARTIFACTS_TABLE  = var.artifacts_table_name
      ARTIFACTS_BUCKET = var.artifacts_bucket_name
    }
  }

  tags = merge(var.tags, {
    Name      = local.function_name
    Module    = "api"
    Component = "lambda"
    Role      = "artifacts-api"
  })
}

# ═════════════════════════════════════════════════════════════════════════════
# API Gateway -- REST API
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_api_gateway_rest_api" "artifacts" {
  name        = local.api_name
  description = "Artifacts and runs API for ${var.resource_prefix} ${var.environment}"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(var.tags, {
    Name      = local.api_name
    Module    = "api"
    Component = "apigateway"
    Role      = "artifacts-api"
  })
}

# ── Resource Tree ────────────────────────────────────────────────────────────

# /api
resource "aws_api_gateway_resource" "api" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  parent_id   = aws_api_gateway_rest_api.artifacts.root_resource_id
  path_part   = "api"
}

# /api/artifacts
resource "aws_api_gateway_resource" "artifacts" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "artifacts"
}

# /api/artifacts/{artifact_id}
resource "aws_api_gateway_resource" "artifact_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  parent_id   = aws_api_gateway_resource.artifacts.id
  path_part   = "{artifact_id}"
}

# /api/artifacts/{artifact_id}/data
resource "aws_api_gateway_resource" "artifact_data" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  parent_id   = aws_api_gateway_resource.artifact_by_id.id
  path_part   = "data"
}

# /api/runs
resource "aws_api_gateway_resource" "runs" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "runs"
}

# /api/runs/{execution_id}
resource "aws_api_gateway_resource" "run_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  parent_id   = aws_api_gateway_resource.runs.id
  path_part   = "{execution_id}"
}

# ── GET Methods (AWS_IAM authorization) ──────────────────────────────────────

# GET /api/artifacts
resource "aws_api_gateway_method" "get_artifacts" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifacts.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "get_artifacts" {
  rest_api_id             = aws_api_gateway_rest_api.artifacts.id
  resource_id             = aws_api_gateway_resource.artifacts.id
  http_method             = aws_api_gateway_method.get_artifacts.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.artifacts_api.invoke_arn
}

# POST /api/artifacts
resource "aws_api_gateway_method" "post_artifacts" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifacts.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "post_artifacts" {
  rest_api_id             = aws_api_gateway_rest_api.artifacts.id
  resource_id             = aws_api_gateway_resource.artifacts.id
  http_method             = aws_api_gateway_method.post_artifacts.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.artifacts_api.invoke_arn
}

# GET /api/artifacts/{artifact_id}
resource "aws_api_gateway_method" "get_artifact_by_id" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifact_by_id.id
  http_method   = "GET"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.artifact_id" = true
  }
}

resource "aws_api_gateway_integration" "get_artifact_by_id" {
  rest_api_id             = aws_api_gateway_rest_api.artifacts.id
  resource_id             = aws_api_gateway_resource.artifact_by_id.id
  http_method             = aws_api_gateway_method.get_artifact_by_id.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.artifacts_api.invoke_arn
}

# GET /api/artifacts/{artifact_id}/data
resource "aws_api_gateway_method" "get_artifact_data" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifact_data.id
  http_method   = "GET"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.artifact_id" = true
  }
}

resource "aws_api_gateway_integration" "get_artifact_data" {
  rest_api_id             = aws_api_gateway_rest_api.artifacts.id
  resource_id             = aws_api_gateway_resource.artifact_data.id
  http_method             = aws_api_gateway_method.get_artifact_data.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.artifacts_api.invoke_arn
}

# GET /api/runs
resource "aws_api_gateway_method" "get_runs" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.runs.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "get_runs" {
  rest_api_id             = aws_api_gateway_rest_api.artifacts.id
  resource_id             = aws_api_gateway_resource.runs.id
  http_method             = aws_api_gateway_method.get_runs.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.artifacts_api.invoke_arn
}

# GET /api/runs/{execution_id}
resource "aws_api_gateway_method" "get_run_by_id" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.run_by_id.id
  http_method   = "GET"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.execution_id" = true
  }
}

resource "aws_api_gateway_integration" "get_run_by_id" {
  rest_api_id             = aws_api_gateway_rest_api.artifacts.id
  resource_id             = aws_api_gateway_resource.run_by_id.id
  http_method             = aws_api_gateway_method.get_run_by_id.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.artifacts_api.invoke_arn
}

# ── CORS -- OPTIONS Methods with Mock Integration ────────────────────────────

# OPTIONS /api/artifacts
resource "aws_api_gateway_method" "options_artifacts" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifacts.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_artifacts" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifacts.id
  http_method = aws_api_gateway_method.options_artifacts.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_artifacts" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifacts.id
  http_method = aws_api_gateway_method.options_artifacts.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "options_artifacts" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifacts.id
  http_method = aws_api_gateway_method.options_artifacts.http_method
  status_code = aws_api_gateway_method_response.options_artifacts.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.cors_headers}'"
  }
}

# OPTIONS /api/artifacts/{artifact_id}
resource "aws_api_gateway_method" "options_artifact_by_id" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifact_by_id.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_artifact_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifact_by_id.id
  http_method = aws_api_gateway_method.options_artifact_by_id.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_artifact_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifact_by_id.id
  http_method = aws_api_gateway_method.options_artifact_by_id.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "options_artifact_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifact_by_id.id
  http_method = aws_api_gateway_method.options_artifact_by_id.http_method
  status_code = aws_api_gateway_method_response.options_artifact_by_id.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.cors_headers}'"
  }
}

# OPTIONS /api/artifacts/{artifact_id}/data
resource "aws_api_gateway_method" "options_artifact_data" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.artifact_data.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_artifact_data" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifact_data.id
  http_method = aws_api_gateway_method.options_artifact_data.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_artifact_data" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifact_data.id
  http_method = aws_api_gateway_method.options_artifact_data.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "options_artifact_data" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.artifact_data.id
  http_method = aws_api_gateway_method.options_artifact_data.http_method
  status_code = aws_api_gateway_method_response.options_artifact_data.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.cors_headers}'"
  }
}

# OPTIONS /api/runs
resource "aws_api_gateway_method" "options_runs" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.runs.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_runs" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.runs.id
  http_method = aws_api_gateway_method.options_runs.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_runs" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.runs.id
  http_method = aws_api_gateway_method.options_runs.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "options_runs" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.runs.id
  http_method = aws_api_gateway_method.options_runs.http_method
  status_code = aws_api_gateway_method_response.options_runs.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.cors_headers}'"
  }
}

# OPTIONS /api/runs/{execution_id}
resource "aws_api_gateway_method" "options_run_by_id" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  resource_id   = aws_api_gateway_resource.run_by_id.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_run_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.run_by_id.id
  http_method = aws_api_gateway_method.options_run_by_id.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_run_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.run_by_id.id
  http_method = aws_api_gateway_method.options_run_by_id.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "options_run_by_id" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  resource_id = aws_api_gateway_resource.run_by_id.id
  http_method = aws_api_gateway_method.options_run_by_id.http_method
  status_code = aws_api_gateway_method_response.options_run_by_id.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.cors_headers}'"
  }
}

# ═════════════════════════════════════════════════════════════════════════════
# Deployment + Stage
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id

  # Redeploy whenever any method or integration changes
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_method.get_artifacts.id,
      aws_api_gateway_method.get_artifact_by_id.id,
      aws_api_gateway_method.get_artifact_data.id,
      aws_api_gateway_method.get_runs.id,
      aws_api_gateway_method.get_run_by_id.id,
      aws_api_gateway_integration.get_artifacts.id,
      aws_api_gateway_integration.get_artifact_by_id.id,
      aws_api_gateway_integration.get_artifact_data.id,
      aws_api_gateway_integration.get_runs.id,
      aws_api_gateway_integration.get_run_by_id.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.get_artifacts,
    aws_api_gateway_integration.post_artifacts,
    aws_api_gateway_integration.get_artifact_by_id,
    aws_api_gateway_integration.get_artifact_data,
    aws_api_gateway_integration.get_runs,
    aws_api_gateway_integration.get_run_by_id,
    aws_api_gateway_integration.options_artifacts,
    aws_api_gateway_integration.options_artifact_by_id,
    aws_api_gateway_integration.options_artifact_data,
    aws_api_gateway_integration.options_runs,
    aws_api_gateway_integration.options_run_by_id,
  ]
}

resource "aws_api_gateway_stage" "main" {
  rest_api_id   = aws_api_gateway_rest_api.artifacts.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = var.environment

  tags = merge(var.tags, {
    Name      = "${local.api_name}-${var.environment}"
    Module    = "api"
    Component = "apigateway"
    Role      = "stage"
  })
}

# ── Method Settings -- Throttling ─────────────────────────────────────────────

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.artifacts.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.api_throttle_rate
    throttling_burst_limit = var.api_throttle_burst
  }
}

# ═════════════════════════════════════════════════════════════════════════════
# Lambda Permission -- Allow API Gateway Invocation
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.artifacts_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.artifacts.execution_arn}/*/*"
}

# ═════════════════════════════════════════════════════════════════════════════
# WAF Association (conditional)
# ═════════════════════════════════════════════════════════════════════════════

resource "aws_wafv2_web_acl_association" "api_gateway" {
  count = var.waf_enabled && var.waf_acl_arn != "" ? 1 : 0

  resource_arn = aws_api_gateway_stage.main.arn
  web_acl_arn  = var.waf_acl_arn
}

# ═════════════════════════════════════════════════════════════════════════════
# Lambda Function -- Artifacts MCP Tools (AgentCore Gateway Target)
#
# Separate function from the REST API Lambda because this one needs full
# read+write permissions (DynamoDB, S3, SQS, KMS encrypt). The REST API
# Lambda is read-only. Gateway routes MCP tool calls here.
# ═════════════════════════════════════════════════════════════════════════════

# -- IAM Role ---------------------------------------------------------------

data "aws_iam_policy_document" "mcp_tools_permissions" {
  # DynamoDB full access on artifacts table
  statement {
    sid    = "DynamoDBFullArtifacts"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchGetItem",
    ]

    resources = [
      var.artifacts_table_arn,
      "${var.artifacts_table_arn}/index/*",
    ]
  }

  # S3 full access on artifacts bucket
  statement {
    sid    = "S3FullArtifacts"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]

    resources = [
      var.artifacts_bucket_arn,
      "${var.artifacts_bucket_arn}/*",
    ]
  }

  # SQS send to artifact notifications queue
  statement {
    sid    = "SQSSendArtifactNotifications"
    effect = "Allow"

    actions = [
      "sqs:SendMessage",
    ]

    resources = [
      var.artifact_queue_arn,
    ]
  }

  # KMS encrypt + decrypt for both platform and domain artifact keys
  statement {
    sid    = "KMSArtifactKeys"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]

    resources = [
      var.platform_artifacts_kms_key_arn,
      var.domain_artifacts_kms_key_arn,
      var.data_kms_key_arn,
    ]
  }
}

resource "aws_iam_role" "mcp_tools_lambda" {
  name               = "${var.resource_prefix}-${var.environment}-artifacts-mcp-tools-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-artifacts-mcp-tools-role"
    Module    = "api"
    Component = "iam"
    Role      = "mcp-tools-lambda-execution"
  })
}

resource "aws_iam_role_policy_attachment" "mcp_tools_basic_execution" {
  role       = aws_iam_role.mcp_tools_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "mcp_tools_permissions" {
  name   = "${var.resource_prefix}-${var.environment}-artifacts-mcp-tools-permissions"
  role   = aws_iam_role.mcp_tools_lambda.id
  policy = data.aws_iam_policy_document.mcp_tools_permissions.json
}

# -- Shared Lambda Layer (pydantic + mcp_artifacts for arm64/python3.12) ------
#
# Built hermetically by Terraform: terraform_data.build_platform_deps_layer runs
# scripts/build-lambda-layer.sh during `apply`. source_code_hash derives from the
# build INPUTS, not the output zip, so plan/validate never read a file on disk and
# consumers can git-source this module with no pre-build step.
# --------------------------------------------------------------------------

locals {
  layer_build_script      = "${path.module}/../../scripts/build-lambda-layer.sh"
  layer_mcp_artifacts_dir = "${path.module}/../../../../artifacts/src/mcp_artifacts"
  layer_zip               = "${path.module}/../../.build/lambda-layer.zip"

  # Hash the build INPUTS (the script carries the pydantic pin; mcp_artifacts is
  # the first-party payload) — drives both the rebuild trigger and the layer's
  # source_code_hash so they move together. No plan-time read of the output zip.
  layer_src_hash = sha1(join("", concat(
    [filesha1(local.layer_build_script)],
    [for f in sort(fileset(local.layer_mcp_artifacts_dir, "**/*.py")) :
    filesha1("${local.layer_mcp_artifacts_dir}/${f}")],
  )))
}

resource "terraform_data" "build_platform_deps_layer" {
  triggers_replace = local.layer_src_hash

  provisioner "local-exec" {
    command = "bash ${local.layer_build_script}"
  }
}

resource "aws_lambda_layer_version" "platform_deps" {
  depends_on               = [terraform_data.build_platform_deps_layer]
  layer_name               = "${var.resource_prefix}-${var.environment}-platform-deps"
  filename                 = local.layer_zip
  source_code_hash         = local.layer_src_hash
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["arm64"]
  description              = "Platform shared deps: pydantic, mcp_artifacts"
}

# -- artifacts-mcp-tools: handler zip (deps from layer) ----------------------

data "archive_file" "artifacts_mcp_tools" {
  type        = "zip"
  output_path = "${path.module}/build/artifacts-mcp-tools.zip"

  source {
    content  = file("${path.module}/../../../../core/src/agent_core/api/artifacts_mcp_handler.py")
    filename = "agent_core/api/artifacts_mcp_handler.py"
  }
  source {
    content  = ""
    filename = "agent_core/__init__.py"
  }
  source {
    content  = ""
    filename = "agent_core/api/__init__.py"
  }
}

resource "aws_lambda_function" "artifacts_mcp_tools" {
  function_name    = "${var.resource_prefix}-${var.environment}-artifacts-mcp-tools"
  role             = aws_iam_role.mcp_tools_lambda.arn
  handler          = "agent_core.api.artifacts_mcp_handler.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 512
  timeout          = 60
  filename         = data.archive_file.artifacts_mcp_tools.output_path
  source_code_hash = data.archive_file.artifacts_mcp_tools.output_base64sha256
  layers           = [aws_lambda_layer_version.platform_deps.arn]

  environment {
    variables = {
      ENV_NAME                       = var.environment
      ARTIFACTS_TABLE                = var.artifacts_table_name
      ARTIFACTS_BUCKET               = var.artifacts_bucket_name
      ARTIFACT_QUEUE_URL             = var.artifact_queue_url
      KMS_KEY_ARN_PLATFORM_ARTIFACTS = var.platform_artifacts_kms_key_arn
      KMS_KEY_ARN_DOMAIN_ARTIFACTS   = var.domain_artifacts_kms_key_arn
    }
  }

  tags = merge(var.tags, {
    Name      = "${var.resource_prefix}-${var.environment}-artifacts-mcp-tools"
    Module    = "api"
    Component = "lambda"
    Role      = "artifacts-mcp-tools"
  })
}
