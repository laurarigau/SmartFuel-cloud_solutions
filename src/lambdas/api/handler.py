"""Phase D · Public API Lambda (behind API Gateway HTTP API, payload v2.0).

Routes:
    GET /stations?geohash=sp3e3          -> stations in that ~5x5 km cell        (public)
    GET /stations/{id}                   -> one station + its latest prices      (public)
    GET /predictions/{id}                -> latest prediction for each fuel      (public)
    GET /me                              -> who is logged in                     (JWT)
    GET /subscriptions                   -> stations the user follows            (JWT)
    POST /subscriptions                  -> follow {station_id, fuel_type, target_price} (JWT)
    DELETE /subscriptions/{station_fuel} -> stop following "<station_id>#<fuel_type>"  (JWT)
    GET /admin/status                    -> pipeline health: latest raw/clean files      (JWT + group admins)
    GET /admin/quarantine                -> files rejected by validation                 (JWT + group admins)

Private routes are protected by the Cognito JWT authorizer in API Gateway:
the Lambda only runs with a valid token and reads the user from its claims.
Admin routes also need the user to be in the Cognito group "admins" (403 otherwise):
authentication = who you are (token), authorization = what you can do (group).

Public responses carry Cache-Control so browsers reuse them for a few minutes
(HTTP APIs have no server-side cache); private ones are never cached.

Environment variables (set by Terraform):
    STATIONS_TABLE       smartfuel-stations
    PRICES_TABLE         smartfuel-latest-prices
    PREDICTIONS_TABLE    smartfuel-predictions
    SUBSCRIPTIONS_TABLE  smartfuel-subscriptions
    LAKE_BUCKET          smartfuel-lake-<suffix> (admin routes only list it)
"""
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote

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


def response(status, body, max_age=0):
    """JSON response. max_age > 0 lets browsers cache it (public data only)."""
    cache = f"public, max-age={max_age}" if max_age and status == 200 else "no-store"
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": cache},
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

    # stations barely change: 10 minutes
    return response(200, {"geohash": geohash, "count": len(items), "stations": items}, max_age=600)


def get_station(station_id):
    stations, prices = tables()
    station = stations.get_item(Key={"station_id": station_id}).get("Item")
    if not station:
        return response(404, {"error": f"Station {station_id} not found"})

    price_items = prices.query(KeyConditionExpression=Key("station_id").eq(station_id))["Items"]
    station["prices"] = {p["fuel_type"]: {"price_eur": p.get("price_eur"), "ts": p.get("ts")} for p in price_items}
    return response(200, station, max_age=60)  # prices change up to 4 times a day


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
    return response(200, {"station_id": station_id, "predictions": predictions}, max_age=300)


# ---------------------------------------------------------------------------
# Private routes (JWT)
# ---------------------------------------------------------------------------
STATION_ID_RE = re.compile(r"^[0-9]{1,10}$")
MIN_TARGET, MAX_TARGET = Decimal("0.5"), Decimal("5")
MAX_SUBSCRIPTIONS = 20  # per user, keeps the alerts cheap


def subscriptions_table():
    """Subscriptions table. Separate function so tests can replace it."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(os.environ["SUBSCRIPTIONS_TABLE"])


def claims(event):
    """User data from the Cognito token, already verified by API Gateway."""
    return (event.get("requestContext") or {}).get("authorizer", {}).get("jwt", {}).get("claims", {})


def get_me(event):
    c = claims(event)
    groups = user_groups(event)
    return response(200, {
        "user_id": c.get("sub"),
        "email": c.get("email"),
        "groups": groups,
        "is_admin": "admins" in groups,
    })


def user_subscriptions(user_id):
    return subscriptions_table().query(KeyConditionExpression=Key("user_id").eq(user_id))["Items"]


def list_subscriptions(event):
    user_id = claims(event).get("sub")
    items = user_subscriptions(user_id)
    for item in items:
        item.pop("user_id", None)
        item.pop("email", None)  # the user already knows their email
    return response(200, {"count": len(items), "subscriptions": items})


def parse_body(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def create_subscription(event):
    c = claims(event)
    user_id, email = c.get("sub"), c.get("email")
    if not user_id or not email:
        return response(401, {"error": "The token has no user or email"})

    data = parse_body(event)
    if data is None:
        return response(400, {"error": "Body must be a JSON object"})

    station_id = str(data.get("station_id", "")).strip()
    fuel_type = str(data.get("fuel_type", "")).strip()
    if not STATION_ID_RE.match(station_id):
        return response(400, {"error": "'station_id' must be a station number"})
    if fuel_type not in FUEL_TYPES:
        return response(400, {"error": f"'fuel_type' must be one of {FUEL_TYPES}"})
    try:
        target = Decimal(str(data.get("target_price"))).quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        return response(400, {"error": "'target_price' must be a number in EUR/L, e.g. 1.45"})
    if not MIN_TARGET <= target <= MAX_TARGET:
        return response(400, {"error": f"'target_price' must be between {MIN_TARGET} and {MAX_TARGET} EUR/L"})

    stations, _ = tables()
    station = stations.get_item(Key={"station_id": station_id}).get("Item")
    if not station:
        return response(404, {"error": f"Station {station_id} not found"})

    station_fuel = f"{station_id}#{fuel_type}"
    existing = user_subscriptions(user_id)
    if len(existing) >= MAX_SUBSCRIPTIONS and all(i["station_fuel"] != station_fuel for i in existing):
        return response(409, {"error": f"You can follow at most {MAX_SUBSCRIPTIONS} station fuels"})

    item = {
        "user_id": user_id,
        "station_fuel": station_fuel,
        "station_id": station_id,
        "fuel_type": fuel_type,
        "station_name": station.get("name", ""),
        "municipality": station.get("municipality", ""),
        "email": email,  # phase C sends the alert here
        "target_price": target,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    subscriptions_table().put_item(Item=item)  # same station + fuel again = update the target
    item.pop("user_id")
    item.pop("email")
    return response(201, item)


def delete_subscription(event):
    user_id = claims(event).get("sub")
    # "4375#gasoleo_a" arrives as "4375%23gasoleo_a" in the URL
    station_fuel = unquote((event.get("pathParameters") or {}).get("station_fuel", ""))
    station_id, _, fuel_type = station_fuel.partition("#")
    if not STATION_ID_RE.match(station_id) or fuel_type not in FUEL_TYPES:
        return response(400, {"error": "Use DELETE /subscriptions/<station_id>%23<fuel_type>"})
    subscriptions_table().delete_item(Key={"user_id": user_id, "station_fuel": station_fuel})
    return response(200, {"deleted": station_fuel})


# ---------------------------------------------------------------------------
# Admin routes (JWT + group "admins")
# ---------------------------------------------------------------------------
INGEST_EVERY_HOURS = 6  # EventBridge schedule: 01, 07, 13, 19 h
_s3 = None


def s3():
    """S3 client. Separate function so tests can replace it."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def user_groups(event):
    # API Gateway passes the groups as "[admins]" or "admins"
    return [g for g in str(claims(event).get("cognito:groups", "")).strip("[]").replace(",", " ").split() if g]


def list_objects(prefix):
    """All objects under a prefix of the lake (keys sort by date: raw/YYYY/MM/DD/HHmm.json)."""
    objects, kwargs = [], {"Bucket": os.environ["LAKE_BUCKET"], "Prefix": prefix}
    while True:
        page = s3().list_objects_v2(**kwargs)
        objects.extend(page.get("Contents", []))
        if not page.get("IsTruncated"):
            return objects
        kwargs["ContinuationToken"] = page["NextContinuationToken"]


def summary(objects):
    if not objects:
        return {"files": 0, "latest": None}
    latest = max(objects, key=lambda o: o["LastModified"])
    return {
        "files": len(objects),
        "size_mb": round(sum(o["Size"] for o in objects) / 1_000_000, 1),
        "latest": {"key": latest["Key"], "at": latest["LastModified"].isoformat()},
    }


def admin_status(event):
    raw, clean, quarantine = list_objects("raw/"), list_objects("clean/"), list_objects("quarantine/")
    status = {"raw": summary(raw), "clean": summary(clean), "quarantine": {"files": len(quarantine)}}

    # Healthy if the last ingestion is recent (one missed run is tolerated)
    if raw:
        last = max(o["LastModified"] for o in raw)
        hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        status["hours_since_last_ingestion"] = round(hours, 1)
        status["ingestion_ok"] = hours <= 2 * INGEST_EVERY_HOURS
    else:
        status["ingestion_ok"] = False
    status["processing_ok"] = bool(clean)
    return response(200, status)


def admin_quarantine(event):
    files = sorted(list_objects("quarantine/"), key=lambda o: o["LastModified"], reverse=True)[:100]
    return response(200, {
        "count": len(files),
        "files": [{"key": o["Key"], "size_kb": round(o["Size"] / 1000), "at": o["LastModified"].isoformat()}
                  for o in files],
    })


ADMIN_ROUTES = {
    "GET /admin/status": admin_status,
    "GET /admin/quarantine": admin_quarantine,
}

PRIVATE_ROUTES = {
    "GET /me": get_me,
    "GET /subscriptions": list_subscriptions,
    "POST /subscriptions": create_subscription,
    "DELETE /subscriptions/{station_fuel}": delete_subscription,
}


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    if route == "GET /stations":
        return list_stations(event.get("queryStringParameters"))
    if route == "GET /stations/{id}":
        return get_station(event["pathParameters"]["id"])
    if route == "GET /predictions/{id}":
        return get_predictions(event["pathParameters"]["id"])
    if route in PRIVATE_ROUTES:
        if not claims(event).get("sub"):  # API Gateway already checks it; defence in depth
            return response(401, {"error": "Log in first"})
        return PRIVATE_ROUTES[route](event)
    if route in ADMIN_ROUTES:
        if not claims(event).get("sub"):
            return response(401, {"error": "Log in first"})
        if "admins" not in user_groups(event):
            return response(403, {"error": "Only for administrators"})
        return ADMIN_ROUTES[route](event)
    return response(404, {"error": f"Unknown route {route}"})
