# SmartFuel Forecast

Serverless, event-driven AWS solution that collects Spain's fuel prices (Ministry open data), keeps the history in an S3 data lake, predicts whether prices will go up or down and emails users when a station they follow gets cheaper.

Cloud Solutions project — Carla Escassi, Marc Farràs, Laura Rigau, Marta Palet.

**Live web app:** https://main.dtmg8q0mjq0b4.amplifyapp.com/ (public map and prices; log in to follow stations)

## Architecture

```
Ministry API ──(EventBridge Scheduler, 4×/day)──► Lambda ingest ──► S3 raw/
                                                                     │ EventBridge rule (undeliverable → SQS DLQ)
                                                                     ▼
                         Step Functions smartfuel-processing: Validate → Clean → ( SaveChanges ‖ Predict )
                           invalid → quarantine/ + SNS admins        │              │            │
                                                                S3 clean/ (Parquet) DynamoDB    DynamoDB
                                                                                 latest-prices  predictions
                                                                                     │ Streams
                                                                                     ▼
                                                     Lambda check-alerts ──► SNS ──► Lambda ──► SES email
Browser ──► Amplify (static web) ──► API Gateway HTTP API (+ Cognito JWT) ──► Lambda api ──► DynamoDB
```

Everything is serverless (no EC2, RDS, NAT or VPC), defined in Terraform, with one least-privilege IAM role per Lambda / workflow.

## Where it runs: one shared AWS account

The whole project is deployed in **one AWS account shared by the team** (Free plan), in **eu-north-1 (Stockholm)**.
Each member has their own user (invited by email); nobody shares passwords.

The ESADE Innovation Sandbox lacked permissions for Cognito, Amplify, Step Functions, SNS and SES, so we deployed the same Terraform in this account without changing the architecture. The sandbox copy is kept as a backup.

Account limits to keep in mind:

- **Only eu-north-1** is allowed (an organization SCP). In any other region you get `AccessDenied ... explicit deny in a service control policy`. It is the default region of every script and stack.
- **Lambdas up to 512 MB** of memory.

GitHub only holds the code: the pipeline checks it (fmt, validate, tests) but does not deploy.

## Connect your terminal

Requirements: AWS CLI v2 (with `aws login`), Terraform ≥ 1.10, Python 3.12 with boto3 (Anaconda works).

```bash
# Once: log in with your user of the shared account (opens a link to sign in)
aws login --profile smartfuel --region eu-north-1 --remote

# In every new terminal tab (or when credentials expire)
export AWS_PROFILE=smartfuel AWS_DEFAULT_REGION=eu-north-1
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION
eval "$(aws configure export-credentials --profile smartfuel --format env)"
aws sts get-caller-identity --query Account --output text   # must print the shared account id
```

Terraform does not read `aws login` sessions yet, hence the `export-credentials` line. If it says the session expired, run `aws login` again.

Tip: wrap those lines in a `smartfuel` shell function in `~/.zshrc`.

## Deploy

```bash
git pull
./scripts/deploy.sh                    # everything, in order (core first)
./scripts/deploy.sh processing         # only one stack
./scripts/deploy.sh --plan             # compare GitHub with AWS: "No changes" = in sync
./scripts/deploy_web.sh                # publish frontend/ on Amplify (after web-api)
python scripts/seed_stations.py <file> # load stations into DynamoDB from a Ministry JSON
```

Order: `core` → `ingestion` → `processing` → `ml-alerts` → `web-api`. The first run creates the state bucket `smartfuel-tfstate-<account-id>`.

Shared resources (`core`) are used by everyone: announce in the group before deploying it, and never run `deploy.sh` without a stack name unless you mean to update everything.

Other scripts:

| Script | What it does |
|---|---|
| `scripts/test_processing.sh` | Runs the Step Functions workflow on the latest file in `raw/` |
| `scripts/backfill_clean.sh` | Builds `clean/` (Parquet history) from every `raw/` file, without touching DynamoDB |
| `scripts/destroy.sh` | Removes the stacks (careful: shared account) |

To use the ESADE sandbox instead: `export AWS_DEFAULT_REGION=us-east-1` and load the sandbox credentials.

## Repository layout

```
infra/
  core/          # shared: S3 lake (lifecycle, encryption, TLS only), DynamoDB tables, SNS topics, SQS DLQ
  ingestion/     # Phase A · EventBridge Scheduler + ingest Lambda
  processing/    # Phase B · S3 event rule, Step Functions, validate/clean/save-changes/predict Lambdas
  ml-alerts/     # Phase C · Streams -> check-alerts Lambda, weekly retraining (ECR + Lambdas)
  web-api/       # Phase D · HTTP API + Lambda, Cognito, admin routes, Amplify
scripts/         # deploy, publish, seed, test and backfill scripts (+ exploration/: first API tests)
src/lambdas/     # one folder per Lambda: handler.py + test_handler.py
frontend/        # static web app: map, log-in, follow stations, admin panel
ml/              # model v0 notebook, training and history loader
fixtures/        # small sample files for tests (raw_sample.json = 50 real stations)
docs/contracts.md
```

Each folder in `infra/` is its own Terraform stack with its own state (`<stack>/terraform.tfstate`). Phase stacks read the shared resources from `core` (`local.core.lake_bucket`, `local.core.tables.stations`, ...). Names, keys and payloads shared between phases are in `docs/contracts.md`.

## Status

| Phase | Owner | Done | Pending |
|---|---|---|---|
| A · Ingestion | Laura | Scheduler 4×/day → Lambda → S3 `raw/` | — |
| B · Processing | Carla | Step Functions with retries, catch, SNS and DLQ; Parquet in `clean/`; prices in DynamoDB; history backfilled | Real model in predict (scikit-learn) |
| C · Model & alerts | Marta | Model v0 vs baseline; check-alerts Lambda | Model in `models/production/`, emails (SNS → Lambda → SES), weekly retraining with Step Functions + Athena |
| D · Web, API & auth | Marc | Map, prices, prediction, Cognito log-in, subscriptions, admin routes, browser caching, Amplify | Cheapest stations in the area |
| Shared | — | IAM least privilege, encryption, logs | Admin emails subscribed to SNS, Athena table, CloudWatch alarms, budget alert |

## Git workflow

- One branch per task (`a/...`, `b/...`, `c/...`, `d/...`), then a Pull Request to `main`.
- The `checks` workflow (terraform fmt/validate per stack + pytest) must pass before merging.
- Run `./scripts/deploy.sh --plan <stack>` before opening the PR, and deploy after the merge.
- After a merge, everyone runs `git pull`.
- Changes in `core` or `docs/contracts.md` affect everyone: say it in the PR and in the group.
