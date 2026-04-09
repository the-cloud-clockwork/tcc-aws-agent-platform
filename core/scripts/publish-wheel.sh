#!/usr/bin/env bash
#
# publish-wheel.sh — build agent-core wheel and republish to CodeArtifact.
#
# Version is pinned to a fixed "floating" label in core/pyproject.toml
# (currently 1.0.0). We never bump it — every call to this script
# deletes the prior version from CodeArtifact and uploads a freshly
# built wheel with the same label.
#
# Rationale: bumping semver on every dev iteration is friction.
# This script keeps the CodeArtifact publishing flow intact but makes
# version numbers a no-op for dev. Cut a real semver release by hand
# when you actually need a reproducible snapshot.
#
# Requirements: aws cli, twine, python -m build.
#
# Usage:
#   ./core/scripts/publish-wheel.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "$HERE/.." && pwd)"
REGION="${AWS_REGION:-eu-west-1}"
DOMAIN="${CODEARTIFACT_DOMAIN:-platform}"
DOMAIN_OWNER="${CODEARTIFACT_DOMAIN_OWNER:-835618032093}"
REPO="${CODEARTIFACT_REPO:-platform-python}"
PACKAGE="agent-core"

# Read the fixed version straight from pyproject.toml
VERSION="$(grep -E '^version = ' "$CORE_DIR/pyproject.toml" | head -1 | sed -E 's/version = "(.*)"/\1/')"
if [[ -z "$VERSION" ]]; then
    echo "ERROR: could not read version from $CORE_DIR/pyproject.toml" >&2
    exit 1
fi

echo ">> Publishing $PACKAGE $VERSION to CodeArtifact ($DOMAIN/$REPO)"

# 1. Build the wheel
BUILD_OUT="$(mktemp -d)"
trap 'rm -rf "$BUILD_OUT"' EXIT

echo ">> Building wheel..."
(cd "$CORE_DIR" && python3 -m build --wheel --outdir "$BUILD_OUT")

WHEEL="$(ls "$BUILD_OUT"/*.whl | head -1)"
if [[ -z "$WHEEL" ]]; then
    echo "ERROR: no wheel produced in $BUILD_OUT" >&2
    exit 1
fi
echo ">> Built: $(basename "$WHEEL")"

# 2. Delete any existing copy of this version (CodeArtifact is immutable)
echo ">> Deleting any existing $PACKAGE==$VERSION from CodeArtifact..."
aws codeartifact delete-package-versions \
    --region "$REGION" \
    --domain "$DOMAIN" \
    --domain-owner "$DOMAIN_OWNER" \
    --repository "$REPO" \
    --package "$PACKAGE" \
    --format pypi \
    --versions "$VERSION" \
    --query 'successfulVersions' --output json 2>/dev/null || echo "   (no prior version to delete)"

# 3. Upload the fresh wheel
echo ">> Uploading wheel..."
CA_TOKEN="$(aws codeartifact get-authorization-token \
    --domain "$DOMAIN" \
    --domain-owner "$DOMAIN_OWNER" \
    --region "$REGION" \
    --query authorizationToken --output text)"

TWINE_USERNAME=aws \
TWINE_PASSWORD="$CA_TOKEN" \
twine upload \
    --repository-url "https://${DOMAIN}-${DOMAIN_OWNER}.d.codeartifact.${REGION}.amazonaws.com/pypi/${REPO}/" \
    "$WHEEL"

echo ">> Done. $PACKAGE $VERSION republished to CodeArtifact."
