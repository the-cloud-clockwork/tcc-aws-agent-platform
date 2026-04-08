# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Build
#
# Per-blueprint Docker image builds via CodeBuild. Triggered by terraform apply
# when build_enabled=true. Runs in parallel (Terraform parallelism, default 10).
#
# Usage from domain:
#   terraform apply -var="build_enabled=true"                    # all services
#   terraform apply -var="build_enabled=true" \
#     -var='build_services={"watchlist-screener":true}'           # one service
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Determine which blueprints to build
  build_targets = {
    for id, bp in local.blueprints : id => bp
    if var.build_enabled && (length(var.build_services) == 0 || lookup(var.build_services, id, false))
  }

  # S3 key prefix for build source zips
  build_s3_prefix = "${local.name_prefix}-source"

  # For monorepo: single shared zip key. For polyrepo: per-service keys.
  build_s3_key = {
    for id, _ in local.build_targets : id => (
      var.source_layout == "monorepo"
      ? "${local.build_s3_prefix}/shared-source.zip"
      : "${local.build_s3_prefix}/${id}-source.zip"
    )
  }
}

resource "terraform_data" "build" {
  for_each = local.build_targets

  # Rebuild when source changes or we force it
  triggers_replace = {
    blueprint = each.key
    timestamp = timestamp()
  }

  provisioner "local-exec" {
    command     = "bash ${path.module}/scripts/build-runtime.sh"
    working_dir = var.source_dir != "" ? var.source_dir : path.root

    environment = {
      RUNTIME_NAME       = each.key
      SOURCE_DIR         = var.source_dir
      SOURCE_LAYOUT      = var.source_layout
      POLYREPO_SUFFIX    = var.polyrepo_suffix
      S3_BUCKET          = var.codebuild_source_bucket
      S3_KEY             = local.build_s3_key[each.key]
      CODEBUILD_PROJECT  = "${local.name_prefix}-build-${each.key}"
      EXTRA_DEPS         = lookup(var.extra_build_deps, each.key, "")
      REPO_ROOT          = var.source_dir != "" ? abspath("${var.source_dir}/..") : path.root
      AWS_DEFAULT_REGION = var.aws_region
    }
  }

  depends_on = [
    aws_ecr_repository.agent,
    aws_codebuild_project.agent,
  ]
}
