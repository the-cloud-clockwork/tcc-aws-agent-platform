# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Gateway Targets
#
# Registers tool targets with the AgentCore Gateway. Supports two target types:
#
# 1. LAMBDA — wraps a Lambda function as MCP tools
#    Required: lambda_arn, tools[]
#
# 2. MCP_SERVER — points to an AgentCore Runtime running protocol: MCP
#    Auto-registered for every blueprint with runtime.protocol == "MCP"
#    Uses the Runtime endpoint URL derived from the Runtime ARN
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Explicit targets from gateway-targets.yaml (typically LAMBDA targets)
  gateway_target_map = {
    for target in try(local.gateway_targets.targets, []) :
    target.name => target
  }

  # Auto-registered MCP Runtime targets — every blueprint with protocol: MCP
  mcp_runtime_targets = {
    for id, bp in local.blueprints :
    id => bp
    if try(upper(bp.runtime.protocol), "HTTP") == "MCP"
  }
}

# ── Explicit targets (LAMBDA) from gateway-targets.yaml ──────────────────────

resource "aws_bedrockagentcore_gateway_target" "explicit" {
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

# ── Auto-registered MCP Runtime targets ──────────────────────────────────────
#
# For each blueprint with runtime.protocol: MCP, create a gateway target
# pointing to the Runtime's /invocations endpoint. Auth uses the Gateway's
# IAM role (Runtime-to-Gateway communication is IAM-based within the same
# account/VPC).

resource "aws_bedrockagentcore_gateway_target" "mcp_runtime" {
  for_each = local.mcp_runtime_targets

  name               = each.key
  gateway_identifier = var.gateway_id

  target_configuration {
    mcp {
      mcp_server {
        endpoint = "https://bedrock-agentcore.${var.aws_region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.agent[each.key].agent_runtime_arn)}/invocations"
      }
    }
  }

  credential_provider_configuration {
    gateway_iam_role {}
  }

  depends_on = [
    aws_bedrockagentcore_agent_runtime.agent,
    aws_bedrockagentcore_agent_runtime_endpoint.agent,
  ]
}
