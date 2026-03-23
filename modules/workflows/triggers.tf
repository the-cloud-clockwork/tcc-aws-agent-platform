## -----------------------------------------------------
## Workflows Module -- EventBridge Triggers
## Scheduled execution of workflow state machines.
## -----------------------------------------------------

resource "aws_cloudwatch_event_rule" "scheduled" {
  for_each = {
    for k, wf in local.workflows :
    k => wf if try(wf.trigger.type, "") == "schedule"
  }

  name                = "${local.name_prefix}-${each.key}-trigger"
  schedule_expression = each.value.trigger.schedule

  tags = merge(local.tags, {
    Workflow = each.key
  })
}

resource "aws_cloudwatch_event_target" "sfn" {
  for_each = aws_cloudwatch_event_rule.scheduled

  rule     = each.value.name
  arn      = aws_sfn_state_machine.workflows[each.key].arn
  role_arn = aws_iam_role.events[each.key].arn

  input_transformer {
    input_paths = {
      time = "$.time"
    }
    input_template = <<-TEMPLATE
      {
        "trigger": "scheduled",
        "scheduled_time": <time>,
        "workflow": "${each.key}",
        "environment": "${var.environment}"
      }
    TEMPLATE
  }
}
