## -----------------------------------------------------
## Agents Module -- Variables
## Reads blueprint YAML and deploys per-agent resources.
## -----------------------------------------------------

variable "environment" {
  type = string
}

variable "resource_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "bedrock_region" {
  type    = string
  default = ""
}

variable "ssm_root_path" {
  type = string
}

variable "blueprint_dir" {
  type        = string
  description = "Path to directory containing agent blueprint YAML files"
}

variable "gateway_targets_file" {
  type        = string
  description = "Path to gateway-targets.yaml declaring Lambda tool targets"
  default     = ""
}

# -- Platform outputs (wired from platform module) -------------------

variable "gateway_id" {
  type        = string
  description = "AgentCore Gateway ID from platform module"
}

variable "gateway_url" {
  type        = string
  description = "AgentCore Gateway URL for agent tool access"
}

variable "gateway_role_arn" {
  type        = string
  description = "IAM role ARN used by Gateway to invoke targets"
}

variable "memory_id" {
  type        = string
  description = "AgentCore Memory ID from platform module"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "agent_security_group_id" {
  type = string
}

variable "artifacts_bucket_name" {
  type    = string
  default = ""
}

variable "artifacts_table_name" {
  type        = string
  description = "DynamoDB artifacts catalog table name for mandatory registration"
  default     = ""
}

variable "artifacts_bucket_arn" {
  type    = string
  default = ""
}

variable "platform_artifacts_kms_key_arn" {
  type    = string
  default = ""
}

variable "domain_artifacts_kms_key_arn" {
  type    = string
  default = ""
}

variable "storage_kms_key_arn" {
  type        = string
  description = "ARN of the storage KMS key for ECR encryption."
  default     = ""
}

# -- OAuth2 MCP Gateway -----------------------------------------------

variable "mcp_oauth2_provider_arn" {
  type        = string
  description = "ARN of OAuth2 credential provider for MCP server gateway targets. Empty = gateway_iam_role fallback."
  default     = ""
}

variable "mcp_oauth2_scopes" {
  type        = list(string)
  description = "OAuth2 scopes for MCP server gateway targets."
  default     = []
}

variable "mcp_oauth2_discovery_url" {
  type        = string
  description = "OIDC discovery URL for MCP Runtime JWT authorizer (Cognito). Empty = no authorizer."
  default     = ""
}

variable "mcp_oauth2_allowed_clients" {
  type        = list(string)
  description = "Allowed OAuth2 client IDs for MCP Runtime JWT authorizer."
  default     = []
}

# -- Prompt Registry --------------------------------------------------

variable "prompt_registry_url" {
  type        = string
  description = "Lambda Function URL for the Prompt Registry API."
  default     = ""
}

variable "idempotency_table_name" {
  type        = string
  description = "DynamoDB table name for idempotency keys. Injected as IDEMPOTENCY_TABLE env var."
  default     = ""
}

variable "prompt_registry_function_arn" {
  type        = string
  description = "ARN of the Prompt Registry Lambda function. Grants lambda:InvokeFunction to agent roles."
  default     = ""
}

variable "prompt_registry_function_name" {
  type        = string
  description = "Name of the Prompt Registry Lambda function. Injected as PROMPT_REGISTRY_FUNCTION env var for direct boto3 invocation."
  default     = ""
}

# -- Build -----------------------------------------------------------

variable "codebuild_source_bucket" {
  type        = string
  description = "S3 bucket for agent source code uploads (CodeBuild input)"
  default     = ""
}

variable "codeartifact_domain" {
  description = "CodeArtifact domain name for package resolution during builds."
  type        = string
  default     = ""
}

variable "codeartifact_repo" {
  description = "CodeArtifact repository name for Python packages."
  type        = string
  default     = ""
}

# -- Tags ------------------------------------------------------------

variable "tags" {
  type    = map(string)
  default = {}
}

# -- Observability ---------------------------------------------------

variable "log_retention_days" {
  type        = number
  default     = 14
  description = "Retention in days for agent CloudWatch log groups."
}

variable "observability_enabled" {
  type        = bool
  default     = true
  description = "Inject OTEL environment variables into agent containers for CloudWatch GenAI Observability."
}

variable "observability_log_group_prefix" {
  type        = string
  default     = "/aws/bedrock-agentcore/runtimes/"
  description = "CloudWatch log group prefix for agent OTEL logs. Agent ID is appended."
}

variable "observability_metric_namespace" {
  type        = string
  default     = "bedrock-agentcore"
  description = "CloudWatch metric namespace for agent OTEL metrics."
}

# -- Build -----------------------------------------------------------

variable "source_dir" {
  type        = string
  description = "Path to agent/MCP source code root. Monorepo: dir with Dockerfile. Polyrepo: parent dir with per-service subdirs."
  default     = ""
}

variable "source_layout" {
  type        = string
  description = "Source layout: 'monorepo' (single Dockerfile at root) or 'polyrepo' (per-service subdirs)."
  default     = "monorepo"

  validation {
    condition     = contains(["monorepo", "polyrepo"], var.source_layout)
    error_message = "source_layout must be 'monorepo' or 'polyrepo'."
  }
}

variable "polyrepo_suffix" {
  type        = string
  description = "Suffix to strip from blueprint ID to derive subdirectory name (polyrepo only)."
  default     = "-mcp"
}

variable "build_enabled" {
  type        = bool
  description = "Build Docker images on terraform apply. Set false for infra-only changes."
  default     = false
}

variable "build_services" {
  type        = map(bool)
  description = "Per-service build override. Key = blueprint ID, value = true. Empty map = build all when build_enabled=true."
  default     = {}
}

variable "extra_build_deps" {
  type        = map(string)
  description = "Extra dirs for polyrepo builds. Key = blueprint ID, value = 'src_path:zip_path'. Multiple deps comma-separated."
  default     = {}
}

# ── Langfuse observability ──

variable "langfuse_public_key" {
  type        = string
  description = "Langfuse public key for LLM trace tracking."
  default     = ""
}

variable "langfuse_secret_key" {
  type        = string
  description = "Langfuse secret key. Pass from SSM SecureString, never hardcode."
  default     = ""
  sensitive   = true
}

variable "langfuse_host" {
  type        = string
  description = "Langfuse host URL (e.g. https://langfuse.example.com)."
  default     = ""
}

variable "data_kms_key_arn" {
  type        = string
  description = "KMS key ARN for DynamoDB table encryption (needed for artifacts catalog PutItem)"
  default     = ""
}

variable "execution_mode" {
  type        = string
  description = "Passed through as EXECUTION_MODE env var. Domain defines the semantics."
  default     = ""
}
