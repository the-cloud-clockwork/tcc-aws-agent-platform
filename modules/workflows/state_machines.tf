## -----------------------------------------------------
## Workflows Module -- Step Functions State Machines
## Reads workflow YAML and generates SFN definitions.
##
## Supported state types:
##   - task (agent_ref/agent)   → invokeAgentRuntime
##   - task (lambda_ref)        → lambda:invoke
##   - wait_for_token           → lambda:invoke.waitForTaskToken
##   - choice                   → Choice routing
##   - parallel                 → Parallel branches
##   - succeed                  → Terminal success
##   - fail                     → Terminal failure
##
## Memory branching: when workflow-level memory_branching.enabled
## is true, agent task Payloads include memory_branch namespace.
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

      # ═══════════════════════════════════════════════════
      # AGENT TASK STATES (agent_ref / agent, no lambda_ref)
      # Invoked via Lambda wrapper to bypass 60s SDK timeout.
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if(try(s.type, null) == "task" || try(s.type, null) == null) && (try(s.agent_ref, null) != null || try(s.agent, null) != null) && try(s.lambda_ref, null) == null
        ] :
        state.id => merge(
          {
            Type     = "Task"
            Resource = "arn:aws:states:::lambda:invoke"
            Parameters = {
              "FunctionName" = aws_lambda_function.invoke_agent.arn
              "Payload" = {
                "AgentRuntimeArn" = try(
                  var.agent_runtime_arns[coalesce(try(state.agent_ref, null), try(state.agent, "unknown"))],
                  "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${coalesce(try(state.agent_ref, null), try(state.agent, "unknown"))}"
                )
                "Qualifier"          = "DEFAULT"
                "Prompt.$"           = try(state.prompt, "$.prompt")
                "MemoryBranch"       = try(each.value.memory_branching.enabled, false) ? replace(try(each.value.memory_branching.branch_namespace, "{sessionId}/branches/{stateId}"), "{stateId}", state.id) : ""
                "MemoryMergeStrategy" = try(each.value.memory_branching.merge_strategy, "")
              }
            }
            ResultSelector = {
              "body.$"       = "States.StringToJson($.Payload.Response)"
              "status_code.$" = "$.Payload.StatusCode"
              "session_id.$"  = "$.Payload.RuntimeSessionId"
            }
            ResultPath       = try(state.result_path, "$.results.${coalesce(try(state.agent_ref, null), try(state.agent, "unknown"))}")
            TimeoutSeconds   = try(state.timeout_seconds, 900)
            HeartbeatSeconds = try(state.heartbeat_seconds, 840)
            Retry = try(state.retry, null) != null ? [
              for r in state.retry : {
                ErrorEquals     = try(r.error_equals, ["States.ALL"])
                IntervalSeconds = try(r.interval_seconds, try(r.interval, 2))
                MaxAttempts     = try(r.max_attempts, 3)
                BackoffRate     = try(r.backoff_rate, 2.0)
              }
            ] : [{
              ErrorEquals     = ["States.ALL"]
              IntervalSeconds = try(state.retry_interval, 2)
              MaxAttempts     = try(state.retry_max, 3)
              BackoffRate     = try(state.retry_backoff, 2.0)
            }]
            Catch = try(state.catch, null) != null ? [
              for c in state.catch : {
                ErrorEquals = try(c.error_equals, ["States.ALL"])
                ResultPath  = try(c.result_path, "$.error.${state.id}")
                Next        = c.next
              }
            ] : [{
              ErrorEquals = ["States.ALL"]
              ResultPath  = "$.error.${coalesce(try(state.agent_ref, null), try(state.agent, "unknown"))}"
              Next        = "${state.id}_Failed"
            }]
          },
          try(state.next, null) != null ? { Next = state.next } : { End = true }
        )
      },

      # Auto-generated Fail states for agent tasks without explicit catch
      {
        for state in [
          for s in try(each.value.states, []) :
          s if(try(s.type, null) == "task" || try(s.type, null) == null) && (try(s.agent_ref, null) != null || try(s.agent, null) != null) && try(s.lambda_ref, null) == null && try(s.catch, null) == null
        ] :
        "${state.id}_Failed" => {
          Type  = "Fail"
          Error = "AgentExecutionFailed"
          Cause = "Agent ${coalesce(try(state.agent_ref, null), try(state.agent, "unknown"))} failed during ${state.id}"
        }
      },

      # ═══════════════════════════════════════════════════
      # LAMBDA TASK STATES (lambda_ref, no agent)
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if(try(s.type, null) == "task" || try(s.type, null) == null) && try(s.lambda_ref, null) != null && try(s.agent_ref, null) == null && try(s.agent, null) == null
        ] :
        state.id => merge(
          {
            Type     = "Task"
            Resource = "arn:aws:states:::lambda:invoke"
            Parameters = {
              "FunctionName" = try(
                var.lambda_arns[state.lambda_ref],
                "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.name_prefix}-${state.lambda_ref}"
              )
              "Payload.$" = "$"
            }
            ResultPath     = try(state.result_path, "$.results.${state.lambda_ref}")
            ResultSelector = { "body.$" = "$.Payload" }
            Retry = try(state.retry, null) != null ? [
              for r in state.retry : {
                ErrorEquals     = try(r.error_equals, ["States.ALL"])
                IntervalSeconds = try(r.interval_seconds, try(r.interval, 2))
                MaxAttempts     = try(r.max_attempts, 3)
                BackoffRate     = try(r.backoff_rate, 2.0)
              }
            ] : [{
              ErrorEquals     = ["States.ALL"]
              IntervalSeconds = try(state.retry_interval, 2)
              MaxAttempts     = try(state.retry_max, 3)
              BackoffRate     = try(state.retry_backoff, 2.0)
            }]
            Catch = try(state.catch, null) != null ? [
              for c in state.catch : {
                ErrorEquals = try(c.error_equals, ["States.ALL"])
                ResultPath  = try(c.result_path, "$.error.${state.id}")
                Next        = c.next
              }
            ] : [{
              ErrorEquals = ["States.ALL"]
              ResultPath  = "$.error.${state.lambda_ref}"
              Next        = "${state.id}_Failed"
            }]
          },
          try(state.next, null) != null ? { Next = state.next } : { End = true }
        )
      },

      # Auto-generated Fail states for lambda tasks without explicit catch
      {
        for state in [
          for s in try(each.value.states, []) :
          s if(try(s.type, null) == "task" || try(s.type, null) == null) && try(s.lambda_ref, null) != null && try(s.agent_ref, null) == null && try(s.agent, null) == null && try(s.catch, null) == null
        ] :
        "${state.id}_Failed" => {
          Type  = "Fail"
          Error = "LambdaExecutionFailed"
          Cause = "Lambda ${state.lambda_ref} failed during ${state.id}"
        }
      },

      # ═══════════════════════════════════════════════════
      # WAIT_FOR_TOKEN STATES (human-in-the-loop gates)
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if try(s.type, null) == "wait_for_token"
        ] :
        state.id => merge(
          {
            Type     = "Task"
            Resource = "arn:aws:states:::lambda:invoke.waitForTaskToken"
            Parameters = {
              "FunctionName" = try(
                var.lambda_arns[state.lambda_ref],
                "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.name_prefix}-${state.lambda_ref}"
              )
              "Payload" = {
                "task_token.$" = "$$.Task.Token"
                "input.$"      = "$"
              }
            }
            HeartbeatSeconds = try(state.heartbeat_seconds, 3600)
            ResultPath       = try(state.result_path, "$.token_result")
            Catch = try(state.catch, null) != null ? [
              for c in state.catch : {
                ErrorEquals = try(c.error_equals, ["States.ALL"])
                ResultPath  = try(c.result_path, "$.error.${state.id}")
                Next        = c.next
              }
            ] : [{
              ErrorEquals = ["States.ALL"]
              ResultPath  = "$.error.${state.id}"
              Next        = "${state.id}_Failed"
            }]
          },
          try(state.next, null) != null ? { Next = state.next } : { End = true }
        )
      },

      # Auto-generated Fail states for wait_for_token without explicit catch
      {
        for state in [
          for s in try(each.value.states, []) :
          s if try(s.type, null) == "wait_for_token" && try(s.catch, null) == null
        ] :
        "${state.id}_Failed" => {
          Type  = "Fail"
          Error = "WaitForTokenFailed"
          Cause = "Wait-for-token timed out or failed during ${state.id}"
        }
      },

      # ═══════════════════════════════════════════════════
      # CHOICE STATES (conditional routing)
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if try(s.type, null) == "choice"
        ] :
        state.id => merge(
          {
            Type = "Choice"
            Choices = [
              for rule in try(state.choices, []) :
              merge(
                { Variable = rule.condition.path },
                # Presence check (IsPresent / IsNull) — before type coercion
                try(rule.condition.op, "") == "is_present" ? {
                  IsPresent = tobool(rule.condition.value)
                } : {},
                try(rule.condition.op, "") == "is_null" ? {
                  IsNull = tobool(rule.condition.value)
                } : {},
                # Boolean comparison (check first — tobool is strictest)
                can(tobool(rule.condition.value)) && try(rule.condition.op, "eq") == "eq" ? {
                  BooleanEquals = tobool(rule.condition.value)
                } : {},
                can(tobool(rule.condition.value)) && try(rule.condition.op, "") == "neq" ? {
                  BooleanNotEquals = tobool(rule.condition.value)
                } : {},
                # Numeric comparisons (check before string — tonumber is stricter)
                !can(tobool(rule.condition.value)) && can(tonumber(rule.condition.value)) ? merge(
                  try(rule.condition.op, "eq") == "eq" ? { NumericEquals = tonumber(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "neq" ? { NumericNotEquals = tonumber(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "gt" ? { NumericGreaterThan = tonumber(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "gte" ? { NumericGreaterThanEquals = tonumber(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "lt" ? { NumericLessThan = tonumber(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "lte" ? { NumericLessThanEquals = tonumber(rule.condition.value) } : {}
                ) : {},
                # String comparisons (fallback)
                !can(tobool(rule.condition.value)) && !can(tonumber(rule.condition.value)) ? merge(
                  try(rule.condition.op, "eq") == "eq" ? { StringEquals = tostring(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "neq" ? { StringNotEquals = tostring(rule.condition.value) } : {},
                  try(rule.condition.op, "") == "matches" ? { StringMatches = tostring(rule.condition.value) } : {}
                ) : {},
                { Next = rule.next }
              )
              if try(rule.condition, null) != null
            ]
          },
          # Default: from entry without condition, or from state.default
          length([for r in try(state.choices, []) : r if try(r.condition, null) == null]) > 0 ? {
            Default = [for r in try(state.choices, []) : r.next if try(r.condition, null) == null][0]
          } : try(state.default, null) != null ? {
            Default = state.default
          } : {}
        )
      },

      # ═══════════════════════════════════════════════════
      # PARALLEL STATES
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if try(s.type, null) == "parallel" || (try(s.type, null) == null && can(s.parallel))
        ] :
        state.id => merge(
          {
            Type = "Parallel"
            Branches = [
              for branch in try(state.branches, try(state.parallel, [])) :
              # jsondecode(jsonencode()) normalizes dynamic object types
              # so TF doesn't complain about different State keys per branch.
              jsondecode(jsonencode(try(branch.states, null) != null ? {
                StartAt = branch.states[0].id
                States = {
                  for bs in branch.states :
                  bs.id => merge(
                    {
                      Type     = "Task"
                      Resource = "arn:aws:states:::lambda:invoke"
                      Parameters = {
                        "FunctionName" = aws_lambda_function.invoke_agent.arn
                        "Payload" = {
                          "AgentRuntimeArn" = try(
                            var.agent_runtime_arns[coalesce(try(bs.agent_ref, null), try(bs.agent, "unknown"))],
                            "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${coalesce(try(bs.agent_ref, null), try(bs.agent, "unknown"))}"
                          )
                          "Qualifier"          = "DEFAULT"
                          "Prompt.$"           = try(bs.prompt, "$.prompt")
                          "MemoryBranch"       = ""
                          "MemoryMergeStrategy" = ""
                        }
                      }
                      ResultPath = try(bs.result_path, "$.results.${coalesce(try(bs.agent_ref, null), try(bs.agent, "unknown"))}")
                      TimeoutSeconds = try(bs.timeout_seconds, 900)
                    },
                    {
                      ResultSelector = {
                        "body.$"       = "States.StringToJson($.Payload.Response)"
                        "status_code.$" = "$.Payload.StatusCode"
                        "session_id.$"  = "$.Payload.RuntimeSessionId"
                      }
                    },
                    {
                      Retry = try(bs.retry, null) != null ? [
                        for r in bs.retry : {
                          ErrorEquals     = try(r.error_equals, ["States.ALL"])
                          IntervalSeconds = try(r.interval_seconds, 2)
                          MaxAttempts     = try(r.max_attempts, 3)
                          BackoffRate     = try(r.backoff_rate, 2.0)
                        }
                      ] : [{
                        ErrorEquals     = ["States.ALL"]
                        IntervalSeconds = 2
                        MaxAttempts     = try(bs.retry_max, 3)
                        BackoffRate     = 2.0
                      }]
                    },
                    try(bs.next, null) != null ? { Next = bs.next } : { End = true }
                  )
                }
              } : {
                # Legacy simple branch: single agent reference — also via Lambda wrapper
                StartAt = coalesce(try(branch.agent_ref, null), try(branch.agent, "unknown"))
                States = {
                  (coalesce(try(branch.agent_ref, null), try(branch.agent, "unknown"))) = {
                    Type     = "Task"
                    Resource = "arn:aws:states:::lambda:invoke"
                    Parameters = {
                      "FunctionName" = aws_lambda_function.invoke_agent.arn
                      "Payload" = {
                        "AgentRuntimeArn" = try(
                          var.agent_runtime_arns[coalesce(try(branch.agent_ref, null), try(branch.agent, "unknown"))],
                          "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/${coalesce(try(branch.agent_ref, null), try(branch.agent, "unknown"))}"
                        )
                        "Qualifier"          = "DEFAULT"
                        "Prompt.$"           = "$.prompt"
                        "MemoryBranch"       = ""
                        "MemoryMergeStrategy" = ""
                      }
                    }
                    ResultSelector = {
                      "body.$"       = "States.StringToJson($.Payload.Response)"
                      "status_code.$" = "$.Payload.StatusCode"
                      "session_id.$"  = "$.Payload.RuntimeSessionId"
                    }
                    ResultPath = "$.results.${coalesce(try(branch.agent_ref, null), try(branch.agent, "unknown"))}"
                    TimeoutSeconds = 900
                    Retry = [{
                      ErrorEquals     = ["States.ALL"]
                      IntervalSeconds = 2
                      MaxAttempts     = 3
                      BackoffRate     = 2.0
                    }]
                    End = true
                  }
                }
              }))
            ]
            ResultPath = try(state.result_path, "$.parallel_results")
            Catch = try(state.catch, null) != null ? [
              for c in state.catch : {
                ErrorEquals = try(c.error_equals, ["States.ALL"])
                ResultPath  = try(c.result_path, "$.error.${state.id}")
                Next        = c.next
              }
            ] : []
          },
          try(state.next, null) != null ? { Next = state.next } : { End = true }
        )
      },

      # ═══════════════════════════════════════════════════
      # SUCCEED STATES (terminal success)
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if try(s.type, null) == "succeed"
        ] :
        state.id => merge(
          { Type = "Succeed" },
          try(state.comment, null) != null ? { Comment = state.comment } : {}
        )
      },

      # ═══════════════════════════════════════════════════
      # FAIL STATES (terminal failure)
      # ═══════════════════════════════════════════════════
      {
        for state in [
          for s in try(each.value.states, []) :
          s if try(s.type, null) == "fail"
        ] :
        state.id => {
          Type  = "Fail"
          Error = try(state.error, state.id)
          Cause = try(state.cause, "Workflow reached fail state: ${state.id}")
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
