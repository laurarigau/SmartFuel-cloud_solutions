# Orchestrator: replaces the Step Functions state machine (not available in the sandbox).
#
#   S3 "Object Created" on raw/  --EventBridge rule-->  smartfuel-process
#     smartfuel-process: validate -> clean -> save-changes | predict  (retry + catch)
#     on final failure: admin alert (SNS if it exists, ERROR log line) + event to the DLQ (if it exists)

locals {
  process_name = "${var.project}-process"
}

# ---------------------------------------------------------------------------
# Role: may only invoke the 4 step Lambdas (+ SNS / DLQ when they exist)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "process" {
  name               = "${local.process_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "process" {
  statement {
    sid       = "InvokeSteps"
    actions   = ["lambda:InvokeFunction"]
    resources = [for f in aws_lambda_function.lambda : f.arn]
  }
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.process.arn}:*"]
  }
  dynamic "statement" {
    for_each = local.admin_topic == null ? [] : [local.admin_topic]
    content {
      sid       = "AlertAdmins"
      actions   = ["sns:Publish"]
      resources = [statement.value]
    }
  }
  dynamic "statement" {
    for_each = local.dlq_arn == null ? [] : [local.dlq_arn]
    content {
      sid       = "FailedEventsToDlq"
      actions   = ["sqs:SendMessage"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "process" {
  name   = "least-privilege"
  role   = aws_iam_role.process.id
  policy = data.aws_iam_policy_document.process.json
}

# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------
data "archive_file" "process" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/lambdas/process"
  output_path = "${path.module}/build/process.zip"
  excludes    = ["test_handler.py", "__pycache__"]
}

resource "aws_cloudwatch_log_group" "process" {
  name              = "/aws/lambda/${local.process_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "process" {
  function_name    = local.process_name
  role             = aws_iam_role.process.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.process.output_path
  source_code_hash = data.archive_file.process.output_base64sha256
  timeout          = 900 # waits for the 4 steps, retries included
  memory_size      = 128

  environment {
    variables = {
      for k, v in {
        FN_VALIDATE     = aws_lambda_function.lambda["validate"].function_name
        FN_CLEAN        = aws_lambda_function.lambda["clean"].function_name
        FN_SAVE_CHANGES = aws_lambda_function.lambda["save-changes"].function_name
        FN_PREDICT      = aws_lambda_function.lambda["predict"].function_name
        MAX_ATTEMPTS    = "3"
        ADMIN_TOPIC_ARN = local.admin_topic
      } : k => v if v != null
    }
  }

  depends_on = [aws_cloudwatch_log_group.process, aws_iam_role_policy.process]
}

# One file = one run: no automatic re-run of the whole chain (the orchestrator
# already retries each step). Failed events go to the DLQ when it exists.
resource "aws_lambda_function_event_invoke_config" "process" {
  function_name                = aws_lambda_function.process.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600

  dynamic "destination_config" {
    for_each = local.dlq_arn == null ? [] : [local.dlq_arn]
    content {
      on_failure {
        destination = destination_config.value
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Trigger: every new object under raw/ in the lake (core enables EventBridge on the bucket)
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "raw_created" {
  name        = "${var.project}-raw-object-created"
  description = "New raw snapshot in the lake -> processing"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [local.core.lake_bucket] }
      object = { key = [{ prefix = "raw/" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "process" {
  rule      = aws_cloudwatch_event_rule.raw_created.name
  target_id = "process"
  arn       = aws_lambda_function.process.arn

  retry_policy {
    maximum_retry_attempts       = 3
    maximum_event_age_in_seconds = 3600
  }
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeRawCreated"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.process.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.raw_created.arn
}
