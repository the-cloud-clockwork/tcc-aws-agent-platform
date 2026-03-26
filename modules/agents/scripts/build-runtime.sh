#!/usr/bin/env bash
set -euo pipefail

# build-runtime.sh — Build a single AgentCore Runtime image
#
# Called by terraform_data local-exec provisioner. All config via env vars.
#
# Required env vars (set by build.tf):
#   RUNTIME_NAME      — blueprint ID (e.g., watchlist-screener, market-data-mcp)
#   SOURCE_DIR        — absolute path to source root
#   SOURCE_LAYOUT     — "monorepo" or "polyrepo"
#   POLYREPO_SUFFIX   — suffix to strip for subdir name (e.g., "-mcp")
#   S3_BUCKET         — CodeBuild source bucket
#   S3_KEY            — S3 key for the zip
#   CODEBUILD_PROJECT — CodeBuild project name
#   EXTRA_DEPS        — extra deps spec (e.g., "simulation:deps/simulation")
#   REPO_ROOT         — domain repo root (for resolving extra deps)

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[build:${RUNTIME_NAME}]${NC} $*"; }
ok()  { echo -e "${GREEN}[  ok:${RUNTIME_NAME}]${NC} $*"; }
err() { echo -e "${RED}[fail:${RUNTIME_NAME}]${NC} $*" >&2; }

TMPZIP="/tmp/build-${RUNTIME_NAME}-$$.zip"
trap 'rm -f "$TMPZIP" "${TMPZIP}.tmp"' EXIT

# ── Zip source ───────────────────────────────────────────────────────────────

zip_source() {
  if [[ "$SOURCE_LAYOUT" == "polyrepo" ]]; then
    local subdir="${RUNTIME_NAME%${POLYREPO_SUFFIX}}"
    local service_dir="$SOURCE_DIR/$subdir"

    if [[ ! -f "$service_dir/Dockerfile" ]]; then
      err "No Dockerfile at $service_dir/Dockerfile"
      exit 1
    fi

    log "Zipping $service_dir/"
    (cd "$service_dir" && zip -r "$TMPZIP" Dockerfile pyproject.toml src/ prompts/ \
      -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null || \
     cd "$service_dir" && zip -r "$TMPZIP" Dockerfile pyproject.toml src/ \
      -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null)

    # Handle extra dependencies
    if [[ -n "${EXTRA_DEPS:-}" ]]; then
      IFS=',' read -ra deps <<< "$EXTRA_DEPS"
      for dep in "${deps[@]}"; do
        local src_path="${dep%%:*}"
        local zip_path="${dep##*:}"
        if [[ -d "$REPO_ROOT/$src_path" ]]; then
          log "Adding dep: $src_path → $zip_path"
          (cd "$REPO_ROOT" && zip -r "$TMPZIP" "$src_path/" \
            -x '*__pycache__*' '*/.git/*' '*.pyc' '*.coverage*' '*pytest_cache*' 2>/dev/null)
          if [[ "$src_path" != "$zip_path" ]]; then
            python3 -c "
import zipfile, os
src, dst = '${src_path}/', '${zip_path}/'
tmp = '${TMPZIP}.tmp'
with zipfile.ZipFile('${TMPZIP}', 'r') as zin, zipfile.ZipFile(tmp, 'w') as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.startswith(src):
            item.filename = dst + item.filename[len(src):]
        zout.writestr(item, data)
os.replace(tmp, '${TMPZIP}')
"
          fi
        else
          err "Extra dep not found: $REPO_ROOT/$src_path"
          exit 1
        fi
      done
    fi
  else
    # Monorepo: zip from source root
    if [[ ! -f "$SOURCE_DIR/Dockerfile" ]]; then
      err "No Dockerfile at $SOURCE_DIR/Dockerfile"
      exit 1
    fi

    log "Zipping $SOURCE_DIR/"
    (cd "$SOURCE_DIR" && zip -r "$TMPZIP" Dockerfile pyproject.toml src/ blueprints/ prompts/ \
      -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null || \
     cd "$SOURCE_DIR" && zip -r "$TMPZIP" Dockerfile pyproject.toml src/ blueprints/ \
      -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null)
  fi
}

# ── Upload to S3 ─────────────────────────────────────────────────────────────

upload_source() {
  log "Uploading to s3://$S3_BUCKET/$S3_KEY"
  aws s3 cp "$TMPZIP" "s3://$S3_BUCKET/$S3_KEY" --quiet
}

# ── Trigger CodeBuild + poll ─────────────────────────────────────────────────

build_and_wait() {
  log "Triggering CodeBuild: $CODEBUILD_PROJECT"

  local build_id
  build_id=$(aws codebuild start-build \
    --project-name "$CODEBUILD_PROJECT" \
    --source-type-override S3 \
    --source-location-override "$S3_BUCKET/$S3_KEY" \
    --query 'build.id' --output text 2>&1)

  if [[ "$build_id" == *"rror"* ]]; then
    err "Failed to start: $build_id"
    exit 1
  fi

  log "Build $build_id — polling..."
  local status="IN_PROGRESS"
  while [[ "$status" == "IN_PROGRESS" ]]; do
    sleep 20
    status=$(aws codebuild batch-get-builds --ids "$build_id" \
      --query 'builds[0].buildStatus' --output text 2>&1)
    echo -ne "\r  [build:${RUNTIME_NAME}] $(date +%H:%M:%S) - $status    "
  done
  echo

  if [[ "$status" == "SUCCEEDED" ]]; then
    ok "Build succeeded"
  else
    err "Build $status"
    err "Logs: aws logs tail /aws/codebuild/$CODEBUILD_PROJECT --since 10m"
    exit 1
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

zip_source
upload_source
build_and_wait
