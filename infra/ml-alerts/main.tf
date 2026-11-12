# Phase C · ML model & price alerts
# Owner: [name]
#
# TODO (see the plan doc and docs/contracts.md):
#   [ ] Weekly EventBridge schedule -> retraining state machine: Athena query -> train -> evaluate -> Choice (promote to models/production/ or notify admin-alerts)
#   [ ] Lambda "check-alerts": event source = core latest_prices_stream_arn, reads subscriptions (station_fuel-index), publishes to price-alerts
#   [ ] Lambda "send-email": subscribed to price-alerts SNS topic, sends through SES
#   [ ] SES email identities for the team (demo)
#
# IAM: one role per Lambda / state machine with only the permissions it needs.
# If the sandbox does not allow creating roles, use the provided role and
# document the least-privilege policy you would attach.
