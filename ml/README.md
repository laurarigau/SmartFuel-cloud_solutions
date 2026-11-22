# Model — Phase C: Machine Learning & Price Alerts

**Owner:** Marta Palet  
**Project:** SmartFuel Forecast  
**AWS Region:** `eu-north-1`  
**Status:** Deployed and running in the team's shared AWS account

## 1. Overview

Phase C is responsible for training and evaluating the fuel-price prediction model, automating weekly retraining, and detecting price drops for subscribed users.

The implementation includes:

- A Machine Learning notebook with a baseline and Random Forest v0.
- Historical data loading from local files or AWS S3.
- Reproducible model training and evaluation.
- AWS Lambda functions for training and evaluating models.
- Prediction with the production model inside the Phase B workflow (`smartfuel-predict-ml`).
- Weekly retraining: EventBridge Scheduler starts a Step Functions workflow (train → evaluate) that reads `clean/` with Athena.
- Automatic promotion of a candidate only when it beats the baseline and the production model.
- Price alerts: DynamoDB Streams → `check-alerts` → SNS → `send-email` → SES.
- Model versioning and evaluation results stored in S3.

The first version was built in the ESADE AWS Sandbox, where Step Functions, SNS and SES were not available. The project then moved to a shared AWS account (`eu-north-1`), where the full design is deployed. This document describes the deployed version; the Sandbox tests are kept in section 9 as history.

## 2. Implementation Status

| Component | Status | Description |
|---|---|---|
| ML v0 notebook | Completed | Data exploration, baseline, Random Forest training and evaluation |
| Historical data loader | Completed | Loads historical JSON snapshots locally or from S3 |
| Training script | Completed | Trains, evaluates and exports candidate models |
| Lambda `smartfuel-train` | Deployed | Trains a model with data read through Athena and uploads it to S3 as a candidate |
| Lambda `smartfuel-evaluate` | Deployed | Compares the candidate with the baseline and the production model, and promotes it when it is better |
| Step Functions `smartfuel-ml-retraining` | Deployed | Train → Evaluate, with retries |
| EventBridge Scheduler | Enabled | Starts the retraining workflow on Mondays at 03:00 UTC |
| Lambda `smartfuel-predict-ml` | Deployed | Predictions with the production model (container image), called by the Phase B workflow |
| Lambda `smartfuel-check-alerts` | Deployed | Finds price drops that match user subscriptions and publishes the alerts to SNS |
| Lambda `smartfuel-send-email` | Deployed | Sends the alert emails with SES (verified addresses only, SES sandbox) |
| DynamoDB Streams | Enabled | Automatically triggers `check-alerts` when prices change |
| Production model promotion | Automatic | Only when the candidate's macro F1 beats the baseline and the production model |

## 3. Historical Dataset

### Initial Exploration

The original notebook used a single snapshot collected on November 4, 2026.

This dataset contained:

- 11,465 petrol stations.
- 22,145 valid fuel-price observations.

It was used for initial exploration, data cleaning and baseline preparation.

However, a single snapshot was insufficient to train and evaluate a model predicting future price changes.

### Historical Dataset Used for Training

Additional historical data was subsequently collected and used for ML v0.

| Dataset characteristic | Value |
|---|---|
| Collection period | November 12–17, 2026 |
| Historical snapshots | 23 |
| Unique petrol stations | 11,365 |
| Valid price observations | 511,065 |
| Labeled observations | 466,512 |
| Training observations | 310,835 |
| Testing observations | 133,467 |

**Fuel types:**

- `gasolina_95_e5`
- `gasoleo_a`

The target predicts the direction of the next observed price movement:

- `up`: Price increase.
- `down`: Price decrease.
- `flat`: No price change.

Training labels use subsequent observations within an eight-hour window.

A chronological train/test split is used to reduce the risk of future information leaking into training.

## 4. Machine Learning Model v0

### Baseline

The baseline assumes that the fuel price will remain unchanged (`flat`).

This is an important benchmark because most observations do not contain price changes.

### Random Forest Model

The initial ML model uses a `RandomForestClassifier` with five features:

1. `price_eur`
2. `weekday`
3. `hour`
4. `province_mean`
5. `price_vs_province`

The model predicts one of three classes: `up`, `down`, or `flat`.

### Model Performance

| Metric | Baseline (Always Flat) | Random Forest v0 |
|---|---|---|
| Accuracy | 86.06% | 73.33% |
| Balanced Accuracy | 33.33% | 45.18% |
| Macro F1 | 0.3084 | 0.4199 |

The Random Forest improves Balanced Accuracy and Macro F1 compared with the baseline.

However:

- Overall accuracy is lower than the baseline.
- Price increases remain difficult to predict.
- The dataset is highly imbalanced.
- Performance varies across testing dates.
- Only approximately six days of historical data were available.

**Conclusion:** ML v0 clearly beats the baseline and is the model in production, but it was trained on only six days of data. More historical observations will make it more reliable, and the weekly retraining replaces it only when a better candidate appears.

## 5. Model Artifacts and S3 Storage

The trained model is exported as:

- `model.joblib`: Serialized Random Forest model.
- `metadata.json`: Model version, features, classes and evaluation metrics.

The initial model was tested locally with the Phase B `predict` Lambda code.

Models are stored in Amazon S3.

**Initial candidate:**

`models/candidates/v0/`

**Candidates generated during retraining:**

`models/candidates/<timestamp>/`

Each retraining candidate contains:

- `model.joblib`
- `metadata.json`
- `evaluation.json` (after successful evaluation)

**Production model location:**

`models/production/`

This path follows the interface specified in `docs/contracts.md`.

**Archived models:**

`models/archive/<timestamp>/`

**Current status:** the production model is in `models/production/` and is used by `smartfuel-predict-ml` in the Phase B workflow. When a better candidate is promoted, the previous production model is archived in `models/archive/<timestamp>/`.

## 6. Automated Model Retraining

### Architecture

The implemented retraining workflow is:

1. EventBridge Scheduler (`smartfuel-weekly-train`) starts the Step Functions workflow `smartfuel-ml-retraining` every Monday at 03:00 UTC.
2. **Train:** `smartfuel-train` reads the last 8 days of `clean/` with Athena (Glue table `smartfuel_ml.clean_prices`, workgroup `smartfuel-ml`).
3. It prepares the training dataset, trains a new Random Forest and evaluates it against the baseline.
4. The candidate is uploaded to `models/candidates/<timestamp>/`.
5. **Evaluate:** `smartfuel-evaluate` compares the candidate's macro F1 with the baseline and the current production model.
6. If the candidate is better than both, the current model is archived in `models/archive/<timestamp>/` and the candidate is copied to `models/production/`.
7. The result is saved as `evaluation.json`, and the admins receive an email (SNS `admin-alerts`) whether the model was promoted or not.

Both steps retry up to twice on Lambda errors.

This is the design of the original project (Athena + Step Functions). In the ESADE Sandbox, a first version read the raw JSON files from S3 and the training Lambda invoked the evaluation Lambda directly; that code path still exists (`TRAINING_SOURCE=s3`) but is not used in the deployed version.

### Lambda: `smartfuel-train`

**Function name:** `smartfuel-train`

- Runtime: AWS Lambda container image.
- Architecture: ARM64.
- Docker image stored in Amazon ECR.
- Memory: 512 MB (the maximum allowed in the shared account).
- Timeout: 900 seconds.
- Temporary storage: 2,048 MB.

The Lambda uses:

- `ml/history_loader.py`
- `ml/train_model.py`
- `src/lambdas/train/handler.py`

The Docker image is defined in:

`ml/Dockerfile.train`

Its dependencies include NumPy, pandas, SciPy, scikit-learn, joblib and boto3.

The model artifacts are saved to a temporary directory before being uploaded to S3.

### Lambda: `smartfuel-evaluate`

**Function name:** `smartfuel-evaluate`

- Runtime: Python 3.11.
- Memory: 128 MB.
- Timeout: 30 seconds.

The Lambda reads the candidate's evaluation metrics and compares its Macro F1 against:

- The always-flat baseline.
- The current production model, if production metadata exists.

If the candidate is better than both and `auto_promote_model` is `true` (the default), the Lambda archives the current production model and promotes the candidate. In every case it saves `evaluation.json` and emails the admins with the result.

It does not retrain the model.

### Weekly Scheduler

**Scheduler name:** `smartfuel-weekly-train`

| Setting | Value |
|---|---|
| Service | Amazon EventBridge Scheduler |
| Frequency | Weekly |
| Day | Monday |
| Time | 03:00 UTC |
| Expression | `cron(0 3 ? * MON *)` |
| State | ENABLED |
| Target | Step Functions `smartfuel-ml-retraining` |

The schedule is defined in Terraform (`enable_weekly_scheduler`, default `true`). A CloudWatch alarm emails the team if the retraining workflow fails.

## 7. Price Alerts

### Architecture

Price alerts use the following event-driven flow:

DynamoDB `smartfuel-latest-prices` → DynamoDB Streams → Lambda `smartfuel-check-alerts` (looks up `smartfuel-subscriptions`) → SNS `smartfuel-phase-c-price-alerts` → Lambda `smartfuel-send-email` → Amazon SES

### Lambda: `smartfuel-check-alerts`

The Lambda:

1. Receives price-change events from DynamoDB Streams.
2. Processes `MODIFY` events.
3. Compares old and new fuel prices.
4. Identifies price decreases.
5. Queries the `station_fuel-index` in the subscriptions table.
6. Checks whether the new price meets each user's threshold, or whether the drop is large.
7. Publishes each alert to SNS.
8. Records aggregate alert counts in CloudWatch.

The alert condition is satisfied when `new_price < old_price` and at least one of these is true:

- `new_price <= target_price`
- the price dropped by at least 0.05 € (`LARGE_DROP_EUR`)

### End-to-End Validation

The alert workflow was first tested in the Sandbox, using a fictitious petrol station and subscription (email delivery did not exist there yet).

**Test scenario:**

- Previous fuel price: €1.60/L
- New fuel price: €1.45/L
- User threshold: €1.50/L

CloudWatch confirmed:

`price_drops=1, alerts_matched=1, delivery=disabled`

This validates the real DynamoDB Streams → Lambda → subscription lookup workflow.

The fictitious test records were subsequently deleted.

### Email Delivery

`check-alerts` publishes each alert to SNS, and `smartfuel-send-email` sends it with SES from the verified sender address. SES is still in sandbox mode, so alerts only reach verified recipients.

No user email addresses are written to the application logs.

## 8. AWS Infrastructure and Terraform

Phase C infrastructure is located in:

`infra/ml-alerts/`

**Main files:**

| File | Purpose |
|---|---|
| `main.tf` | Alert Lambda, IAM permissions and DynamoDB Streams trigger |
| `alert-delivery.tf` | SNS price-alerts topic and `send-email` Lambda (SES) |
| `retraining.tf` | ECR, training/evaluation Lambdas, IAM and weekly Scheduler |
| `retraining-sfn.tf` | Step Functions retraining workflow |
| `athena.tf` | Glue database and table over `clean/`, Athena workgroup |
| `predict-image.tf` | ECR repository for the prediction image |
| `predict-runtime.tf` | `smartfuel-predict-ml` Lambda used by Phase B |
| `predict-smoke.tf` | Small test Lambda for the prediction image |
| `core.tf` | Access to the shared core Terraform outputs |
| `providers.tf` | Provider configuration |
| `variables.tf` | Terraform variables |

### Important Deployment Variables

**Phase C is switched on by default in Terraform**, exactly as deployed in the shared account:

- `ml-alerts`: `enable_predict_runtime`, `enable_alert_publish`, `enable_alert_delivery`, `enable_ml_retraining` and `enable_weekly_scheduler` default to `true`; `alert_sender_email` defaults to the verified SES sender.
- `retraining_lake_bucket` defaults to empty, which means the lake bucket of `core`.
- `processing`: `use_ml_predict = true` makes the Step Functions workflow call `smartfuel-predict-ml`.

So the normal script keeps everything running:

```bash
./scripts/deploy.sh --plan ml-alerts processing   # must show nothing to destroy
./scripts/deploy.sh ml-alerts processing
```

Set a variable to `false` (for example `TF_VAR_enable_weekly_scheduler=false`) only to switch that part off.

`auto_promote_model` (default `true`): when the weekly candidate beats the baseline and the production model, the evaluate Lambda archives the current model in `models/archive/<time>/`, copies the candidate to `models/production/` and emails the admins (SNS `admin-alerts`). If it is not better, production does not change and the admins get the reasons.

Always review `terraform plan` before applying changes.

The Terraform state bucket and the application resources are both in `eu-north-1` (the only region allowed in the shared account).

Do not change the backend configuration or state keys without coordinating with the team.

### Docker and ECR

The training Lambda uses a Docker image because it requires compiled Machine Learning dependencies.

To rebuild the training image from the repository root:

```bash
docker buildx build \
  --platform linux/arm64 \
  --provenance=false \
  --load \
  -f ml/Dockerfile.train \
  -t smartfuel-train:v1 .
```

Before deploying in another AWS account, the image must be uploaded to an ECR repository accessible to that account's Lambda.

When publishing an updated image, use a new image tag or digest and update the corresponding Terraform configuration. Reusing the same ECR tag does not automatically update an existing Lambda deployment.

All Phase C resources, ECR images and S3 data live in the team's shared AWS account (`eu-north-1`).

## 9. Testing and Validation

### Local Tests

The repository test suite passes (`python -m pytest -q`):

**69 tests passed**

The Terraform configuration was also validated successfully.

Validation included:

- Loading historical data locally and from AWS S3.
- Reproducing the notebook's training results using `train_model.py`.
- Testing the Lambda handler logic.
- Building the ARM64 Docker image.
- Checking Python imports inside the container.
- Validating Terraform syntax and configuration.

### AWS Tests (first version, in the ESADE Sandbox)

**Training**

`smartfuel-train` successfully:

- Loaded historical snapshots from S3.
- Trained a Random Forest model.
- Uploaded a new candidate to S3.
- Requested evaluation by `smartfuel-evaluate`.

**Evaluation**

`smartfuel-evaluate` was invoked successfully.

Example AWS evaluation results:

| Metric | Value |
|---|---|
| Candidate Macro F1 | 0.4202 |
| Baseline Macro F1 | 0.3084 |
| Evaluation status | `eligible_for_manual_review` |
| Production promoted | `false` |

The evaluation results are saved to S3 as `evaluation.json`.

**Alerts**

DynamoDB Streams successfully triggered `smartfuel-check-alerts` after a real DynamoDB price update.

The Lambda detected one price decrease and one matching subscription.

**Scheduler**

EventBridge Scheduler was confirmed as `ENABLED`.

A scheduled execution has not yet been independently observed.

## 10. Current Limitations

### AWS Account

The ESADE Sandbox did not permit Step Functions, SNS, SQS or SES, so Phase C moved, with the rest of the project, to a shared AWS account where all of them are deployed. That account only allows `eu-north-1` and Lambdas of up to 512 MB, and SES is in sandbox mode (verified recipients only).

### Machine Learning Limitations

- Only six days of historical data were available for the initial model.
- Most fuel-price observations remain unchanged.
- The model struggles to detect some price movements, especially increases.
- Performance is not stable across testing dates.
- Evaluation relies on the metrics calculated during training.

### Integration Limitations

- `smartfuel-predict-ml` and the training code must keep the same feature schema and library versions: a change in one needs the other.

## 11. Next Steps and Team Handover

**1. Model improvements**

As more historical snapshots become available, retrain the model and reassess performance against the baseline and production model. Add features such as oil prices, holidays and nearby stations.

**2. Email delivery for every user**

Request SES production access and send the alerts from our own domain.

**3. Weekly retraining monitoring**

Keep an eye on the admin emails and the CloudWatch alarm for failed retraining workflows.

**4. Terraform maintenance**

Keep the Phase C variables at their defaults (`true`) when maintaining the deployed environment.

## 12. Main Code Locations

| File | Description |
|---|---|
| `ml/smartfuel_model_v0.ipynb` | ML exploration, baseline and Random Forest v0 |
| `ml/history_loader.py` | Historical data loading from local files and S3 |
| `ml/train_model.py` | Training, evaluation and S3 candidate upload |
| `ml/Dockerfile.train` | Training Lambda container image |
| `ml/Dockerfile.predict` | Prediction Lambda container image |
| `src/lambdas/predict/handler.py` | Prediction handler (used by the `smartfuel-predict-ml` image) |
| `src/lambdas/train/handler.py` | Training Lambda handler |
| `src/lambdas/train/test_handler.py` | Training Lambda tests |
| `src/lambdas/evaluate/handler.py` | Evaluation Lambda handler |
| `src/lambdas/evaluate/test_handler.py` | Evaluation Lambda tests |
| `src/lambdas/check-alerts/handler.py` | Price-drop detection |
| `src/lambdas/send-email/handler.py` | Alert email delivery (SES) |
| `infra/ml-alerts/main.tf` | Alert Lambda infrastructure |
| `infra/ml-alerts/alert-delivery.tf` | SNS topic and email Lambda |
| `infra/ml-alerts/retraining.tf` | Retraining and Scheduler infrastructure |
| `infra/ml-alerts/retraining-sfn.tf` | Retraining workflow (Step Functions) |
| `infra/ml-alerts/athena.tf` | Glue table and Athena workgroup |
| `infra/ml-alerts/predict-runtime.tf` | Prediction Lambda used by Phase B |
| `docs/contracts.md` | Shared data and model interfaces |

---

## Final Phase C Summary

Phase C is deployed and running in the team's shared AWS account.

**Completed:**
- ML v0 training and evaluation against an always-flat baseline.
- Predictions with the production model in the Phase B workflow (`smartfuel-predict-ml`).
- Weekly retraining with Step Functions and Athena, with automatic promotion only when the candidate is better.
- Price alerts by email: DynamoDB Streams → `check-alerts` → SNS → `send-email` → SES.
- Local tests, Terraform validation and AWS integration tests.

**Remaining:**
- SES production access, so alerts can reach any user.
- More historical data to improve the model.
