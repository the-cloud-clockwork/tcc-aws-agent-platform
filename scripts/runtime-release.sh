#!/usr/bin/env bash
set -euo pipefail

# runtime-release.sh — Platform-generic build/deploy for AgentCore Runtimes
#
# Handles BOTH layouts:
#   monorepo:  single Dockerfile at source root  (agents pattern)
#   polyrepo:  per-service subdirectories         (MCPs pattern)
#
# This script is distributed to domain repos via setup-dev.sh.
# Domain wrapper scripts (e.g., agent-release.sh) set config vars
# then source this file to get the library functions.
#
# Required env vars (set by domain wrapper):
#   REPO_ROOT             — domain repo root
#   INFRA_DIR             — path to infra/ directory
#   SOURCE_DIR            — path to source directory (agents/ or mcps/)
#   CODEBUILD_SOURCE_BUCKET — S3 bucket for build source
#   SOURCE_ZIP_KEY        — S3 key for the source zip
#   CODEBUILD_PREFIX      — CodeBuild project name prefix
#   TF_MODULE             — Terraform module name (agents or mcps)
#   RUNTIME_OUTPUT        — Terraform output key for runtime ARNs
#   CODEARTIFACT_DOMAIN   — CodeArtifact domain name
#   CODEARTIFACT_REPO     — CodeArtifact repository name
#
# Optional:
#   SOURCE_LAYOUT         — "monorepo" (default) or "polyrepo"
#   POLYREPO_SUFFIX       — suffix to strip from blueprint ID to get subdir (default: "-mcp")

# ── Defaults ─────────────────────────────────────────────────────────────────
SOURCE_LAYOUT="${SOURCE_LAYOUT:-monorepo}"
POLYREPO_SUFFIX="${POLYREPO_SUFFIX:--mcp}"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[release]${NC} $*"; }
ok()   { echo -e "${GREEN}[  ok  ]${NC} $*"; }
err()  { echo -e "${RED}[error ]${NC} $*" >&2; }

# ── Source Zipping ───────────────────────────────────────────────────────────

# Zip a monorepo source directory (Dockerfile at root).
# Called once, shared across all runtimes.
_zip_monorepo() {
  local tmpzip="$1"
  cd "$SOURCE_DIR"
  zip -r "$tmpzip" Dockerfile pyproject.toml src/ blueprints/ prompts/ \
    -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null || \
  zip -r "$tmpzip" Dockerfile pyproject.toml src/ blueprints/ \
    -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null
  cd "$REPO_ROOT"
}

# Zip a single service from a polyrepo directory.
# Called per-runtime with the runtime name.
_zip_polyrepo() {
  local tmpzip="$1"
  local runtime_name="$2"
  local subdir="${runtime_name%${POLYREPO_SUFFIX}}"
  local service_dir="$SOURCE_DIR/$subdir"

  if [[ ! -d "$service_dir" ]]; then
    err "Service directory not found: $service_dir (runtime: $runtime_name, subdir: $subdir)"
    return 1
  fi

  if [[ ! -f "$service_dir/Dockerfile" ]]; then
    err "No Dockerfile in $service_dir"
    return 1
  fi

  cd "$service_dir"
  zip -r "$tmpzip" Dockerfile pyproject.toml src/ prompts/ \
    -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null || \
  zip -r "$tmpzip" Dockerfile pyproject.toml src/ \
    -x '*__pycache__*' '*/.git/*' '*.pyc' 2>/dev/null
  cd "$REPO_ROOT"
}

# Public: build and upload source zip to S3.
# For monorepo: call once before the loop.
# For polyrepo: call per-runtime inside the loop.
build_source_zip() {
  local runtime_name="${1:-}"
  local tmpzip="/tmp/qitp-source-$$.zip"
  local s3_key="$SOURCE_ZIP_KEY"

  if [[ "$SOURCE_LAYOUT" == "polyrepo" ]]; then
    if [[ -z "$runtime_name" ]]; then
      err "build_source_zip requires runtime name for polyrepo layout"
      return 1
    fi
    log "Zipping source for $runtime_name from $SOURCE_DIR/${runtime_name%${POLYREPO_SUFFIX}}/..."
    s3_key="${SOURCE_ZIP_KEY%/*}/${runtime_name}-source.zip"
    _zip_polyrepo "$tmpzip" "$runtime_name"
  else
    log "Zipping source from $SOURCE_DIR..."
    _zip_monorepo "$tmpzip"
  fi

  log "Uploading to s3://$CODEBUILD_SOURCE_BUCKET/$s3_key"
  aws s3 cp "$tmpzip" "s3://$CODEBUILD_SOURCE_BUCKET/$s3_key" --quiet
  rm -f "$tmpzip"
  ok "Source uploaded"

  # Export for trigger_and_wait to use
  _LAST_S3_KEY="$s3_key"
}

# ── CodeBuild Trigger + Poll ────────────────────────────────────────────────

trigger_and_wait() {
  local runtime_name="$1"
  local project="${CODEBUILD_PREFIX}-${runtime_name}"
  local s3_key="${_LAST_S3_KEY:-$SOURCE_ZIP_KEY}"

  log "Triggering CodeBuild: $project"
  local build_id
  build_id=$(aws codebuild start-build \
    --project-name "$project" \
    --source-type-override S3 \
    --source-location-override "$CODEBUILD_SOURCE_BUCKET/$s3_key" \
    --query 'build.id' --output text 2>&1)

  if [[ "$build_id" == *"error"* ]] || [[ "$build_id" == *"Error"* ]]; then
    err "Failed to start build: $build_id"
    return 1
  fi

  log "Build: $build_id — polling..."
  local status="IN_PROGRESS"
  while [[ "$status" == "IN_PROGRESS" ]]; do
    sleep 30
    status=$(aws codebuild batch-get-builds --ids "$build_id" \
      --query 'builds[0].buildStatus' --output text 2>&1)
    echo -ne "\r  $(date +%H:%M:%S) - $status    "
  done
  echo

  if [[ "$status" == "SUCCEEDED" ]]; then
    ok "Build succeeded: $runtime_name"
  else
    err "Build $status: $runtime_name"
    err "Logs: aws logs get-log-events --log-group-name /aws/codebuild/$project --log-stream-name ${build_id#*:}"
    return 1
  fi
}

# ── Terraform Deploy ─────────────────────────────────────────────────────────

deploy_runtime() {
  local runtime_name="$1"
  local tf_var_file="${TF_VAR_FILE:-envs/dev.tfvars}"
  log "Deploying $runtime_name (terraform apply)..."

  cd "$INFRA_DIR"
  terraform apply -var-file="$tf_var_file" \
    -target="module.${TF_MODULE}.aws_bedrockagentcore_agent_runtime.agent[\"${runtime_name}\"]" \
    -auto-approve -no-color 2>&1 | grep -E "Apply complete|Error" | head -1
  cd "$REPO_ROOT"
  ok "Runtime updated: $runtime_name"
}

# ── Invoke Agent ─────────────────────────────────────────────────────────────

invoke_runtime() {
  local runtime_name="$1"

  local runtime_arn
  runtime_arn=$(cd "$INFRA_DIR" && terraform output -json "$RUNTIME_OUTPUT" 2>/dev/null | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('$runtime_name',''))")

  if [[ -z "$runtime_arn" ]]; then
    err "No runtime ARN found for $runtime_name"
    return 1
  fi

  local session_id="release-test-$(date +%s)-$(head -c 4 /dev/urandom | xxd -p)"
  local outfile="/tmp/invoke-${runtime_name}-$$.json"

  log "Invoking $runtime_name (session: $session_id)..."
  aws bedrock-agentcore invoke-agent-runtime \
    --agent-runtime-arn "$runtime_arn" \
    --payload "{\"agent_id\":\"$runtime_name\",\"session_id\":\"$session_id\",\"prompt\":\"Health check: produce a minimal output to verify the agent pipeline.\",\"parameters\":{\"date\":\"$(date +%Y-%m-%d)\"}}" \
    "$outfile" 2>&1 | grep -v "^$"

  python3 -c "
import json
with open('$outfile') as f:
    data = json.load(f)
status = data.get('status','?')
artifact = data.get('artifact_id','')
s3_key = data.get('s3_key','')
claim = data.get('claim_check', False)
tier = data.get('tier','')
error = data.get('error','')
if status == 'success':
    print(f'  Status:      \033[0;32m{status}\033[0m')
else:
    print(f'  Status:      \033[0;31m{status}\033[0m')
print(f'  Artifact ID: {artifact}')
print(f'  S3 Key:      {s3_key}')
print(f'  Claim Check: {claim}')
print(f'  Tier:        {tier}')
if error:
    print(f'  Error:       {error[:300]}')
"
  rm -f "$outfile"
}

# ── CodeArtifact Publish ─────────────────────────────────────────────────────

publish_package() {
  local package_dir="$1"
  local region="${AWS_DEFAULT_REGION:-eu-west-1}"
  local account_id
  account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)

  log "Publishing package from $package_dir..."
  cd "$package_dir"
  rm -rf dist/
  python3 -m build 2>&1 | tail -1

  local token
  token=$(aws codeartifact get-authorization-token \
    --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$account_id" \
    --region "$region" --query authorizationToken --output text)

  local repo_url
  repo_url=$(aws codeartifact get-repository-endpoint \
    --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$account_id" \
    --repository "$CODEARTIFACT_REPO" --format pypi \
    --region "$region" --query repositoryEndpoint --output text)

  TWINE_USERNAME=aws TWINE_PASSWORD="$token" TWINE_REPOSITORY_URL="$repo_url" \
    python3 -m twine upload dist/* 2>&1 | tail -3

  local version
  version=$(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)
  ok "Published $version to CodeArtifact"
  cd "$REPO_ROOT"
}

# ── Version ──────────────────────────────────────────────────────────────────
PLATFORM_SCRIPTS_VERSION="1.0.0"
