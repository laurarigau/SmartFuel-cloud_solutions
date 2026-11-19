#!/usr/bin/env bash
# End-to-end test of Phase B in YOUR sandbox.
# Runs the Step Functions state machine (smartfuel-processing) on the LATEST real file in raw/:
# validate -> clean -> save-changes | predict. Re-running on the same file is safe.
# If raw/ is still empty, it uploads the Ministry snapshot from fixtures/ instead.
#
#   ./scripts/test_processing.sh            # latest raw/ file
#   ./scripts/test_processing.sh raw/2026/11/18/1200.json
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-north-1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="smartfuel-lake-${ACCOUNT_ID}"
TMP="$(mktemp -d)"

KEY="${1:-$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix raw/ --region "$REGION" \
  --query 'sort_by(Contents, &Key)[-1].Key' --output text 2>/dev/null || true)}"

if [[ -z "$KEY" || "$KEY" == "None" ]]; then
  KEY="raw/2026/11/04/1325.json"   # Fecha of the fixture
  echo "raw/ is empty: uploading fixtures/fuel_prices_sample.json as ${KEY}"
  echo "(the EventBridge rule also starts a run for it automatically)"
  aws s3 cp "${ROOT}/fixtures/fuel_prices_sample.json" "s3://${BUCKET}/${KEY}" --region "$REGION" --only-show-errors
fi

SM_ARN="arn:aws:states:${REGION}:${ACCOUNT_ID}:stateMachine:smartfuel-processing"
echo "Account ${ACCOUNT_ID} · processing s3://${BUCKET}/${KEY} with Step Functions (1-3 min)..."
EXEC_ARN=$(aws stepfunctions start-execution --region "$REGION" --state-machine-arn "$SM_ARN" \
  --name "test-$(date +%Y%m%d-%H%M%S)" \
  --input "{\"bucket\": \"${BUCKET}\", \"key\": \"${KEY}\"}" \
  --query executionArn --output text)

while true; do
  STATUS=$(aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC_ARN" \
    --query status --output text)
  [[ "$STATUS" == "RUNNING" ]] || break
  sleep 5
done

if [[ "$STATUS" != "SUCCEEDED" ]]; then
  echo "❌ Execution ${STATUS}:"
  aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC_ARN" \
    --query '{error: error, cause: cause}' --output json
  echo "See the steps: AWS console > Step Functions > smartfuel-processing > the latest execution"
  exit 1
fi
echo "✅ ${STATUS}: $(aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC_ARN" --query output --output text)"

echo
echo "DynamoDB (items):"
for t in stations latest-prices predictions; do
  printf "  smartfuel-%-14s %s\n" "$t" \
    "$(aws dynamodb scan --table-name "smartfuel-$t" --select COUNT --region "$REGION" --query Count --output text)"
done
rm -rf "$TMP"
