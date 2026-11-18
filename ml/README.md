# Model (Phase C)

Notebook that builds model v0 from the history in the lake (Athena) and uploads it to `s3://smartfuel-lake-<suffix>/models/production/`. Must follow the interface in `docs/contracts.md`.

## Current Progress

The notebook `smartfuel_model_v0.ipynb` has been created and includes:

- **Data loading:** Loaded the existing dataset of 11,465 petrol stations.
- **Data exploration:** Checked missing values, duplicates, timestamps and fuel-price statistics.
- **Data preparation:** Converted the dataset into 22,145 valid fuel-price observations.
- **Baseline model:** Implemented the assumption that the next price remains unchanged (`flat`).
- **Historical data preparation:** Prepared the logic to calculate price changes (`up`, `down`, `flat`) using future observations.

## Current Limitations

The available dataset contains only one snapshot (November 4, 2026). Therefore, the baseline has been implemented but cannot yet be evaluated.

Additional historical observations are required to train and evaluate the ML model.

## ML v0 — Training and Evaluation Results

### Historical Dataset

The first ML model was trained using historical fuel-price data shared by a team member.

- 23 historical snapshots (November 12–17, 2026).
- 11,365 unique petrol stations.
- 511,065 valid fuel-price observations.
- 466,512 labeled observations after preparing future price changes.
- Two fuel types: gasolina_95_e5 and gasoleo_a.

The target variable classifies the next observed price movement as:
- `up`: Price increase.
- `down`: Price decrease.
- `flat`: No price change.

### Model Implementation

A Random Forest Classifier was trained using five features:

- `price_eur`
- `weekday`
- `hour`
- `province_mean`
- `price_vs_province`

The dataset was split chronologically to prevent future information from being used during training.

- Training observations: 310,835
- Testing observations: 133,467

### Model Performance

| Metric | Baseline (Always Flat) | Random Forest v0 |
|---|---|---|
| Accuracy | 86.06% | 73.33% |
| Balanced Accuracy | 33.33% | 45.18% |
| Macro F1 | 0.3084 | 0.4199 |

The Random Forest improves Balanced Accuracy and Macro F1 compared with the baseline, allowing it to identify some price increases and decreases.

However, the model has lower overall accuracy and still struggles to identify price increases reliably.

Performance also varies across test dates. More historical data is required before considering production deployment.

### Model Artifacts

The trained model was exported as:

- `model.joblib`: Serialized Random Forest classifier.
- `metadata.json`: Model version, features, classes, and evaluation metrics.

The artifacts were validated locally and successfully tested with the existing Phase B `predict` Lambda code.

They are stored in the AWS S3 data lake under:

`models/candidates/v0/`

**Status: Candidate model — Not approved for production.**

### Current Limitations

- Only six days of historical data are available.
- The target classes are highly imbalanced.
- Model performance is not consistent across test dates.
- AWS Lambda requires compatible scikit-learn and joblib dependencies.
- The notebook currently reads historical JSON files from a local folder.

### Next Steps

1. Make historical data loading reproducible from S3.
2. Implement automated model retraining and evaluation.
3. Add quality checks before model promotion.
4. Coordinate AWS prediction deployment with Phase B.
5. Validate the complete pipeline before production use.
