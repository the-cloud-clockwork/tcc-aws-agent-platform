# ── Scheduled Lambda ──────────────────────────────────────────────────────────
# Encapsulates the EventBridge rule + target + Lambda permission triad.

resource "aws_cloudwatch_event_rule" "this" {
  name                = "${var.resource_prefix}-${var.name}"
  description         = var.description
  schedule_expression = var.schedule_expression

  tags = merge(var.tags, {
    Name = "${var.resource_prefix}-${var.name}"
  })
}

resource "aws_cloudwatch_event_target" "this" {
  rule = aws_cloudwatch_event_rule.this.name
  arn  = var.function_arn
}

resource "aws_lambda_permission" "this" {
  statement_id  = "AllowEventBridge-${var.name}"
  action        = "lambda:InvokeFunction"
  function_name = var.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.this.arn
}
