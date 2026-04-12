# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module -- Artifacts Gateway Target
#
# Registers the platform artifacts MCP tools Lambda as a Gateway target.
# This enables all agents to discover and call artifact tools (create, get,
# list, search, poll) via the standard MCP protocol through the Gateway.
#
# The target is conditional on var.artifacts_mcp_lambda_arn being non-empty.
# When the api sub-module deploys the MCP tools Lambda, it passes the ARN
# through to this module.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_gateway_target" "artifacts_tools" {
  count = var.enable_artifacts_gateway_target ? 1 : 0

  name               = "${local.prefix}-${local.env}-artifacts-tools"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id
  description        = "Platform artifact storage tools — create, get, list, search artifacts in S3 + DynamoDB"

  target_configuration {
    mcp {
      lambda {
        lambda_arn = var.artifacts_mcp_lambda_arn

        # Provider MaxItems=1 on tool_schema — register primary tool only.
        # Full tool list (create, get, list, poll) discovered at runtime from Lambda handler.
        tool_schema {
          inline_payload {
            name        = "create_artifact"
            description = "Store agent output as a versioned S3 artifact with DynamoDB catalog entry. Returns artifact_id and signed_url."
            input_schema {
              type = "object"
              # Explicit properties so the Gateway delivers typed keys to the
              # Lambda. Without this, `type` and `content` arrive as an opaque
              # blob and the handler misroutes to list_artifacts, raising
              # KeyError: 'type'.
              property {
                name        = "type"
                type        = "string"
                description = "Artifact type (chart, report, simulation_result, recommendation, image, data_export, pipeline_run)"
                required    = true
              }
              property {
                name        = "content"
                type        = "string"
                description = "Artifact content string (base64 for images)"
                required    = true
              }
              property {
                name        = "metadata"
                type        = "object"
                description = "Optional key/value metadata"
              }
              property {
                name        = "agent_id"
                type        = "string"
                description = "Agent that created this artifact"
              }
              property {
                name        = "execution_id"
                type        = "string"
                description = "Execution/run identifier"
              }
              property {
                name        = "idempotency_key"
                type        = "string"
                description = "Idempotency key ({agent_id}:{execution_id}:{operation}:{param_hash})"
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
