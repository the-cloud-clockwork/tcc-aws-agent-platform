variable "bucket_name" {
  description = "S3 bucket name."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for server-side encryption."
  type        = string
}

variable "ssm_path" {
  description = "SSM parameter path to store the bucket name. Empty to skip."
  type        = string
  default     = ""
}

variable "force_destroy" {
  description = "Allow Terraform to destroy the bucket even if it contains objects."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
