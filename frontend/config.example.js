// Copy this file to config.js and put YOUR values
// (the outputs of ./scripts/deploy.sh web-api). API_URL must end with "/".
// config.js is git-ignored: each member points to their own account.
window.SMARTFUEL_CONFIG = {
  API_URL: "https://xxxxxxxxxx.execute-api.eu-north-1.amazonaws.com/",

  // Log-in (outputs cognito_domain and cognito_client_id). Leave empty to hide the log-in.
  COGNITO_DOMAIN: "https://smartfuel-123456789012.auth.eu-north-1.amazoncognito.com",
  COGNITO_CLIENT_ID: "",
};
