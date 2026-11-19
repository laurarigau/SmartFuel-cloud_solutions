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


# ---------------------------------------------------------------------------
# Private routes: /me and /subscriptions (the JWT is checked by API Gateway)
# ---------------------------------------------------------------------------
USER = {"sub": "user-1", "email": "ana@example.com"}


class FakeSubscriptions:
    def __init__(self):
        self.items = {}  # (user_id, station_fuel) -> item

    def query(self, KeyConditionExpression):
        user_id = KeyConditionExpression.get_expression()["values"][1]
        return {"Items": [dict(i) for (u, _), i in self.items.items() if u == user_id]}

    def put_item(self, Item):
        self.items[(Item["user_id"], Item["station_fuel"])] = dict(Item)

    def delete_item(self, Key):
        self.items.pop((Key["user_id"], Key["station_fuel"]), None)


def use_subscriptions(monkeypatch):
    subs = FakeSubscriptions()
    use_fakes(monkeypatch, [STATION])
    monkeypatch.setattr(handler, "subscriptions_table", lambda: subs)
    return subs


def call_private(route, user=USER, body=None, path=None):
    event = {"routeKey": route, "pathParameters": path,
             "body": json.dumps(body) if body is not None else None,
             "requestContext": {"authorizer": {"jwt": {"claims": user}}} if user else {}}
    res = handler.lambda_handler(event, None)
    return res["statusCode"], json.loads(res["body"])


def test_me_returns_user_and_admin_flag():
    status, body = call_private("GET /me", user={**USER, "cognito:groups": "[admins]"})
    assert status == 200
    assert body == {"user_id": "user-1", "email": "ana@example.com", "groups": ["admins"], "is_admin": True}


def test_private_route_without_token_is_rejected():
    status, _ = call_private("GET /subscriptions", user=None)
    assert status == 401


def test_follow_list_and_unfollow(monkeypatch):
    subs = use_subscriptions(monkeypatch)

    status, body = call_private("POST /subscriptions",
                                body={"station_id": "4375", "fuel_type": "gasoleo_a", "target_price": 1.45})
    assert status == 201
    assert body["station_fuel"] == "4375#gasoleo_a"
    assert body["station_name"] == "Nº 10.935"
    stored = subs.items[("user-1", "4375#gasoleo_a")]
    assert stored["email"] == "ana@example.com"      # phase C needs it for the alert
    assert stored["target_price"] == Decimal("1.450")  # Decimal, as DynamoDB requires

    status, body = call_private("GET /subscriptions")
    assert status == 200 and body["count"] == 1
    assert "email" not in body["subscriptions"][0]

    status, _ = call_private("DELETE /subscriptions/{station_fuel}", path={"station_fuel": "4375%23gasoleo_a"})
    assert status == 200
    assert subs.items == {}


def test_follow_again_updates_target(monkeypatch):
    subs = use_subscriptions(monkeypatch)
    for price in (1.50, 1.40):
        call_private("POST /subscriptions", body={"station_id": "4375", "fuel_type": "gasoleo_a", "target_price": price})
    assert len(subs.items) == 1
    assert subs.items[("user-1", "4375#gasoleo_a")]["target_price"] == Decimal("1.400")


def test_follow_validates_input(monkeypatch):
    use_subscriptions(monkeypatch)
    bad_bodies = [
        {"station_id": "abc", "fuel_type": "gasoleo_a", "target_price": 1.4},
        {"station_id": "4375", "fuel_type": "diesel", "target_price": 1.4},
        {"station_id": "4375", "fuel_type": "gasoleo_a", "target_price": "cheap"},
        {"station_id": "4375", "fuel_type": "gasoleo_a", "target_price": 99},
    ]
    for body in bad_bodies:
        status, _ = call_private("POST /subscriptions", body=body)
        assert status == 400, body
    status, _ = call_private("POST /subscriptions", body={"station_id": "999999", "fuel_type": "glp", "target_price": 1})
    assert status == 404


def test_users_only_see_their_own_subscriptions(monkeypatch):
    use_subscriptions(monkeypatch)
    call_private("POST /subscriptions", body={"station_id": "4375", "fuel_type": "glp", "target_price": 1.0})
    status, body = call_private("GET /subscriptions", user={"sub": "user-2", "email": "otro@example.com"})
    assert status == 200 and body["count"] == 0


def test_follow_limit(monkeypatch):
    subs = use_subscriptions(monkeypatch)
    for n in range(handler.MAX_SUBSCRIPTIONS):
        subs.put_item({"user_id": "user-1", "station_fuel": f"{n}#glp"})
    status, _ = call_private("POST /subscriptions", body={"station_id": "4375", "fuel_type": "glp", "target_price": 1.0})
    assert status == 409


# ---------------------------------------------------------------------------
# Admin routes (group "admins") and browser cache headers
# ---------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402

ADMIN = {**USER, "cognito:groups": "[admins]"}


class FakeS3:
    def __init__(self, keys_by_age_hours):
        now = datetime.now(timezone.utc)
        self.objects = [{"Key": k, "Size": 12_000_000, "LastModified": now - timedelta(hours=h)}
                        for k, h in keys_by_age_hours.items()]

    def list_objects_v2(self, Bucket, Prefix, **_):
        return {"Contents": [o for o in self.objects if o["Key"].startswith(Prefix)], "IsTruncated": False}


def use_s3(monkeypatch, keys):
    monkeypatch.setenv("LAKE_BUCKET", "smartfuel-lake-test")
    monkeypatch.setattr(handler, "s3", lambda: FakeS3(keys))


def test_admin_routes_need_admin_group(monkeypatch):
    use_s3(monkeypatch, {})
    for route in ("GET /admin/status", "GET /admin/quarantine"):
        assert call_private(route, user=USER)[0] == 403   # logged in, not admin
        assert call_private(route, user=None)[0] == 401   # not logged in
        assert call_private(route, user=ADMIN)[0] == 200


def test_admin_status(monkeypatch):
    use_s3(monkeypatch, {
        "raw/2026/11/18/0700.json": 8,
        "raw/2026/11/18/1300.json": 2,
        "clean/2026/11/18/1300.parquet": 2,
        "quarantine/2026/11/17/1900.json": 20,
    })
    status, body = call_private("GET /admin/status", user=ADMIN)
    assert status == 200
    assert body["raw"]["files"] == 2
    assert body["raw"]["latest"]["key"] == "raw/2026/11/18/1300.json"
    assert body["quarantine"]["files"] == 1
    assert body["ingestion_ok"] is True and body["processing_ok"] is True


def test_admin_status_detects_stopped_ingestion(monkeypatch):
    use_s3(monkeypatch, {"raw/2026/11/17/0100.json": 30})
    _, body = call_private("GET /admin/status", user=ADMIN)
    assert body["ingestion_ok"] is False
    assert body["processing_ok"] is False


def test_admin_quarantine_newest_first(monkeypatch):
    use_s3(monkeypatch, {"quarantine/a.json": 30, "quarantine/b.json": 1, "raw/x.json": 1})
    _, body = call_private("GET /admin/quarantine", user=ADMIN)
    assert [f["key"] for f in body["files"]] == ["quarantine/b.json", "quarantine/a.json"]


def test_cache_headers(monkeypatch):
    use_fakes(monkeypatch, [STATION])
    public = handler.lambda_handler({"routeKey": "GET /stations", "queryStringParameters": {"geohash": "eyyzh"}}, None)
    assert public["headers"]["Cache-Control"] == "public, max-age=600"
    error = handler.lambda_handler({"routeKey": "GET /stations", "queryStringParameters": {}}, None)
    assert error["headers"]["Cache-Control"] == "no-store"
    private = handler.lambda_handler({"routeKey": "GET /me", "requestContext": {"authorizer": {"jwt": {"claims": USER}}}}, None)
    assert private["headers"]["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# GET /cheapest: cheapest stations of an area for one fuel
# ---------------------------------------------------------------------------
def area_station(sid, lat, lon, cell="sp3e3"):
    return {"station_id": sid, "name": f"Station {sid}", "municipality": "Barcelona",
            "lat": Decimal(str(lat)), "lon": Decimal(str(lon)), "geohash5": cell}


def use_area(monkeypatch, stations, prices):
    use_fakes(monkeypatch, stations)
    asked = []

    def fake_batch(ids, fuel):
        asked.append((sorted(ids), fuel))
        return {sid: {"station_id": sid, "fuel_type": fuel, "price_eur": Decimal(p)}
                for sid, p in prices.items() if sid in ids}

    monkeypatch.setattr(handler, "batch_get_prices", fake_batch)
    return asked


def test_cheapest_sorted_by_price(monkeypatch):
    stations = [area_station("1", 41.38, 2.17), area_station("2", 41.39, 2.18), area_station("3", 41.40, 2.16)]
    asked = use_area(monkeypatch, stations, {"1": "1.559", "2": "1.499", "3": "1.529"})
    status, body = call("GET /cheapest", query={"geohash": "sp3e3", "fuel": "gasolina_95_e5", "limit": "2"})
    assert status == 200
    assert [s["station_id"] for s in body["cheapest"]] == ["2", "3"]
    assert body["cheapest"][0]["price_eur"] == 1.499
    assert body["stations_in_area"] == 3 and body["with_price"] == 3
    assert asked == [(["1", "2", "3"], "gasolina_95_e5")]


def test_cheapest_skips_stations_without_price_and_outside_bbox(monkeypatch):
    stations = [area_station("1", 41.38, 2.17), area_station("2", 41.39, 2.18), area_station("9", 42.50, 3.00)]
    use_area(monkeypatch, stations, {"1": "1.6", "9": "0.9"})
    status, body = call("GET /cheapest", query={"geohash": "sp3e3", "fuel": "glp", "bbox": "41.3,2.1,41.5,2.2"})
    assert status == 200
    assert body["stations_in_area"] == 2          # station 9 is outside the visible map
    assert [s["station_id"] for s in body["cheapest"]] == ["1"]  # station 2 has no price


def test_cheapest_validates_input(monkeypatch):
    use_area(monkeypatch, [], {})
    for query in ({"fuel": "glp"}, {"geohash": "sp3e3", "fuel": "diesel"},
                  {"geohash": ",".join(["sp3e3"] * 31), "fuel": "glp"}, {"geohash": "zz!", "fuel": "glp"}):
        assert call("GET /cheapest", query=query)[0] == 400, query


def test_cheapest_is_cached_by_browser(monkeypatch):
    use_area(monkeypatch, [area_station("1", 41.38, 2.17)], {"1": "1.5"})
    res = handler.lambda_handler({"routeKey": "GET /cheapest",
                                  "queryStringParameters": {"geohash": "sp3e3", "fuel": "glp"}}, None)
    assert res["headers"]["Cache-Control"] == "public, max-age=300"


def test_batch_get_prices_chunks_and_retries(monkeypatch):
    monkeypatch.setenv("PRICES_TABLE", "prices")
    calls = []

    class FakeResource:
        def batch_get_item(self, RequestItems):
            keys = RequestItems["prices"]["Keys"]
            calls.append(len(keys))
            if len(calls) == 1:  # first call: DynamoDB leaves the last key unprocessed
                return {"Responses": {"prices": [{"station_id": k["station_id"], "price_eur": 1} for k in keys[:-1]]},
                        "UnprocessedKeys": {"prices": {"Keys": keys[-1:]}}}
            return {"Responses": {"prices": [{"station_id": k["station_id"], "price_eur": 1} for k in keys]}}

    monkeypatch.setattr(handler, "_dynamodb", FakeResource())
    found = handler.batch_get_prices([str(i) for i in range(150)], "glp")
    assert len(found) == 150
    assert calls == [100, 1, 50]  # 100 keys max per call + the retried key
