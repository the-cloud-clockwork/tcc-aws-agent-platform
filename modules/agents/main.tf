# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — Main
#
# This module reads agent blueprint YAML files and creates per-agent
# AgentCore resources: IAM roles, ECR repos, CodeBuild projects,
# AgentCore Runtimes, Gateway targets, memory strategies, identity
# providers, and SSM parameter outputs.
#
# Resource definitions are split across named files:
#   locals.tf             — Blueprint parsing and derived locals
#   iam.tf                — Per-agent IAM roles and policies
#   ecr.tf                — Per-agent ECR repositories
#   codebuild.tf          — Per-agent ARM64 CodeBuild projects
#   runtime.tf            — Per-agent AgentCore Runtime resources
#   gateway_targets.tf    — Gateway target registration
#   memory_strategies.tf  — Memory strategy resources
#   identity_providers.tf — Credential provider resources
#   ssm.tf                — Per-agent SSM parameter outputs
#   outputs.tf            — Module outputs
# ──────────────────────────────────────────────────────────────────────────────
