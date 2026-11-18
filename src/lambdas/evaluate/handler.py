
"""Phase C — Evaluate a new ML model candidate."""

import json
import os
from datetime import datetime, timezone


def get_metric(metadata, name):
    if not metadata:
        return None

    metrics = metadata.get("metrics", metadata)
    value = metrics.get(name)

    return float(value) if value is not None else None


def evaluate(candidate, production=None):
    candidate_f1 = get_metric(candidate, "macro_f1")
    baseline_f1 = get_metric(
        candidate, "baseline_macro_f1"
    )
    production_f1 = get_metric(
        production, "macro_f1"
    )

    reasons = []

    if candidate_f1 is None or baseline_f1 is None:
        reasons.append("missing_metrics")
    elif candidate_f1 <= baseline_f1:
        reasons.append("below_baseline")

    if production is not None:
        if production_f1 is None:
            reasons.append("missing_production_metric")
        elif (
            candidate_f1 is not None
            and candidate_f1 <= production_f1
        ):
            reasons.append("below_production")

    return {
        "status": (
            "eligible_for_manual_review"
            if not reasons else "not_eligible"
        ),
        "candidate_macro_f1": candidate_f1,
        "baseline_macro_f1": baseline_f1,
        "production_macro_f1": production_f1,
        "reasons": reasons,
        "production_promoted": False
    }


def lambda_handler(event, context):
    import boto3
    from botocore.exceptions import ClientError

    bucket = os.environ["LAKE_BUCKET"]
    prefix = event["candidate_prefix"]

    if not (
        prefix.startswith("models/candidates/")
        and prefix.endswith("/")
    ):
        raise ValueError("Invalid candidate prefix")

    s3 = boto3.client("s3")

    candidate = json.loads(
        s3.get_object(
            Bucket=bucket,
            Key=prefix + "metadata.json"
        )["Body"].read()
    )

    production = None

    try:
        production = json.loads(
            s3.get_object(
                Bucket=bucket,
                Key="models/production/metadata.json"
            )["Body"].read()
        )
    except ClientError as exc:
        error = exc.response["Error"]["Code"]

        if error not in ("NoSuchKey", "404", "NotFound"):
            raise

    result = evaluate(candidate, production)

    result["evaluated_at"] = (
        datetime.now(timezone.utc).isoformat()
    )
    result["candidate_prefix"] = prefix

    s3.put_object(
        Bucket=bucket,
        Key=prefix + "evaluation.json",
        Body=json.dumps(result, indent=2).encode(),
        ContentType="application/json"
    )

    print("Evaluation status:", result["status"])

    return result
