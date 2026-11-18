
"""Phase C — Weekly ML training Lambda."""

import json
import os


def lambda_handler(event, context):
    from train_model import train_model

    bucket = os.environ["LAKE_BUCKET"]

    # AWS Lambda can write temporary files in /tmp.
    os.environ["MODEL_OUTPUT_DIR"] = "/tmp/smartfuel-model"

    result = train_model(
        s3_bucket=bucket,
        s3_prefix="raw/",
        upload_s3_bucket=bucket
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            "train_model must return the candidate information."
        )

    candidate_prefix = result["candidate_prefix"]

    # Step Functions is blocked in the sandbox.
    # Invoke evaluation directly if configured.
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
