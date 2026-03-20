#!/usr/bin/env bash
# Generate pinned requirements files for each module using pip-compile.
# Requires: pip install pip-tools
#
# Usage:
#   ./scripts/lock-deps.sh          # lock all modules
#   ./scripts/lock-deps.sh core     # lock a single module
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODULES=(core infra cli prompts)

lock_module() {
    local mod="$1"
    local dir="${REPO_ROOT}/${mod}"
    if [[ ! -f "${dir}/pyproject.toml" ]]; then
        echo "SKIP: ${mod} — no pyproject.toml"
        return
    fi
    echo "Locking ${mod}..."
    pip-compile \
        --strip-extras \
        --output-file="${dir}/requirements.lock" \
        "${dir}/pyproject.toml"
    echo "  -> ${mod}/requirements.lock"
}

if [[ $# -gt 0 ]]; then
    lock_module "$1"
else
    for mod in "${MODULES[@]}"; do
        lock_module "$mod"
    done
fi

echo "Done."
