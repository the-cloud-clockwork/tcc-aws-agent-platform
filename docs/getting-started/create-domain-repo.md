---
title: Create a Domain Repo
nav_order: 0
parent: Getting Started
---

# Create a Domain Repo

One command. Full project. Ready for `terraform init`.

---

## Run the Scaffolder

Open any terminal and paste:

```bash
bash <(curl -sL https://raw.githubusercontent.com/The-Cloud-Clockwork/tccw-aws-agent-platform/main/scripts/create-domain.sh)
```

It asks two questions:

```
Domain name (e.g., logistics, finops, healthcare): my-project
Org prefix (e.g., myco, acme): acme
```

That's it. You get a full repo at `acme-my-project/`.

---

## What You Get

```
acme-my-project/
├── agents/                        ← Your AI agents (shared Docker image)
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/my_project_agents/
│   │   ├── app.py                 ← 6-line entrypoint (identical for all domains)
│   │   └── agent_configs.py       ← Register your prompt builders here
│   ├── blueprints/
│   │   ├── agents/
│   │   │   └── example-agent.yaml ← Your first agent — edit this
│   │   ├── strategies/
│   │   └── workflows/
│   └── prompts/
│       └── my_project/
│           └── example-agent.txt  ← Your first system prompt — edit this
│
├── mcps/                          ← Your MCP tool servers (one Dockerfile each)
│   ├── blueprints/
│   └── example-service/
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/.../server.py      ← Example MCP with a hello() tool
│
├── lambdas/                       ← Lambda functions for workflow steps
│   └── stubs/handler.py
│
├── infra/                         ← Terraform (consumes platform modules)
│   ├── main.tf                    ← 3 modules: platform → agents → workflows
│   ├── variables.tf               ← All variables with sensible defaults
│   ├── providers.tf               ← AWS + Bedrock provider aliases
│   ├── backend.tf                 ← S3 backend (edit the bucket name)
│   └── envs/
│       ├── dev.tfvars             ← Development config
│       ├── staging.tfvars         ← Staging config
│       └── production.tfvars      ← Production config
│
├── .gitignore
├── pyproject.toml
└── ruff.toml
```

**30 files**, all wired together, git initialized with a first commit.

---

## Next: Deploy

### 1. Edit the state bucket

Open `infra/backend.tf` and replace the placeholder bucket name with your actual S3 bucket:

```hcl
terraform {
  backend "s3" {
    bucket = "acme-my-project-infra"   # ← your bucket here
    key    = "terraform.tfstate"
    region = "eu-west-1"
  }
}
```

### 2. Initialize Terraform

```bash
cd acme-my-project/infra
terraform init
```

This downloads the platform modules from GitHub.

### 3. Plan

```bash
terraform plan -var-file=envs/dev.tfvars
```

Review the resources that will be created: VPC, KMS keys, DynamoDB tables, Gateway, Memory, ECR repo, CodeBuild project, Runtime, and more.

### 4. Apply

```bash
terraform apply -var-file=envs/dev.tfvars
```

### 5. Build your agent image

```bash
terraform apply -var-file=envs/dev.tfvars -var="build_enabled=true"
```

This builds the Docker image via CodeBuild and pushes to ECR.

---

## Customize Your Agent

### Edit the blueprint

Open `agents/blueprints/agents/example-agent.yaml`:

```yaml
id: example-agent                          # ← rename this
name: Example Agent                        # ← rename this
version: "1.0.0"
prompt_ref: "my_project/example-agent"     # ← matches prompts/ path

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.7
  max_tokens: 4096

runtime:
  type: agentcore
  network_mode: VPC
  idle_timeout_minutes: 15

tools: []                                  # ← add MCP tools here

memory:
  strategies: []                           # ← add memory strategies here
  event_expiry_days: 30
```

### Edit the system prompt

Open `agents/prompts/my_project/example-agent.txt` and write your agent's personality and instructions.

### Add tools

Add MCP tool references to your blueprint:

```yaml
tools:
  - mcp: my-data-service-mcp
    tools: [query_data, get_report]
  - builtin: code_interpreter
```

### Add memory

```yaml
memory:
  strategies:
    - type: SEMANTIC
      name: FactExtractor
      namespace: "{actorId}/facts/"
  event_expiry_days: 30
  short_term_k: 5
```

---

## Add More Agents

1. Create a new YAML file in `agents/blueprints/agents/`
2. Create a matching prompt in `agents/prompts/my_project/`
3. Run `terraform apply` — the platform creates all resources automatically

Each YAML file = one agent runtime. No code changes needed.

---

## Add an MCP Server

1. Create a blueprint in `mcps/blueprints/my-service-mcp.yaml`
2. Create a directory `mcps/my-service/` with a `Dockerfile` and `src/`
3. Add the MCP module to `infra/main.tf`:

```hcl
module "mcps" {
  source     = "git::https://github.com/The-Cloud-Clockwork/tccw-aws-agent-platform.git//modules/agents?ref=main"
  depends_on = [module.platform]

  resource_prefix = "${var.resource_prefix}-mcp"
  blueprint_dir   = "${path.module}/../mcps/blueprints"
  source_dir      = "${path.root}/../mcps"
  source_layout   = "polyrepo"
  polyrepo_suffix = "-mcp"
  # ... wire platform outputs (same as the agents module)
}
```

{: .important }
> The blueprint ID minus the suffix must match the subdirectory name.
> Blueprint `my-service-mcp` with suffix `-mcp` → looks for `mcps/my-service/Dockerfile`.

---

## CLI Options

Skip the interactive prompts with flags:

```bash
bash <(curl -sL https://raw.githubusercontent.com/The-Cloud-Clockwork/tccw-aws-agent-platform/main/scripts/create-domain.sh) \
  --name my-project \
  --prefix acme \
  --region us-east-1 \
  --bedrock-region us-west-2
```

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | *(asks)* | Domain name |
| `--prefix` | *(asks)* | Org prefix |
| `--region` | `eu-west-1` | Primary AWS region |
| `--bedrock-region` | `us-west-2` | Bedrock model region |
| `--platform-ref` | `main` | Git ref for platform modules |

---

## Next Steps

- [Quickstart]({{ '/docs/getting-started/quickstart' | relative_url }}) — install the SDK and CLI
- [First Agent]({{ '/docs/getting-started/first-agent' | relative_url }}) — detailed tutorial with memory, tools, and policy
- [Agent Blueprint Spec]({{ '/docs/blueprints/agent-blueprint' | relative_url }}) — every YAML field documented
- [Infrastructure]({{ '/docs/infrastructure' | relative_url }}) — Terraform module reference
