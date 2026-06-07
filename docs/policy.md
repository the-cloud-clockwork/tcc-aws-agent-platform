---
title: "Identity, Policy & IAM"
nav_order: 7
has_children: true
---

# Identity, Policy & IAM

The platform manages authentication at every boundary: inbound (who can call your agent), outbound (what credentials your agent uses), and between agents (machine-to-machine tokens via delegation, not impersonation). On top of identity, a Cedar policy engine enforces fine-grained access control on every tool call before it reaches any backend.

This section covers three topics:

- **[Identity](policy/identity)** — inbound JWT/IAM validation, outbound API key injection, three-legged OAuth, and machine-to-machine (M2M) tokens.
- **[Cedar Policy](policy/cedar-policy)** — default-DENY access control engine attached to the Gateway; every tool call is evaluated against Cedar rules before reaching any backend.
- **[IAM](policy/iam)** — per-agent execution roles, Gateway role, KMS envelope encryption, and how inference API keys are wired into the runtime.
