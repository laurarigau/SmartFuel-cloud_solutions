"""SmartFuel — Match price drops with user subscriptions."""

import json
import os
from decimal import Decimal


def should_alert(old_price, new_price, target_price):
    return (
        Decimal(str(new_price)) < Decimal(str(old_price))
        and Decimal(str(new_price)) <= Decimal(str(target_price))
    )


def is_large_drop(old_price, new_price, minimum=0.05):
    old = Decimal(str(old_price))
    new = Decimal(str(new_price))
    return old > new and old - new >= Decimal(str(minimum))


def extract_price_drops(event):
    drops = []
    for record in event.get("Records", []):
        if record.get("eventName") != "MODIFY":
            continue

        data = record.get("dynamodb", {})
        old = data.get("OldImage") or {}
        new = data.get("NewImage") or {}

        try:
            station = new["station_id"]["S"]
            fuel = new["fuel_type"]["S"]
            old_price = Decimal(old["price_eur"]["N"])
            new_price = Decimal(new["price_eur"]["N"])
        except (KeyError, TypeError, ValueError):
            continue

        if new_price < old_price:
            drops.append({
                "station_id": station,
                "fuel_type": fuel,
                "old_price": old_price,
                "new_price": new_price,
            })
    return drops


def get_subscribers(table, station_fuel):
    params = {
        "IndexName": "station_fuel-index",
        "KeyConditionExpression": "station_fuel = :sf",
        "ExpressionAttributeValues": {":sf": station_fuel},
    }
    while True:
        response = table.query(**params)
        yield from response.get("Items", [])
        if not response.get("LastEvaluatedKey"):
            break
        params["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def find_matching_alerts(price_drops, subscriptions_table):
    alerts = []
    minimum = os.environ.get("LARGE_DROP_EUR", "0.05")

    for drop in price_drops:
        station_fuel = f"{drop['station_id']}#{drop['fuel_type']}"
        large = is_large_drop(
            drop["old_price"], drop["new_price"], minimum
        )

        for subscriber in get_subscribers(subscriptions_table, station_fuel):
            email = subscriber.get("email")
            user_id = subscriber.get("user_id")
            target = subscriber.get("target_price")

            if not email or not user_id:
                continue

            reached = (
                target is not None
                and should_alert(
                    drop["old_price"], drop["new_price"], target
                )
            )

            if not reached and not large:
                continue

            reason = (
                "target_and_large_drop" if reached and large
                else "target_reached" if reached
                else "large_drop"
            )

            alerts.append({
                "user_id": user_id,
                "email": email,
                "station_id": drop["station_id"],
                "fuel_type": drop["fuel_type"],
                "old_price": float(drop["old_price"]),
                "new_price": float(drop["new_price"]),
                "target_price": float(target) if target is not None else None,
                "reason": reason,
            })

    return alerts


def get_subscriptions_table():
    import boto3
    return boto3.resource("dynamodb").Table(
        os.environ["SUBSCRIPTIONS_TABLE"]
    )


def lambda_handler(event, context):
    drops = extract_price_drops(event)

    if not drops:
        return {
            "price_drops": 0,
            "alerts_matched": 0,
            "delivery": "disabled",
        }

    alerts = find_matching_alerts(
        drops, get_subscriptions_table()
    )

    enabled = (
        os.environ.get("ALERT_PUBLISH_ENABLED", "false").lower()
        == "true"
    )

    if not enabled:
        print(f"price_drops={len(drops)}, alerts_matched={len(alerts)}, delivery=disabled")
        return {
            "price_drops": len(drops),
            "alerts_matched": len(alerts),
            "delivery": "disabled",
        }

    topic = os.environ["SNS_TOPIC_ARN"]
    import boto3
    sns = boto3.client("sns")
    published = 0

    for alert in alerts:
        sns.publish(
            TopicArn=topic,
            Message=json.dumps(alert),
        )
        published += 1

    print(f"price_drops={len(drops)}, alerts_published={published}")
    return {
        "price_drops": len(drops),
        "alerts_matched": len(alerts),
        "alerts_published": published,
        "delivery": "sns",
    }
