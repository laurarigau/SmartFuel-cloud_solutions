# Phase B · Processing (Step Functions)
# Owner: [name]
#
# TODO (see the plan doc and docs/contracts.md):
#   [ ] EventBridge rule: S3 "Object Created" on prefix raw/ -> state machine, DLQ = core dlq_arn
#   [ ] Lambdas validate / clean / save-changes / predict (src/lambdas/*)
#   [ ] State machine: Validate -> Clean -> Parallel(SaveChanges, Predict), Retry + Catch on every state, Catch -> admin-alerts
#
# IAM: one role per Lambda / state machine with only the permissions it needs.
# If the sandbox does not allow creating roles, use the provided role and
# document the least-privilege policy you would attach.
