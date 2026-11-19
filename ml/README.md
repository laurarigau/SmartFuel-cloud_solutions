# Model — Phase C: Machine Learning & Price Alerts

**Owner:** Marta Palet  
**Project:** SmartFuel Forecast  
**AWS Region:** `eu-north-1`  
**Status:** Implemented and tested in the Phase C AWS Sandbox

## 1. Overview

Phase C is responsible for training and evaluating the fuel-price prediction model, automating weekly retraining, and detecting price drops for subscribed users.

The implementation includes:

- A Machine Learning notebook with a baseline and Random Forest v0.
- Historical data loading from local files or AWS S3.
- Reproducible model training and evaluation.
- AWS Lambda functions for training and evaluating models.
- Weekly retraining using EventBridge Scheduler.
- Price-drop detection using DynamoDB Streams and a Lambda function.
- Model versioning and evaluation results stored in S3.

**Important:** Step Functions and email delivery remain unavailable due to the ESADE AWS Sandbox restrictions.

## 2. Implementation Status

| Component | Status | Description |
|---|---|---|
| ML v0 notebook | Completed | Data exploration, baseline, Random Forest training and evaluation |
| Historical data loader | Completed | Loads historical JSON snapshots locally or from S3 |
| Training script | Completed | Trains, evaluates and exports candidate models |
| Lambda `smartfuel-train` | Deployed & tested | Trains a model and uploads its artifacts to S3 |
| Lambda `smartfuel-evaluate` | Deployed & tested | Compares candidate metrics against the baseline and production model, when available |
| EventBridge Scheduler | Enabled | Weekly retraining on Mondays at 03:00 UTC |
| Lambda `smartfuel-check-alerts` | Deployed & tested | Identifies price drops matching user subscriptions |
| DynamoDB Streams | Enabled | Automatically triggers `check-alerts` when prices change |
| Production model promotion | Pending approval | Candidates are evaluated but not promoted automatically |
| Step Functions | Blocked | Original orchestration unavailable in the Sandbox |
| Email notifications | Blocked | SNS and SES unavailable in the Sandbox |

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

**Conclusion:** ML v0 is a working prototype, but further validation and additional historical observations are required before production deployment.

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

**Current status:** No model has been approved for production. The trained models remain candidates, and the production path has not been populated through the Phase C deployment.

## 6. Automated Model Retraining

### Architecture

The implemented retraining workflow is:

1. EventBridge Scheduler triggers `smartfuel-train` weekly.
2. The training Lambda loads historical snapshots from S3 `raw/`.
3. It prepares the training dataset and trains a new Random Forest.
4. The model is evaluated against the baseline.
5. A new candidate is uploaded to S3.
6. The training Lambda asynchronously invokes `smartfuel-evaluate`.
7. The evaluation Lambda compares the candidate with the baseline and current production metadata, if available.
8. The results are saved as `evaluation.json`.

**No automatic promotion to production is performed.**

The original project proposed Athena and Step Functions for retraining orchestration. The current Sandbox implementation reads historical JSON files directly from S3 and uses a direct Lambda-to-Lambda invocation because Step Functions is unavailable.

### Lambda: `smartfuel-train`

**Function name:** `smartfuel-train`

- Runtime: AWS Lambda container image.
- Architecture: ARM64.
- Docker image stored in Amazon ECR.
- Memory: 2,048 MB.
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

The evaluation result indicates whether the candidate is eligible for manual review.

It does not independently retrain the model or automatically promote it to production.

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
| Target | `smartfuel-train` |

The Scheduler was confirmed as `ENABLED` in the Phase C Sandbox.

Manual training and evaluation executions were tested successfully. The first execution triggered by the weekly schedule has not yet been independently verified.

## 7. Price Alerts

### Architecture

Price alerts use the following event-driven flow:

DynamoDB `smartfuel-latest-prices` → DynamoDB Streams → Lambda `smartfuel-check-alerts` → DynamoDB `smartfuel-subscriptions`

### Lambda: `smartfuel-check-alerts`

The Lambda:

1. Receives price-change events from DynamoDB Streams.
2. Processes `MODIFY` events.
3. Compares old and new fuel prices.
4. Identifies price decreases.
5. Queries the `station_fuel-index` in the subscriptions table.
6. Checks whether the new price meets each user's threshold.
7. Records aggregate alert counts in CloudWatch.

The alert condition is satisfied when:

- `new_price < old_price`
- `new_price <= target_price`

### End-to-End Validation

The alert workflow was tested using a fictitious petrol station and subscription.

**Test scenario:**

- Previous fuel price: €1.60/L
- New fuel price: €1.45/L
- User threshold: €1.50/L

CloudWatch confirmed:

`price_drops=1, alerts_matched=1, delivery=disabled`

This validates the real DynamoDB Streams → Lambda → subscription lookup workflow.

The fictitious test records were subsequently deleted.

### Email Delivery

Email delivery remains disabled because SNS and SES are unavailable in the ESADE Sandbox.

The Lambda identifies matching subscriptions but does not send notifications.

No user email addresses are written to the application logs.

## 8. AWS Infrastructure and Terraform

Phase C infrastructure is located in:

`infra/ml-alerts/`

**Main files:**

| File | Purpose |
|---|---|
| `main.tf` | Alert Lambda, IAM permissions and DynamoDB Streams trigger |
| `retraining.tf` | ECR, training/evaluation Lambdas, IAM and weekly Scheduler |
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

Each team member uses a separate AWS Sandbox. Resources, ECR images and S3 data are not automatically shared between accounts.

## 9. Testing and Validation

### Local Tests

The repository test suite passed:

**44 tests passed**

The Terraform configuration was also validated successfully.

Validation included:

- Loading historical data locally and from AWS S3.
- Reproducing the notebook's training results using `train_model.py`.
- Testing the Lambda handler logic.
- Building the ARM64 Docker image.
- Checking Python imports inside the container.
- Validating Terraform syntax and configuration.

### AWS Tests

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

### AWS Sandbox Restrictions

The ESADE Sandbox does not permit:

- Step Functions.
- SNS.
- SQS.
- SES.

As a result:

- The original Step Functions retraining workflow is not deployed.
- The implementation uses direct invocation between the training and evaluation Lambdas.
- Email alerts cannot be delivered.
- SNS-based administrative notifications and SQS-based dead-letter queues are unavailable.

These components require further coordination with the professor.

### Machine Learning Limitations

- Only six days of historical data were available for the initial model.
- Most fuel-price observations remain unchanged.
- The model struggles to detect some price movements, especially increases.
- Performance is not stable across testing dates.
- The current model is not approved for production.
- Evaluation currently relies on previously calculated metrics.
- The initial training process reads raw JSON snapshots from S3 rather than using Athena.

### Integration Limitations

- The Phase B `predict` Lambda must be compatible with the model dependencies and feature schema.
- Until a production model is published, Phase B may continue using its fallback prediction logic.
- The first automatic weekly execution still needs to be monitored.
- The AWS deployment configuration is specific to the Phase C Sandbox.

## 11. Next Steps and Team Handover

**1. Production model approval**

Agree on minimum quality requirements and validate the model using additional historical data before moving an approved candidate to `models/production/`.

**2. Phase B integration**

Coordinate with Carla to ensure the prediction Lambda can load the production model and calculate the expected features.

**3. Weekly retraining monitoring**

After the first scheduled execution, verify that:

- `smartfuel-train` runs successfully.
- A new model candidate appears in S3.
- `smartfuel-evaluate` executes successfully.
- `evaluation.json` is generated.
- No errors appear in CloudWatch.

**4. Sandbox restrictions**

Wait for the professor's guidance before implementing the blocked Step Functions and SNS/SES workflows.

**5. Terraform maintenance**

Keep the required deployment variables set to `true` when maintaining the deployed Phase C environment.

**6. Model improvements**

As more historical snapshots become available, retrain the model and reassess performance against the baseline and production model.

## 12. Main Code Locations

| File | Description |
|---|---|
| `ml/smartfuel_model_v0.ipynb` | ML exploration, baseline and Random Forest v0 |
| `ml/history_loader.py` | Historical data loading from local files and S3 |
| `ml/train_model.py` | Training, evaluation and S3 candidate upload |
| `ml/Dockerfile.train` | Training Lambda container image |
| `src/lambdas/train/handler.py` | Training Lambda handler |
| `src/lambdas/train/test_handler.py` | Training Lambda tests |
| `src/lambdas/evaluate/handler.py` | Evaluation Lambda handler |
| `src/lambdas/evaluate/test_handler.py` | Evaluation Lambda tests |
| `src/lambdas/check-alerts/handler.py` | Price-drop detection |
| `infra/ml-alerts/main.tf` | Alert Lambda infrastructure |
| `infra/ml-alerts/retraining.tf` | Retraining and Scheduler infrastructure |
| `docs/contracts.md` | Shared data and model interfaces |

---

## Final Phase C Summary

Phase C has implemented and validated the main Machine Learning and price-alert components in the ESADE AWS Sandbox.

**Completed:**
- ML v0 training and evaluation.
- Historical data loading from S3.
- Automated creation and evaluation of model candidates.
- AWS Lambda training and evaluation deployment.
- Enabled weekly retraining Scheduler.
- Event-driven price-drop detection using DynamoDB Streams.
- Local tests, Terraform validation and AWS integration tests.

**Remaining dependencies:**
- Production model approval and final Phase B integration.
- Monitoring the first scheduled weekly execution.
- Step Functions and email delivery, currently blocked by the AWS Sandbox.

The deployed system is functional for model training, candidate evaluation and alert detection. Production prediction integration and email delivery remain pending.