---
title: "Tools, MCP & Gateway"
nav_order: 8
has_children: true
---

# Tools, MCP & Gateway

AgentCore Gateway is the universal tool bridge: it translates any backend — Lambda functions, OpenAPI services, Smithy services, API Gateway endpoints, or MCP servers — into a single MCP interface that agents consume without writing custom adapters or managing backend credentials.

The platform also provides:

- **`BaseMCPServer`** — a base class for building domain MCP servers with transport handling, tool registration, `$defs` flattening, and observability built in
- **Built-in tools** — Code Interpreter and Browser, both Gateway-mediated with no local SDK client
- **Artifact Store** — a Lambda-backed MCP tool set implementing the claim-check pattern for large outputs that would otherwise exceed Step Functions payload limits

## In This Section

| Page | What It Covers |
|------|---------------|
| [Gateway](tools/gateway) | Protocol translation, the five target types (Lambda, MCP Server, OpenAPI, Smithy, API Gateway), two auth layers (inbound SigV4/JWT, outbound IAM/OAuth2), `gateway-targets.yaml` format, `GatewayClient` usage |
| [MCP Servers](tools/mcp) | `BaseMCPServer` usage and `$defs` flattening, Redis cache layer (`cache_get`/`cache_set`), execution-mode provider routing (`resolve_provider`), naming conventions |
| [Built-in Tools](tools/builtin-tools) | Code Interpreter and Browser providers — Gateway-mediated, dynamically discovered, no local lifecycle management |
| [Artifacts](tools/artifacts) | Claim-check pattern, the four MCP tools (`create_artifact`, `get_artifact`, `list_artifacts`, `poll_artifact`), two-tier S3/KMS security model, signed URL strategies, SQS notifications |

## Key Design Principle

**Agents never connect directly to tool backends.** Every tool call — whether to a Lambda function, an MCP server, or a built-in AWS service — goes through Gateway. This means:

- Credentials stay in one place (resolved by Gateway), not scattered across agent code
- Policy enforcement (Cedar) happens centrally at Gateway before any backend is reached
- Agents mix local tools and remote Gateway tools in a single flat tool list
- Backend infrastructure can change without modifying agent code
