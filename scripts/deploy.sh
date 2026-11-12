
#!/usr/bin/env bash

# Deploy the whole SmartFuel project or selected stacks.
# Each team member deploys into their own AWS Sandbox account.

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ALL_STACKS=(core ingestion processing ml-alerts web-api)
MODE="apply"

if [[ "${1:-}" == "--plan" ]]; then
  MODE="plan"
  shift
fi

STACKS=("${@:-${ALL_STACKS[@]}}")
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)" \
  || { echo "Load your sandbox credentials first"; exit 1; }

SUFFIX="${ACCOUNT_ID}"
STATE_BUCKET="smartfuel-tfstate-${SUFFIX}"

echo "Account ${ACCOUNT_ID} · region ${REGION} · mode ${MODE} · stacks: ${STACKS[*]}"

prepare_ingestion_package() {
  echo "Checking ingestion Lambda package..."

  local package_dir="${ROOT}/infra/ingestion/package"
  local requirements="${ROOT}/src/lambdas/ingest/requirements.txt"
  local handler="${ROOT}/src/lambdas/ingest/handler.py"
  local fingerprint_file="/tmp/smartfuel-ingestion-${ACCOUNT_ID}.fingerprint"

  local fingerprint
  fingerprint="$(cat "${requirements}" "${handler}" | shasum -a 256 | awk '{print $1}')"

  if [[ -f "${fingerprint_file}" ]] &&
     [[ "$(cat "${fingerprint_file}")" == "${fingerprint}" ]] &&
     [[ -f "${package_dir}/handler.py" ]] &&
     [[ -d "${package_dir}/requests" ]]; then
    echo "Package is already up to date. Skipping rebuild."
    return
  fi

  echo "Building Linux-compatible Python 3.12 dependencies..."

  mkdir -p "${package_dir}"
  find "${package_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

  python -m pip install \
    -r "${requirements}" \
    --target "${package_dir}" \
    --platform manylinux2014_x86_64 \
    --python-version 3.12 \
    --implementation cp \
    --abi cp312 \
    --only-binary=:all: \
    --no-compile

  cp "${handler}" "${package_dir}/handler.py"

  echo "${fingerprint}" > "${fingerprint_file}"

  echo "Ingestion Lambda package prepared successfully."
}

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
  echo
  echo "=== ${stack} ==="

  if [[ "${stack}" == "ingestion" ]]; then
    prepare_ingestion_package
  fi

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

echo
echo "Done: ${STACKS[*]} (${MODE}) in account ${ACCOUNT_ID}"
