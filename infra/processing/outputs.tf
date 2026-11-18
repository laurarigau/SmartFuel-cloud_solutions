output "lambda_names" {
  value = merge(
    { for k, f in aws_lambda_function.lambda : k => f.function_name },
    { process = aws_lambda_function.process.function_name },
  )
}

output "raw_created_rule" {
  description = "EventBridge rule that starts processing for every new raw/ file"
  value       = aws_cloudwatch_event_rule.raw_created.name
}
