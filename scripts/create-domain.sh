#!/usr/bin/env bash
set -euo pipefail

# create-domain.sh — Scaffold a new domain repo for AWS Agent Platform
#
# Usage:
#   bash <(curl -sL https://raw.githubusercontent.com/The-Cloud-Clockwork/tcc-aws-agent-platform/main/scripts/create-domain.sh)
#   ./scripts/create-domain.sh --name my-project --prefix myco
#   ./scripts/create-domain.sh --name my-project --prefix myco --region us-east-1

BOLD='\033[1m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${BLUE}[scaffold]${NC} $*"; }
ok()   { echo -e "${GREEN}[  ok  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ warn ]${NC} $*"; }

# ── Defaults ──────────────────────────────────────────────────────────────────

DOMAIN=""
PREFIX=""
REGION="eu-west-1"
BEDROCK_REGION="us-west-2"
PLATFORM_SOURCE="git::https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform.git"
PLATFORM_REF="main"

# ── Argument parsing ─────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case $1 in
    --name)             DOMAIN="$2"; shift 2 ;;
    --prefix)           PREFIX="$2"; shift 2 ;;
    --region)           REGION="$2"; shift 2 ;;
    --bedrock-region)   BEDROCK_REGION="$2"; shift 2 ;;
    --platform-source)  PLATFORM_SOURCE="$2"; shift 2 ;;
    --platform-ref)     PLATFORM_REF="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--name DOMAIN] [--prefix PREFIX] [--region REGION] [--bedrock-region REGION]"
      echo ""
      echo "Scaffolds a new domain repo with the correct folder structure for"
      echo "consuming the AWS Agent Platform modules."
      echo ""
      echo "Options:"
      echo "  --name            Domain name (e.g., logistics, finops)"
      echo "  --prefix          Org prefix (e.g., myco, acme)"
      echo "  --region          AWS region (default: eu-west-1)"
      echo "  --bedrock-region  Bedrock region (default: us-west-2)"
      echo "  --platform-source Git URL for platform modules"
      echo "  --platform-ref    Git ref for platform modules (default: main)"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Interactive prompts ──────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}AWS Agent Platform — Domain Repo Scaffolder${NC}"
echo -e "Creates a new domain repo with the correct folder structure."
echo ""

if [[ -z "$DOMAIN" ]]; then
  read -rp "Domain name (e.g., logistics, finops, healthcare): " DOMAIN
fi

if [[ -z "$PREFIX" ]]; then
  read -rp "Org prefix (e.g., myco, acme): " PREFIX
fi

# Validate
if [[ -z "$DOMAIN" || -z "$PREFIX" ]]; then
  echo "ERROR: Both domain name and prefix are required."
  exit 1
fi

# Lowercase, replace spaces/dashes
DOMAIN=$(echo "$DOMAIN" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
PREFIX=$(echo "$PREFIX" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')

# Python module name: replace dashes with underscores
DOMAIN_SNAKE=$(echo "$DOMAIN" | tr '-' '_')
PREFIX_SNAKE=$(echo "$PREFIX" | tr '-' '_')

REPO_DIR="${PREFIX}-${DOMAIN}"

if [[ -d "$REPO_DIR" ]]; then
  echo "ERROR: Directory '$REPO_DIR' already exists."
  exit 1
fi

PLATFORM_MODULE_URL="${PLATFORM_SOURCE}//modules"

echo ""
echo -e "${BOLD}Configuration:${NC}"
echo "  Repo directory:   $REPO_DIR"
echo "  Domain:           $DOMAIN"
echo "  Prefix:           $PREFIX"
echo "  Python package:   ${DOMAIN_SNAKE}_agents"
echo "  AWS region:       $REGION"
echo "  Bedrock region:   $BEDROCK_REGION"
echo "  Platform source:  $PLATFORM_MODULE_URL"
echo ""
read -rp "Proceed? [Y/n] " confirm
if [[ "${confirm:-Y}" =~ ^[Nn] ]]; then
  echo "Aborted."
  exit 0
fi

# ── Create directory structure ───────────────────────────────────────────────

log "Creating directory structure..."

mkdir -p "$REPO_DIR"/{agents/{src/${DOMAIN_SNAKE}_agents,blueprints/{agents,strategies,workflows},prompts/${DOMAIN_SNAKE}},mcps/{blueprints,example-service/src/${DOMAIN_SNAKE}_mcp_example},lambdas/stubs,infra/envs,scripts}

# ── agents/Dockerfile ────────────────────────────────────────────────────────

cat > "$REPO_DIR/agents/Dockerfile" << 'DOCKERFILE'
FROM public.ecr.aws/docker/library/python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
COPY blueprints/ blueprints/
COPY prompts/ prompts/

ARG PIP_EXTRA_INDEX_URL=""
ENV PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}
RUN pip install --no-cache-dir ".[agentcore]"

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

EXPOSE 8080

DOCKERFILE
# Append CMD with variable substitution
echo "CMD [\"opentelemetry-instrument\", \"python\", \"-m\", \"${DOMAIN_SNAKE}_agents.app\"]" >> "$REPO_DIR/agents/Dockerfile"

# ── agents/pyproject.toml ────────────────────────────────────────────────────

cat > "$REPO_DIR/agents/pyproject.toml" << EOF
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "${DOMAIN}-agents"
version = "0.1.0"
description = "${DOMAIN} agents"
requires-python = ">=3.12"
dependencies = [
    "agent-core>=0.9.0",
    "strands-agents>=1.0",
    "strands-agents-tools>=0.1.0",
    "boto3>=1.35",
    "pydantic>=2.6,<3",
    "pyyaml>=6.0",
    "aws-opentelemetry-distro>=0.7.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
agentcore = [
    "bedrock-agentcore>=1.0.0",
    "bedrock-agentcore-starter-toolkit>=0.3.0",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0.0",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/${DOMAIN_SNAKE}_agents"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
EOF

# ── agents/src/__init__.py ───────────────────────────────────────────────────

cat > "$REPO_DIR/agents/src/${DOMAIN_SNAKE}_agents/__init__.py" << 'EOF'
EOF

# ── agents/src/app.py ────────────────────────────────────────────────────────

cat > "$REPO_DIR/agents/src/${DOMAIN_SNAKE}_agents/app.py" << 'EOF'
"""Agent entrypoint — identical across all domain repos."""

from agent_core.blueprints.loader import BlueprintLoader

loader = BlueprintLoader("blueprints", prompt_dir="prompts")
app = loader.build_entrypoint("example-agent")

if __name__ == "__main__":
    app.run()
EOF

# ── agents/src/agent_configs.py ──────────────────────────────────────────────

cat > "$REPO_DIR/agents/src/${DOMAIN_SNAKE}_agents/agent_configs.py" << 'EOF'
"""Agent configuration registry — register prompt builders and config here."""

from agent_core.runtime.config_registry import AgentConfig, AgentConfigRegistry

REGISTRY = AgentConfigRegistry()

# Register your agents here:
# REGISTRY.register(AgentConfig(
#     agent_id="my-agent",
#     operation_name="process",
#     required_fields=["input"],
#     build_prompt=lambda params, key: f"Process: {params['input']}",
# ))
EOF

# ── agents/blueprints/agents/example-agent.yaml ─────────────────────────────

cat > "$REPO_DIR/agents/blueprints/agents/example-agent.yaml" << EOF
id: example-agent
name: Example Agent
version: "1.0.0"
prompt_ref: "${DOMAIN_SNAKE}/example-agent"

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  temperature: 0.7
  max_tokens: 4096

runtime:
  type: agentcore
  network_mode: VPC
  idle_timeout_minutes: 15

tools: []

memory:
  strategies: []
  event_expiry_days: 30
EOF

# ── agents/blueprints/.gitkeep files ─────────────────────────────────────────

touch "$REPO_DIR/agents/blueprints/strategies/.gitkeep"
touch "$REPO_DIR/agents/blueprints/workflows/.gitkeep"

# ── agents/prompts ───────────────────────────────────────────────────────────

cat > "$REPO_DIR/agents/prompts/${DOMAIN_SNAKE}/example-agent.txt" << 'EOF'
You are a helpful assistant. Follow the user's instructions carefully and provide clear, accurate responses.
EOF

# ── mcps/blueprints/.gitkeep ─────────────────────────────────────────────────

touch "$REPO_DIR/mcps/blueprints/.gitkeep"

# ── mcps/example-service/Dockerfile ──────────────────────────────────────────

cat > "$REPO_DIR/mcps/example-service/Dockerfile" << EOF
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

ARG PIP_EXTRA_INDEX_URL=""
ENV PIP_EXTRA_INDEX_URL=\${PIP_EXTRA_INDEX_URL}
RUN pip install --no-cache-dir .

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

EXPOSE 8000

ENTRYPOINT ["opentelemetry-instrument", "example-service-mcp"]
EOF

# ── mcps/example-service/pyproject.toml ──────────────────────────────────────

cat > "$REPO_DIR/mcps/example-service/pyproject.toml" << EOF
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "${DOMAIN}-mcp-example-service"
version = "0.1.0"
description = "Example MCP server"
requires-python = ">=3.12"
dependencies = [
    "agent-core>=0.9.0",
    "aws-opentelemetry-distro>=0.7.0",
    "mcp[server]>=1.0.0",
    "pydantic>=2.6,<3",
    "boto3>=1.34",
    "uvicorn>=0.27",
    "starlette>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.8",
]

[project.scripts]
example-service-mcp = "${DOMAIN_SNAKE}_mcp_example.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/${DOMAIN_SNAKE}_mcp_example"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
EOF

# ── mcps/example-service/src ─────────────────────────────────────────────────

cat > "$REPO_DIR/mcps/example-service/src/${DOMAIN_SNAKE}_mcp_example/__init__.py" << 'EOF'
EOF

cat > "$REPO_DIR/mcps/example-service/src/${DOMAIN_SNAKE}_mcp_example/server.py" << 'EOF'
"""Example MCP server — replace with your domain logic."""

from agent_core.mcp.base_server import BaseMCPServer


def create_server() -> BaseMCPServer:
    server = BaseMCPServer("example-service-mcp")

    @server.tool()
    async def hello(name: str) -> str:
        """Say hello."""
        return f"Hello, {name}!"

    return server


def main() -> None:
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
EOF

# ── lambdas/stubs/handler.py ─────────────────────────────────────────────────

cat > "$REPO_DIR/lambdas/stubs/handler.py" << 'EOF'
"""Generic stub handler for workflow Lambda steps."""

import json


def handler(event, context):
    """Passthrough handler — logs the event and returns it."""
    print(json.dumps({"stub": True, "event": event}))
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "ok", "stub": True}),
    }
EOF

# ── infra/versions.tf ────────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/versions.tf" << 'EOF'
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.21"
    }
  }
}
EOF

# ── infra/providers.tf ───────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/providers.tf" << EOF
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "${DOMAIN}"
      ManagedBy   = "terraform"
    }
  }
}

provider "aws" {
  alias  = "bedrock"
  region = var.bedrock_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "${DOMAIN}"
      ManagedBy   = "terraform"
    }
  }
}
EOF

# ── infra/backend.tf ─────────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/backend.tf" << EOF
terraform {
  backend "s3" {
    bucket       = "${PREFIX}-${DOMAIN}-infra"   # TODO: create this S3 bucket first
    key          = "terraform.tfstate"
    region       = "${REGION}"
    encrypt      = true
    use_lockfile = true
  }
}
EOF

# ── infra/variables.tf ───────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/variables.tf" << EOF
# --- Required ---

variable "environment" {
  type        = string
  description = "Deployment environment: dev, staging, production"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be dev, staging, or production"
  }
}

variable "resource_prefix" {
  type        = string
  description = "Prefix for all resource names"
  default     = "${DOMAIN}"
}

variable "aws_region" {
  type        = string
  description = "Primary AWS region"
  default     = "${REGION}"
}

variable "bedrock_region" {
  type        = string
  description = "Region for Bedrock model access"
  default     = "${BEDROCK_REGION}"
}

variable "ssm_root_path" {
  type        = string
  description = "Root SSM parameter path"
  default     = "/${DOMAIN}"
}

# --- Platform passthrough ---

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
  default     = "10.0.0.0/16"
}

variable "nat_gateway_count" {
  type        = number
  description = "Number of NAT gateways (1 for dev, 3 for prod)"
  default     = 1
}

variable "removal_policy_destroy" {
  type        = bool
  description = "Destroy resources on removal (dev=true, prod=false)"
  default     = true
}

variable "gateway_auth_type" {
  type        = string
  description = "Gateway auth type: AWS_IAM, CUSTOM_JWT, NONE"
  default     = "AWS_IAM"
}

variable "memory_event_expiry_days" {
  type        = number
  description = "Memory event expiry in days"
  default     = 30
}

variable "dynamodb_billing_mode" {
  type        = string
  description = "DynamoDB billing mode"
  default     = "PAY_PER_REQUEST"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention in days"
  default     = 14
}

variable "cognito_enabled" {
  type        = bool
  description = "Enable Cognito user pool"
  default     = false
}

variable "waf_enabled" {
  type        = bool
  description = "Enable WAF"
  default     = false
}

# --- CodeArtifact ---

variable "codeartifact_domain" {
  type        = string
  description = "CodeArtifact domain for agent-core resolution"
  default     = ""
}

variable "codeartifact_repo" {
  type        = string
  description = "CodeArtifact repository for Python packages"
  default     = ""
}

# --- Build ---

variable "build_enabled" {
  type        = bool
  description = "Build Docker images on terraform apply"
  default     = false
}

variable "build_services" {
  type        = map(bool)
  description = "Per-service build override. Key = blueprint ID. Empty = build all."
  default     = {}
}
EOF

# ── infra/locals.tf ──────────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/locals.tf" << EOF
locals {
  tags = {
    Domain = "${DOMAIN}"
  }
}
EOF

# ── infra/main.tf ────────────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/main.tf" << EOF
# --- Platform Foundation ---

module "platform" {
  source = "${PLATFORM_MODULE_URL}/platform?ref=${PLATFORM_REF}"

  environment              = var.environment
  resource_prefix          = var.resource_prefix
  aws_region               = var.aws_region
  bedrock_region           = var.bedrock_region
  ssm_root_path            = "\${var.ssm_root_path}/\${var.environment}"
  vpc_cidr                 = var.vpc_cidr
  nat_gateway_count        = var.nat_gateway_count
  removal_policy_destroy   = var.removal_policy_destroy
  gateway_auth_type        = var.gateway_auth_type
  memory_event_expiry_days = var.memory_event_expiry_days
  dynamodb_billing_mode    = var.dynamodb_billing_mode
  log_retention_days       = var.log_retention_days
  cognito_enabled          = var.cognito_enabled
  waf_enabled              = var.waf_enabled
  tags                     = local.tags
}

# --- Agent Runtimes (monorepo layout) ---

module "agents" {
  source     = "${PLATFORM_MODULE_URL}/agents?ref=${PLATFORM_REF}"
  depends_on = [module.platform]

  environment             = var.environment
  resource_prefix         = var.resource_prefix
  aws_region              = var.aws_region
  bedrock_region          = var.bedrock_region
  ssm_root_path           = "\${var.ssm_root_path}/\${var.environment}"
  blueprint_dir           = "\${path.module}/../agents/blueprints/agents"
  gateway_id              = module.platform.gateway_id
  gateway_url             = module.platform.gateway_url
  gateway_role_arn        = module.platform.gateway_role_arn
  memory_id               = module.platform.memory_id
  vpc_id                  = module.platform.vpc_id
  private_subnet_ids      = module.platform.private_subnet_ids
  agent_security_group_id = module.platform.agent_security_group_id
  storage_kms_key_arn     = module.platform.storage_kms_key_arn
  artifacts_bucket_name              = module.platform.artifacts_bucket_name
  artifacts_bucket_arn               = module.platform.artifacts_bucket_arn
  platform_artifacts_kms_key_arn     = module.platform.platform_artifacts_kms_key_arn
  domain_artifacts_kms_key_arn       = module.platform.domain_artifacts_kms_key_arn
  codeartifact_domain     = var.codeartifact_domain
  codeartifact_repo       = var.codeartifact_repo
  codebuild_source_bucket = module.platform.codebuild_source_bucket
  prompt_registry_url           = module.platform.prompt_registry_url
  idempotency_table_name        = module.platform.table_names["idempotency"]
  prompt_registry_function_arn  = module.platform.prompt_registry_function_arn
  prompt_registry_function_name = module.platform.prompt_registry_function_name
  observability_enabled   = true
  source_dir              = "\${path.root}/../agents"
  source_layout           = "monorepo"
  build_enabled           = var.build_enabled
  build_services          = var.build_services
  tags                    = local.tags
}

# --- Workflows (Step Functions from YAML) ---

module "workflows" {
  source     = "${PLATFORM_MODULE_URL}/workflows?ref=${PLATFORM_REF}"
  depends_on = [module.agents]

  environment        = var.environment
  resource_prefix    = var.resource_prefix
  aws_region         = var.aws_region
  ssm_root_path      = "\${var.ssm_root_path}/\${var.environment}"
  workflow_dir       = "\${path.module}/../agents/blueprints/workflows"
  agent_runtime_arns = module.agents.runtime_arns
  lambda_arns        = {}
  log_retention_days = var.log_retention_days
  tags               = local.tags
}
EOF

# ── infra/outputs.tf ─────────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/outputs.tf" << 'EOF'
output "gateway_url" {
  value = module.platform.gateway_url
}

output "runtime_arns" {
  value = module.agents.runtime_arns
}

output "runtime_endpoints" {
  value = module.agents.runtime_endpoints
}
EOF

# ── infra/envs/*.tfvars ──────────────────────────────────────────────────────

cat > "$REPO_DIR/infra/envs/dev.tfvars" << EOF
environment            = "dev"
resource_prefix        = "${DOMAIN}"
aws_region             = "${REGION}"
bedrock_region         = "${BEDROCK_REGION}"
ssm_root_path          = "/${DOMAIN}"
vpc_cidr               = "10.0.0.0/16"
nat_gateway_count      = 1
removal_policy_destroy = true
dynamodb_billing_mode  = "PAY_PER_REQUEST"
log_retention_days     = 14
cognito_enabled        = false
waf_enabled            = false
EOF

cat > "$REPO_DIR/infra/envs/staging.tfvars" << EOF
environment            = "staging"
resource_prefix        = "${DOMAIN}"
aws_region             = "${REGION}"
bedrock_region         = "${BEDROCK_REGION}"
ssm_root_path          = "/${DOMAIN}"
vpc_cidr               = "10.1.0.0/16"
nat_gateway_count      = 2
removal_policy_destroy = false
dynamodb_billing_mode  = "PAY_PER_REQUEST"
log_retention_days     = 30
cognito_enabled        = true
waf_enabled            = true
EOF

cat > "$REPO_DIR/infra/envs/production.tfvars" << EOF
environment            = "production"
resource_prefix        = "${DOMAIN}"
aws_region             = "${REGION}"
bedrock_region         = "${BEDROCK_REGION}"
ssm_root_path          = "/${DOMAIN}"
vpc_cidr               = "10.2.0.0/16"
nat_gateway_count      = 3
removal_policy_destroy = false
dynamodb_billing_mode  = "PROVISIONED"
log_retention_days     = 90
cognito_enabled        = true
waf_enabled            = true
EOF

# ── scripts/.gitkeep ─────────────────────────────────────────────────────────

touch "$REPO_DIR/scripts/.gitkeep"

# ── .gitignore ───────────────────────────────────────────────────────────────

cat > "$REPO_DIR/.gitignore" << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
.env
.env.*

# Testing & Linting
.mypy_cache/
.pytest_cache/
.ruff_cache/
coverage.xml
.coverage
htmlcov/

# SonarQube
.scannerwork/

# Terraform
.terraform/
!.terraform.lock.hcl
*.tfstate*
.generated/
plan.out
infra/plan.out

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Build
.build/
.claude/worktrees/
EOF

# ── Root pyproject.toml ──────────────────────────────────────────────────────

cat > "$REPO_DIR/pyproject.toml" << EOF
[project]
name = "${PREFIX}-${DOMAIN}"
version = "0.1.0"
description = "${DOMAIN} domain — AI agent platform"
requires-python = ">=3.12"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.8",
]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B", "SIM"]
EOF

# ── Root ruff.toml ───────────────────────────────────────────────────────────

cat > "$REPO_DIR/ruff.toml" << 'EOF'
target-version = "py312"
line-length = 120

[lint]
select = ["E", "F", "I", "W", "UP", "B", "SIM"]
EOF

# ── README.md ────────────────────────────────────────────────────────────────

cat > "$REPO_DIR/README.md" << EOF
# ${PREFIX}-${DOMAIN}

Domain-specific AI agent platform built on [AWS Agent Platform](https://github.com/The-Cloud-Clockwork/tcc-aws-agent-platform).

## Quick Start

\`\`\`bash
# Install agent SDK
pip install agent-core  # from CodeArtifact

# Deploy infrastructure
cd infra
terraform init
terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars

# Build agent images
terraform apply -var-file=envs/dev.tfvars -var="build_enabled=true"
\`\`\`

## Structure

| Directory | Purpose |
|-----------|---------|
| \`agents/\` | Agent runtimes (monorepo — shared Dockerfile) |
| \`mcps/\` | MCP servers (polyrepo — per-service Dockerfiles) |
| \`lambdas/\` | Lambda functions for workflow steps |
| \`infra/\` | Terraform — consumes platform modules |

## Adding an Agent

1. Create a blueprint: \`agents/blueprints/agents/my-agent.yaml\`
2. Create a prompt: \`agents/prompts/${DOMAIN_SNAKE}/my-agent.txt\`
3. Wire it in \`agents/src/${DOMAIN_SNAKE}_agents/app.py\`
4. Deploy: \`terraform apply -var-file=envs/dev.tfvars -var="build_enabled=true"\`
EOF

# ── Git init + commit ────────────────────────────────────────────────────────

log "Initializing git repository..."
(
  cd "$REPO_DIR"
  git init -q
  git add -A
  git commit -q -m "feat: scaffold ${PREFIX}-${DOMAIN} domain repo

Generated by create-domain.sh from aws-agent-platform.
Includes: agents (monorepo), MCPs (polyrepo), lambdas, infra modules."
)

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}Domain repo created: ${REPO_DIR}/${NC}"
echo ""

FILE_COUNT=$(find "$REPO_DIR" -type f -not -path '*/.git/*' | wc -l)
echo -e "  ${CYAN}Files created:${NC} $FILE_COUNT"
echo ""

echo -e "${BOLD}Directory structure:${NC}"
echo ""
find "$REPO_DIR" -type f -not -path '*/.git/*' | sort | sed "s|^$REPO_DIR/|  |"

echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo "  1. Edit infra/backend.tf with your S3 state bucket"
echo "  2. cd ${REPO_DIR}/infra && terraform init && terraform plan -var-file=envs/dev.tfvars"
echo "  3. Edit agents/blueprints/agents/example-agent.yaml with your first agent"
echo "  4. Edit agents/prompts/${DOMAIN_SNAKE}/example-agent.txt with your system prompt"
echo "  5. Deploy: terraform apply -var-file=envs/dev.tfvars"
echo ""

# ── Open IDE ─────────────────────────────────────────────────────────────────

if command -v cursor &>/dev/null; then
  echo -ne "  Open in Cursor? [Y/n] "
  read -r open_ide
  if [[ "${open_ide:-Y}" =~ ^[Yy]|^$ ]]; then
    cursor "$REPO_DIR"
  fi
elif command -v code &>/dev/null; then
  echo -ne "  Open in VS Code? [Y/n] "
  read -r open_ide
  if [[ "${open_ide:-Y}" =~ ^[Yy]|^$ ]]; then
    code "$REPO_DIR"
  fi
fi

ok "Done."
