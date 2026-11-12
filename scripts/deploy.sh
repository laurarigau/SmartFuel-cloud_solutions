#!/usr/bin/env bash
# Deploy the whole SmartFuel project (or some stacks) into YOUR sandbox.
# Each team member runs it with their own sandbox credentials: 4 independent copies.
#
#   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
#   ./scripts/deploy.sh                    # all stacks, in order
#   ./scripts/deploy.sh processing         # only your stack (core must exist)
#   ./scripts/deploy.sh --plan web-api     # plan only, no changes
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ALL_STACKS=(core ingestion processing ml-alerts web-api)
MODE="apply"
if [[ "${1:-}" == "--plan" ]]; then MODE="plan"; shift; fi
STACKS=("${@:-${ALL_STACKS[@]}}")

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)" \
  || { echo "Load your sandbox credentials first"; exit 1; }

# The account id makes every bucket name unique per sandbox, with no setup.
SUFFIX="${ACCOUNT_ID}"
STATE_BUCKET="smartfuel-tfstate-${SUFFIX}"
echo "Account ${ACCOUNT_ID} · region ${REGION} · mode ${MODE} · stacks: ${STACKS[*]}"

if ! aws s3api head-bucket --bucket "${STATE_BUCKET}" 2>/dev/null; then
  echo "Creating Terraform state bucket ${STATE_BUCKET}"
  aws s3 mb "s3://${STATE_BUCKET}" --region "${REGION}"
  aws s3api put-bucket-versioning --bucket "${STATE_BUCKET}" \
    --versioning-configuration Status=Enabled
  aws s3api put-public-access-block --bucket "${STATE_BUCKET}" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

export TF_VAR_region="${REGION}"
export TF_VAR_suffix="${SUFFIX}"
export TF_VAR_state_bucket="${STATE_BUCKET}"

for stack in "${STACKS[@]}"; do
  echo; echo "=== ${stack} ==="
  cd "${ROOT}/infra/${stack}"
  terraform init -input=false -reconfigure \
    -backend-config="bucket=${STATE_BUCKET}" \
    -backend-config="key=${stack}/terraform.tfstate" \
    -backend-config="region=${REGION}" \
    -backend-config="use_lockfile=true" > /dev/null
  if [[ "${MODE}" == "plan" ]]; then
    terraform plan -input=false
  else
    terraform apply -input=false -auto-approve
  fi
done
echo; echo "Done: ${STACKS[*]} (${MODE}) in account ${ACCOUNT_ID}"
