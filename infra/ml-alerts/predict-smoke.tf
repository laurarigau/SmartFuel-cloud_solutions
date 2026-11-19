
resource "aws_iam_role" "predict_smoke" {
  name = "${var.project}-predict-smoke-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "predict_smoke" {
  name = "read-candidate-and-clean"
  role = aws_iam_role.predict_smoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject"]
      Resource = [
        "arn:aws:s3:::${local.lake_bucket}/clean/*",
        "arn:aws:s3:::${local.lake_bucket}/models/candidates/*"
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "predict_smoke_logs" {
  role       = aws_iam_role.predict_smoke.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "predict_smoke" {
  name              = "/aws/lambda/${var.project}-predict-smoke"
  retention_in_days = 7
}

resource "aws_lambda_function" "predict_smoke" {
  function_name = "${var.project}-predict-smoke"
  role          = aws_iam_role.predict_smoke.arn

  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.ml_predict.repository_url}:v2"
  architectures = ["x86_64"]

  timeout     = 120
  memory_size = 512

  image_config {
    command = ["predict_smoke.lambda_handler"]
  }

  depends_on = [
    aws_iam_role_policy.predict_smoke,
    aws_iam_role_policy_attachment.predict_smoke_logs,
    aws_cloudwatch_log_group.predict_smoke
  ]
}
