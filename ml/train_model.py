
"""Train and evaluate SmartFuel ML model v0."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
)

from history_loader import load_history, load_history_from_s3


FEATURES = [
    "price_eur",
    "weekday",
    "hour",
    "province_mean",
    "price_vs_province",
]

def train_model(input_folder=None, s3_bucket=None, s3_prefix="raw/", upload_s3_bucket=None):
    # 1. Load historical data
    if s3_bucket:
        print("Loading historical data from AWS S3...")
        history = load_history_from_s3(
            bucket=s3_bucket,
            prefix=s3_prefix
        )
    else:
        print("Loading historical data locally...")
        history = load_history(input_folder)

    # 2. Calculate features from current snapshots
    history["weekday"] = history["ts"].dt.weekday
    history["hour"] = history["ts"].dt.hour

    history["province_mean"] = (
        history.groupby(
            ["ts", "province", "fuel_type"]
        )["price_eur"].transform("mean")
    )

    history["price_vs_province"] = (
        history["price_eur"] - history["province_mean"]
    )

    # 3. Create future price labels
    history = history.sort_values(
        ["station_id", "fuel_type", "ts"]
    )

    group = history.groupby(["station_id", "fuel_type"])

    history["next_price_eur"] = (
        group["price_eur"].shift(-1)
    )

    history["next_ts"] = group["ts"].shift(-1)

    labeled = history.dropna(
        subset=["next_price_eur", "next_ts"]
    ).copy()

    labeled["hours_to_next"] = (
        (labeled["next_ts"] - labeled["ts"])
        .dt.total_seconds() / 3600
    )

    labeled = labeled[
        (labeled["hours_to_next"] > 0) &
        (labeled["hours_to_next"] <= 8)
    ].copy()

    change = (
        labeled["next_price_eur"] -
        labeled["price_eur"]
    ).round(3)

    labeled["direction"] = np.select(
        [change > 0, change < 0],
        ["up", "down"],
        default="flat"
    )

    # 4. Chronological split
    # Reserve the final two calendar days for testing
    split_date = (
        history["ts"].max().normalize()
        - pd.Timedelta(days=1)
    )

    train = labeled[
        labeled["next_ts"] < split_date
    ].copy()

    test = labeled[
        labeled["ts"] >= split_date
    ].copy()

    if train.empty or test.empty:
        raise ValueError(
            "Not enough historical data for training/testing."
        )

    X_train = train[FEATURES]
    y_train = train["direction"]

    X_test = test[FEATURES]
    y_test = test["direction"]

    if X_train.isna().any().any() or X_test.isna().any().any():
        raise ValueError("Missing values in model features.")

    # 5. Train Random Forest
    model = RandomForestClassifier(
        n_estimators=80,
        max_depth=12,
        min_samples_leaf=30,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    # 6. Evaluate model and baseline
    predictions = model.predict(X_test)
    baseline = np.full(len(y_test), "flat")

    metrics = {
        "accuracy": float(
            accuracy_score(y_test, predictions)
        ),
        "balanced_accuracy": float(
            balanced_accuracy_score(y_test, predictions)
        ),
        "macro_f1": float(
            f1_score(y_test, predictions, average="macro")
        ),
        "baseline_accuracy": float(
            accuracy_score(y_test, baseline)
        ),
        "baseline_macro_f1": float(
            f1_score(y_test, baseline, average="macro")
        )
    }

    # 7. Export as candidate, not production
    output_dir = (
        Path(__file__).resolve().parent /
        "models/candidates/v0-script"
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, output_dir / "model.joblib")

    metadata = {
        "version": "v0-random-forest-script",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES,
        "classes": list(model.classes_),
        "training_observations": len(train),
        "testing_observations": len(test),
        "split_date": str(split_date.date()),
        "metrics": metrics,
        "status": "candidate",
        "production_approved": False
    }

    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # 8. Show results
    print("\nTraining completed!")
    print("Training observations:", len(train))
    print("Testing observations:", len(test))
    print("\nModel metrics:")

    for key, value in metrics.items():
        print(f"{key}: {value:.4f}")

    print("\nCandidate saved to:", output_dir)


    # 9. Optionally upload candidate to AWS S3
    if upload_s3_bucket:
        import boto3
        from uuid import uuid4

        s3 = boto3.client("s3", region_name="us-east-1")

        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid4().hex[:8]
        )

        prefix = f"models/candidates/{run_id}/"

        for filename in ["model.joblib", "metadata.json"]:
            s3.upload_file(
                str(output_dir / filename),
                upload_s3_bucket,
                prefix + filename
            )

        print(
            "Candidate uploaded to:",
            f"s3://{upload_s3_bucket}/{prefix}"
        )



if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--s3-bucket")

    parser.add_argument("--s3-prefix", default="raw/")
    parser.add_argument("--upload-s3-bucket")
    args = parser.parse_args()

    train_model(
    input_folder=args.input,
    s3_bucket=args.s3_bucket,
    s3_prefix=args.s3_prefix,
    upload_s3_bucket=args.upload_s3_bucket
)
