#!/usr/bin/env bash
# End-to-end test of Phase B in YOUR sandbox.
# Runs the orchestrator (smartfuel-process) on the LATEST real file in raw/:
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
  echo "(the EventBridge rule will also process it automatically)"
  aws s3 cp "${ROOT}/fixtures/fuel_prices_sample.json" "s3://${BUCKET}/${KEY}" --region "$REGION" --only-show-errors
fi

echo "Account ${ACCOUNT_ID} · processing s3://${BUCKET}/${KEY} (1-3 min)..."
echo "{\"bucket\": \"${BUCKET}\", \"key\": \"${KEY}\"}" > "$TMP/in.json"
ERR=$(aws lambda invoke --region "$REGION" --function-name smartfuel-process \
  --cli-binary-format raw-in-base64-out --cli-read-timeout 900 \
  --payload "fileb://$TMP/in.json" "$TMP/out.json" --query FunctionError --output text)

if [[ "$ERR" != "None" ]]; then
  echo "❌ Processing failed:"; cat "$TMP/out.json"; echo
  echo "Logs: aws logs tail /aws/lambda/smartfuel-process --since 15m --region $REGION"
  exit 1
fi
echo "✅ $(cat "$TMP/out.json")"

echo
echo "DynamoDB (items):"
for t in stations latest-prices predictions; do
  printf "  smartfuel-%-14s %s\n" "$t" \
    "$(aws dynamodb scan --table-name "smartfuel-$t" --select COUNT --region "$REGION" --query Count --output text)"
done
rm -rf "$TMP"
