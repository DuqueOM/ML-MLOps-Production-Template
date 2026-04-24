#!/usr/bin/env bash
# Devcontainer post-create: install template dev dependencies.
# Idempotent — safe to re-run when a service is added.

set -euo pipefail

echo "[post-create] installing Python dev dependencies..."
python -m pip install --upgrade pip
if [ -f requirements-dev.txt ]; then
  pip install -r requirements-dev.txt
fi
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

echo "[post-create] installing tools not covered by features..."
# conftest for Rego policy tests
if ! command -v conftest >/dev/null 2>&1; then
  curl -sL https://github.com/open-policy-agent/conftest/releases/download/v0.56.0/conftest_0.56.0_Linux_x86_64.tar.gz | \
    tar xz -C /tmp && sudo mv /tmp/conftest /usr/local/bin/
fi

# Syft for SBOM generation
if ! command -v syft >/dev/null 2>&1; then
  curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | \
    sudo sh -s -- -b /usr/local/bin
fi

# gitleaks for secret scanning
if ! command -v gitleaks >/dev/null 2>&1; then
  curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.18.0/gitleaks_8.18.0_linux_x64.tar.gz | \
    tar xz -C /tmp && sudo mv /tmp/gitleaks /usr/local/bin/
fi

echo "[post-create] verifying invariants..."
python -c "import pandas, sklearn, fastapi, pydantic" || { echo "Core deps missing"; exit 1; }

echo "[post-create] done. Run 'pytest' to verify the environment."
