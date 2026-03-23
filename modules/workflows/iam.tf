## -----------------------------------------------------
## Workflows Module -- IAM Roles
## Step Functions execution roles with agent + lambda
## invoke permissions. EventBridge roles for triggers.
## -----------------------------------------------------

resource "aws_iam_role" "sfn" {
  for_each = local.workflows

  name = "${local.name_prefix}-sfn-${each.key}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = local.account_id
        }
      }
    }]
  })

  tags = merge(local.tags, {
    Workflow = each.key
  })
}

# --- Agent Runtime invoke permissions ---
resource "aws_iam_role_policy" "sfn_invoke_agents" {
  for_each = {
    for k, wf in local.workflows :
    k => wf if length(try(local.workflow_agent_refs[k], [])) > 0
  }

  name = "invoke-agent-runtimes"
  role = aws_iam_role.sfn[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock-agentcore:InvokeAgentRuntime",
        "bedrock-agentcore:StopRuntimeSession"
      ]
      Resource = [
        for agent_id in local.workflow_agent_refs[each.key] :
        try(
          var.agent_runtime_arns[agent_id],
          "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${agent_id}"
        )
      ]
    }]
  })
}

# --- Lambda invoke permissions (conditional — only when lambda_ref states exist) ---
resource "aws_iam_role_policy" "sfn_invoke_lambdas" {
  for_each = {
    for k, wf in local.workflows :
    k => wf if length(try(local.workflow_lambda_refs[k], [])) > 0
  }

  name = "invoke-lambda-functions"
  role = aws_iam_role.sfn[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "lambda:InvokeFunction"
      ]
      Resource = [
        for lambda_name in local.workflow_lambda_refs[each.key] :
        try(
          var.lambda_arns[lambda_name],
          "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.name_prefix}-${lambda_name}"
        )
      ]
    }]
  })
}

# --- CloudWatch Logs + X-Ray permissions (always) ---
resource "aws_iam_role_policy" "sfn_logging" {
  for_each = local.workflows

  name = "logging-and-tracing"
  role = aws_iam_role.sfn[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:CreateLogStream",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
        Resource = "*"
      }
    ]
  })
}

# --- EventBridge execution roles (for schedule + event_pattern triggers) ---
resource "aws_iam_role" "events" {
  for_each = local.workflows_with_triggers

  name = "${local.name_prefix}-events-${each.key}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "events_start_sfn" {
  for_each = aws_iam_role.events

  name = "start-state-machine"
  role = each.value.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.workflows[each.key].arn
    }]
  })
}
