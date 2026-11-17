"""Phase D · Public API Lambda (behind API Gateway HTTP API, payload v2.0).

Routes:
    GET /stations?geohash=sp3e3   -> stations in that ~5x5 km cell
    GET /stations/{id}            -> one station + its latest prices
    GET /predictions/{id}         -> latest prediction for each fuel of a station

Environment variables (set by Terraform):
    STATIONS_TABLE   smartfuel-stations
    PRICES_TABLE     smartfuel-latest-prices
    PREDICTIONS_TABLE smartfuel-predictions
"""
import json
import os
import re
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

GEOHASH_RE = re.compile(r"^[0123456789bcdefghjkmnpqrstuvwxyz]{5}$")

_dynamodb = None


def tables():
    """Return (stations, prices) tables. Created lazily so tests can replace it."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return (
        _dynamodb.Table(os.environ["STATIONS_TABLE"]),
        _dynamodb.Table(os.environ["PRICES_TABLE"]),
    )


# Fuel types used in the keys of the predictions table ("<station_id>#<fuel_type>"),
# as defined in docs/contracts.md
FUEL_TYPES = ["gasolina_95_e5", "gasolina_98_e5", "gasoleo_a", "gasoleo_premium", "glp"]


def predictions_table():
    """Predictions table. Separate function so tests can replace it."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(os.environ["PREDICTIONS_TABLE"])


def _json_default(value):
    # DynamoDB returns numbers as Decimal; JSON needs int/float
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Not serializable: {type(value)}")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default, ensure_ascii=False),
    }


def list_stations(params):
    geohash = (params or {}).get("geohash", "").lower()
    if not GEOHASH_RE.match(geohash):
        return response(400, {"error": "Query parameter 'geohash' must be 5 geohash characters, e.g. sp3e3"})

    stations, _ = tables()
    items, kwargs = [], {"IndexName": "geohash5-index", "KeyConditionExpression": Key("geohash5").eq(geohash)}
    while True:  # follow pagination
        page = stations.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    return response(200, {"geohash": geohash, "count": len(items), "stations": items})


def get_station(station_id):
    stations, prices = tables()
    station = stations.get_item(Key={"station_id": station_id}).get("Item")
    if not station:
        return response(404, {"error": f"Station {station_id} not found"})

    price_items = prices.query(KeyConditionExpression=Key("station_id").eq(station_id))["Items"]
    station["prices"] = {p["fuel_type"]: {"price_eur": p.get("price_eur"), "ts": p.get("ts")} for p in price_items}
    return response(200, station)


def get_predictions(station_id):
    """Latest prediction of each fuel. Empty until phase B writes predictions."""
    table = predictions_table()
    predictions = {}
    for fuel in FUEL_TYPES:
        items = table.query(
            KeyConditionExpression=Key("station_fuel").eq(f"{station_id}#{fuel}"),
            ScanIndexForward=False,  # newest date first
            Limit=1,
        )["Items"]
        if items:
            item = items[0]
            predictions[fuel] = {
                "date": item.get("date"),
                "direction": item.get("direction"),
                "prob": item.get("prob"),
                "model_version": item.get("model_version"),
            }
    return response(200, {"station_id": station_id, "predictions": predictions})


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    if route == "GET /stations":
        return list_stations(event.get("queryStringParameters"))
    if route == "GET /stations/{id}":
        return get_station(event["pathParameters"]["id"])
    if route == "GET /predictions/{id}":
        return get_predictions(event["pathParameters"]["id"])
    return response(404, {"error": f"Unknown route {route}"})
