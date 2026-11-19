
variable "enable_predict_runtime" {
  description = "Deploy the ML prediction Lambda without switching Phase B to use it"
  type        = bool
  default     = false
}

resource "aws_iam_role" "predict_runtime" {
  count = var.enable_predict_runtime ? 1 : 0
  name  = "${var.project}-predict-ml-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "predict_runtime" {
  count = var.enable_predict_runtime ? 1 : 0
  name  = "predict-ml-least-privilege"
  role  = aws_iam_role.predict_runtime[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "arn:aws:s3:::${var.retraining_lake_bucket}/clean/*",
          "arn:aws:s3:::${var.retraining_lake_bucket}/models/production/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:BatchWriteItem", "dynamodb:PutItem"]
        Resource = local.core.table_arns.predictions
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "predict_runtime_logs" {
  count      = var.enable_predict_runtime ? 1 : 0
  role       = aws_iam_role.predict_runtime[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "predict_runtime" {
  count             = var.enable_predict_runtime ? 1 : 0
  name              = "/aws/lambda/${var.project}-predict-ml"
  retention_in_days = 14
}

resource "aws_lambda_function" "predict_runtime" {
  count         = var.enable_predict_runtime ? 1 : 0
  function_name = "${var.project}-predict-ml"
  role          = aws_iam_role.predict_runtime[0].arn

  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.ml_predict.repository_url}:v2"
  architectures = ["x86_64"]

  timeout     = 300
  memory_size = 512

  environment {
    variables = {
      LAKE_BUCKET       = var.retraining_lake_bucket
      PREDICTIONS_TABLE = local.core.tables.predictions
      MODEL_PREFIX      = "models/production/"
      TTL_DAYS          = "7"
    }
  }

  depends_on = [
    aws_iam_role_policy.predict_runtime,
    aws_iam_role_policy_attachment.predict_runtime_logs,
    aws_cloudwatch_log_group.predict_runtime
  ]
}

output "predict_ml_lambda_arn" {
  value = var.enable_predict_runtime ? aws_lambda_function.predict_runtime[0].arn : null
}
