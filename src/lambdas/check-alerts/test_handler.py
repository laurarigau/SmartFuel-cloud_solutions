
import pytest


@pytest.fixture
def handler(load):
    return load("check-alerts")


def test_alert_when_price_drops_below_threshold(handler):
    assert handler.should_alert(1.60, 1.45, 1.50) is True


def test_no_alert_when_price_remains_too_high(handler):
    assert handler.should_alert(1.60, 1.55, 1.50) is False


def test_no_alert_when_price_increases(handler):
    assert handler.should_alert(1.45, 1.50, 1.50) is False


def test_alert_for_another_drop_below_threshold(handler):
    assert handler.should_alert(1.45, 1.40, 1.50) is True


def test_extract_price_drop(handler):

    event = {
        "Records": [{
            "eventName": "MODIFY",
            "dynamodb": {
                "OldImage": {
                    "price_eur": {"N": "1.60"}
                },
                "NewImage": {
                    "station_id": {"S": "4375"},
                    "fuel_type": {"S": "gasolina_95_e5"},
                    "price_eur": {"N": "1.45"}
                }
            }
        }]
    }

    drops = handler.extract_price_drops(event)

    assert len(drops) == 1
    assert drops[0]["station_id"] == "4375"
    assert drops[0]["new_price"] == handler.Decimal("1.45")


def test_ignore_price_increase(handler):

    event = {
        "Records": [{
            "eventName": "MODIFY",
            "dynamodb": {
                "OldImage": {
                    "price_eur": {"N": "1.45"}
                },
                "NewImage": {
                    "station_id": {"S": "4375"},
                    "fuel_type": {"S": "gasolina_95_e5"},
                    "price_eur": {"N": "1.60"}
                }
            }
        }]
    }

    assert handler.extract_price_drops(event) == []


def test_ignore_new_station(handler):

    event = {
        "Records": [{
            "eventName": "INSERT",
            "dynamodb": {
                "NewImage": {
                    "station_id": {"S": "4375"},
                    "price_eur": {"N": "1.45"}
                }
            }
        }]
    }

    assert handler.extract_price_drops(event) == []


class FakeSubscriptionsTable:
    """Simulate DynamoDB subscriptions without AWS."""

    def __init__(self, items):
        self.items = items

    def query(self, **kwargs):
        station_fuel = kwargs[
            "ExpressionAttributeValues"
        ][":sf"]

        matches = [
            item for item in self.items
            if item["station_fuel"] == station_fuel
        ]

        return {"Items": matches}


def test_matching_subscription_generates_alert(handler):

    drop = {
        "station_id": "4375",
        "fuel_type": "gasolina_95_e5",
        "old_price": handler.Decimal("1.60"),
        "new_price": handler.Decimal("1.45")
    }

    table = FakeSubscriptionsTable([{
        "user_id": "user123",
        "email": "example@test.com",
        "station_fuel": "4375#gasolina_95_e5",
        "target_price": handler.Decimal("1.50")
    }])

    alerts = handler.find_matching_alerts(
        [drop], table
    )

    assert len(alerts) == 1
    assert alerts[0]["user_id"] == "user123"
    assert alerts[0]["new_price"] == 1.45


def test_subscription_above_threshold_generates_no_alert(handler):

    drop = {
        "station_id": "4375",
        "fuel_type": "gasolina_95_e5",
        "old_price": handler.Decimal("1.60"),
        "new_price": handler.Decimal("1.55")
    }

    table = FakeSubscriptionsTable([{
        "user_id": "user123",
        "email": "example@test.com",
        "station_fuel": "4375#gasolina_95_e5",
        "target_price": handler.Decimal("1.50")
    }])

    alerts = handler.find_matching_alerts(
        [drop], table
    )

    assert alerts == []


def test_lambda_handler_matches_alerts(handler, monkeypatch):
    """Test the complete alert detection flow."""

    table = FakeSubscriptionsTable([{
        "user_id": "user123",
        "email": "example@test.com",
        "station_fuel": "4375#gasolina_95_e5",
        "target_price": handler.Decimal("1.50")
    }])

    # Use our fake table instead of real AWS
    monkeypatch.setattr(
        handler,
        "get_subscriptions_table",
        lambda: table
    )

    event = {
        "Records": [{
            "eventName": "MODIFY",
            "dynamodb": {
                "OldImage": {
                    "price_eur": {"N": "1.60"}
                },
                "NewImage": {
                    "station_id": {"S": "4375"},
                    "fuel_type": {"S": "gasolina_95_e5"},
                    "price_eur": {"N": "1.45"}
                }
            }
        }]
    }

    result = handler.lambda_handler(event, None)

    assert result["price_drops"] == 1
    assert result["alerts_matched"] == 1
    assert result["delivery"] == "disabled"


def test_lambda_handler_no_price_changes(handler):

    result = handler.lambda_handler(
        {"Records": []}, None
    )

    assert result["price_drops"] == 0
    assert result["alerts_matched"] == 0
