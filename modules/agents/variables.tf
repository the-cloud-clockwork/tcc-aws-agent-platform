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
