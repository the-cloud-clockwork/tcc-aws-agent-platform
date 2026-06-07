---
title: Getting Started
nav_order: 2
has_children: true
---

# Getting Started

This section is the on-ramp for new users. By the end you will have the SDK installed, a running agent blueprint validated locally, and a clear picture of how to wire the full AWS infrastructure.

---

## In This Section

| Page | What It Covers |
|------|----------------|
| [**Create a Domain Repo**]({{ '/docs/getting-started/create-domain-repo' | relative_url }}) | One command scaffolds a complete project — agents, MCP servers, Lambdas, Terraform. **Start here if you want a full project fast.** |
| [Quickstart]({{ '/docs/getting-started/quickstart' | relative_url }}) | Install the SDK and CLI, write a minimal blueprint, validate with `agentcli`. Working in under 10 minutes. |
| [Installation]({{ '/docs/getting-started/installation' | relative_url }}) | All packages, optional extras, development install, Terraform module wiring, and every environment variable the platform reads. |
| [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) | Step-by-step tutorial: blueprint YAML, prompt builder, 5-line handler, validate, deploy, invoke. |

---

## How the Platform Works in One Paragraph

You declare agents as YAML blueprints in your domain repo. The platform reads those declarations and produces fully operational AWS infrastructure — AgentCore Runtime containers, Gateway tool routing, Memory persistence, Identity flows, Cedar policies, observability hooks, and multi-agent orchestration — with no runtime glue code. One handler file serves every agent you declare. The blueprint determines which model provider, tools, prompts, memory strategies, identity providers, and policies are wired at startup.

---

## Before You Start

- **AWS account** with Bedrock enabled in your target region (required for the Bedrock provider; other providers work without Bedrock model access).
- **Python 3.11 or higher** — 3.12 recommended.
- **Terraform 1.9+** for infrastructure deployment.
- **Docker 24+** for building Runtime container images.
- **AWS CLI 2.x** configured with credentials (`aws configure` or environment variables).

{: .note }
> The `agent-core` and `agent-cli` packages are distributed via a private Python package repository. Configure your pip index URL according to your organization's package distribution setup before running `pip install`.

---

## Choosing an Inference Provider

The platform is provider-agnostic. Pick the provider that matches your setup:

| Provider | When to use | Key requirement |
|----------|-------------|-----------------|
| `bedrock` (default) | AWS-native deployments | `BEDROCK_REGION` env var |
| `litellm` | Self-hosted proxy, OpenAI-compatible APIs, multi-model | `base_url` + `api_key_env` in blueprint |
| `anthropic` | Direct Anthropic API | `api_key_env` in blueprint |
| `vertex` | Google Cloud / Gemini models | `GOOGLE_APPLICATION_CREDENTIALS` |

The [Inference Providers]({{ '/docs/inference/' | relative_url }}) section covers every provider in detail, including how to switch providers by changing two lines in your blueprint YAML.

---

## Next Steps

Start with [Create a Domain Repo]({{ '/docs/getting-started/create-domain-repo' | relative_url }}) for the fastest path to a deployable project, or go to [Quickstart]({{ '/docs/getting-started/quickstart' | relative_url }}) to install the SDK and validate a blueprint in under 10 minutes.
