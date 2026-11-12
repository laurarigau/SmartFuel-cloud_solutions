"""smartfuel-predict (Phase B, parallel branch 2).

Input: output of clean ({"bucket", "clean_key", "snapshot", ...}).

Loads the production model from s3://<lake>/models/production/ (model.joblib +
metadata.json). Until Phase C uploads one, it uses the stub agreed in
docs/contracts.md: {"direction": "flat", "prob": 1.0}.

Writes one prediction per station x fuel to smartfuel-predictions:
  PK station_fuel = "<station_id>#<fuel_type>", SK date = YYYY-MM-DD,
  direction, prob, model_version, expires_at (TTL, +7 days).

Output: {"predictions_written", "model_version"}

Env: LAKE_BUCKET (fallback), PREDICTIONS_TABLE, MODEL_PREFIX (default models/production/),
     TTL_DAYS (default 7).
Needs pandas + pyarrow (AWS SDK for pandas layer). A real sklearn model will also
need scikit-learn + joblib (container image or extra layer) — agree with Phase C.
"""
import io
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import pandas as pd

STUB_VERSION = "stub"

_s3 = None
_dynamodb = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


# ---------------------------------------------------------------------------
# Features (C decides which ones the model uses: metadata.json "features")
# ---------------------------------------------------------------------------
def build_features(df):
    """Features available from one clean snapshot."""
    f = df.copy()
    ts = pd.to_datetime(f["ts"])
    f["weekday"] = ts.dt.weekday
    f["hour"] = ts.dt.hour
    grp = f.groupby(["province", "fuel_type"])["price_eur"]
    f["province_mean"] = grp.transform("mean")
    f["price_vs_province"] = f["price_eur"] - f["province_mean"]
    f["price_rank_in_geohash"] = f.groupby(["geohash5", "fuel_type"])["price_eur"].rank(pct=True)
    return f


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def stub_predict(features_df):
    return [{"direction": "flat", "prob": 1.0} for _ in range(len(features_df))]


def load_model(bucket, prefix):
    """Return (predict_fn, version). Falls back to the stub if there is no model."""
    try:
        meta = json.loads(s3().get_object(Bucket=bucket, Key=prefix + "metadata.json")["Body"].read())
        blob = s3().get_object(Bucket=bucket, Key=prefix + "model.joblib")["Body"].read()
    except Exception as e:  # noqa: BLE001 - NoSuchKey or AccessDenied -> stub
        print(f"No production model ({type(e).__name__}): using stub")
        return stub_predict, STUB_VERSION

    import joblib  # only needed once a real model exists

    model = joblib.load(io.BytesIO(blob))
    features = meta["features"]

    def predict_fn(features_df):
        # sklearn classifier with classes_ like ["down", "flat", "up"]
        proba = model.predict_proba(features_df[features])
        classes = list(model.classes_)
        out = []
        for row in proba:
            i = int(row.argmax())
            out.append({"direction": str(classes[i]), "prob": float(row[i])})
        return out

    return predict_fn, meta.get("version", "unknown")


def prediction_items(features_df, preds, model_version, ttl_days):
    items = []
    for (_, r), p in zip(features_df.iterrows(), preds):
        day = pd.Timestamp(r["ts"]).date()
        expires = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=ttl_days)
        items.append({
            "station_fuel": f"{r['station_id']}#{r['fuel_type']}",
            "date": day.isoformat(),
            "direction": p["direction"],
            "prob": Decimal(str(round(p["prob"], 4))),
            "price_eur": Decimal(str(round(float(r["price_eur"]), 3))),
            "model_version": model_version,
            "expires_at": int(expires.timestamp()),
        })
    return items


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    bucket = event.get("bucket") or os.environ["LAKE_BUCKET"]
    prefix = os.environ.get("MODEL_PREFIX", "models/production/")
    ttl_days = int(os.environ.get("TTL_DAYS", "7"))

    body = s3().get_object(Bucket=bucket, Key=event["clean_key"])["Body"].read()
    features_df = build_features(pd.read_parquet(io.BytesIO(body)))

    predict_fn, version = load_model(bucket, prefix)
    items = prediction_items(features_df, predict_fn(features_df), version, ttl_days)

    table = dynamodb().Table(os.environ["PREDICTIONS_TABLE"])
    with table.batch_writer(overwrite_by_pkeys=["station_fuel", "date"]) as batch:
        for item in items:
            batch.put_item(Item=item)

    result = {"predictions_written": len(items), "model_version": version}
    print(json.dumps(result))
    return result
