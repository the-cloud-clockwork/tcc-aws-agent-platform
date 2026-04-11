# ──────────────────────────────────────────────────────────────────────────────
# Agent Invocation Lambda — replaces aws-sdk:invokeAgentRuntime
#
# The SFN SDK integration has a hardcoded 60s HTTP timeout. This Lambda
# calls AgentCore runtimes with a configurable timeout (default 600s).
# Domain-agnostic — every workflow module gets one automatically.
# ──────────────────────────────────────────────────────────────────────────────

data "archive_file" "invoke_agent" {
  type        = "zip"
  source_file = "${path.module}/lambda/invoke_agent.py"
  output_path = "${path.module}/.build/invoke-agent.zip"
}

resource "aws_iam_role" "invoke_agent_lambda" {
  name = "${local.name_prefix}-invoke-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "invoke_agent_lambda" {
  name = "${local.name_prefix}-invoke-agent-policy"
  role = aws_iam_role.invoke_agent_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeAgentRuntime"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:InvokeAgentRuntime",
          "bedrock-agentcore-control:InvokeAgentRuntime",
          "bedrock:InvokeAgent",
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

resource "aws_lambda_function" "invoke_agent" {
  function_name    = "${local.name_prefix}-invoke-agent"
  role             = aws_iam_role.invoke_agent_lambda.arn
  handler          = "invoke_agent.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 256
  timeout          = 900  # 15 min max Lambda timeout
  filename         = data.archive_file.invoke_agent.output_path
  source_code_hash = data.archive_file.invoke_agent.output_base64sha256

  environment {
    variables = {
      INVOKE_REGION         = local.region
      AGENT_INVOKE_TIMEOUT  = "600"
    }
  }

  tags = merge(local.tags, {
    Component = "workflow"
    Role      = "agent-invoker"
  })
}
