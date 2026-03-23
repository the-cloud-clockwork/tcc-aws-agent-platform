# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Gateway Targets
#
# Registers tool targets with the AgentCore Gateway based on the
# gateway-targets.yaml file. Each target maps a Lambda function to a set
# of tool definitions that agents can invoke through the Gateway.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Build a map of targets keyed by name for for_each
  gateway_target_map = {
    for target in try(local.gateway_targets.targets, []) :
    target.name => target
  }
}

resource "aws_bedrockagentcore_gateway_target" "this" {
  for_each = local.gateway_target_map

  name               = each.value.name
  gateway_identifier = var.gateway_id

  target_configuration {
    mcp {
      lambda {
        lambda_arn = each.value.lambda_arn

        dynamic "tool_schema" {
          for_each = try(each.value.tools, [])
          content {
            inline_payload {
              name        = tool_schema.value.name
              description = try(tool_schema.value.description, "Tool: ${tool_schema.value.name}")

              input_schema {
                type        = "object"
                description = try(tool_schema.value.description, "Input for ${tool_schema.value.name}")
              }
            }
          }
        }
      }
    }
  }

  credential_provider_configuration {
    gateway_iam_role {}
  }
}
