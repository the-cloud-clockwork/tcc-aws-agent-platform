# ──────────────────────────────────────────────────────────────────────────────
# Data Sources Sub-Module -- Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "vpc_id" {
  description = "ID of the pre-existing VPC. All other networking properties are derived from this."
  type        = string
}
