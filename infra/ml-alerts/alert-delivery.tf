
variable "enable_alert_publish" {
  type    = bool
  default = false
}

variable "enable_alert_delivery" {
  type    = bool
  default = false
}

variable "alert_sender_email" {
  type    = string
  default = ""
}

resource "aws_sns_topic" "price_alerts" {
  name = "${var.project}-phase-c-price-alerts"
}

resource "aws_iam_role_policy" "check_alerts_sns" {
  name = "publish-price-alerts"
  role = aws_iam_role.check_alerts.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = aws_sns_topic.price_alerts.arn
    }]
  })
}

data "archive_file" "send_email" {
  type        = "zip"
  source_file = "${path.module}/../../src/lambdas/send-email/handler.py"
  output_path = "${path.module}/.terraform/send-email.zip"
}

resource "aws_iam_role" "send_email" {
  name = "${var.project}-send-email-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "send_email_logs" {
  role       = aws_iam_role.send_email.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "send_email_ses" {
  name = "send-verified-email"
  role = aws_iam_role.send_email.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:SendEmail"]
      Resource = "arn:aws:ses:${var.region}:${data.aws_caller_identity.current.account_id}:identity/${var.alert_sender_email != "" ? var.alert_sender_email : "disabled.invalid"}"
    }]
  })
}

resource "aws_cloudwatch_log_group" "send_email" {
  name              = "/aws/lambda/${var.project}-send-email"
  retention_in_days = 7
}

resource "aws_lambda_function" "send_email" {
  function_name    = "${var.project}-send-email"
  role             = aws_iam_role.send_email.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.send_email.output_path
  source_code_hash = data.archive_file.send_email.output_base64sha256
  memory_size      = 128
  timeout          = 30

  environment {
    variables = {
      SEND_EMAIL_ENABLED = tostring(var.enable_alert_delivery)
      SES_FROM_EMAIL     = var.alert_sender_email
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.send_email_logs,
    aws_iam_role_policy.send_email_ses,
    aws_cloudwatch_log_group.send_email
  ]
}

resource "aws_lambda_permission" "sns_send_email" {
  statement_id  = "AllowSNSPriceAlerts"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.send_email.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.price_alerts.arn
}

resource "aws_sns_topic_subscription" "send_email" {
  topic_arn = aws_sns_topic.price_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.send_email.arn

  depends_on = [aws_lambda_permission.sns_send_email]
}
