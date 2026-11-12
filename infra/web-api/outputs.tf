output "api_url" {
  description = "Base URL of the HTTP API"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "example_request" {
  description = "Open it in the browser to test"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}stations?geohash=sp3e3"
}
