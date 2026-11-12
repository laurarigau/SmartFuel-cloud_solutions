#!/usr/bin/env bash
# Sandbox credentials expire: run this every time you start a new sandbox
# session so GitHub Actions can keep deploying.
set -euo pipefail
REPO="laurarigau/SmartFuel-cloud_solutions"

: "${AWS_ACCESS_KEY_ID:?load the sandbox credentials first}"
: "${AWS_SECRET_ACCESS_KEY:?}"
: "${AWS_SESSION_TOKEN:?}"

gh secret set AWS_ACCESS_KEY_ID     --app actions --body "$AWS_ACCESS_KEY_ID"     --repo "$REPO"
gh secret set AWS_SECRET_ACCESS_KEY --app actions --body "$AWS_SECRET_ACCESS_KEY" --repo "$REPO"
gh secret set AWS_SESSION_TOKEN     --app actions --body "$AWS_SESSION_TOKEN"     --repo "$REPO"
echo "GitHub secrets updated."
