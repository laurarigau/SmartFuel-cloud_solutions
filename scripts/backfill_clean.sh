#!/usr/bin/env bash
# Phase B · backfill: build clean/ (Parquet history for Athena and ML) from every raw/ file.
#
# Runs ONLY validate -> clean, oldest file first. It does NOT run save-changes or predict:
#   - old prices must not overwrite today's prices in DynamoDB (smartfuel-latest-prices);
#   - writing to that table would fire price-alert emails through its Stream (Phase C).
# Re-running is safe: the same raw file always gives the same clean/ file.
#
#   ./scripts/backfill_clean.sh                 # every file in raw/
#   ./scripts/backfill_clean.sh raw/2026/11/1   # only keys starting with this prefix
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-north-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="smartfuel-lake-${ACCOUNT_ID}"
PREFIX="${1:-raw/}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

invoke() {  # invoke <lambda> <payload file> <output file> -> 0 ok / 1 failed
  local err
  err=$(aws lambda invoke --region "$REGION" --function-name "smartfuel-$1" \
    --cli-binary-format raw-in-base64-out --cli-read-timeout 320 \
    --payload "fileb://$2" "$3" --query FunctionError --output text)
  [[ "$err" == "None" ]]
}

# raw/YYYY/MM/DD/HHmm.json sorts by date as text: oldest first
KEYS=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$PREFIX" --region "$REGION" \
  --query 'Contents[].Key' --output text | tr '\t' '\n' | grep '\.json$' | sort)
TOTAL=$(echo "$KEYS" | grep -c . || true)
echo "Account ${ACCOUNT_ID} · ${TOTAL} raw files to backfill (validate -> clean only)"
[[ "$TOTAL" -gt 0 ]] || exit 0

ok=0; quarantined=0; failed=0; i=0
for KEY in $KEYS; do
  i=$((i + 1))
  echo "{\"bucket\": \"${BUCKET}\", \"key\": \"${KEY}\"}" > "$TMP/in.json"

  if ! invoke validate "$TMP/in.json" "$TMP/validate.json"; then
    echo "[$i/$TOTAL] ❌ validate failed: $KEY"; cat "$TMP/validate.json"; echo; failed=$((failed + 1)); continue
  fi
  if [[ "$(python3 -c "import json; print(json.load(open('$TMP/validate.json'))['valid'])")" != "True" ]]; then
    echo "[$i/$TOTAL] ⚠️  quarantined: $KEY"; quarantined=$((quarantined + 1)); continue
  fi
  if ! invoke clean "$TMP/validate.json" "$TMP/clean.json"; then
    echo "[$i/$TOTAL] ❌ clean failed: $KEY"; cat "$TMP/clean.json"; echo; failed=$((failed + 1)); continue
  fi
  echo "[$i/$TOTAL] ✅ $KEY -> $(python3 -c "import json; d=json.load(open('$TMP/clean.json')); print(d['clean_key'], '·', d['rows'], 'rows ·', d['changes'], 'changes')")"
  ok=$((ok + 1))
done

echo
echo "Done: ${ok} cleaned · ${quarantined} quarantined · ${failed} failed"
[[ "$failed" -eq 0 ]]
