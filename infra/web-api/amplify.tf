# ---------------------------------------------------------------------------
# Amplify Hosting: public URL for the web app (frontend/)
#
# The app is not linked to GitHub (the repo belongs to another member's
# account): scripts/deploy_web.sh zips frontend/ with a config.js generated
# from this stack's outputs and uploads it as a manual deployment.
# Amplify serves it over HTTPS through its own CDN (CloudFront).
# ---------------------------------------------------------------------------
resource "aws_amplify_app" "web" {
  name     = "${var.project}-web"
  platform = "WEB"
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.web.id
  branch_name = "main"
  stage       = "PRODUCTION"
}

locals {
  amplify_url = "https://${aws_amplify_branch.main.branch_name}.${aws_amplify_app.web.default_domain}/"
}
