#!/usr/bin/env bash
# Phase 0 · run ONCE from a laptop with the shared sandbox credentials loaded.
# Creates the Terraform state bucket and stores the GitHub secrets/variables.
#
#   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
#   gh auth login
#   ./infra/bootstrap/bootstrap.sh
set -euo pipefail

REGION="us-east-1"
REPO="laurarigau/SmartFuel-cloud_solutions"
SUFFIX="${SUFFIX:-$(date +%s)}"
STATE_BUCKET="smartfuel-tfstate-${SUFFIX}"

aws sts get-caller-identity > /dev/null || { echo "AWS credentials not loaded"; exit 1; }

echo "Creating state bucket: ${STATE_BUCKET}"
aws s3 mb "s3://${STATE_BUCKET}" --region "${REGION}"
aws s3api put-bucket-versioning --bucket "${STATE_BUCKET}" \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket "${STATE_BUCKET}" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "Saving GitHub variables and secrets in ${REPO}"
gh variable set TF_STATE_BUCKET --body "${STATE_BUCKET}" --repo "${REPO}"
gh variable set SUFFIX --body "${SUFFIX}" --repo "${REPO}"
"$(dirname "$0")/update_secrets.sh"

cat <<EOF

Done.
  State bucket : ${STATE_BUCKET}
  Suffix       : ${SUFFIX}   (lake bucket = smartfuel-lake-${SUFFIX})

Local runs: copy infra/backend.hcl.example to infra/backend.hcl and fill it in.
EOF
