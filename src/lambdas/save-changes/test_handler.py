import gzip
import json
from decimal import Decimal

import pytest

CHANGES_KEY = "changes/date=2026-11-04/1925.jsonl.gz"

CHANGES = [
    {"station_id": "4375", "fuel_type": "gasoleo_a", "price_eur": 1.799, "old_price_eur": 1.839,
     "ts": "2026-11-04T19:25:51", "is_new_station": False},
    {"station_id": "999999", "fuel_type": "gasoleo_a", "price_eur": 1.659, "old_price_eur": None,
     "ts": "2026-11-04T19:25:51", "is_new_station": True,
     "station": {"station_name": "REPSOL", "address": "CR CM-332, 46,4", "municipality": "Alatoz",
                 "province": "ALBACETE", "lat": 39.100389, "lon": -1.346083, "geohash5": "eyyy1"}},
    {"station_id": "999999", "fuel_type": "gasolina_95_e5", "price_eur": 1.559, "old_price_eur": None,
     "ts": "2026-11-04T19:25:51", "is_new_station": True,
     "station": {"station_name": "REPSOL", "address": None, "municipality": "Alatoz",
                 "province": "ALBACETE", "lat": 39.100389, "lon": -1.346083, "geohash5": "eyyy1"}},
]


@pytest.fixture
def h(load, fake_s3, fake_dynamo, env):
    module = load("save-changes")
    module._s3, module._dynamodb = fake_s3, fake_dynamo
    body = gzip.compress("\n".join(json.dumps(c) for c in CHANGES).encode())
    fake_s3.put_object(Bucket="lake", Key=CHANGES_KEY, Body=body)
    return module


def test_writes_prices_and_new_stations(h, fake_dynamo):
    out = h.lambda_handler({"bucket": "lake", "changes_key": CHANGES_KEY}, None)

    assert out == {"stations_written": 1, "prices_written": 3}

    prices = fake_dynamo.Table("smartfuel-latest-prices").items
    item = prices[("4375", "gasoleo_a")]
    assert item["price_eur"] == Decimal("1.799")
    assert item["previous_price_eur"] == Decimal("1.839")
    assert "previous_price_eur" not in prices[("999999", "gasoleo_a")]

    stations = fake_dynamo.Table("smartfuel-stations").items
    st = stations[("999999",)]
    assert st["geohash5"] == "eyyy1" and st["name"] == "REPSOL"
    assert isinstance(st["lat"], Decimal)


def test_no_floats_reach_dynamodb(h):
    prices, stations = h.split_items(CHANGES)
    for item in prices + stations:
        assert not any(isinstance(v, float) for v in item.values())
        assert not any(v is None for v in item.values())


def test_end_to_end_with_clean(load, fake_s3, fake_dynamo, env, raw_sample):
    """clean -> save-changes on the real 50-station fixture."""
    clean = load("clean")
    clean._s3 = fake_s3
    fake_s3.put_object(Bucket="lake", Key="raw/2026/11/04/1325.json", Body=json.dumps(raw_sample).encode())
    out_clean = clean.lambda_handler({"key": "raw/2026/11/04/1325.json"}, None)

    save = load("save-changes")
    save._s3, save._dynamodb = fake_s3, fake_dynamo
    out = save.lambda_handler(out_clean, None)

    assert out["prices_written"] == out_clean["rows"]
    assert out["stations_written"] == 49  # 14612 sells only natural gas
