# ---------------------------------------------------------------------------
# Cognito: sign-up / log-in for the web app and the "admins" group
#
# The web app uses Cognito's hosted login page (OAuth 2.0 authorization code
# flow with PKCE), so no password ever goes through our own code.
# ---------------------------------------------------------------------------
resource "aws_cognito_user_pool" "users" {
  name = "${var.project}-users"

  # Users log in with their email
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # Verification and password-reset emails sent by Cognito itself (no SES needed)
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "SmartFuel Forecast - your verification code"
    email_message        = "Your SmartFuel verification code is {####}"
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

# Hosted login page: https://<prefix>.auth.<region>.amazoncognito.com
resource "aws_cognito_user_pool_domain" "users" {
  domain       = "${var.project}-${var.suffix}"
  user_pool_id = aws_cognito_user_pool.users.id
}

# App client used by the web app (public client: no secret in the browser)
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project}-web"
  user_pool_id = aws_cognito_user_pool.users.id

  generate_secret = false

  # Hosted login page with authorization code + PKCE
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = concat(var.web_urls, [local.amplify_url])
  logout_urls                          = concat(var.web_urls, [local.amplify_url])

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_USER_PASSWORD_AUTH", # testing from the terminal
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60 # minutes
  id_token_validity      = 60 # minutes
  refresh_token_validity = 30 # days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_user_group" "admins" {
  name         = "admins"
  user_pool_id = aws_cognito_user_pool.users.id
  description  = "SmartFuel administrators"
}

# ---------------------------------------------------------------------------
# JWT authorizer: API Gateway checks the Cognito token on private routes
# ---------------------------------------------------------------------------
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.http.id
  name             = "cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
    audience = [aws_cognito_user_pool_client.web.id]
  }
}

# Private routes (need a valid token). The /admin routes also need the group
# "admins": the Lambda checks the "cognito:groups" claim and returns 403 otherwise.
locals {
  private_routes = {
    me                  = "GET /me"
    list_subscriptions  = "GET /subscriptions"
    create_subscription = "POST /subscriptions"
    delete_subscription = "DELETE /subscriptions/{station_fuel}"
    admin_status        = "GET /admin/status"
    admin_quarantine    = "GET /admin/quarantine"
  }
}

resource "aws_apigatewayv2_route" "private" {
  for_each = local.private_routes

  api_id             = aws_apigatewayv2_api.http.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}
