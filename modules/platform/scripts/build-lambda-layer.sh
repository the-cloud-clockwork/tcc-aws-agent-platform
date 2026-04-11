#!/usr/bin/env bash
set -euo pipefail

# Builds a shared Lambda layer with common Python deps for arm64/python3.12.
# Output: modules/platform/.build/lambda-layer.zip
#
# Layer structure (Lambda unpacks to /opt/):
#   python/lib/python3.12/site-packages/
#     pydantic/
#     pydantic_core/
#     mcp_artifacts/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PLATFORM_DIR/../.." && pwd)"

BUILD_DIR="$PLATFORM_DIR/.build/layer/python/lib/python3.12/site-packages"
ZIP_PATH="$PLATFORM_DIR/.build/lambda-layer.zip"

rm -rf "$PLATFORM_DIR/.build/layer" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

echo ">> Installing pydantic (arm64, python3.12)..."
pip install --platform manylinux2014_aarch64 --python-version 3.12 \
  --only-binary=:all: --target "$BUILD_DIR" \
  --index-url https://pypi.org/simple/ \
  "pydantic>=2.6,<3" --quiet

echo ">> Copying mcp_artifacts..."
cp -r "$REPO_ROOT/artifacts/src/mcp_artifacts" "$BUILD_DIR/"

echo ">> Zipping layer..."
cd "$PLATFORM_DIR/.build/layer" && zip -qr "$ZIP_PATH" python/

echo ">> Done: lambda-layer.zip ($(du -h "$ZIP_PATH" | cut -f1))"
