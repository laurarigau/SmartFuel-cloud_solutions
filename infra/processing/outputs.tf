output "lambda_names" {
  value = { for k, f in aws_lambda_function.lambda : k => f.function_name }
}

output "state_machine_arn" {
  description = "Step Functions state machine that processes each raw/ file"
  value       = aws_sfn_state_machine.processing.arn
}

output "raw_created_rule" {
  description = "EventBridge rule that starts processing for every new raw/ file"
  value       = aws_cloudwatch_event_rule.raw_created.name
}
