
resource "aws_iam_role" "ml_sfn" {
  count = var.enable_ml_retraining ? 1 : 0
  name  = "${var.project}-ml-retraining-sfn-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "states.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ml_sfn" {
  count = var.enable_ml_retraining ? 1 : 0
  name  = "invoke-training-and-evaluation"
  role  = aws_iam_role.ml_sfn[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["lambda:InvokeFunction"]
      Resource = [
        aws_lambda_function.ml_train[0].arn,
        aws_lambda_function.ml_evaluate[0].arn
      ]
    }]
  })
}

resource "aws_sfn_state_machine" "ml_retraining" {
  count    = var.enable_ml_retraining ? 1 : 0
  name     = "${var.project}-ml-retraining"
  role_arn = aws_iam_role.ml_sfn[0].arn
  type     = "STANDARD"

  definition = jsonencode({
    Comment = "Weekly SmartFuel ML training from Athena and candidate evaluation"
    StartAt = "Train"
    States = {
      Train = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.ml_train[0].arn
          Payload      = {}
        }
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals = [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Next = "Evaluate"
      }

      Evaluate = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.ml_evaluate[0].arn
          "Payload.$"  = "$"
        }
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals = [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        End = true
      }
    }
  })

  depends_on = [aws_iam_role_policy.ml_sfn]
}
