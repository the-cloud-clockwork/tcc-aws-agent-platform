# BLOCKS.md — Active Work Blocks

> **Purpose:** Major work blocks for the project. Always kept current.
> **Rule:** Update this file every session. Blocks move through: `design` → `ready` → `in-progress` → `done`

---

## Block: Remove Network Sub-Module ▸ `done`

Networking is owned by a separate project. This platform module now consumes externally-created VPC resources via input variables + data sources.

- [x] Remove `modules/platform/modules/network/` (VPC, subnets, IGW, NAT, route tables, security groups)
- [x] Replace `vpc_cidr`, `availability_zones`, `nat_gateway_count` with input variables (`vpc_id`, `private_subnet_ids`, etc.)
- [x] Add `data "aws_vpc" "main"` to hydrate VPC ID for `cidr_block` access
- [x] Update security module wiring, outputs, SSM parameters
- [x] Update all 3 tfvars with documented placeholder IDs
- [x] Update CLAUDE.md: add Network Requirements table, add rule #10, trim to <200 lines
- [x] Sweep: removed 3 unused data sources, added `private_subnet_ids` validation

---

## Sweep Log

### 2026-04-02

- **Issues found:** 13 (quality: 13, compliance: 0, integration: 0)
- **Fixed:** 5 (3 unused data sources removed, 1 validation added, 1 doc update)
- **Remaining:** 8 pre-existing issues (throttle burst/rate inversion in staging+prod tfvars, hardcoded `enable_artifacts_gateway_target`, missing JWT cross-variable validation, SSM SecureString for KMS ARNs, CloudFront output guards, missing `sns_alert_email` in staging/prod, `mcp_m2m_client_id` sensitivity)
