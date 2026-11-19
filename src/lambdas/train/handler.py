
"""Phase C — Weekly ML training Lambda."""

import json
import os


def lambda_handler(event, context):
    from train_model import train_model

    bucket = os.environ["LAKE_BUCKET"]

    # AWS Lambda can write temporary files in /tmp.
    os.environ["MODEL_OUTPUT_DIR"] = "/tmp/smartfuel-model"

    source = os.environ.get("TRAINING_SOURCE", "s3")

    if source == "athena":
        result = train_model(
            athena_database=os.environ.get(
                "ATHENA_DATABASE", "smartfuel_ml"
            ),
            athena_table=os.environ.get(
                "ATHENA_TABLE", "clean_prices"
            ),
            athena_workgroup=os.environ.get(
                "ATHENA_WORKGROUP", "smartfuel-ml"
            ),
            athena_lookback_days=int(
                os.environ.get("ATHENA_LOOKBACK_DAYS", "14")
            ),
            athena_station_sample_modulus=int(
                os.environ.get("ATHENA_STATION_SAMPLE_MODULUS", "1")
            ),
            upload_s3_bucket=bucket,
        )
    elif source == "s3":
        result = train_model(
            s3_bucket=bucket,
            s3_prefix="raw/",
            upload_s3_bucket=bucket,
        )
    else:
        raise ValueError(f"Unsupported training source: {source}")

    if not isinstance(result, dict):
        raise RuntimeError(
            "train_model must return the candidate information."
        )

    candidate_prefix = result["candidate_prefix"]

    # Step Functions performs evaluation in the shared account.
    # Legacy direct invocation remains optional.
    evaluator = os.environ.get("EVALUATE_FUNCTION_NAME")

    if evaluator:
        import boto3

        boto3.client("lambda").invoke(
            FunctionName=evaluator,
            InvocationType="Event",
            Payload=json.dumps({
                "candidate_prefix": candidate_prefix
            }).encode()
        )

    return {
        "candidate_prefix": candidate_prefix,
        "evaluation_requested": bool(evaluator)
    }
