"""smartfuel-save-changes (Phase B, parallel branch 1).

Input: output of clean ({"bucket", "changes_key", ...}).

Reads changes/...jsonl.gz and writes:
  - every changed price to smartfuel-latest-prices (PK station_id, SK fuel_type).
    The table's Stream then triggers the price alerts (Phase C).
  - details of stations that were not in the previous snapshot to smartfuel-stations.

Output: {"prices_written", "stations_written"}

Env: LAKE_BUCKET (fallback), LATEST_PRICES_TABLE, STATIONS_TABLE.
Only boto3: no layer needed.
"""
import gzip
import json
import os
from decimal import Decimal

import boto3

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
# Pure logic (unit-tested without AWS)
# ---------------------------------------------------------------------------
def to_decimal(value, places=6):
    """DynamoDB does not accept float: convert to Decimal (None stays None)."""
    if value is None:
        return None
    return Decimal(str(round(float(value), places)))


def read_changes(raw_bytes):
    text = gzip.decompress(raw_bytes).decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def price_item(change):
    item = {
        "station_id": change["station_id"],
        "fuel_type": change["fuel_type"],
        "price_eur": to_decimal(change["price_eur"], 3),
        "ts": change["ts"],
    }
    if change.get("old_price_eur") is not None:
        item["previous_price_eur"] = to_decimal(change["old_price_eur"], 3)
    return item


def station_item(change):
    st = change.get("station") or {}
    item = {
        "station_id": change["station_id"],
        "name": st.get("station_name"),
        "address": st.get("address"),
        "municipality": st.get("municipality"),
        "province": st.get("province"),
        "lat": to_decimal(st.get("lat")),
        "lon": to_decimal(st.get("lon")),
        "geohash5": st.get("geohash5"),
    }
    # DynamoDB rejects empty/None values for index keys: drop them
    return {k: v for k, v in item.items() if v not in (None, "")}


def split_items(changes):
    prices = [price_item(c) for c in changes]
    stations = {}
    for c in changes:
        if c.get("is_new_station") and c["station_id"] not in stations:
            stations[c["station_id"]] = station_item(c)
    return prices, list(stations.values())


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------
def write_all(table_name, items):
    table = dynamodb().Table(table_name)
    with table.batch_writer(overwrite_by_pkeys=_pkeys(table_name)) as batch:
        for item in items:
            batch.put_item(Item=item)
    return len(items)


def _pkeys(table_name):
    if table_name == os.environ.get("STATIONS_TABLE"):
        return ["station_id"]
    return ["station_id", "fuel_type"]


def lambda_handler(event, context):
    bucket = event.get("bucket") or os.environ["LAKE_BUCKET"]
    raw = s3().get_object(Bucket=bucket, Key=event["changes_key"])["Body"].read()
    changes = read_changes(raw)
    prices, stations = split_items(changes)

    result = {
        "stations_written": write_all(os.environ["STATIONS_TABLE"], stations),
        "prices_written": write_all(os.environ["LATEST_PRICES_TABLE"], prices),
    }
    print(json.dumps(result))
    return result
