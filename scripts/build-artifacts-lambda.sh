#!/usr/bin/env bash
set -euo pipefail

# Build and deploy the artifacts-mcp-tools Lambda package.
# Packages: mcp_artifacts library + handler stub + pydantic (aarch64).
#
# Usage:
#   ./scripts/build-artifacts-lambda.sh --function-name my-artifacts-mcp-tools --region eu-west-1
#   ./scripts/build-artifacts-lambda.sh  # uses defaults

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
FUNCTION_NAME=""
REGION="eu-west-1"
SKIP_DEPLOY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --function-name) FUNCTION_NAME="$2"; shift 2 ;;
    --region)        REGION="$2"; shift 2 ;;
    --skip-deploy)   SKIP_DEPLOY=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--function-name NAME] [--region REGION] [--skip-deploy]"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$FUNCTION_NAME" && "$SKIP_DEPLOY" == "false" ]]; then
  echo "ERROR: --function-name is required (or use --skip-deploy to only build the zip)"
  exit 1
fi

# Paths
ARTIFACTS_SRC="$REPO_ROOT/artifacts/src/mcp_artifacts"
HANDLER_SRC="$REPO_ROOT/core/src/agent_core/api/artifacts_mcp_handler.py"
BUILD_DIR=$(mktemp -d)
PACKAGE_DIR="$BUILD_DIR/package"
ZIP_PATH="$BUILD_DIR/artifacts-mcp-tools.zip"

trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Building artifacts-mcp-tools Lambda package"
echo "    Build dir: $BUILD_DIR"

# 1. Install pydantic for aarch64 Lambda runtime
echo "==> Installing pydantic (aarch64/python3.12)..."
pip install \
  --platform manylinux2014_aarch64 \
  --python-version 3.12 \
  --only-binary=:all: \
  --target "$PACKAGE_DIR" \
  "pydantic>=2.6,<3" \
  --quiet

# 2. Copy mcp_artifacts library
echo "==> Copying mcp_artifacts library..."
cp -r "$ARTIFACTS_SRC" "$PACKAGE_DIR/mcp_artifacts"

# 3. Create minimal agent_core stub (handler only, empty __init__.py)
echo "==> Creating agent_core handler stub..."
mkdir -p "$PACKAGE_DIR/agent_core/api"
touch "$PACKAGE_DIR/agent_core/__init__.py"
touch "$PACKAGE_DIR/agent_core/api/__init__.py"
cp "$HANDLER_SRC" "$PACKAGE_DIR/agent_core/api/artifacts_mcp_handler.py"

# 4. Create zip
echo "==> Creating zip..."
(cd "$PACKAGE_DIR" && zip -r "$ZIP_PATH" . -q)

ZIP_SIZE=$(du -h "$ZIP_PATH" | cut -f1)
echo "    Zip size: $ZIP_SIZE"

if [[ "$SKIP_DEPLOY" == "true" ]]; then
  # Copy zip to a stable location
  DEST="$REPO_ROOT/build/artifacts-mcp-tools.zip"
  mkdir -p "$REPO_ROOT/build"
  cp "$ZIP_PATH" "$DEST"
  echo "==> Zip saved to: $DEST (deploy skipped)"
  exit 0
fi

# 5. Deploy to Lambda
echo "==> Deploying to Lambda: $FUNCTION_NAME ($REGION)..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --region "$REGION" \
  --output json \
  --query '{FunctionArn:FunctionArn,CodeSize:CodeSize,LastModified:LastModified}'

echo ""
echo "==> Waiting for function update to complete..."
aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION"

echo "==> Done. Lambda $FUNCTION_NAME deployed successfully."
