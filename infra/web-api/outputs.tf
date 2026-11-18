output "api_url" {
  description = "Base URL of the HTTP API"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "example_request" {
  description = "Open it in the browser to test"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}stations?geohash=sp3e3"
}

output "cognito_domain" {
  description = "Hosted login page (COGNITO_DOMAIN in frontend/config.js)"
  value       = "https://${aws_cognito_user_pool_domain.users.domain}.auth.${var.region}.amazoncognito.com"
}

output "cognito_client_id" {
  description = "COGNITO_CLIENT_ID in frontend/config.js"
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.users.id
}

output "web_url" {
  description = "Public URL of the web app (after scripts/deploy_web.sh)"
  value       = local.amplify_url
}

output "amplify_app_id" {
  value = aws_amplify_app.web.id
}
