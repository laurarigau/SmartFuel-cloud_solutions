# Phase D · Web, API & auth
# Owner: [name]
#
# TODO (see the plan doc and docs/contracts.md):
#   [ ] Cognito User Pool + app client + group "admins"
#   [ ] API Gateway HTTP API: JWT authorizer (Cognito) on private routes, stage throttling
#   [ ] API Lambdas: GET /stations, GET /stations/{id}, GET /predictions/{id}, GET/POST/DELETE /subscriptions, /admin/*
#   [ ] Amplify Hosting app for frontend/
#
# IAM: one role per Lambda / state machine with only the permissions it needs.
# If the sandbox does not allow creating roles, use the provided role and
# document the least-privilege policy you would attach.
