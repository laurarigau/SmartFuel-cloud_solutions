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
