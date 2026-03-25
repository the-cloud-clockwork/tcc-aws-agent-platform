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
  count = var.artifacts_mcp_lambda_arn != "" ? 1 : 0

  name               = "${local.prefix}-${local.env}-artifacts-tools"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id
  description        = "Platform artifact storage tools — create, get, list, search artifacts in S3 + DynamoDB"

  target_configuration {
    mcp {
      lambda {
        lambda_arn = var.artifacts_mcp_lambda_arn

        tool_schema {
          inline_payload {
            name        = "create_artifact"
            description = "Store agent output as a versioned S3 artifact with DynamoDB catalog entry. Returns artifact_id and signed_url."
            input_schema {
              type        = "object"
              description = "Artifact creation parameters: type (chart|report|simulation_result|recommendation|image|data_export|pipeline_run), content (string), optional: metadata, agent_id, execution_id, idempotency_key, tier, kms_key_alias, pipeline_date"
            }
          }
        }

        tool_schema {
          inline_payload {
            name        = "get_artifact"
            description = "Retrieve artifact metadata and a pre-signed S3 download URL by artifact_id."
            input_schema {
              type        = "object"
              description = "Parameters: artifact_id (string, required)"
            }
          }
        }

        tool_schema {
          inline_payload {
            name        = "list_artifacts"
            description = "List artifacts with optional filters by type, agent_id, date, execution_id. Returns catalog entries without content."
            input_schema {
              type        = "object"
              description = "Optional parameters: type, agent_id, date, limit (default 50), execution_id"
            }
          }
        }

        tool_schema {
          inline_payload {
            name        = "poll_artifact"
            description = "Poll for artifact readiness (deprecated — create_artifact now returns signed_url directly). Retained for backward compatibility."
            input_schema {
              type        = "object"
              description = "Parameters: artifact_id (string, required), timeout_s (int, default 30)"
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
