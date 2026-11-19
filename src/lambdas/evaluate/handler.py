
"""Phase C — Evaluate a new ML model candidate and promote it if it is better.

Draft: "If the new model is better than the current one, it is put into
production. If not, the old model stays and the admins are notified."

    better than the baseline AND than the production model
        -> copy the current production model to models/archive/<time>/
        -> copy the candidate (model.joblib + metadata.json) to models/production/
        -> email the admins (SNS) that a new model is live
    otherwise
        -> production does not change, admins get the reasons by email

Env: LAKE_BUCKET, ADMIN_TOPIC_ARN (optional), AUTO_PROMOTE ("true" by default)
"""

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
        "status": "eligible" if not reasons else "not_eligible",
        "candidate_macro_f1": candidate_f1,
        "baseline_macro_f1": baseline_f1,
        "production_macro_f1": production_f1,
        "reasons": reasons,
        "production_promoted": False
    }


MODEL_FILES = ["model.joblib", "metadata.json"]
PRODUCTION_PREFIX = "models/production/"


def promote(s3, bucket, candidate_prefix, has_production, now):
    """Archive the current production model, then copy the candidate over it."""
    archived_to = None
    if has_production:
        archived_to = f"models/archive/{now:%Y%m%dT%H%M%SZ}/"
        for name in MODEL_FILES:
            s3.copy_object(
                Bucket=bucket,
                Key=archived_to + name,
                CopySource={"Bucket": bucket, "Key": PRODUCTION_PREFIX + name},
            )
    # metadata.json last, so predict never sees new metadata with the old model
    for name in MODEL_FILES:
        s3.copy_object(
            Bucket=bucket,
            Key=PRODUCTION_PREFIX + name,
            CopySource={"Bucket": bucket, "Key": candidate_prefix + name},
        )
    return archived_to


def notify_admins(result):
    topic = os.environ.get("ADMIN_TOPIC_ARN")
    if not topic:
        return False

    if result["production_promoted"]:
        subject = "SmartFuel: new ML model in production"
        body = (
            "The weekly retraining produced a better model and it is now in production.\n\n"
            f"Candidate: {result['candidate_prefix']}\n"
            f"Macro F1 candidate: {result['candidate_macro_f1']}\n"
            f"Macro F1 baseline: {result['baseline_macro_f1']}\n"
            f"Macro F1 previous model: {result['production_macro_f1']}\n"
            f"Previous model archived in: {result.get('archived_to') or '-'}\n"
        )
    else:
        subject = "SmartFuel: new ML model not promoted"
        body = (
            "The weekly retraining finished, but the new model is not better, "
            "so the current model stays in production.\n\n"
            f"Candidate: {result['candidate_prefix']}\n"
            f"Reasons: {', '.join(result['reasons']) or '-'}\n"
            f"Macro F1 candidate: {result['candidate_macro_f1']}\n"
            f"Macro F1 baseline: {result['baseline_macro_f1']}\n"
            f"Macro F1 current model: {result['production_macro_f1']}\n"
        )

    import boto3
    boto3.client("sns").publish(TopicArn=topic, Subject=subject, Message=body)
    return True


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

    now = datetime.now(timezone.utc)
    result["evaluated_at"] = now.isoformat()
    result["candidate_prefix"] = prefix

    auto_promote = os.environ.get("AUTO_PROMOTE", "true").lower() == "true"
    if result["status"] == "eligible" and auto_promote:
        result["archived_to"] = promote(s3, bucket, prefix, production is not None, now)
        result["production_promoted"] = True

    s3.put_object(
        Bucket=bucket,
        Key=prefix + "evaluation.json",
        Body=json.dumps(result, indent=2).encode(),
        ContentType="application/json"
    )

    result["admins_notified"] = notify_admins(result)

    print(
        "Evaluation status:", result["status"],
        "| promoted:", result["production_promoted"],
        "| admins notified:", result["admins_notified"],
    )

    return result
