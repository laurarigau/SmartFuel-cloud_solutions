"""Unit tests for the API Lambda. No AWS needed: DynamoDB is replaced by fakes."""
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
import handler  # noqa: E402

STATION = {"station_id": "4375", "name": "Nº 10.935", "municipality": "Abengibre",
           "lat": Decimal("39.211417"), "lon": Decimal("-1.539167"), "geohash5": "eyyzh"}


class FakeTable:
    def __init__(self, items):
        self.items = items

    def query(self, **kwargs):
        return {"Items": self.items}

    def get_item(self, Key):
        found = [i for i in self.items if i["station_id"] == Key["station_id"]]
        return {"Item": dict(found[0])} if found else {}


def use_fakes(monkeypatch, stations, prices=()):
    monkeypatch.setattr(handler, "tables", lambda: (FakeTable(list(stations)), FakeTable(list(prices))))


def call(route, query=None, path=None):
    event = {"routeKey": route, "queryStringParameters": query, "pathParameters": path}
    res = handler.lambda_handler(event, None)
    return res["statusCode"], json.loads(res["body"])


def test_list_stations_by_geohash(monkeypatch):
    use_fakes(monkeypatch, [STATION])
    status, body = call("GET /stations", query={"geohash": "eyyzh"})
    assert status == 200
    assert body["count"] == 1
    assert body["stations"][0]["lat"] == 39.211417  # Decimal converted to number


def test_list_stations_rejects_bad_geohash(monkeypatch):
    use_fakes(monkeypatch, [])
    for bad in [None, {}, {"geohash": "abc"}, {"geohash": "sp3e3a"}, {"geohash": "ailo0"}]:
        status, _ = call("GET /stations", query=bad)
        assert status == 400


def test_get_station_with_prices(monkeypatch):
    prices = [{"station_id": "4375", "fuel_type": "gasoleo_a", "price_eur": Decimal("1.459"), "ts": "2026-11-04T13:25:51"}]
    use_fakes(monkeypatch, [STATION], prices)
    status, body = call("GET /stations/{id}", path={"id": "4375"})
    assert status == 200
    assert body["prices"]["gasoleo_a"]["price_eur"] == 1.459


def test_get_station_not_found(monkeypatch):
    use_fakes(monkeypatch, [STATION])
    status, _ = call("GET /stations/{id}", path={"id": "999999"})
    assert status == 404


def test_unknown_route(monkeypatch):
    use_fakes(monkeypatch, [])
    status, _ = call("POST /nothing")
    assert status == 404


class FakePredictions:
    def __init__(self, items):
        self.items = items
        self.queries = []

    def query(self, KeyConditionExpression, ScanIndexForward, Limit):
        key = KeyConditionExpression.get_expression()["values"][1]
        self.queries.append(key)
        found = sorted([i for i in self.items if i["station_fuel"] == key], key=lambda i: i["date"], reverse=True)
        return {"Items": found[:Limit]}


def test_predictions_latest_per_fuel(monkeypatch):
    fake = FakePredictions([
        {"station_fuel": "4375#gasoleo_a", "date": "2026-11-16", "direction": "up", "prob": Decimal("0.61"), "model_version": "v0"},
        {"station_fuel": "4375#gasoleo_a", "date": "2026-11-17", "direction": "down", "prob": Decimal("0.72"), "model_version": "v0"},
        {"station_fuel": "4375#gasolina_95_e5", "date": "2026-11-17", "direction": "flat", "prob": Decimal("0.55"), "model_version": "v0"},
    ])
    monkeypatch.setattr(handler, "predictions_table", lambda: fake)
    status, body = call("GET /predictions/{id}", path={"id": "4375"})
    assert status == 200
    assert body["predictions"]["gasoleo_a"] == {"date": "2026-11-17", "direction": "down", "prob": 0.72, "model_version": "v0"}
    assert body["predictions"]["gasolina_95_e5"]["direction"] == "flat"
    assert "glp" not in body["predictions"]
    assert len(fake.queries) == len(handler.FUEL_TYPES)


def test_predictions_empty_when_none(monkeypatch):
    monkeypatch.setattr(handler, "predictions_table", lambda: FakePredictions([]))
    status, body = call("GET /predictions/{id}", path={"id": "999"})
    assert status == 200
    assert body == {"station_id": "999", "predictions": {}}
