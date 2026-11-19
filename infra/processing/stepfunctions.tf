# Phase B · Orchestration with Step Functions (as in the architecture diagram).
#
#   S3 "Object Created" on raw/ --EventBridge rule--> state machine smartfuel-processing
#                                    (delivery failures -> SQS DLQ)
#   Validate -> IsValid? --no--> Quarantined (file already in quarantine/, admins alerted by validate)
#                        --yes-> Clean -> Parallel( SaveChanges | Predict )
#   Every task: Retry 3 attempts (2 s, 4 s) + Catch -> NotifyFailure (SNS admin-alerts) -> Failed
#
# Replaces the orchestrator Lambda "process" used while Step Functions was unavailable.

locals {
  state_machine_name = "${var.project}-processing"
  dlq_url            = try(local.core.dlq_url, null)

  # Same retry policy on every task: 3 attempts in total, waiting 2 s then 4 s
  task_retry = [{
    ErrorEquals     = ["States.ALL"]
    IntervalSeconds = 2
    MaxAttempts     = 2
    BackoffRate     = 2
  }]
  on_error = local.admin_topic == null ? "Failed" : "NotifyFailure"
  task_catch = [{
    ErrorEquals = ["States.ALL"]
    ResultPath  = "$.error"
    Next        = local.on_error
  }]

  invoke = { for k, f in aws_lambda_function.lambda : k => {
    Type     = "Task"
    Resource = "arn:aws:states:::lambda:invoke"
    Parameters = {
      FunctionName = k == "predict" && var.predict_lambda_arn != "" ? var.predict_lambda_arn : f.arn
      "Payload.$"  = "$"
    }
    OutputPath = "$.Payload"
    Retry      = local.task_retry
  } }

  # Only when SNS exists (core enable_messaging = true)
  notify_state = { for k, v in {
    NotifyFailure = {
      Type     = "Task"
      Resource = "arn:aws:states:::sns:publish"
      Parameters = {
        TopicArn    = local.admin_topic
        Subject     = "SmartFuel: processing failed"
        "Message.$" = "States.JsonToString($)"
      }
      Catch = [{ ErrorEquals = ["States.ALL"], Next = "Failed" }]
      Next  = "Failed"
    }
  } : k => v if local.admin_topic != null }

  definition = {
    Comment = "SmartFuel Phase B: process one raw/ snapshot"
    StartAt = "Validate"
    States = merge({
      Validate = merge(local.invoke["validate"], { Catch = local.task_catch, Next = "IsValid" })

      IsValid = {
        Type    = "Choice"
        Choices = [{ Variable = "$.valid", BooleanEquals = true, Next = "Clean" }]
        Default = "Quarantined"
      }

      Quarantined = {
        Type    = "Succeed"
        Comment = "Invalid file: validate already moved it to quarantine/ and alerted"
      }

      Clean = merge(local.invoke["clean"], { Catch = local.task_catch, Next = "SaveAndPredict" })

      SaveAndPredict = {
        Type = "Parallel"
        Branches = [
          { StartAt = "SaveChanges", States = { SaveChanges = merge(local.invoke["save-changes"], { End = true }) } },
          { StartAt = "Predict", States = { Predict = merge(local.invoke["predict"], { End = true }) } },
        ]
        ResultSelector = { "save_changes.$" = "$[0]", "predict.$" = "$[1]" }
        Catch          = local.task_catch
        End            = true
      }

      Failed = {
        Type  = "Fail"
        Error = "ProcessingFailed"
        Cause = "A step failed 3 times: see the execution history"
      }
    }, local.notify_state)
  }
}

# ---------------------------------------------------------------------------
# State machine + its role (may only invoke the 4 Lambdas and publish to admin-alerts)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.state_machine_name}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid     = "InvokeSteps"
    actions = ["lambda:InvokeFunction"]
    resources = concat(
      flatten([
        for f in aws_lambda_function.lambda : [f.arn, "${f.arn}:*"]
      ]),
      var.predict_lambda_arn == "" ? [] : [
        var.predict_lambda_arn,
        "${var.predict_lambda_arn}:*"
      ]
    )
  }
  dynamic "statement" {
    for_each = local.admin_topic == null ? [] : [local.admin_topic]
    content {
      sid       = "AlertAdmins"
      actions   = ["sns:Publish"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "least-privilege"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

resource "aws_sfn_state_machine" "processing" {
  name       = local.state_machine_name
  role_arn   = aws_iam_role.sfn.arn
  type       = "STANDARD"
  definition = jsonencode(local.definition)

  depends_on = [aws_iam_role_policy.sfn]
}

# ---------------------------------------------------------------------------
# Trigger: every new object under raw/ -> one execution. Undeliverable events -> DLQ.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "raw_created" {
  name        = "${var.project}-raw-object-created"
  description = "New raw snapshot in the lake -> processing state machine"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [local.core.lake_bucket] }
      object = { key = [{ prefix = "raw/" }] }
    }
  })
}

data "aws_iam_policy_document" "events_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "events" {
  name               = "${var.project}-raw-created-events"
  assume_role_policy = data.aws_iam_policy_document.events_assume.json
}

resource "aws_iam_role_policy" "events" {
  name = "start-processing"
  role = aws_iam_role.events.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.processing.arn
    }]
  })
}

resource "aws_cloudwatch_event_target" "processing" {
  rule      = aws_cloudwatch_event_rule.raw_created.name
  target_id = "processing"
  arn       = aws_sfn_state_machine.processing.arn
  role_arn  = aws_iam_role.events.arn

  retry_policy {
    maximum_retry_attempts       = 3
    maximum_event_age_in_seconds = 3600
  }

  dynamic "dead_letter_config" {
    for_each = local.dlq_arn == null ? [] : [local.dlq_arn]
    content {
      arn = dead_letter_config.value
    }
  }
}

# The DLQ (created by core) must allow EventBridge to drop failed events into it.
# core defines no queue policy, so this stack owns it: if another stack ever needs
# one, merge the statements here instead of adding a second policy.
resource "aws_sqs_queue_policy" "dlq_from_eventbridge" {
  count     = local.dlq_url == null ? 0 : 1
  queue_url = local.dlq_url
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EventBridgeRawCreatedDlq"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = local.dlq_arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.raw_created.arn } }
    }]
  })
}
