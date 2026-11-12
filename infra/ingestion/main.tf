
locals {
  lake_bucket = local.core.lake_bucket
  lambda_name = "${var.project}-ingest"
}

data "archive_file" "ingest_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/package"
  output_path = "${path.module}/.terraform/smartfuel-ingest.zip"
}

resource "aws_iam_role" "ingest_lambda" {
  name = "${local.lambda_name}-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ingest_lambda" {
  name = "${local.lambda_name}-permissions"
  role = aws_iam_role.ingest_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${local.lake_bucket}/raw/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "ingest" {
  function_name    = local.lambda_name
  role             = aws_iam_role.ingest_lambda.arn
  filename         = data.archive_file.ingest_lambda.output_path
  source_code_hash = data.archive_file.ingest_lambda.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 128

  environment {
    variables = {
      LAKE_BUCKET = local.lake_bucket
    }
  }

  depends_on = [aws_iam_role_policy.ingest_lambda]
}
