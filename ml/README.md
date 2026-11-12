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

## Next Steps

1. Load historical data from S3/Athena.
2. Train and evaluate model v0 against the baseline.
3. Export `model.joblib` and `metadata.json`.
4. Upload the validated model to S3 under `models/production/`.
5. Integrate the model with the existing prediction Lambda.

## Status

**In progress.** Data preparation and baseline implementation completed. Model training, evaluation and deployment pending.
