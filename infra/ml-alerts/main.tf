
# Phase C · ML model & price alerts
# Owner: Marta
#
# Implemented:
#   - Lambda check-alerts
#   - DynamoDB Streams trigger
#   - IAM permissions for subscriptions, streams and logs
#
# Pending:
#   - Scheduled ML retraining
#   - Email delivery (SNS/SES blocked in university sandbox)
#
# IAM: one role per Lambda with least-privilege permissions.


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


# ---------------------------------------------------------
# IAM permissions for check-alerts Lambda
# ---------------------------------------------------------

resource "aws_iam_role_policy" "check_alerts" {
  name = "${var.project}-check-alerts-policy"
  role = aws_iam_role.check_alerts.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [

      # 1. Read user subscriptions
      {
        Effect = "Allow"

        Action = [
          "dynamodb:Query"
        ]

        Resource = [
          local.core.table_arns.subscriptions,
          "${local.core.table_arns.subscriptions}/index/station_fuel-index"
        ]
      },

      # 2. Read price changes from DynamoDB Streams
      {
        Effect = "Allow"

        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator"
        ]

        Resource = local.core.latest_prices_stream_arn
      },

      # 3. List DynamoDB Streams
      {
        Effect = "Allow"

        Action = [
          "dynamodb:ListStreams"
        ]

        Resource = "*"
      },

      # 4. Write CloudWatch logs
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


# ---------------------------------------------------------
# AWS Lambda — check-alerts
# ---------------------------------------------------------

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
      SNS_TOPIC_ARN         = aws_sns_topic.price_alerts.arn
      ALERT_PUBLISH_ENABLED = tostring(var.enable_alert_publish)
      LARGE_DROP_EUR        = "0.05"

      SUBSCRIPTIONS_TABLE = local.core.tables.subscriptions
    }
  }

  depends_on = [
    aws_iam_role_policy.check_alerts,
    aws_cloudwatch_log_group.check_alerts
  ]
}


# ---------------------------------------------------------
# Phase C — DynamoDB Streams trigger
# ---------------------------------------------------------

resource "aws_lambda_event_source_mapping" "check_alerts_stream" {
  event_source_arn  = local.core.latest_prices_stream_arn
  function_name     = aws_lambda_function.check_alerts.arn
  starting_position = "LATEST"

  batch_size = 10
  enabled    = true

  depends_on = [
    aws_iam_role_policy.check_alerts
  ]
}


# ---------------------------------------------------------
# Email delivery
# ---------------------------------------------------------

# SNS and SES are unavailable in the university sandbox.
# The Lambda detects matching price drops but does not
# send notifications.
#
# Email delivery remains disabled.
