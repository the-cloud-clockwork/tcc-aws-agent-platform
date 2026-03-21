## -----------------------------------------------------
## Workflows Module — Step Functions State Machines
## Reads workflow YAML and generates SFN definitions.
## Each agent step invokes an AgentCore Runtime.
## -----------------------------------------------------

resource "aws_cloudwatch_log_group" "sfn" {
  for_each = local.workflows

  name              = "/aws/stepfunctions/${local.name_prefix}-${each.key}"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, {
    Workflow = each.key
  })
}

resource "aws_sfn_state_machine" "workflows" {
  for_each = local.workflows

  name     = "${local.name_prefix}-${each.key}"
  role_arn = aws_iam_role.sfn[each.key].arn

  definition = jsonencode({
    Comment        = try(each.value.description, "Workflow: ${each.key}")
    TimeoutSeconds = try(each.value.timeout_minutes, 60) * 60
    StartAt        = try(each.value.states[0].id, "Start")
    States = merge(
      # Sequential agent steps
      {
        for idx, state in [
          for s in try(each.value.states, []) :
          s if can(s.agent)
        ] :
        state.id => {
          Type = "Task"
          Resource = "arn:aws:states:::bedrock-agentcore:invokeAgentRuntime"
          Parameters = {
            "AgentRuntimeArn" = try(
              var.agent_runtime_arns[state.agent],
              "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${state.agent}"
            )
            "SessionState" = {
              "Prompt.$" = try(state.prompt, "$.prompt")
            }
          }
          ResultPath = "$.results.${state.agent}"
          Retry = [{
            ErrorEquals     = ["States.ALL"]
            IntervalSeconds = 2
            MaxAttempts     = try(state.retry_max, 3)
            BackoffRate     = 2.0
          }]
          Catch = [{
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error.${state.agent}"
            Next        = "${state.id}_Failed"
          }]
          Next = try(state.next, null) != null ? state.next : null
          End  = try(state.next, null) == null ? true : null
        }
      },
      # Failure states for each agent
      {
        for state in [
          for s in try(each.value.states, []) :
          s if can(s.agent)
        ] :
        "${state.id}_Failed" => {
          Type  = "Fail"
          Error = "AgentExecutionFailed"
          Cause = "Agent ${state.agent} failed during execution"
        }
      },
      # Parallel steps
      {
        for state in [
          for s in try(each.value.states, []) :
          s if can(s.parallel)
        ] :
        state.id => {
          Type = "Parallel"
          Branches = [
            for branch in state.parallel : {
              StartAt = branch.agent
              States = {
                (branch.agent) = {
                  Type     = "Task"
                  Resource = "arn:aws:states:::bedrock-agentcore:invokeAgentRuntime"
                  Parameters = {
                    "AgentRuntimeArn" = try(
                      var.agent_runtime_arns[branch.agent],
                      "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${branch.agent}"
                    )
                    "SessionState" = {
                      "Prompt.$" = "$.prompt"
                    }
                  }
                  ResultPath = "$.results.${branch.agent}"
                  Retry = [{
                    ErrorEquals     = ["States.ALL"]
                    IntervalSeconds = 2
                    MaxAttempts     = 3
                    BackoffRate     = 2.0
                  }]
                  End = true
                }
              }
            }
          ]
          ResultPath = "$.parallel_results"
          Next       = try(state.next, null) != null ? state.next : null
          End        = try(state.next, null) == null ? true : null
        }
      }
    )
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn[each.key].arn}:*"
    level                  = "ALL"
    include_execution_data = true
  }

  tracing_configuration {
    enabled = true
  }

  tags = merge(local.tags, {
    Workflow = each.key
  })
}
