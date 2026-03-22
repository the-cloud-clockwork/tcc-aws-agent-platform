---
layout: home
title: Home
nav_order: 1
description: "AWS Agent Platform — Declare AI agents in YAML, deploy on AWS with zero boilerplate."
permalink: /
---

# Declare AI agents in YAML. Deploy on AWS.
{: .fs-9 }

A configuration-driven, domain-agnostic runtime built over **Strands Agents SDK** and **Amazon Bedrock AgentCore**. Define agents, strategies, and workflows as YAML blueprints — the platform handles Runtime, Gateway, Memory, Identity, Policy, Observability, and everything else.
{: .fs-6 }

<div class="hero-actions">
  <a href="{{ '/docs/getting-started/quickstart' | relative_url }}" class="btn btn-primary">Get Started</a>
  <a href="{{ '/docs/' | relative_url }}" class="btn btn-outline">Documentation</a>
</div>

---

## The Problem

Amazon Bedrock AgentCore provides 12 powerful services for building AI agents on AWS — Runtime, Gateway, Identity, Memory, Tools, Observability, Evaluation, Policy, A2A, and more. But wiring them together requires hundreds of lines of infrastructure code, SDK integration, and deployment plumbing **per agent**.

**This platform eliminates that boilerplate.** You write a YAML blueprint. The platform reads it, resolves all dependencies, and produces a fully operational agent deployed to AgentCore Runtime.

---

<div class="feature-grid">
  <div class="feature-card">
    <h3>Blueprint Engine</h3>
    <p>Define agents in YAML. The platform assembles Runtime, Gateway, Memory, Identity, Policy, and Observability from a single file. Zero glue code.</p>
  </div>
  <div class="feature-card">
    <h3>Universal Tool Bridge</h3>
    <p>Gateway translates MCP, Lambda, REST, and OpenAPI backends through one protocol. Agents never know what is behind the tools they call.</p>
  </div>
  <div class="feature-card">
    <h3>Terraform Modules</h3>
    <p>Three composable modules — platform, agents, workflows. Domain repos consume via <code>module "platform" { source = "..." }</code>.</p>
  </div>
  <div class="feature-card">
    <h3>Full Observability</h3>
    <p>OTEL auto-instrumentation, Langfuse integration, audit logging, cost tracking, and CloudWatch GenAI traces — all from zero configuration.</p>
  </div>
</div>

---

## How It Works

```mermaid
graph LR
    A[YAML Blueprint] --> B[BlueprintLoader]
    B --> C[Strands Agent]
    C --> D[Docker / ECR]
    D --> E[AgentCore Runtime<br/>microVM]
    E --> F[Gateway]
    F --> G[Lambda Functions]
    F --> H[MCP Servers]
    F --> I[REST APIs]

    E -.-> J[Memory Service]
    E -.-> K[Identity Service]
    E -.-> L[Policy Engine]

    style A fill:#00bcd4,stroke:#00bcd4,color:#000
    style E fill:#ff9800,stroke:#ff9800,color:#000
    style F fill:#10b981,stroke:#10b981,color:#000
```

**One handler serves every agent.** The YAML blueprint determines which model, tools, prompts, memory strategies, identity providers, and Cedar policies are wired. Your domain repo only provides: prompt builders, business schemas, and domain-specific tool implementations.

---

## The 12 Building Blocks

Every agent blueprint can configure any combination of these blocks:
{: .blocks-table }

| # | Block | What It Does |
|---|-------|-------------|
| 1 | [**Runtime**]({{ '/docs/architecture/building-blocks#runtime' | relative_url }}) | Hosts agents in isolated microVMs per session |
| 2 | [**Gateway**]({{ '/docs/architecture/building-blocks#gateway' | relative_url }}) | Protocol translator — makes any backend look like MCP |
| 3 | [**Identity**]({{ '/docs/architecture/building-blocks#identity' | relative_url }}) | JWT validation, API keys, OAuth 3LO, M2M auth |
| 4 | [**Memory**]({{ '/docs/architecture/building-blocks#memory' | relative_url }}) | Short-term events + long-term semantic knowledge |
| 5 | [**Tools**]({{ '/docs/architecture/building-blocks#tools' | relative_url }}) | Managed Code Interpreter + Browser |
| 6 | [**Observability**]({{ '/docs/architecture/building-blocks#observability' | relative_url }}) | OTEL traces, Langfuse, audit logs, cost tracking |
| 7 | [**Evaluation**]({{ '/docs/architecture/building-blocks#evaluation' | relative_url }}) | 13 built-in evaluators + custom LLM-as-judge |
| 8 | [**Policy**]({{ '/docs/architecture/building-blocks#policy' | relative_url }}) | Cedar fine-grained access control on Gateway |
| 9 | [**Strands**]({{ '/docs/architecture/building-blocks#strands' | relative_url }}) | Native integration with Strands Agents SDK |
| 10 | [**A2A**]({{ '/docs/architecture/building-blocks#a2a' | relative_url }}) | Agent-to-agent discovery and communication |
| 11 | [**Infrastructure**]({{ '/docs/infrastructure/' | relative_url }}) | Terraform modules for platform + agents + workflows |
| 12 | [**Blueprints**]({{ '/docs/blueprints/' | relative_url }}) | YAML configuration abstraction over all blocks |

---

## Quick Start

```bash
# Install the SDK and CLI
pip install agent-core agent-cli

# Validate your agent blueprint
agentcli blueprint lint blueprints/agents/my-agent.yaml

# Deploy platform infrastructure (Terraform)
cd infra/
terraform init && terraform apply

# Deploy your agent to AgentCore Runtime
agentcli deploy --env production
```

Your domain repo writes:
- **YAML blueprints** (agent, strategy, workflow definitions)
- **Prompt builders** (5-line Python functions)
- **Domain tools** (your own Lambda functions or MCP servers)

The platform handles everything else.

[Get Started]({{ '/docs/getting-started/quickstart' | relative_url }}){: .btn .btn-primary }

---

## Platform vs. Domain

| Concern | Platform (this repo) | Your Domain Repo |
|---------|---------------------|------------------|
| Blueprint parsing & validation | BlueprintLoader, schema validation | Blueprint YAML files |
| Agent runtime wiring | `@app.entrypoint`, `AgentCoreApp` | `app.py` (5-line handler) |
| Gateway target routing | TargetRegistry, GatewayClient | `gateway-targets.yaml` |
| Memory strategies & hooks | MemoryHookProvider generation | Memory config in YAML |
| Identity provider wiring | Decorator injection, credential resolution | Identity config in YAML |
| Cedar policy generation | CedarPolicyBuilder | Policy rules in YAML |
| Observability auto-instrumentation | Dockerfile generation, OTEL setup | `trace_attributes` in YAML |
| Infrastructure deployment | Terraform modules | `module "platform" { ... }` |
| Prompt versioning | PromptRegistry (S3 + DynamoDB) | Prompt content files |
| Domain-specific tools | — | Lambda functions, custom MCPs |

---

## FAQ

<details>
<summary>What is the relationship to Amazon Bedrock AgentCore?</summary>
<p>This platform is an <strong>abstraction layer</strong> over AgentCore, not a replacement. It uses AgentCore Runtime, Gateway, Memory, Identity, and all other AgentCore services. The platform's value is turning 12 separate service configurations into one YAML blueprint per agent.</p>
</details>

<details>
<summary>Do I need to understand all 12 building blocks?</summary>
<p>No. Start with <strong>Runtime + Gateway</strong> — that gets an agent running with tools. Add Memory, Identity, Policy, and Observability incrementally as your requirements grow. The blueprint schema makes every block optional.</p>
</details>

<details>
<summary>What agent frameworks are supported?</summary>
<p><strong>Strands Agents SDK</strong> is the primary framework with the deepest AgentCore integration (native BedrockModel, HookProvider, MCPClient, A2A). Any framework that exposes <code>POST /invocations</code> + <code>GET /ping</code> on port 8080 can run on AgentCore Runtime.</p>
</details>

<details>
<summary>How do domain repos consume this platform?</summary>
<p>Two ways: <strong>Terraform modules</strong> for infrastructure (<code>module "platform" { source = "..." }</code>) and <strong>pip packages</strong> for the SDK (<code>pip install agent-core</code>). Deploy the platform infrastructure first, then deploy your domain agents on top.</p>
</details>

<details>
<summary>Why Terraform instead of CDK?</summary>
<p>Portability, composability, and wider adoption. Domain consumers use standard <code>terraform init && terraform apply</code>. No CDK knowledge, no Node.js dependency, no synth step.</p>
</details>

<details>
<summary>Why not Lambda for agents?</summary>
<p>Agents are <strong>stateful, long-running, and session-oriented</strong>. Lambda is for short, fast, stateless operations. AgentCore Runtime hosts agents in isolated microVMs with warm pools, session routing, and streaming. Lambda is used for <strong>tools</strong> behind the Gateway.</p>
</details>

<details>
<summary>What does the developer actually write?</summary>
<p>Three things: <strong>YAML blueprints</strong> (agent/strategy/workflow declarations), <strong>prompt builders</strong> (5-line Python functions), and <strong>domain tools</strong> (Lambda functions or MCP servers for your business logic). The platform handles all infrastructure, wiring, and deployment.</p>
</details>
