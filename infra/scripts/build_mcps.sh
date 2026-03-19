#!/bin/bash
set -euo pipefail
# Build and push MCP Docker images to ECR.
# Each MCP gets its own ECR repository.

ACCOUNT="${AWS_ACCOUNT_ID:-123456789012}"
REGION="${AWS_REGION:-eu-west-1}"
ENV_NAME="${ENV_NAME:-dev}"
PREFIX="${RESOURCE_PREFIX:-platform}"
ECR_BASE="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
QITP_ROOT="$HOME/dev/tccw-qitp"
PLATFORM_ROOT="$HOME/dev/tccw-aws-agent-platform"

echo "==> Logging into ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_BASE"

# MCP name → source path mapping
declare -A MCPS=(
  ["market-data"]="$QITP_ROOT/mcps/market-data"
  ["sentiment"]="$QITP_ROOT/mcps/sentiment"
  ["backtest"]="$QITP_ROOT/mcps/backtest"
  ["ibkr"]="$QITP_ROOT/mcps/ibkr"
  ["charting"]="$QITP_ROOT/mcps/charting"
  ["twofa"]="$QITP_ROOT/mcps/twofa"
  ["ml-predict"]="$QITP_ROOT/mcps/ml-predict"
  ["technical"]="$QITP_ROOT/mcps/technical"
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

  # Create ECR repo if not exists
  aws ecr describe-repositories --repository-names "$repo" --region "$REGION" 2>/dev/null || \
    aws ecr create-repository \
      --repository-name "$repo" \
      --region "$REGION" \
      --image-scanning-configuration scanOnPush=true \
      --tags Key=Environment,Value="$ENV_NAME" Key=Project,Value=agent-infra

  # Build for linux/amd64 (Fargate)
  docker build --platform linux/amd64 -t "$full_repo:latest" "$path"

  # Push
  docker push "$full_repo:latest"

  echo "    Pushed: $full_repo:latest"
done

echo ""
echo "==> Build complete."
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "    SKIPPED: ${FAILED[*]}"
fi
