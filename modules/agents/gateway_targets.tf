# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — Gateway Targets
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
    lambda_target_configuration {
      lambda_arn = each.value.lambda_arn

      # Tool schema — inline tool definitions from the targets file
      tool_schema {
        inline_payload {
          inline_tool_definitions = [
            for tool in try(each.value.tools, []) : {
              name        = tool.name
              description = try(tool.description, "Tool: ${tool.name}")
              input_schema = try(
                jsonencode(tool.input_schema),
                jsonencode({ type = "object", properties = {} })
              )
            }
          ]
        }
      }
    }
  }

  credential_provider_configurations = [
    {
      credential_provider_type = "GATEWAY_IAM_ROLE"
    }
  ]

  tags = merge(local.tags, {
    Name      = each.value.name
    Component = "gateway-target"
  })
}
