# SmartFuel Forecast

Serverless, event-driven AWS solution that collects Spain's fuel prices (Ministry open data), keeps the history in an S3 data lake, predicts whether prices will go up or down and emails users when a station they follow gets cheaper.

Cloud Solutions project — Carla Escassi, Marc Farràs, Laura Rigau, Marta Palet.

## How we work: the same project in 4 sandboxes

Each of us deploys the **whole project** in our own university sandbox. Nobody shares credentials.
GitHub only holds the code: the pipeline checks it (fmt, validate, tests) but does not deploy.
Bucket names include the AWS account id, so the 4 copies never collide.

```
GitHub (code + checks)
   │  git pull
   ├── Carla's sandbox   ← ./scripts/deploy.sh
   ├── Marc's sandbox    ← ./scripts/deploy.sh
   ├── Laura's sandbox   ← ./scripts/deploy.sh
   └── Marta's sandbox   ← ./scripts/deploy.sh
```

## Repository layout

```
infra/
  core/          # shared resources: S3 lake, DynamoDB tables, SNS topics, DLQ
  ingestion/     # Phase A · Scheduler, ingest Lambda, Glue/Athena, monitoring
  processing/    # Phase B · S3 event rule, Step Functions, validate/clean/save/predict
  ml-alerts/     # Phase C · weekly retraining, Streams -> Lambda -> SNS -> Lambda -> SES
  web-api/       # Phase D · Cognito, HTTP API, API Lambdas, Amplify
scripts/
  deploy.sh      # deploy all (or some) stacks to YOUR sandbox
  destroy.sh     # remove everything from YOUR sandbox
  exploration/   # first API exploration scripts
src/lambdas/     # one folder per Lambda: handler.py + test_handler.py
frontend/        # static web app (map)
ml/              # notebook for model v0
fixtures/        # small sample files for tests (raw_sample.json = 50 real stations)
docs/contracts.md
```

Each folder in `infra/` is its own Terraform stack with its own state (`<stack>/terraform.tfstate` in `smartfuel-tfstate-<account-id>`). Phase stacks read the shared resources from `core` (`local.core.lake_bucket`, `local.core.tables.stations`, ...).

## Deploy to your sandbox

Requirements: AWS CLI, Terraform ≥ 1.10.

```bash
# 1. Start your sandbox and load its credentials (they expire every session)
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...

# 2. Get the latest code
git pull

# 3. Deploy
./scripts/deploy.sh                  # everything, in order (core first)
./scripts/deploy.sh processing       # only one stack
./scripts/deploy.sh --plan web-api   # see what would change
```

The first run creates the state bucket automatically. To clean up: `./scripts/destroy.sh`.

## Git workflow

- Branch per task: `a/ingest-lambda`, `b/state-machine`, `c/retraining`, `d/cognito`...
- Test in your sandbox with `./scripts/deploy.sh <your-stack>` before opening the PR.
- Open a PR to `main`; the `checks` workflow must pass and another member reviews.
- After a merge, everyone runs `git pull && ./scripts/deploy.sh` to update their copy.
- Changing something in `core` or `docs/contracts.md` affects everyone: say it in the PR.

Protect `main` in GitHub → Settings → Branches: require a PR, 1 approval and the `checks` workflow.

## Demo sandbox

All 4 copies collect data, but pick **one** sandbox for the demo (the one whose ingestion has run the longest without gaps) and train the final model there.

## Sandbox checks (day 1)

- [ ] Can we create IAM roles, or must we use the pre-created role (e.g. `LabRole`)?
- [ ] Are EventBridge Scheduler, Step Functions, Athena/Glue, Cognito, Amplify, SES and Budgets available?
- [ ] Do the Scheduler and Lambdas keep running when the session is closed?
- [ ] Back up `raw/` weekly outside AWS (`aws s3 sync`): university accounts can be reset.
