## -----------------------------------------------------
## Workflows Module -- EventBridge Triggers
## Schedule and event-pattern execution of workflows.
## -----------------------------------------------------

# --- Schedule-based triggers ---
resource "aws_cloudwatch_event_rule" "scheduled" {
  for_each = local.workflows_with_schedule_triggers

  name                = "${local.name_prefix}-${each.key}-trigger"
  schedule_expression = each.value.trigger.schedule

  tags = merge(local.tags, {
    Workflow = each.key
  })
}

resource "aws_cloudwatch_event_target" "sfn_scheduled" {
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

# --- Event-pattern-based triggers ---
resource "aws_cloudwatch_event_rule" "event_pattern" {
  for_each = local.workflows_with_event_triggers

  name           = "${local.name_prefix}-${each.key}-event-trigger"
  event_bus_name = try(each.value.trigger.event_bus_name, "default")
  event_pattern  = jsonencode(each.value.trigger.event_pattern)

  tags = merge(local.tags, {
    Workflow = each.key
  })
}

resource "aws_cloudwatch_event_target" "sfn_event_pattern" {
  for_each = aws_cloudwatch_event_rule.event_pattern

  rule           = each.value.name
  event_bus_name = try(local.workflows_with_event_triggers[each.key].trigger.event_bus_name, "default")
  arn            = aws_sfn_state_machine.workflows[each.key].arn
  role_arn       = aws_iam_role.events[each.key].arn

  input_transformer {
    input_paths = {
      source      = "$.source"
      detail_type = "$.detail-type"
      detail      = "$.detail"
      time        = "$.time"
    }
    input_template = <<-TEMPLATE
      {
        "trigger": "event",
        "event_source": <source>,
        "event_detail_type": <detail_type>,
        "event_detail": <detail>,
        "event_time": <time>,
        "workflow": "${each.key}",
        "environment": "${var.environment}"
      }
    TEMPLATE
  }
}
