output "ingest_lambda" {
  value = "${aws_lambda_function.ingest.function_name} (${var.ingest_region})"
}

output "schedule" {
  value = "${var.ingest_schedule} Europe/Madrid"
}

output "test_command" {
  description = "Run the ingestion once by hand"
  value       = "aws lambda invoke --region ${var.ingest_region} --function-name ${aws_lambda_function.ingest.function_name} /tmp/out.json && cat /tmp/out.json"
}
