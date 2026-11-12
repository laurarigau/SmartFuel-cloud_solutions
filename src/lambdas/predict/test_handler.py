import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest


@pytest.fixture
def clean_output(load, fake_s3, env, raw_sample):
    """Run clean on the 50-station fixture to get a real clean/ parquet."""
    clean = load("clean")
    clean._s3 = fake_s3
    fake_s3.put_object(Bucket="lake", Key="raw/2026/11/04/1325.json", Body=json.dumps(raw_sample).encode())
    return clean.lambda_handler({"key": "raw/2026/11/04/1325.json"}, None)


@pytest.fixture
def h(load, fake_s3, fake_dynamo, env):
    module = load("predict")
    module._s3, module._dynamodb = fake_s3, fake_dynamo
    return module


def test_stub_when_no_model(h, fake_dynamo, clean_output):
    out = h.lambda_handler(clean_output, None)

    assert out["model_version"] == "stub"
    assert out["predictions_written"] == clean_output["rows"]

    items = fake_dynamo.Table("smartfuel-predictions").items
    item = items[("4375#gasoleo_a", "2026-11-04")]
    assert item["direction"] == "flat"
    assert item["prob"] == Decimal("1.0")
    assert item["price_eur"] == Decimal("1.839")
    # TTL: 7 days after the prediction date (UTC midnight)
    assert item["expires_at"] == int(datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp())


def test_features(h, fake_s3, clean_output):
    import io

    import pandas as pd

    df = pd.read_parquet(io.BytesIO(fake_s3.objects[("lake", clean_output["clean_key"])]))
    f = h.build_features(df)
    for col in ("weekday", "hour", "price_vs_province", "price_rank_in_geohash"):
        assert col in f.columns
    assert (f["weekday"] == 2).all()  # 4 Nov 2026 is a Wednesday
    assert f["price_rank_in_geohash"].between(0, 1).all()
