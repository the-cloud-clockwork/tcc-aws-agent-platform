## -----------------------------------------------------
## Workflows Module -- IAM Roles
## Step Functions execution roles with agent invoke perms.
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

resource "aws_iam_role_policy" "sfn_invoke_agents" {
  for_each = local.workflows

  name = "invoke-agent-runtimes"
  role = aws_iam_role.sfn[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:InvokeAgentRuntime",
          "bedrock-agentcore:StopRuntimeSession"
        ]
        Resource = [
          for agent_id in try(
            distinct(flatten([
              for state in try(each.value.states, []) :
              try([state.agent], try(state.parallel, []))
            ])),
            values(var.agent_runtime_arns)
          ) :
          try(var.agent_runtime_arns[agent_id], "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:*")
        ]
      },
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

resource "aws_iam_role" "events" {
  for_each = {
    for k, wf in local.workflows :
    k => wf if try(wf.trigger.type, "") == "schedule"
  }

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
