// SmartFuel Forecast · log-in with Cognito (Phase D)
//
// Uses Cognito's hosted login page with the OAuth 2.0 "authorization code + PKCE"
// flow: the browser never sees a password and no client secret is needed.
//   1. login()   -> redirect to <COGNITO_DOMAIN>/oauth2/authorize
//   2. Cognito   -> redirects back here with ?code=...
//   3. handleRedirect() exchanges the code for tokens at /oauth2/token
// The ID token is sent to our API as "Authorization: Bearer <token>" and
// API Gateway's JWT authorizer verifies it.

const Auth = (() => {
  const cfg = window.SMARTFUEL_CONFIG || {};
  const DOMAIN = (cfg.COGNITO_DOMAIN || "").replace(/\/$/, "");
  const CLIENT_ID = cfg.COGNITO_CLIENT_ID || "";
  // Must match one of the callback URLs in Cognito (var.web_urls in infra/web-api)
  const REDIRECT_URI = cfg.REDIRECT_URI || window.location.origin + "/";
  const KEY = "smartfuel.tokens";

  const enabled = () => Boolean(DOMAIN && CLIENT_ID);

  function base64url(bytes) {
    let text = "";
    bytes.forEach((b) => { text += String.fromCharCode(b); });
    return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function randomString(size = 48) {
    return base64url(crypto.getRandomValues(new Uint8Array(size)));
  }

  async function sha256(text) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return base64url(new Uint8Array(digest));
  }

  function decodeJwt(token) {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      atob(payload).split("").map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join("")
    );
    return JSON.parse(json);
  }

  function save(tokens) {
    const stored = load() || {};
    const merged = {
      id_token: tokens.id_token,
      refresh_token: tokens.refresh_token || stored.refresh_token,
      expires_at: Date.now() + (tokens.expires_in - 60) * 1000, // renew 1 min early
    };
    sessionStorage.setItem(KEY, JSON.stringify(merged));
    return merged;
  }

  function load() {
    try {
      return JSON.parse(sessionStorage.getItem(KEY));
    } catch {
      return null;
    }
  }

  function clear() {
    sessionStorage.removeItem(KEY);
  }

  async function tokenRequest(params) {
    const res = await fetch(`${DOMAIN}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: CLIENT_ID, ...params }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.error_description || body.error || `HTTP ${res.status}`);
    return body;
  }

  async function login() {
    const verifier = randomString();
    const state = randomString(16);
    sessionStorage.setItem("smartfuel.pkce", JSON.stringify({ verifier, state }));
    const params = new URLSearchParams({
      response_type: "code",
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      scope: "openid email profile",
      code_challenge_method: "S256",
      code_challenge: await sha256(verifier),
      state,
    });
    window.location.assign(`${DOMAIN}/oauth2/authorize?${params}`);
  }

  function logout() {
    clear();
    const params = new URLSearchParams({ client_id: CLIENT_ID, logout_uri: REDIRECT_URI });
    window.location.assign(`${DOMAIN}/logout?${params}`);
  }

  // Call once when the page loads: finishes the log-in if Cognito sent us back with a code
  async function handleRedirect() {
    const url = new URL(window.location.href);
    const code = url.searchParams.get("code");
    const state = url.searchParams.get("state");
    const error = url.searchParams.get("error_description") || url.searchParams.get("error");
    if (!code && !error) return;

    // Clean the URL so a reload does not reuse the code
    window.history.replaceState({}, "", url.pathname);
    if (error) throw new Error(error);

    const pkce = JSON.parse(sessionStorage.getItem("smartfuel.pkce") || "{}");
    sessionStorage.removeItem("smartfuel.pkce");
    if (!pkce.verifier || pkce.state !== state) throw new Error(t("auth.mismatch"));

    save(await tokenRequest({
      grant_type: "authorization_code",
      code,
      redirect_uri: REDIRECT_URI,
      code_verifier: pkce.verifier,
    }));
  }

  // Valid ID token (renewed with the refresh token if needed) or null if logged out
  async function getToken() {
    const tokens = load();
    if (!tokens) return null;
    if (Date.now() < tokens.expires_at) return tokens.id_token;
    if (!tokens.refresh_token) {
      clear();
      return null;
    }
    try {
      return save(await tokenRequest({ grant_type: "refresh_token", refresh_token: tokens.refresh_token })).id_token;
    } catch {
      clear();
      return null;
    }
  }

  function user() {
    const tokens = load();
    if (!tokens) return null;
    const claims = decodeJwt(tokens.id_token);
    return { email: claims.email, groups: claims["cognito:groups"] || [] };
  }

  return { enabled, login, logout, handleRedirect, getToken, user, clear };
})();
