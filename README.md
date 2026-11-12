# SmartFuel Forecast

Serverless, event-driven AWS solution that collects Spain's fuel prices (Ministry open data), keeps the history in an S3 data lake, predicts whether prices will go up or down and emails users when a station they follow gets cheaper.

Cloud Solutions project — Carla Escassi, Marc Farràs, Laura Rigau, Marta Palet.

## Repository layout

```
infra/
  bootstrap/     # one-off: Terraform state bucket + GitHub secrets
  core/          # shared: S3 lake, DynamoDB tables, SNS topics, DLQ
  ingestion/     # Phase A · Scheduler, ingest Lambda, Glue/Athena, monitoring
  processing/    # Phase B · S3 event rule, Step Functions, validate/clean/save/predict
  ml-alerts/     # Phase C · weekly retraining, Streams -> Lambda -> SNS -> Lambda -> SES
  web-api/       # Phase D · Cognito, HTTP API, API Lambdas, Amplify
src/lambdas/     # one folder per Lambda: handler.py + test_handler.py
frontend/        # static web app (map)
ml/              # notebook for model v0
fixtures/        # small sample files for tests (raw_sample.json = 50 real stations)
scripts/         # exploration scripts
docs/contracts.md
```

Each folder in `infra/` is its own Terraform stack with its own state (`<stack>/terraform.tfstate`), so four people can deploy at the same time. Phase stacks read the shared resources from `core` (`local.core.lake_bucket`, `local.core.tables.stations`, ...).

## Phase 0 setup (once)

1. Start the shared sandbox, copy its credentials and run:
   ```bash
   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
   gh auth login
   ./infra/bootstrap/bootstrap.sh
   ```
   It creates the state bucket and sets the GitHub variables `TF_STATE_BUCKET`, `SUFFIX` and the three AWS secrets.
2. GitHub → Settings → Actions → General → Workflow permissions → **Read and write** (needed to comment plans on PRs).
3. GitHub → Settings → Branches → protect `main`: require a pull request with 1 approval and the `terraform` checks passing.
4. Merge the Phase 0 PR → the pipeline applies `core`.

**Every new sandbox session:** credentials expire, so whoever starts it runs `./infra/bootstrap/update_secrets.sh`.

## Workflow

- Branch per task: `a/ingest-lambda`, `b/state-machine`, `c/retraining`, `d/cognito`...
- Open a PR to `main`: the pipeline runs `fmt`, Lambda tests, `validate` and `plan` for every stack and comments the plans.
- Another member reviews → merge → the pipeline applies `core`, then the four phase stacks.
- Never `terraform apply` locally on someone else's stack.

## Sandbox checks (day 1)

- [ ] Can we create IAM roles, or must we use a pre-created role?
- [ ] Are EventBridge Scheduler, Step Functions, Athena/Glue, Cognito, Amplify, SES and Budgets available?
- [ ] Do the Scheduler and Lambdas keep running when no session is open?
- [ ] How long do credentials last?
