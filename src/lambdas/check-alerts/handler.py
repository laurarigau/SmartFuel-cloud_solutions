
"""SmartFuel — Phase C: Fuel price alerts.

Detects when a fuel price decreases below a user's
configured price threshold.
"""

from decimal import Decimal


def should_alert(old_price, new_price, target_price):
    """Return True when a price drop meets the user's threshold."""

    old_price = Decimal(str(old_price))
    new_price = Decimal(str(new_price))
    target_price = Decimal(str(target_price))

    return (
        new_price < old_price
        and new_price <= target_price
    )


def extract_price_drops(event):
    """Extract fuel price decreases from DynamoDB Streams."""

    price_drops = []

    for record in event.get("Records", []):

        # Only process updated records
        if record.get("eventName") != "MODIFY":
            continue

        dynamodb_data = record.get("dynamodb", {})
        old_image = dynamodb_data.get("OldImage") or {}
        new_image = dynamodb_data.get("NewImage") or {}

        try:
            station_id = new_image["station_id"]["S"]
            fuel_type = new_image["fuel_type"]["S"]

            old_price = Decimal(old_image["price_eur"]["N"])
            new_price = Decimal(new_image["price_eur"]["N"])

        except (KeyError, TypeError, ValueError):
            continue

        # Only keep price decreases
        if new_price < old_price:
            price_drops.append({
                "station_id": station_id,
                "fuel_type": fuel_type,
                "old_price": old_price,
                "new_price": new_price
            })

    return price_drops


def get_subscribers(table, station_fuel):
    """Find users following a station and fuel type."""

    params = {
        "IndexName": "station_fuel-index",
        "KeyConditionExpression": "station_fuel = :sf",
        "ExpressionAttributeValues": {
            ":sf": station_fuel
        }
    }

    while True:
        response = table.query(**params)

        for item in response.get("Items", []):
            yield item

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

        params["ExclusiveStartKey"] = last_key


def find_matching_alerts(price_drops, subscriptions_table):
    """Find subscriptions that meet the alert conditions."""

    alerts = []

    for drop in price_drops:
        station_fuel = (
            f"{drop['station_id']}#{drop['fuel_type']}"
        )

        subscribers = get_subscribers(
            subscriptions_table,
            station_fuel
        )

        for subscriber in subscribers:
            target = subscriber.get("target_price")

            if target is None:
                continue

            if should_alert(
                drop["old_price"],
                drop["new_price"],
                target
            ):
                alerts.append({
                    "user_id": subscriber["user_id"],
                    "email": subscriber["email"],
                    "station_id": drop["station_id"],
                    "fuel_type": drop["fuel_type"],
                    "old_price": float(drop["old_price"]),
                    "new_price": float(drop["new_price"]),
                    "target_price": float(target)
                })

    return alerts


import os


def get_subscriptions_table():
    """Connect to the DynamoDB subscriptions table."""
    import boto3

    table_name = os.environ["SUBSCRIPTIONS_TABLE"]
    return boto3.resource("dynamodb").Table(table_name)


def lambda_handler(event, context):
    """Process DynamoDB Streams and identify matching alerts."""

    # Step 1: Extract fuel price decreases
    price_drops = extract_price_drops(event)

    if not price_drops:
        return {
            "price_drops": 0,
            "alerts_matched": 0,
            "delivery": "disabled"
        }

    # Step 2: Find users whose thresholds are satisfied
    subscriptions_table = get_subscriptions_table()

    alerts = find_matching_alerts(
        price_drops,
        subscriptions_table
    )

    # SNS/SES delivery is not enabled yet.
    # Return only counts to avoid exposing user emails.
    return {
        "price_drops": len(price_drops),
        "alerts_matched": len(alerts),
        "delivery": "disabled"
    }
