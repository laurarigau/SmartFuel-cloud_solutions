
# Phase C — Weekly ML retraining
# Weekly retraining: Scheduler -> Step Functions -> Train -> Evaluate.

variable "enable_ml_retraining" {
  type    = bool
  default = true
}

variable "enable_weekly_scheduler" {
  type    = bool
  default = true
}

variable "retraining_lake_bucket" {
  description = "Lake bucket used by the ML Lambdas and Athena. Empty = the lake bucket of core"
  type        = string
  default     = ""
}

# Docker image repository
resource "aws_ecr_repository" "ml_train" {
  name                 = "${var.project}-train"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Package evaluate (only needs boto3)
data "archive_file" "ml_evaluate" {
  count       = var.enable_ml_retraining ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/../../src/lambdas/evaluate/handler.py"
  output_path = "${path.module}/.terraform/evaluate.zip"
}

# Roles
resource "aws_iam_role" "ml_train" {
  count = var.enable_ml_retraining ? 1 : 0
  name  = "${var.project}-train-role"

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

resource "aws_iam_role" "ml_evaluate" {
  count = var.enable_ml_retraining ? 1 : 0
  name  = "${var.project}-evaluate-role"

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

# Logs
resource "aws_cloudwatch_log_group" "ml_train" {
  count             = var.enable_ml_retraining ? 1 : 0
  name              = "/aws/lambda/${var.project}-train"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "ml_evaluate" {
  count             = var.enable_ml_retraining ? 1 : 0
  name              = "/aws/lambda/${var.project}-evaluate"
  retention_in_days = 7
}

# Train permissions

resource "aws_iam_role_policy" "ml_train" {
  count = var.enable_ml_retraining ? 1 : 0
  name  = "${var.project}-train-policy"
  role  = aws_iam_role.ml_train[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${local.lake_bucket}"
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "clean/", "clean/*",
              "athena-results/ml/", "athena-results/ml/*"
            ]
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation"]
        Resource = "arn:aws:s3:::${local.lake_bucket}"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "arn:aws:s3:::${local.lake_bucket}/clean/*",
          "arn:aws:s3:::${local.lake_bucket}/athena-results/ml/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:AbortMultipartUpload"]
        Resource = "arn:aws:s3:::${local.lake_bucket}/athena-results/ml/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${local.lake_bucket}/models/candidates/*"
      },
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetWorkGroup"
        ]
        Resource = aws_athena_workgroup.ml.arn
      },
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"]
        Resource = [
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:catalog",
          aws_glue_catalog_database.ml.arn,
          aws_glue_catalog_table.clean_prices.arn
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.ml_train[0].arn}:*"
      }
    ]
  })
}

# Evaluate permissions

resource "aws_iam_role_policy" "ml_evaluate" {
  count = var.enable_ml_retraining ? 1 : 0
  role  = aws_iam_role.ml_evaluate[0].id
  name  = "${var.project}-evaluate-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${local.lake_bucket}"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "arn:aws:s3:::${local.lake_bucket}/models/candidates/*",
          "arn:aws:s3:::${local.lake_bucket}/models/production/metadata.json"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${local.lake_bucket}/models/candidates/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.ml_evaluate[0].arn}:*"
      }
    ]
  })
}


# Evaluate Lambda
resource "aws_lambda_function" "ml_evaluate" {
  count         = var.enable_ml_retraining ? 1 : 0
  function_name = "${var.project}-evaluate"

  filename         = data.archive_file.ml_evaluate[0].output_path
  source_code_hash = data.archive_file.ml_evaluate[0].output_base64sha256

  role        = aws_iam_role.ml_evaluate[0].arn
  handler     = "handler.lambda_handler"
  runtime     = "python3.11"
  memory_size = 128
  timeout     = 30

  environment {
    variables = {
      LAKE_BUCKET = local.lake_bucket
    }
  }

  depends_on = [
    aws_iam_role_policy.ml_evaluate,
    aws_cloudwatch_log_group.ml_evaluate
  ]
}

# Train Lambda
resource "aws_lambda_function" "ml_train" {
  count         = var.enable_ml_retraining ? 1 : 0
  function_name = "${var.project}-train"

  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.ml_train.repository_url}:v2"
  architectures = ["arm64"]

  role        = aws_iam_role.ml_train[0].arn
  memory_size = 512
  timeout     = 900

  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      LAKE_BUCKET                   = local.lake_bucket
      MODEL_OUTPUT_DIR              = "/tmp/smartfuel-model"
      TRAINING_SOURCE               = "athena"
      ATHENA_DATABASE               = aws_glue_catalog_database.ml.name
      ATHENA_TABLE                  = aws_glue_catalog_table.clean_prices.name
      ATHENA_WORKGROUP              = aws_athena_workgroup.ml.name
      ATHENA_LOOKBACK_DAYS          = "8"
      ATHENA_STATION_SAMPLE_MODULUS = "10"
      RF_N_JOBS                     = "1"
    }
  }

  depends_on = [
    aws_iam_role_policy.ml_train,
    aws_cloudwatch_log_group.ml_train
  ]
}

# EventBridge Scheduler role
resource "aws_iam_role" "ml_scheduler" {
  count = var.enable_ml_retraining ? 1 : 0
  name  = "${var.project}-ml-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "sts:AssumeRole"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
    }]
  })
}


resource "aws_iam_role_policy" "ml_scheduler" {
  count = var.enable_ml_retraining ? 1 : 0
  role  = aws_iam_role.ml_scheduler[0].id
  name  = "${var.project}-ml-scheduler-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["states:StartExecution"]
      Resource = aws_sfn_state_machine.ml_retraining[0].arn
    }]
  })
}


# Weekly schedule: Monday 03:00 UTC
resource "aws_scheduler_schedule" "ml_weekly" {
  count = var.enable_ml_retraining ? 1 : 0

  name                         = "${var.project}-weekly-train"
  schedule_expression          = "cron(0 3 ? * MON *)"
  schedule_expression_timezone = "Etc/UTC"

  state = var.enable_weekly_scheduler ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.ml_retraining[0].arn
    role_arn = aws_iam_role.ml_scheduler[0].arn
    input    = "{}"
  }

  depends_on = [
    aws_iam_role_policy.ml_scheduler
  ]
}
