
# Phase C — Weekly ML retraining
# Step Functions and email delivery remain disabled.

variable "enable_ml_retraining" {
  type    = bool
  default = false
}

variable "enable_weekly_scheduler" {
  type    = bool
  default = false
}

variable "retraining_lake_bucket" {
  type    = string
  default = ""
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
  role  = aws_iam_role.ml_train[0].id
  name  = "${var.project}-train-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${var.retraining_lake_bucket}"
        Condition = {
          StringLike = {
            "s3:prefix" = ["raw/*"]
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.retraining_lake_bucket}/raw/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${var.retraining_lake_bucket}/models/candidates/*"
      },
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.ml_evaluate[0].arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
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
        Resource = "arn:aws:s3:::${var.retraining_lake_bucket}"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "arn:aws:s3:::${var.retraining_lake_bucket}/models/candidates/*",
          "arn:aws:s3:::${var.retraining_lake_bucket}/models/production/metadata.json"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${var.retraining_lake_bucket}/models/candidates/*"
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
      LAKE_BUCKET = var.retraining_lake_bucket
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
  image_uri     = "${aws_ecr_repository.ml_train.repository_url}:v1"
  architectures = ["arm64"]

  role        = aws_iam_role.ml_train[0].arn
  memory_size = 2048
  timeout     = 900

  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      LAKE_BUCKET            = var.retraining_lake_bucket
      RAW_PREFIX             = "raw/"
      MODEL_OUTPUT_DIR       = "/tmp/smartfuel-model"
      EVALUATE_FUNCTION_NAME = aws_lambda_function.ml_evaluate[0].function_name
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
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.ml_train[0].arn
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
    arn      = aws_lambda_function.ml_train[0].arn
    role_arn = aws_iam_role.ml_scheduler[0].arn
    input    = "{}"
  }

  depends_on = [
    aws_iam_role_policy.ml_scheduler
  ]
}
