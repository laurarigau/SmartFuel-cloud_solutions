"""smartfuel-clean (Phase B, step 2 of the processing workflow).

Input: output of validate ({"bucket", "key", "valid": true, ...}).

1. Reads the raw JSON and turns it into one row per station x fuel
   (schema in docs/contracts.md), dropping empty prices.
2. Writes clean/date=YYYY-MM-DD/HHmm.parquet.
3. Compares with the previous clean snapshot and writes only the rows that are
   new or whose price changed to changes/date=YYYY-MM-DD/HHmm.jsonl.gz
   (too many rows to pass them through Step Functions, max 256 KB).

Output: input + {"snapshot", "clean_key", "changes_key", "previous_key",
                 "rows", "changes", "new_stations"}

Env: LAKE_BUCKET (fallback), LOOKBACK_DAYS (default 7) to find the previous snapshot.
Needs pandas + pyarrow: attach the AWS SDK for pandas Lambda layer.
"""
import gzip
import io
import json
import os
from datetime import datetime, timedelta

import boto3
import pandas as pd

FECHA_FORMAT = "%d/%m/%Y %H:%M:%S"
FUELS = {
    "gasolina_95_e5": "Precio Gasolina 95 E5",
    "gasolina_98_e5": "Precio Gasolina 98 E5",
    "gasoleo_a": "Precio Gasoleo A",
    "gasoleo_premium": "Precio Gasoleo Premium",
    "glp": "Precio Gases licuados del petróleo",
}
CLEAN_COLUMNS = [
    "station_id", "fuel_type", "price_eur", "ts", "station_name",
    "municipality", "province", "lat", "lon", "geohash5",
]
_GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


# ---------------------------------------------------------------------------
# Pure logic (unit-tested without AWS)
# ---------------------------------------------------------------------------
def parse_number(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def geohash(lat, lon, precision=5):
    """Standard geohash encoding (precision 5 = cell of ~5 x 5 km)."""
    if lat is None or lon is None:
        return None
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    bits, bit_count, even, out = 0, 0, True, []
    while len(out) < precision:
        rng, val = (lon_range, lon) if even else (lat_range, lat)
        mid = (rng[0] + rng[1]) / 2
        if val >= mid:
            bits = (bits << 1) | 1
            rng[0] = mid
        else:
            bits <<= 1
            rng[1] = mid
        even = not even
        bit_count += 1
        if bit_count == 5:
            out.append(_GEOHASH_ALPHABET[bits])
            bits, bit_count = 0, 0
    return "".join(out)


def snapshot_time(data):
    return datetime.strptime(data["Fecha"], FECHA_FORMAT)


def build_rows(data):
    """Raw API response -> (clean DataFrame, station details for DynamoDB).

    ts is the API's Fecha (Spain local time), as the raw key.
    """
    ts = snapshot_time(data)
    rows, details = [], {}
    for s in data["ListaEESSPrecio"]:
        station_id = str(s.get("IDEESS", "")).strip()
        if not station_id:
            continue
        lat = parse_number(s.get("Latitud"))
        lon = parse_number(s.get("Longitud (WGS84)"))
        gh = geohash(lat, lon)
        base = {
            "station_id": station_id,
            "ts": ts,
            "station_name": s.get("Rótulo"),
            "municipality": s.get("Municipio"),
            "province": s.get("Provincia"),
            "lat": lat,
            "lon": lon,
            "geohash5": gh,
        }
        details[station_id] = {**{k: base[k] for k in
                                  ("station_name", "municipality", "province", "lat", "lon", "geohash5")},
                               "address": s.get("Dirección")}
        for fuel_type, field in FUELS.items():
            price = parse_number(s.get(field))
            if price is None or price <= 0:
                continue  # empty = the station does not sell it (never 0 €)
            rows.append({**base, "fuel_type": fuel_type, "price_eur": price})

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    df = df.drop_duplicates(subset=["station_id", "fuel_type"], keep="last")
    df["ts"] = pd.to_datetime(df["ts"])
    return df.reset_index(drop=True), details


def compute_changes(current, previous):
    """Rows of `current` that are new or whose price differs from `previous`.

    Adds is_new_station = True when the station was not in the previous snapshot
    (save-changes then writes its details to the stations table).
    """
    cur = current[["station_id", "fuel_type", "price_eur", "ts"]]
    if previous is None or previous.empty:
        out = cur.copy()
        out["old_price_eur"] = None
        out["is_new_station"] = True
        return out.reset_index(drop=True)

    prev = previous[["station_id", "fuel_type", "price_eur"]].rename(columns={"price_eur": "old_price_eur"})
    merged = cur.merge(prev, on=["station_id", "fuel_type"], how="left")
    changed = merged["old_price_eur"].isna() | ((merged["price_eur"] - merged["old_price_eur"]).abs() > 1e-9)
    out = merged[changed].copy()
    out["is_new_station"] = ~out["station_id"].isin(set(previous["station_id"]))
    out["old_price_eur"] = out["old_price_eur"].astype(object).where(out["old_price_eur"].notna(), None)
    return out.reset_index(drop=True)


def clean_key_for(ts):
    return f"clean/date={ts:%Y-%m-%d}/{ts:%H%M}.parquet"


def changes_key_for(ts):
    return f"changes/date={ts:%Y-%m-%d}/{ts:%H%M}.jsonl.gz"


def to_jsonl_gz(changes, details):
    """One JSON line per change; new stations carry their details."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for r in changes.to_dict("records"):
            line = {
                "station_id": r["station_id"],
                "fuel_type": r["fuel_type"],
                "price_eur": r["price_eur"],
                "old_price_eur": r["old_price_eur"],
                "ts": pd.Timestamp(r["ts"]).isoformat(),
                "is_new_station": bool(r["is_new_station"]),
            }
            if line["is_new_station"]:
                line["station"] = details.get(r["station_id"], {})
            gz.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------
def find_previous_clean_key(bucket, current_key, ts, lookback_days):
    """Latest clean/ key before current_key, looking back a few days."""
    for days_back in range(0, lookback_days + 1):
        day = ts - timedelta(days=days_back)
        prefix = f"clean/date={day:%Y-%m-%d}/"
        keys, token = [], None
        while True:
            kwargs = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3().list_objects_v2(**kwargs)
            keys += [o["Key"] for o in resp.get("Contents", [])]
            if not resp.get("IsTruncated"):
                break
            token = resp["NextContinuationToken"]
        earlier = sorted(k for k in keys if k.endswith(".parquet") and k < current_key)
        if earlier:
            return earlier[-1]
    return None


def read_parquet(bucket, key):
    body = s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    return pd.read_parquet(io.BytesIO(body))


def to_parquet_bytes(df):
    buf = io.BytesIO()
    # ms timestamps: Athena does not read nanosecond timestamps well
    df.to_parquet(buf, index=False, coerce_timestamps="ms", allow_truncated_timestamps=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    bucket = event.get("bucket") or os.environ["LAKE_BUCKET"]
    key = event["key"]
    lookback = int(os.environ.get("LOOKBACK_DAYS", "7"))

    data = json.loads(s3().get_object(Bucket=bucket, Key=key)["Body"].read())
    df, details = build_rows(data)
    ts = snapshot_time(data)

    clean_key = clean_key_for(ts)
    previous_key = find_previous_clean_key(bucket, clean_key, ts, lookback)
    previous = read_parquet(bucket, previous_key) if previous_key else None

    s3().put_object(Bucket=bucket, Key=clean_key, Body=to_parquet_bytes(df))

    changes = compute_changes(df, previous)
    changes_key = changes_key_for(ts)
    s3().put_object(
        Bucket=bucket,
        Key=changes_key,
        Body=to_jsonl_gz(changes, details),
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
    )

    result = {
        **event,
        "bucket": bucket,
        "snapshot": ts.isoformat(),
        "clean_key": clean_key,
        "changes_key": changes_key,
        "previous_key": previous_key,
        "rows": int(len(df)),
        "changes": int(len(changes)),
        "new_stations": int(changes.loc[changes["is_new_station"], "station_id"].nunique()),
    }
    print(json.dumps({k: v for k, v in result.items() if k != "detail"}))
    return result
