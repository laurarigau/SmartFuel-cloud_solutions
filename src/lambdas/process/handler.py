"""smartfuel-process (Phase B orchestrator).

Step Functions is not available in the university sandbox, so this Lambda plays
the state machine designed in the architecture diagram:

    S3 "Object Created" on raw/ (EventBridge rule)
      -> validate --(valid=false)--> stop (file already in quarantine/)
      -> clean
      -> save-changes  |  predict      (in parallel)

Like Step Functions it adds, per step:
  - Retry: up to MAX_ATTEMPTS attempts with exponential backoff (2 s, 4 s, ...)
  - Catch: on final failure it alerts admins (SNS if available, else an ERROR log
    line for the CloudWatch alarm) and raises, so Lambda's on-failure destination
    (SQS DLQ, when it exists) keeps the event.

Env: FN_VALIDATE, FN_CLEAN, FN_SAVE_CHANGES, FN_PREDICT (function names),
     ADMIN_TOPIC_ARN (optional), MAX_ATTEMPTS (default 3), BACKOFF_SECONDS (default 2).
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config

_lambda = None
_sns = None


def lambda_client():
    global _lambda
    if _lambda is None:
        # predict / save-changes can take minutes: wait for them
        _lambda = boto3.client("lambda", config=Config(read_timeout=900, retries={"max_attempts": 0}))
    return _lambda


def sns():
    global _sns
    if _sns is None:
        _sns = boto3.client("sns")
    return _sns


class StepFailed(Exception):
    def __init__(self, step, detail):
        super().__init__(f"{step} failed: {detail}")
        self.step = step
        self.detail = detail


def invoke(step, payload):
    """Synchronous call to one step's Lambda; raises StepFailed on a function error."""
    resp = lambda_client().invoke(
        FunctionName=os.environ[f"FN_{step.upper().replace('-', '_')}"],
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    body = json.loads(resp["Payload"].read() or b"null")
    if resp.get("FunctionError"):
        raise StepFailed(step, body)
    return body


def run_step(step, payload):
    """Retry with exponential backoff, like a Step Functions Retry block."""
    attempts = int(os.environ.get("MAX_ATTEMPTS", "3"))
    backoff = float(os.environ.get("BACKOFF_SECONDS", "2"))
    for attempt in range(1, attempts + 1):
        try:
            return invoke(step, payload)
        except Exception as e:  # noqa: BLE001
            print(f"{step}: attempt {attempt}/{attempts} failed: {e}")
            if attempt == attempts:
                raise e if isinstance(e, StepFailed) else StepFailed(step, str(e))
            time.sleep(backoff * 2 ** (attempt - 1))


def alert_admins(subject, message):
    """Catch: SNS when the topic exists; always an ERROR line in CloudWatch Logs."""
    print(f"ERROR {subject}: {message}")
    topic = os.environ.get("ADMIN_TOPIC_ARN")
    if topic:
        try:
            sns().publish(TopicArn=topic, Subject=subject[:100], Message=message)
        except Exception as e:  # noqa: BLE001 - never hide the original failure
            print(f"Could not publish to SNS: {e}")


def lambda_handler(event, context):
    detail = event.get("detail", {})
    key = detail.get("object", {}).get("key") or event.get("key")
    started = time.time()
    steps = {}
    try:
        validated = run_step("validate", event)
        steps["validate"] = {"valid": validated["valid"], "stations": validated["stations"]}
        if not validated["valid"]:
            # validate already moved the file to quarantine/ and alerted: not a failure
            return {"key": key, "status": "quarantined", "reasons": validated["reasons"], "steps": steps}

        cleaned = run_step("clean", validated)
        steps["clean"] = {"rows": cleaned["rows"], "changes": cleaned["changes"]}

        # Parallel branch: both get clean's output
        with ThreadPoolExecutor(max_workers=2) as pool:
            save = pool.submit(run_step, "save-changes", cleaned)
            predict = pool.submit(run_step, "predict", cleaned)
            steps["save-changes"] = save.result()
            steps["predict"] = predict.result()

    except StepFailed as e:
        alert_admins(
            "SmartFuel: processing failed",
            f"File: {key}\nStep: {e.step}\nDetail: {json.dumps(e.detail, default=str)[:2000]}\nDone so far: {json.dumps(steps)}",
        )
        raise

    result = {"key": key, "status": "processed", "seconds": round(time.time() - started, 1), "steps": steps}
    print(json.dumps(result))
    return result
