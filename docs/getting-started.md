---
title: Getting Started
nav_order: 2
has_children: true
---

# Getting Started

This section covers everything you need to go from zero to a running AI agent on AWS. By the end, you will have the SDK and CLI installed, a valid agent blueprint, and a clear picture of how to deploy the full stack.

---

## In This Section

| Page | What It Covers |
|------|----------------|
| [Quickstart]({{ '/docs/getting-started/quickstart' | relative_url }}) | Prerequisites, install the SDK and CLI, write a minimal blueprint, validate with `agentcli` |
| [Installation]({{ '/docs/getting-started/installation' | relative_url }}) | All four SDK packages, development installs, Terraform module setup, environment variables |
| [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) | Step-by-step tutorial: blueprint YAML, prompt builder, handler, validate, build, deploy |

---

## How the Platform Works in One Paragraph

You define agents as YAML blueprints in your domain repo. The platform reads those declarations and turns them into fully operational AWS infrastructure: AgentCore Runtime containers, Gateway tool routing, Memory persistence, Identity flows, Cedar policies, observability, and multi-agent orchestration -- without runtime glue code. One handler file serves every agent you declare; the blueprint determines which model, tools, prompts, memory strategies, identity providers, and policies are wired.

---

## Before You Start

- You need an AWS account with Bedrock enabled in your target region.
- Python 3.12 or higher is required.
- Terraform 1.9+ is required for infrastructure deployment.
- The `agent-core` and `agent-cli` packages are distributed via a private package repository. Configure your pip index URL before installing.

---

## Next Steps

Start with the [Quickstart]({{ '/docs/getting-started/quickstart' | relative_url }}) for the fastest path to a running agent. If you want the full installation reference first, go to [Installation]({{ '/docs/getting-started/installation' | relative_url }}).
