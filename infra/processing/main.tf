# Phase B · Processing
# Owner: Carla Escassi
#
#   [x] Lambdas validate / clean / save-changes / predict (src/lambdas/*), one least-privilege role each
#   [x] EventBridge rule: S3 "Object Created" on raw/ -> orchestrator Lambda "process" (process.tf)
#   [x] Orchestrator: validate -> (valid?) -> clean -> save-changes | predict in parallel,
#       retry with backoff + catch -> admin alert, failed events -> DLQ (when it exists)
#
# Step Functions is not available in the university sandbox (see ml/README.md), so the
# orchestrator Lambda does what the state machine in the diagram would do.
# SNS / SQS are optional: core creates them only when enable_messaging = true.
#
# Manual test: scripts/test_processing.sh (uploads fixtures/fuel_prices_sample.json and runs the 4 Lambdas)

locals {
  lake_arn    = local.core.lake_bucket_arn
  admin_topic = try(local.core.admin_alerts_topic_arn, null) # null when SNS is disabled
  dlq_arn     = try(local.core.dlq_arn, null)                # null when SQS is disabled

  # Settings for the 4 Lambdas. pandas = needs the AWS SDK for pandas layer.
  lambdas = {
    validate = {
      timeout = 60
      memory  = 512
      pandas  = false
      # ADMIN_TOPIC_ARN only when SNS exists
      env = {
        for k, v in {
          LAKE_BUCKET     = local.core.lake_bucket
          MIN_STATIONS    = tostring(var.min_stations)
          ADMIN_TOPIC_ARN = local.admin_topic
        } : k => v if v != null
      }
    }
    clean = {
      timeout = 300
      memory  = 512
      pandas  = true
      env = {
        LAKE_BUCKET   = local.core.lake_bucket
        LOOKBACK_DAYS = "7"
      }
    }
    save-changes = {
      timeout = 300
      memory  = 256
      pandas  = false
      env = {
        LAKE_BUCKET         = local.core.lake_bucket
        LATEST_PRICES_TABLE = local.core.tables.latest_prices
        STATIONS_TABLE      = local.core.tables.stations
      }
    }
    predict = {
      timeout = 300
      memory  = 512
      pandas  = true
      env = {
        LAKE_BUCKET       = local.core.lake_bucket
        PREDICTIONS_TABLE = local.core.tables.predictions
        MODEL_PREFIX      = "models/production/"
        TTL_DAYS          = "7"
      }
    }
  }
}

# ---------------------------------------------------------------------------
# AWS SDK for pandas layer (pandas + pyarrow), managed by AWS.
# Latest Python 3.12 / x86_64 version from AWS public SSM parameters,
# unless var.pandas_layer_arn is set.
# ---------------------------------------------------------------------------
data "aws_ssm_parameters_by_path" "pandas_layers" {
  path      = "/aws/service/aws-sdk-pandas"
  recursive = true
}

locals {
  pandas_candidates = [
    for i, name in data.aws_ssm_parameters_by_path.pandas_layers.names :
    data.aws_ssm_parameters_by_path.pandas_layers.values[i]
    if endswith(name, "/py3.12/x86_64/layer-arn")
  ]
  # The ARN ends in ":<layer version>": take the highest
  pandas_versions  = [for arn in local.pandas_candidates : tonumber(reverse(split(":", arn))[0])]
  pandas_layer_arn = var.pandas_layer_arn != "" ? var.pandas_layer_arn : local.pandas_candidates[index(local.pandas_versions, max(local.pandas_versions...))]
}

# ---------------------------------------------------------------------------
# IAM: one role per Lambda, only the permissions it needs
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each           = local.lambdas
  name               = "${var.project}-${each.key}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "validate" {
  statement {
    sid       = "ReadAndRemoveRaw"
    actions   = ["s3:GetObject", "s3:DeleteObject"]
    resources = ["${local.lake_arn}/raw/*"]
  }
  statement {
    sid       = "WriteQuarantine"
    actions   = ["s3:PutObject"]
    resources = ["${local.lake_arn}/quarantine/*"]
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

data "aws_iam_policy_document" "clean" {
  statement {
    sid       = "ReadRawAndClean"
    actions   = ["s3:GetObject"]
    resources = ["${local.lake_arn}/raw/*", "${local.lake_arn}/clean/*"]
  }
  statement {
    sid       = "WriteCleanAndChanges"
    actions   = ["s3:PutObject"]
    resources = ["${local.lake_arn}/clean/*", "${local.lake_arn}/changes/*"]
  }
  statement {
    sid       = "ListCleanToFindPreviousSnapshot"
    actions   = ["s3:ListBucket"]
    resources = [local.lake_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["clean/*"]
    }
  }
}

data "aws_iam_policy_document" "save_changes" {
  statement {
    sid       = "ReadChanges"
    actions   = ["s3:GetObject"]
    resources = ["${local.lake_arn}/changes/*"]
  }
  statement {
    sid       = "WritePricesAndStations"
    actions   = ["dynamodb:BatchWriteItem", "dynamodb:PutItem"]
    resources = [local.core.table_arns.latest_prices, local.core.table_arns.stations]
  }
}

data "aws_iam_policy_document" "predict" {
  statement {
    sid       = "ReadCleanAndModels"
    actions   = ["s3:GetObject"]
    resources = ["${local.lake_arn}/clean/*", "${local.lake_arn}/models/*"]
  }
  statement {
    sid       = "WritePredictions"
    actions   = ["dynamodb:BatchWriteItem", "dynamodb:PutItem"]
    resources = [local.core.table_arns.predictions]
  }
}

locals {
  policies = {
    validate     = data.aws_iam_policy_document.validate.json
    clean        = data.aws_iam_policy_document.clean.json
    save-changes = data.aws_iam_policy_document.save_changes.json
    predict      = data.aws_iam_policy_document.predict.json
  }
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.lambdas
  name     = "least-privilege"
  role     = aws_iam_role.lambda[each.key].id
  policy   = local.policies[each.key]
}

data "aws_iam_policy_document" "logs" {
  for_each = local.lambdas
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  for_each = local.lambdas
  name     = "own-logs"
  role     = aws_iam_role.lambda[each.key].id
  policy   = data.aws_iam_policy_document.logs[each.key].json
}

# ---------------------------------------------------------------------------
# Lambdas: code zipped from src/lambdas/<name> (tests excluded)
# ---------------------------------------------------------------------------
data "archive_file" "lambda" {
  for_each    = local.lambdas
  type        = "zip"
  source_dir  = "${path.module}/../../src/lambdas/${each.key}"
  output_path = "${path.module}/build/${each.key}.zip"
  excludes    = ["test_handler.py", "__pycache__"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambdas
  name              = "/aws/lambda/${var.project}-${each.key}"
  retention_in_days = 14
}

resource "aws_lambda_function" "lambda" {
  for_each         = local.lambdas
  function_name    = "${var.project}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  timeout          = each.value.timeout
  memory_size      = each.value.memory
  layers           = each.value.pandas ? [local.pandas_layer_arn] : []

  environment {
    variables = each.value.env
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda,
    aws_iam_role_policy.logs,
  ]
}
