#!/bin/bash
set -euo pipefail
# Build Lambda deployment package for QITP agents.
# Installs agent-core + qitp-agents into a zip alongside blueprints + prompts.
# Strands SDK comes from the Lambda Layer (not included here).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$INFRA_DIR/lambda/agents/dist"
PLATFORM_ROOT="$(dirname "$INFRA_DIR")"
DOMAIN_ROOT="${DOMAIN_ROOT:-$HOME/dev/tccw-qitp}"

echo "==> Cleaning previous build..."
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

echo "==> Installing agent-core from platform repo..."
pip install \
  --target "$DIST_DIR" \
  --platform manylinux2014_aarch64 \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-deps \
  "$PLATFORM_ROOT/core"

echo "==> Installing qitp-agents from domain repo..."
pip install \
  --target "$DIST_DIR" \
  --platform manylinux2014_aarch64 \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-deps \
  "$DOMAIN_ROOT/agents"

echo "==> Installing runtime dependencies (including strands-agents)..."
pip install \
  --target "$DIST_DIR" \
  --platform manylinux2014_aarch64 \
  --python-version 3.12 \
  --only-binary=:all: \
  strands-agents pydantic boto3 pyyaml

echo "==> Copying blueprints..."
if [ -d "$DOMAIN_ROOT/agents/blueprints" ]; then
  cp -r "$DOMAIN_ROOT/agents/blueprints" "$DIST_DIR/"
fi

echo "==> Copying prompts..."
if [ -d "$DOMAIN_ROOT/agents/prompts" ]; then
  cp -r "$DOMAIN_ROOT/agents/prompts" "$DIST_DIR/"
fi

echo "==> Cleaning up bytecode..."
find "$DIST_DIR" -name '*.pyc' -delete
find "$DIST_DIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> Creating ZIP..."
cd "$DIST_DIR"
zip -r "$INFRA_DIR/lambda/agents/agents.zip" . -x '*.pyc' '__pycache__/*'

ZIP_SIZE=$(du -sh "$INFRA_DIR/lambda/agents/agents.zip" | cut -f1)
echo "==> Done! agents.zip: $ZIP_SIZE"
echo "    Path: $INFRA_DIR/lambda/agents/agents.zip"
