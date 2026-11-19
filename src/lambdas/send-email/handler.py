"""SmartFuel — SNS notifications delivered through Amazon SES."""

import json
import os
from decimal import Decimal


def build_email(alert):
    old = Decimal(str(alert["old_price"]))
    new = Decimal(str(alert["new_price"]))
    saving = old - new
    station = alert["station_id"]
    fuel = alert["fuel_type"]

    subject = "SmartFuel: combustible más barato"
    body = (
        "¡Buenas noticias!\n\n"
        f"Estación: {station}\n"
        f"Combustible: {fuel}\n"
        f"Precio anterior: {old:.3f} €/L\n"
        f"Precio actual: {new:.3f} €/L\n"
        f"Bajada: {saving:.3f} €/L\n\n"
        "Puedes consultar la estación desde SmartFuel.\n"
    )
    return subject, body


def lambda_handler(event, context):
    enabled = (
        os.environ.get("SEND_EMAIL_ENABLED", "false").lower()
        == "true"
    )
    sender = os.environ.get("SES_FROM_EMAIL", "")
    sent = 0
    dry_run = 0

    for record in event.get("Records", []):
        payload = record.get("Sns", {}).get("Message")
        if not payload:
            continue

        alert = json.loads(payload)
        recipient = alert.get("email", "")

        if not recipient or "@" not in recipient:
            continue

        subject, body = build_email(alert)

        if not enabled:
            dry_run += 1
            continue

        if not sender:
            raise RuntimeError("SES_FROM_EMAIL is not configured")

        import boto3
        boto3.client("sesv2").send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [recipient]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": body, "Charset": "UTF-8"}
                    },
                }
            },
        )
        sent += 1

    print(f"emails_sent={sent}, dry_run={dry_run}")
    return {"emails_sent": sent, "dry_run": dry_run}
