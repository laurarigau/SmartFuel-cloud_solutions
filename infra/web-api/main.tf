# Phase D · Web, API & auth
# Owner: Marc Farràs
#
# Done:
#   [x] Lambda "api" (src/lambdas/api): GET /stations?geohash=, GET /stations/{id}
#   [x] API Gateway HTTP API with throttling, public routes
# TODO:
#   [ ] Cognito User Pool + app client + group "admins" (create ONCE: the sandbox cannot delete pools)
#   [ ] JWT authorizer on private routes: GET/POST/DELETE /subscriptions, /admin/*
#   [ ] GET /predictions/{id}
#   [ ] Hosting for frontend/ (Amplify, pending sandbox permissions)

locals {
  name = "${var.project}-api"
}

# ---------------------------------------------------------------------------
# IAM role for the API Lambda: read-only access to the tables it needs
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

resource "aws_iam_role" "api" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "api" {
  statement {
    sid     = "ReadStations"
    actions = ["dynamodb:GetItem", "dynamodb:Query"]

    resources = [
      local.core.table_arns.stations,
      "${local.core.table_arns.stations}/index/geohash5-index",
    ]
  }

  statement {
    sid       = "ReadLatestPrices"
    actions   = ["dynamodb:Query"]
    resources = [local.core.table_arns.latest_prices]
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "least-privilege"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ---------------------------------------------------------------------------
# Lambda: code zipped from src/lambdas/api (tests excluded)
# ---------------------------------------------------------------------------
data "archive_file" "api" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/lambdas/api"
  output_path = "${path.module}/build/api.zip"
  excludes    = ["test_handler.py", "__pycache__"]
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "api" {
  function_name    = local.name
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      STATIONS_TABLE = local.core.tables.stations
      PRICES_TABLE   = local.core.tables.latest_prices
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]
}

# ---------------------------------------------------------------------------
# API Gateway HTTP API
# ---------------------------------------------------------------------------
resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project}-http-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "list_stations" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "GET /stations"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "get_station" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "GET /stations/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  # Throttling: protects the backend (and the $30 budget) from abuse
  default_route_settings {
    throttling_rate_limit  = 20
    throttling_burst_limit = 50
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
