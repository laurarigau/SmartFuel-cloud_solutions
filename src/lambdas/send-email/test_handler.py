import json


def test_email_dry_run(load, monkeypatch):
    handler = load("send-email")
    monkeypatch.setenv("SEND_EMAIL_ENABLED", "false")

    event = {"Records": [{
        "Sns": {
            "Message": json.dumps({
                "email": "test@example.invalid",
                "station_id": "4375",
                "fuel_type": "gasolina_95_e5",
                "old_price": 1.60,
                "new_price": 1.45,
                "reason": "large_drop",
            })
        }
    }]}

    result = handler.lambda_handler(event, None)
    assert result == {"emails_sent": 0, "dry_run": 1}
