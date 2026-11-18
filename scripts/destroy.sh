#!/usr/bin/env bash
# Delete everything from YOUR sandbox (reverse order). The lake bucket must be
# emptied first: aws s3 rm s3://smartfuel-lake-<account-id> --recursive
set -euo pipefail
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
STATE_BUCKET="smartfuel-tfstate-${ACCOUNT_ID}"
export TF_VAR_region="${REGION}" TF_VAR_suffix="${ACCOUNT_ID}" TF_VAR_state_bucket="${STATE_BUCKET}"

read -r -p "Destroy SmartFuel in account ${ACCOUNT_ID}? Type 'yes': " ok
[[ "$ok" == "yes" ]] || exit 1

for stack in web-api ml-alerts processing ingestion core; do
  echo "=== ${stack} ==="
  cd "${ROOT}/infra/${stack}"
  terraform init -input=false -reconfigure \
    -backend-config="bucket=${STATE_BUCKET}" \
    -backend-config="key=${stack}/terraform.tfstate" \
    -backend-config="region=${REGION}" \
    -backend-config="use_lockfile=true" > /dev/null
  terraform destroy -input=false -auto-approve
done
