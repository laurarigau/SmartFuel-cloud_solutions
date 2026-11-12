import copy
import gzip
import io
import json

import pandas as pd
import pytest

RAW_KEY = "raw/2026/11/04/1325.json"


@pytest.fixture
def h(load, fake_s3, env):
    module = load("clean")
    module._s3 = fake_s3
    return module


def put_raw(fake_s3, payload, key=RAW_KEY):
    fake_s3.put_object(Bucket="lake", Key=key, Body=json.dumps(payload).encode())


def read_changes(fake_s3, key):
    raw = fake_s3.get_object(Bucket="lake", Key=key)["Body"].read()
    return [json.loads(line) for line in gzip.decompress(raw).decode().splitlines()]


def test_build_rows_schema(h, raw_sample):
    df, details = h.build_rows(raw_sample)

    assert list(df.columns) == h.CLEAN_COLUMNS
    assert set(df["fuel_type"]) <= set(h.FUELS)
    assert df["price_eur"].notna().all() and (df["price_eur"] > 0).all()
    assert not df.duplicated(["station_id", "fuel_type"]).any()
    assert len(details) == 50

    row = df[(df.station_id == "4375") & (df.fuel_type == "gasoleo_a")].iloc[0]
    assert row.price_eur == pytest.approx(1.839)
    assert row.lat == pytest.approx(39.211417)
    assert row.lon == pytest.approx(-1.539167)
    assert row.ts == pd.Timestamp("2026-11-04 13:25:51")
    # Gasolina 98 is empty for this station -> no row
    assert df[(df.station_id == "4375") & (df.fuel_type == "gasolina_98_e5")].empty


def test_geohash_known_value(h):
    # Plaça de Catalunya, Barcelona
    assert h.geohash(41.3870, 2.1700) == "sp3e3"
    assert h.geohash(None, 2.17) is None


def test_first_snapshot_everything_is_a_change(h, fake_s3, raw_sample):
    put_raw(fake_s3, raw_sample)
    out = h.lambda_handler({"bucket": "lake", "key": RAW_KEY, "valid": True}, None)

    assert out["clean_key"] == "clean/date=2026-11-04/1325.parquet"
    assert out["changes_key"] == "changes/date=2026-11-04/1325.jsonl.gz"
    assert out["previous_key"] is None
    assert out["changes"] == out["rows"] > 0
    # 49: station 14612 only sells natural gas (not a tracked fuel) -> no rows
    assert out["new_stations"] == 49

    clean = pd.read_parquet(io.BytesIO(fake_s3.objects[("lake", out["clean_key"])]))
    assert len(clean) == out["rows"]

    changes = read_changes(fake_s3, out["changes_key"])
    assert all(c["is_new_station"] and "station" in c for c in changes)


def test_second_snapshot_only_changed_prices(h, fake_s3, raw_sample):
    put_raw(fake_s3, raw_sample)
    h.lambda_handler({"key": RAW_KEY}, None)

    later = copy.deepcopy(raw_sample)
    later["Fecha"] = "04/11/2026 19:25:51"
    later["ListaEESSPrecio"][0]["Precio Gasoleo A"] = "1,799"  # 4375: 1.839 -> 1.799
    new_station = copy.deepcopy(later["ListaEESSPrecio"][1])
    new_station["IDEESS"] = "999999"
    later["ListaEESSPrecio"].append(new_station)
    put_raw(fake_s3, later, "raw/2026/11/04/1925.json")

    out = h.lambda_handler({"key": "raw/2026/11/04/1925.json"}, None)

    assert out["previous_key"] == "clean/date=2026-11-04/1325.parquet"
    changes = read_changes(fake_s3, out["changes_key"])
    by_station = {(c["station_id"], c["fuel_type"]): c for c in changes}

    assert by_station[("4375", "gasoleo_a")]["price_eur"] == pytest.approx(1.799)
    assert by_station[("4375", "gasoleo_a")]["old_price_eur"] == pytest.approx(1.839)
    assert by_station[("4375", "gasoleo_a")]["is_new_station"] is False
    assert all(c["is_new_station"] for k, c in by_station.items() if k[0] == "999999")
    # nothing else changed
    assert {k[0] for k in by_station} == {"4375", "999999"}
    assert out["new_stations"] == 1


def test_previous_snapshot_from_an_earlier_day(h, fake_s3, raw_sample):
    put_raw(fake_s3, raw_sample)
    h.lambda_handler({"key": RAW_KEY}, None)

    next_day = copy.deepcopy(raw_sample)
    next_day["Fecha"] = "06/11/2026 07:00:00"  # a day with no data in between
    put_raw(fake_s3, next_day, "raw/2026/11/06/0700.json")
    out = h.lambda_handler({"key": "raw/2026/11/06/0700.json"}, None)

    assert out["previous_key"] == "clean/date=2026-11-04/1325.parquet"
    assert out["changes"] == 0
