#!/bin/bash
set -uo pipefail
# Build and push MCP Docker images to ECR.
# Each MCP gets its own ECR repository.

ACCOUNT="${AWS_ACCOUNT_ID:-123456789012}"
REGION="${AWS_REGION:-eu-west-1}"
ENV_NAME="${ENV_NAME:-dev}"
PREFIX="${RESOURCE_PREFIX:-platform}"
ECR_BASE="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
DOMAIN_ROOT="${DOMAIN_ROOT:-$HOME/dev/tccw-qitp}"
PLATFORM_ROOT="$HOME/dev/tccw-aws-agent-platform"

echo "==> Logging into ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_BASE"

echo "==> Getting CodeArtifact token for agent-core..."
CA_TOKEN=$(aws codeartifact get-authorization-token \
  --domain platform --domain-owner "$ACCOUNT" --region "$REGION" \
  --query authorizationToken --output text)
PIP_EXTRA_INDEX_URL="https://aws:${CA_TOKEN}@platform-${ACCOUNT}.d.codeartifact.${REGION}.amazonaws.com/pypi/platform-python/simple/"

# MCP name → source path mapping
declare -A MCPS=(
  ["market-data"]="$DOMAIN_ROOT/mcps/market-data"
  ["sentiment"]="$DOMAIN_ROOT/mcps/sentiment"
  ["backtest"]="$DOMAIN_ROOT/mcps/backtest"
  ["ibkr"]="$DOMAIN_ROOT/mcps/ibkr"
  ["charting"]="$DOMAIN_ROOT/mcps/charting"
  ["twofa"]="$DOMAIN_ROOT/mcps/twofa"
  ["ml-predict"]="$DOMAIN_ROOT/mcps/ml-predict"
  ["technical"]="$DOMAIN_ROOT/mcps/technical"
  ["artifacts"]="$PLATFORM_ROOT/artifacts"
)

FAILED=()

for name in "${!MCPS[@]}"; do
  path="${MCPS[$name]}"
  repo="$PREFIX-$ENV_NAME-mcp-$name"
  full_repo="$ECR_BASE/$repo"

  echo ""
  echo "==> Building MCP: $name (from $path)"

  if [ ! -d "$path" ]; then
    echo "    WARNING: Source directory not found: $path — skipping"
    FAILED+=("$name")
    continue
  fi

  if [ ! -f "$path/Dockerfile" ]; then
    echo "    WARNING: No Dockerfile found in $path — skipping"
    FAILED+=("$name")
    continue
  fi

  # ECR repos are managed by CDK — verify it exists before pushing
  if ! aws ecr describe-repositories --repository-names "$repo" --region "$REGION" >/dev/null 2>&1; then
    echo "    WARNING: ECR repo $repo not found — deploy CDK first. Skipping."
    FAILED+=("$name")
    continue
  fi

  # Build for linux/amd64 (Fargate)
  # backtest needs monorepo root as build context (depends on simulation/)
  if [ "$name" = "backtest" ]; then
    build_ctx="$DOMAIN_ROOT"
    build_args="-f $path/Dockerfile"
  else
    build_ctx="$path"
    build_args=""
  fi
  if ! docker build --platform linux/amd64 --build-arg PIP_EXTRA_INDEX_URL="$PIP_EXTRA_INDEX_URL" $build_args -t "$full_repo:latest" "$build_ctx"; then
    echo "    ERROR: Docker build failed for $name — skipping"
    FAILED+=("$name")
    continue
  fi

  # Push
  docker push "$full_repo:latest"

  echo "    Pushed: $full_repo:latest"
done

echo ""
echo "==> Build complete."
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "    SKIPPED: ${FAILED[*]}"
fi
