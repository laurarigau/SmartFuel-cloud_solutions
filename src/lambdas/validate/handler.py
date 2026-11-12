"""smartfuel-validate (Phase B, step 1 of the processing workflow).

Input  (Step Functions, from the EventBridge "Object Created" event):
    {"detail": {"bucket": {"name": "..."}, "object": {"key": "raw/YYYY/MM/DD/HHmm.json"}}}
    or, for manual tests, simply {"bucket": "...", "key": "raw/..."}

Checks that the raw file is a usable Ministry API response. If not, it moves the
file to quarantine/<same key without "raw/"> and notifies admin-alerts (SNS).

Output: {"bucket", "key", "valid": bool, "reasons": [...], "snapshot": "YYYY-MM-DDTHH:MM:SS",
         "stations": int, "quarantine_key": str | None}
The state machine uses "valid" in a Choice state.

Env: LAKE_BUCKET (fallback if the event has no bucket), ADMIN_TOPIC_ARN (optional),
     MIN_STATIONS (default 10000).
"""
import json
import os
from datetime import datetime

import boto3

FECHA_FORMAT = "%d/%m/%Y %H:%M:%S"
TRACKED_PRICE_FIELDS = [
    "Precio Gasolina 95 E5",
    "Precio Gasolina 98 E5",
    "Precio Gasoleo A",
    "Precio Gasoleo Premium",
    "Precio Gases licuados del petróleo",
]

_s3 = None
_sns = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def sns():
    global _sns
    if _sns is None:
        _sns = boto3.client("sns")
    return _sns


# ---------------------------------------------------------------------------
# Pure logic (unit-tested without AWS)
# ---------------------------------------------------------------------------
def parse_number(value):
    """'1,699' -> 1.699 ; '' / None / garbage -> None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def check_payload(data, min_stations):
    """Return (reasons, snapshot_iso, n_stations). Empty reasons = valid."""
    reasons = []
    if not isinstance(data, dict):
        return ["payload is not a JSON object"], None, 0

    if data.get("ResultadoConsulta", "OK") != "OK":
        reasons.append(f"ResultadoConsulta = {data.get('ResultadoConsulta')!r}")

    snapshot = None
    try:
        snapshot = datetime.strptime(data["Fecha"], FECHA_FORMAT).isoformat()
    except (KeyError, TypeError, ValueError):
        reasons.append("missing or malformed 'Fecha'")

    stations = data.get("ListaEESSPrecio")
    if not isinstance(stations, list):
        reasons.append("missing 'ListaEESSPrecio' list")
        return reasons, snapshot, 0

    n = len(stations)
    if n < min_stations:
        reasons.append(f"only {n} stations (minimum {min_stations})")
    if n == 0:
        return reasons, snapshot, 0

    with_id_and_coords = sum(
        1
        for s in stations
        if isinstance(s, dict)
        and str(s.get("IDEESS", "")).strip()
        and parse_number(s.get("Latitud")) is not None
        and parse_number(s.get("Longitud (WGS84)")) is not None
    )
    if with_id_and_coords / n < 0.95:
        reasons.append(f"only {with_id_and_coords}/{n} stations have id and coordinates")

    with_price = sum(
        1
        for s in stations
        if isinstance(s, dict) and any(parse_number(s.get(f)) for f in TRACKED_PRICE_FIELDS)
    )
    if with_price / n < 0.5:
        reasons.append(f"only {with_price}/{n} stations have a tracked fuel price")

    return reasons, snapshot, n


def read_location(event):
    """Accept the EventBridge S3 event or a simple {"bucket", "key"} dict."""
    if "detail" in event:
        return event["detail"]["bucket"]["name"], event["detail"]["object"]["key"]
    return event.get("bucket") or os.environ["LAKE_BUCKET"], event["key"]


def quarantine_key_for(key):
    return "quarantine/" + (key[len("raw/"):] if key.startswith("raw/") else key)


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    bucket, key = read_location(event)
    min_stations = int(os.environ.get("MIN_STATIONS", "10000"))

    body = s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        data = None
        reasons, snapshot, n = [f"not valid JSON: {e}"], None, 0
    if data is not None:
        reasons, snapshot, n = check_payload(data, min_stations)

    result = {
        "bucket": bucket,
        "key": key,
        "valid": not reasons,
        "reasons": reasons,
        "snapshot": snapshot,
        "stations": n,
        "quarantine_key": None,
    }

    if reasons:
        q_key = quarantine_key_for(key)
        s3().copy_object(Bucket=bucket, Key=q_key, CopySource={"Bucket": bucket, "Key": key})
        s3().delete_object(Bucket=bucket, Key=key)
        result["quarantine_key"] = q_key

        topic = os.environ.get("ADMIN_TOPIC_ARN")
        if topic:
            sns().publish(
                TopicArn=topic,
                Subject="SmartFuel: raw file quarantined",
                Message=f"s3://{bucket}/{key} moved to {q_key}\nReasons:\n- " + "\n- ".join(reasons),
            )

    print(json.dumps(result))
    return result
