# ---------------------------------------------------------------------------
# Shared · Monitoring: CloudWatch alarms and dashboard
#
# Draft: "CloudWatch for logs, metrics and alarms". Every alarm emails the team
# when something breaks and again when it is OK:
#   - any Lambda fails                       (AWS/Lambda Errors)
#   - a Step Functions execution fails       (AWS/States ExecutionsFailed / TimedOut)
#   - the ingestion stops running            (no ingest invocations for 12 h)
#   - events end up in the dead-letter queue (AWS/SQS messages visible)
#   - the API returns server errors          (AWS/ApiGateway 5xx)
#
# Own SNS topic: the admin-alerts topic of core is encrypted with the AWS managed
# key (alias/aws/sns), and CloudWatch cannot publish to topics encrypted with it.
# This topic uses a customer managed key that allows CloudWatch to publish.
# ---------------------------------------------------------------------------
data "aws_caller_identity" "current" {}

locals {
  name    = "${var.project}-alarms"
  account = data.aws_caller_identity.current.account_id

  state_machine_arns = {
    for sm in var.state_machines :
    sm => "arn:aws:states:${var.region}:${local.account}:stateMachine:${var.project}-${sm}"
  }

  dlq_name = try(element(split(":", local.core.dlq_arn), 5), null)
  api_id   = try(one(data.aws_apigatewayv2_apis.http.ids), null)

  alarm_actions = [aws_sns_topic.alarms.arn]
}

data "aws_apigatewayv2_apis" "http" {
  name          = "${var.project}-http-api"
  protocol_type = "HTTP"
}

# ---------------------------------------------------------------------------
# Topic for the alarm emails (encrypted with a key CloudWatch may use)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "alarms_key" {
  statement {
    sid       = "AccountAdministers"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account}:root"]
    }
  }

  statement {
    sid       = "CloudWatchPublishesAlarms"
    actions   = ["kms:GenerateDataKey*", "kms:Decrypt"]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
  }
}

resource "aws_kms_key" "alarms" {
  description         = "Encrypts the ${local.name} SNS topic (CloudWatch may publish)"
  enable_key_rotation = true
  policy              = data.aws_iam_policy_document.alarms_key.json
}

resource "aws_kms_alias" "alarms" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.alarms.key_id
}

resource "aws_sns_topic" "alarms" {
  name              = local.name
  kms_master_key_id = aws_kms_key.alarms.arn
}

data "aws_iam_policy_document" "alarms_topic" {
  statement {
    sid       = "CloudWatchAlarmsOfThisAccount"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alarms.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_sns_topic_policy" "alarms" {
  arn    = aws_sns_topic.alarms.arn
  policy = data.aws_iam_policy_document.alarms_topic.json
}

resource "aws_sns_topic_subscription" "alarm_email" {
  for_each = toset(var.alarm_emails)

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
}

# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(var.lambda_functions)

  alarm_name        = "${var.project}-${each.value}-errors"
  alarm_description = "The Lambda ${var.project}-${each.value} failed. Check its logs in CloudWatch (/aws/lambda/${var.project}-${each.value})."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  dimensions  = { FunctionName = "${var.project}-${each.value}" }
  statistic   = "Sum"
  period      = 300

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching" # no runs = no errors

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "workflow_failed" {
  for_each = local.state_machine_arns

  alarm_name        = "${var.project}-${each.key}-failed"
  alarm_description = "An execution of the Step Functions workflow ${var.project}-${each.key} failed or timed out. Open it in the Step Functions console to see which step."

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "problems"
    expression  = "failed + timedout"
    label       = "Failed or timed out executions"
    return_data = true
  }

  metric_query {
    id = "failed"
    metric {
      namespace   = "AWS/States"
      metric_name = "ExecutionsFailed"
      dimensions  = { StateMachineArn = each.value }
      stat        = "Sum"
      period      = 300
    }
  }

  metric_query {
    id = "timedout"
    metric {
      namespace   = "AWS/States"
      metric_name = "ExecutionsTimedOut"
      dimensions  = { StateMachineArn = each.value }
      stat        = "Sum"
      period      = 300
    }
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "ingestion_stopped" {
  alarm_name        = "${var.project}-ingestion-stopped"
  alarm_description = "The ingest Lambda has not run for ${2 * var.ingest_every_hours} hours: check the EventBridge schedule ${var.project}-ingest-4x-day."

  namespace   = "AWS/Lambda"
  metric_name = "Invocations"
  dimensions  = { FunctionName = "${var.project}-ingest" }
  statistic   = "Sum"
  period      = var.ingest_every_hours * 3600

  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 2
  treat_missing_data  = "breaching" # no data = it did not run

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  count = local.dlq_name == null ? 0 : 1

  alarm_name        = "${var.project}-dlq-not-empty"
  alarm_description = "There are events in the dead-letter queue ${local.dlq_name}: something could not be processed."

  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  dimensions  = { QueueName = local.dlq_name }
  statistic   = "Maximum"
  period      = 300

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  count = local.api_id == null ? 0 : 1

  alarm_name        = "${var.project}-api-5xx"
  alarm_description = "The API returned 5 or more server errors (5xx) in 5 minutes. Check the logs of ${var.project}-api."

  namespace   = "AWS/ApiGateway"
  metric_name = "5xx"
  dimensions  = { ApiId = local.api_id }
  statistic   = "Sum"
  period      = 300

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# ---------------------------------------------------------------------------
# Dashboard: the health of the whole pipeline on one page
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project

  dashboard_body = jsonencode({
    widgets = concat(
      [
        {
          type   = "alarm"
          x      = 0
          y      = 0
          width  = 24
          height = 4
          properties = {
            title = "Alarms"
            alarms = concat(
              [for a in aws_cloudwatch_metric_alarm.lambda_errors : a.arn],
              [for a in aws_cloudwatch_metric_alarm.workflow_failed : a.arn],
              [aws_cloudwatch_metric_alarm.ingestion_stopped.arn],
              [for a in aws_cloudwatch_metric_alarm.dlq_not_empty : a.arn],
              [for a in aws_cloudwatch_metric_alarm.api_5xx : a.arn],
            )
          }
        },
        {
          type   = "metric"
          x      = 0
          y      = 4
          width  = 12
          height = 6
          properties = {
            title  = "Lambda errors"
            region = var.region
            stat   = "Sum"
            period = 3600
            view   = "timeSeries"
            metrics = [
              for f in var.lambda_functions : ["AWS/Lambda", "Errors", "FunctionName", "${var.project}-${f}"]
            ]
          }
        },
        {
          type   = "metric"
          x      = 12
          y      = 4
          width  = 12
          height = 6
          properties = {
            title  = "Step Functions executions"
            region = var.region
            stat   = "Sum"
            period = 3600
            view   = "timeSeries"
            # concat (not flatten): each metric must stay a list of its own
            metrics = concat(
              [for sm, arn in local.state_machine_arns : ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", arn, { label = "${sm} succeeded" }]],
              [for sm, arn in local.state_machine_arns : ["AWS/States", "ExecutionsFailed", "StateMachineArn", arn, { label = "${sm} failed" }]],
            )
          }
        },
        {
          type   = "metric"
          x      = 0
          y      = 10
          width  = 12
          height = 6
          properties = {
            title  = "Ingestion runs (4 per day)"
            region = var.region
            stat   = "Sum"
            period = 21600
            view   = "timeSeries"
            metrics = [
              ["AWS/Lambda", "Invocations", "FunctionName", "${var.project}-ingest"],
            ]
          }
        },
      ],
      local.api_id == null ? [] : [
        {
          type   = "metric"
          x      = 12
          y      = 10
          width  = 12
          height = 6
          properties = {
            title  = "API: requests and errors"
            region = var.region
            stat   = "Sum"
            period = 300
            view   = "timeSeries"
            metrics = [
              ["AWS/ApiGateway", "Count", "ApiId", local.api_id, { label = "requests" }],
              ["AWS/ApiGateway", "4xx", "ApiId", local.api_id, { label = "4xx" }],
              ["AWS/ApiGateway", "5xx", "ApiId", local.api_id, { label = "5xx" }],
            ]
          }
        },
      ],
    )
  })
}
