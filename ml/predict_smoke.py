
"""Read-only AWS Lambda smoke test for the Phase C candidate model."""

import io
import boto3
import pandas as pd

import handler as predict


def lambda_handler(event, context):
    bucket = event["bucket"]
    prefix = event["candidate_prefix"]
    clean_key = event["clean_key"]

    if not prefix.startswith("models/candidates/"):
        raise ValueError("Only candidate models are allowed.")

    if not clean_key.startswith("clean/") or not clean_key.endswith(".parquet"):
        raise ValueError("Expected a clean Parquet snapshot.")

    s3 = boto3.client("s3")

    body = s3.get_object(
        Bucket=bucket,
        Key=clean_key,
    )["Body"].read()

    snapshot = pd.read_parquet(io.BytesIO(body))

    features = predict.build_features(snapshot)

    predict_fn, version = predict.load_model(bucket, prefix)

    if version == "stub":
        raise RuntimeError("Candidate model was not loaded.")

    predictions = predict_fn(features.head(5))

    return {
        "status": "passed",
        "model_version": version,
        "snapshot_rows": len(snapshot),
        "sample_predictions": predictions,
        "dynamodb_writes": 0,
    }
