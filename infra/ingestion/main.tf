# Phase A · Ingestion & data lake
# Owner: [name]
#
# TODO (see the plan doc and docs/contracts.md):
#   [ ] Lambda "ingest" (src/lambdas/ingest): GET Ministry API -> s3://<lake>/raw/YYYY/MM/DD/HHmm.json
#   [ ] EventBridge Scheduler: 4 times/day -> ingest Lambda (DEPLOY BEFORE DAY 3)
#   [ ] Glue database + table over clean/ (Parquet, partitioned by date) and Athena workgroup -> athena-results/
#   [ ] CloudWatch dashboard + alarms (Lambda errors, Step Functions failures, DLQ messages), budget alert if the sandbox allows it
#
# IAM: one role per Lambda / state machine with only the permissions it needs.
# If the sandbox does not allow creating roles, use the provided role and
# document the least-privilege policy you would attach.
