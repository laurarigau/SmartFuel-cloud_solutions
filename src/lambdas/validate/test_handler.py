import json

import pytest

RAW_KEY = "raw/2026/11/04/1325.json"


@pytest.fixture
def h(load, fake_s3, fake_sns, env):
    module = load("validate")
    module._s3, module._sns = fake_s3, fake_sns
    return module


def put(fake_s3, payload, key=RAW_KEY):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    fake_s3.put_object(Bucket="lake", Key=key, Body=body)


def s3_event(key=RAW_KEY):
    return {"detail": {"bucket": {"name": "lake"}, "object": {"key": key}}}


def test_valid_sample_passes(h, fake_s3, fake_sns, raw_sample):
    put(fake_s3, raw_sample)
    out = h.lambda_handler(s3_event(), None)

    assert out["valid"] is True
    assert out["reasons"] == []
    assert out["stations"] == 50
    assert out["snapshot"] == "2026-11-04T13:25:51"
    assert fake_s3.keys("raw/") == [RAW_KEY]  # untouched
    assert fake_sns.messages == []


def test_invalid_file_goes_to_quarantine_and_alerts(h, fake_s3, fake_sns, raw_invalid):
    put(fake_s3, raw_invalid)
    out = h.lambda_handler(s3_event(), None)

    assert out["valid"] is False
    assert any("ListaEESSPrecio" in r for r in out["reasons"])
    assert out["quarantine_key"] == "quarantine/2026/11/04/1325.json"
    assert fake_s3.keys("raw/") == []
    assert fake_s3.keys("quarantine/") == ["quarantine/2026/11/04/1325.json"]
    assert len(fake_sns.messages) == 1
    assert RAW_KEY in fake_sns.messages[0]["Message"]


def test_too_few_stations_is_invalid(h, fake_s3, raw_sample, monkeypatch):
    monkeypatch.setenv("MIN_STATIONS", "10000")
    put(fake_s3, raw_sample)
    out = h.lambda_handler(s3_event(), None)
    assert out["valid"] is False
    assert "only 50 stations" in out["reasons"][0]


def test_not_json_is_invalid(h, fake_s3):
    put(fake_s3, b"<html>Service unavailable</html>")
    out = h.lambda_handler(s3_event(), None)
    assert out["valid"] is False
    assert "not valid JSON" in out["reasons"][0]


def test_simple_input_without_eventbridge(h, fake_s3, raw_sample):
    put(fake_s3, raw_sample)
    out = h.lambda_handler({"key": RAW_KEY}, None)  # bucket from LAKE_BUCKET
    assert out["valid"] is True and out["bucket"] == "lake"


@pytest.mark.parametrize("value,expected", [("1,699", 1.699), ("", None), (None, None), ("abc", None)])
def test_parse_number(h, value, expected):
    assert h.parse_number(value) == expected


def test_bad_fecha_and_api_error(h, raw_sample):
    raw_sample["Fecha"] = "2026-11-04"
    raw_sample["ResultadoConsulta"] = "ERROR"
    reasons, snapshot, _ = h.check_payload(raw_sample, 10)
    assert snapshot is None
    assert len(reasons) == 2
