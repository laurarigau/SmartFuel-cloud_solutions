# SmartFuel Forecast

Serverless, event-driven AWS solution that collects Spain's fuel prices (Ministry open data), keeps the history in an S3 data lake, predicts whether prices will go up or down and emails users when a station they follow gets cheaper.

Cloud Solutions project — Carla Escassi, Marc Farràs, Laura Rigau, Marta Palet.

**Live web app:** https://main.dtmg8q0mjq0b4.amplifyapp.com/ (public map and prices; log in to follow stations)

## What it does

- **Map** of the ~11,500 petrol stations in Spain with their current prices, updated 4 times a day.
- **Cheapest stations in the area** you are looking at, for the fuel you choose.
- **Forecast** for each station and fuel: the price will go up, go down or stay the same (ML model compared with a baseline).
- **Price alerts:** log in, follow a station with a target price and get an email when it drops.
- **Admin panel** (Cognito group `admins`): pipeline health and quarantined files.
- **Monitoring:** CloudWatch alarms email the team when something fails, and a dashboard shows the whole pipeline.
- Web in **Spanish and English**.

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
Browser ──► Amplify (static web, ES/EN) ──► API Gateway HTTP API (+ Cognito JWT) ──► Lambda api ──► DynamoDB

Weekly: EventBridge Scheduler ──► Step Functions smartfuel-ml-retraining: Train (Athena over clean/) → Evaluate
          better than the baseline and the current model → models/production/ (old one archived) + email to admins
          not better → the current model stays + email to admins with the reasons

Monitoring: CloudWatch logs + alarms (Lambda errors, failed workflows, stopped ingestion, DLQ, API 5xx) ──► SNS smartfuel-alarms ──► team email
            CloudWatch dashboard "smartfuel" with the health of the whole pipeline
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

Order: `core` → `ingestion` → `processing` → `ml-alerts` → `web-api` → `monitoring`. The first run creates the state bucket `smartfuel-tfstate-<account-id>`.

> **Phase C switches.** The real-model predict, the email delivery and the weekly retraining (`enable_*` variables in `ml-alerts`, `use_ml_predict` in `processing`) are **on by default**, exactly as deployed. A plain `deploy.sh` keeps them running; set a variable to `false` only to switch that part off. Always run `--plan` first: it must not show anything to destroy.

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
  ml-alerts/     # Phase C · Streams -> check-alerts -> SNS -> send-email (SES); predict with the real model
                 #           (container image in ECR); weekly retraining (Step Functions + Athena/Glue)
  web-api/       # Phase D · HTTP API + Lambda, Cognito, admin routes, Amplify
  monitoring/    # shared · CloudWatch alarms emailed to the team (own SNS topic + KMS key) and dashboard
scripts/         # deploy, publish, seed, test and backfill scripts (+ exploration/: first API tests)
src/lambdas/     # one folder per Lambda: handler.py + test_handler.py
frontend/        # static web app: map, cheapest stations in the area, log-in, follow stations, admin panel, ES/EN
ml/              # model notebook, training, history loader (Athena) and Dockerfiles for the ML Lambdas
fixtures/        # small sample files for tests (raw_sample.json = 50 real stations)
docs/contracts.md
```

Each folder in `infra/` is its own Terraform stack with its own state (`<stack>/terraform.tfstate`). Phase stacks read the shared resources from `core` (`local.core.lake_bucket`, `local.core.tables.stations`, ...). Names, keys and payloads shared between phases are in `docs/contracts.md`.

## Final status

The whole pipeline runs on its own in the shared account: ingestion 4 times a day → Step Functions processing → prices and predictions in DynamoDB → web, API and email alerts; the model is retrained every week.

| Phase | Owner | Done | Pending |
|---|---|---|---|
| A · Ingestion | Laura | Scheduler 4×/day → Lambda → S3 `raw/` | — |
| B · Processing | Carla | Step Functions with retries, catch, SNS and DLQ; Parquet in `clean/`; prices in DynamoDB; history backfilled; predict uses the Phase C model | — |
| C · Model & alerts | Marta | Model vs baseline in `models/production/`, used by predict; price alerts check-alerts → SNS → send-email → SES; weekly retraining with Step Functions + Athena (Glue table), automatic promotion of a better model and email to admins | SES production access (see *Limitations*) |
| D · Web, API & auth | Marc | Map, prices, prediction, cheapest stations in the area, Cognito log-in, subscriptions, admin routes, browser caching, Spanish/English, Amplify | — |
| Shared | — | IAM least privilege, encryption at rest and in transit, CloudWatch logs, alarms (Lambda errors, failed workflows, stopped ingestion, DLQ, API 5xx) and dashboard, admin emails subscribed to SNS | Budget alert (see *Limitations*) |

## Limitations and next steps

| Limitation | Why | Next step |
|---|---|---|
| No budget alert | The AWS Free plan cannot charge us: when the credits run out, AWS closes the account | AWS Budgets alert in Terraform for a paid account |
| Price alerts only reach verified emails | Amazon SES starts in sandbox mode in new accounts (`aws ses verify-email-identity --email-address <email>`) | Request SES production access and send from our own domain |
| Shared account limits | Only eu-north-1 is allowed and Lambdas have 512 MB at most; the ESADE sandbox lacked permissions for Cognito, Amplify, Step Functions, SNS and SES | Same Terraform in a production account, without changing the architecture |
| No server-side API cache | HTTP APIs have no cache; a REST API cache costs ~14 $/month | Browser caching (`Cache-Control`) is in place; add a REST API or CloudFront cache if traffic grows |

**Future features:** cheapest station on your route, price history charts, a mobile app with push notifications, and CI/CD that deploys from GitHub after each merge (GitOps).

## Git workflow

- One branch per task (`a/...`, `b/...`, `c/...`, `d/...`), then a Pull Request to `main`.
- The `checks` workflow (terraform fmt/validate per stack + pytest) must pass before merging.
- Run `./scripts/deploy.sh --plan <stack>` before opening the PR, and deploy after the merge.
- After a merge, everyone runs `git pull`.
- Changes in `core` or `docs/contracts.md` affect everyone: say it in the PR and in the group.
