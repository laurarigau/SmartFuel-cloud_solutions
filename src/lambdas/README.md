# Lambdas

One folder per function, named like the Lambda without the `smartfuel-` prefix:

```
src/lambdas/<name>/
  handler.py        # def lambda_handler(event, context)
  test_handler.py   # pytest, uses ../../../fixtures/
  requirements.txt  # only if it needs more than boto3
```

| Name | Phase | Trigger |
| --- | --- | --- |
| `ingest` | A | EventBridge Scheduler (4×/day) |
| `validate`, `clean`, `save-changes`, `predict` | B | Step Functions |
| `train`, `evaluate` | C | Step Functions (weekly) |
| `check-alerts` | C | DynamoDB Streams (`latest-prices`) |
| `send-email` | C | SNS `price-alerts` |
| `api-*` | D | API Gateway HTTP API |

Read resource names from environment variables set by Terraform (`LAKE_BUCKET`, `STATIONS_TABLE`, ...), never hard-code them.
The pipeline runs `pytest src/lambdas` on every PR.

## Phase B · processing Lambdas

| Lambda | Input → output | Env vars | Layer |
| --- | --- | --- | --- |
| `validate` | EventBridge S3 event → `{bucket, key, valid, reasons, snapshot, stations, quarantine_key}` | `LAKE_BUCKET`, `ADMIN_TOPIC_ARN`, `MIN_STATIONS` | — |
| `clean` | validate output → `+ {clean_key, changes_key, previous_key, rows, changes, new_stations}` | `LAKE_BUCKET`, `LOOKBACK_DAYS` | AWS SDK for pandas |
| `save-changes` | clean output → `{prices_written, stations_written}` | `LAKE_BUCKET`, `LATEST_PRICES_TABLE`, `STATIONS_TABLE` | — |
| `predict` | clean output → `{predictions_written, model_version}` | `LAKE_BUCKET`, `PREDICTIONS_TABLE`, `MODEL_PREFIX`, `TTL_DAYS` | AWS SDK for pandas (+ sklearn/joblib once C ships a model) |

Run the tests locally: `pip install pytest boto3 pandas pyarrow && pytest -q` (from the repo root).
Tests use in-memory fakes (`src/lambdas/conftest.py`): no AWS account or credentials needed.
