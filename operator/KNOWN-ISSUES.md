# Known Issues — AgentCore Platform

## KI-001: Gateway tools/call fails for MCP runtime targets

**Status:** OPEN (workaround deployed)
**AWS Issues:** [#809](https://github.com/awslabs/amazon-bedrock-agentcore-samples/issues/809), [#1030](https://github.com/awslabs/amazon-bedrock-agentcore-samples/issues/1030)
**Since:** December 2025
**Affected:** All regions, all MCP runtime targets with OAuth

### Symptom

AgentCore Gateway returns `"An internal error occurred"` for every `tools/call` request to MCP runtime targets. `tools/list` works. `PingRequest` works. The tool call never reaches the MCP runtime — CloudWatch logs show only PingRequest, never CallToolRequest.

### Root Cause

AWS service bug in the Gateway's request forwarding to MCP runtimes via OAuth credential provider. The Gateway authenticates the inbound request (SigV4) but fails internally when proxying the tool execution to the MCP runtime using the outbound OAuth2 `client_credentials` flow.

### Workaround

Feature flag `GATEWAY_DIRECT_MCP=true` bypasses the Gateway for MCP tool calls. Agents connect directly to MCP runtimes using Cognito JWT tokens (`client_credentials` grant), while still using the Gateway for Lambda targets (risk-engine, artifacts-mcp).

**Code:** `agent_core.gateway.direct_mcp_client`
**Flag:** `GATEWAY_DIRECT_MCP` env var (set via `gateway_direct_mcp` Terraform variable)
**Env vars injected when enabled:** `MCP_DIRECT_URLS`, `COGNITO_TOKEN_URL`, `COGNITO_MCP_CLIENT_ID`, `COGNITO_MCP_CLIENT_SECRET`, `COGNITO_MCP_SCOPES`

### Remove When

AWS fixes Gateway Issue #809:
1. Set `gateway_direct_mcp = false` in domain tfvars
2. `terraform apply`
3. Verify `tools/call` works through Gateway
4. Remove `direct_mcp_client.py` and feature flag code in cleanup PR

---

## KI-002: Cedar policy engines are SDK-managed, not IaC

**Status:** ACCEPTED (by design)
**Since:** 2026-04-08
**Affected:** All environments

### Description

AgentCore policy engines and Cedar policies are created at runtime by the SDK (`PolicyWiring` in `agent_core.policy.wiring`), not by Terraform. The `aws_bedrockagentcore_policy_engine` resource type does not exist in AWS provider 6.37. The SDK creates engines idempotently via `PolicyClient.create_engine()`.

### Implication

Policy state lives in AgentCore's control plane, not in Terraform state. Policy changes are deployed when agents start (runtime wiring), not during `terraform apply`. This means policy drift is not detectable by Terraform.

### When to Revisit

When AWS publishes `aws_bedrockagentcore_policy_engine` as a Terraform resource, evaluate migrating to IaC-managed policies for state tracking and drift detection.
