# Phase C · ML model & price alerts
# Owner: Marta
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


# ---------------------------------------------------------
# Phase C — check-alerts Lambda
# ---------------------------------------------------------

# Get current AWS account information
data "aws_caller_identity" "current" {}


# Package our Python Lambda into a ZIP file
data "archive_file" "check_alerts" {
  type        = "zip"
  source_file = "${path.module}/../../src/lambdas/check-alerts/handler.py"
  output_path = "${path.module}/.terraform/check-alerts.zip"
}


# IAM role assumed by the Lambda
resource "aws_iam_role" "check_alerts" {
  name = "${var.project}-check-alerts-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [{
      Effect = "Allow"
      Action = "sts:AssumeRole"

      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}


# CloudWatch logs
resource "aws_cloudwatch_log_group" "check_alerts" {
  name              = "/aws/lambda/${var.project}-check-alerts"
  retention_in_days = 7
}


# Permissions: read subscriptions and write logs
resource "aws_iam_role_policy" "check_alerts" {
  name = "${var.project}-check-alerts-policy"
  role = aws_iam_role.check_alerts.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"
        Action = ["dynamodb:Query"]

        Resource = [
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.project}-subscriptions",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.project}-subscriptions/index/station_fuel-index"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]

        Resource = [
          "${aws_cloudwatch_log_group.check_alerts.arn}:*"
        ]
      }
    ]
  })
}


# AWS Lambda
resource "aws_lambda_function" "check_alerts" {
  function_name = "${var.project}-check-alerts"

  filename         = data.archive_file.check_alerts.output_path
  source_code_hash = data.archive_file.check_alerts.output_base64sha256

  role    = aws_iam_role.check_alerts.arn
  handler = "handler.lambda_handler"
  runtime = "python3.11"

  timeout     = 30
  memory_size = 128

  environment {
    variables = {
      SUBSCRIPTIONS_TABLE = "${var.project}-subscriptions"
    }
  }

  depends_on = [
    aws_iam_role_policy.check_alerts,
    aws_cloudwatch_log_group.check_alerts
  ]
}

# DynamoDB Streams trigger intentionally not enabled.
# Email delivery is blocked in the university sandbox.
