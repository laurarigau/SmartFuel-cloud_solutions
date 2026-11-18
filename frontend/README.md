# Frontend (Phase D)

Static web app: map of Spain with the petrol stations, their current prices and (later) the prediction.
It only talks to our HTTP API. Public: `GET /stations?geohash=`, `GET /stations/{id}`, `GET /predictions/{id}`.
With log-in (Cognito): `GET/POST /subscriptions`, `DELETE /subscriptions/{station_fuel}` to follow stations and get price alerts.

## Run it locally

1. Copy the config and put **your** values (outputs `api_url`, `cognito_domain` and `cognito_client_id` of `./scripts/deploy.sh web-api`):
   ```bash
   cp frontend/config.example.js frontend/config.js
   ```
2. Start a local web server (opening the file directly makes OpenStreetMap block the map):
   ```bash
   cd frontend
   python -m http.server 8000
   ```
   Then open http://localhost:8000 (stop the server with Ctrl + C).
   Use exactly `http://localhost:8000/`: it is the address registered in Cognito for the log-in (`web_urls` in `infra/web-api`).
3. Choose a city or zoom in: stations load when the zoom is 12 or more.

`config.js` is git-ignored, so every member can point to their own sandbox.

## How it works

| File | What it does |
| --- | --- |
| `index.html` | Page layout: header, map and side panel |
| `styles.css` | Look and feel |
| `geohash.js` | Same geohash (precision 5) as `scripts/seed_stations.py`: turns the visible map area into ~5 km cells |
| `app.js` | Asks the API for the stations of each visible cell, draws them, shows the detail panel, and the "follow" form and "my stations" list |
| `auth.js` | Log-in with Cognito's hosted page (OAuth 2.0 authorization code + PKCE); keeps the token for the session |
| `config.example.js` | Template for `config.js` (API URL and Cognito) |

Map: [Leaflet](https://leafletjs.com) + OpenStreetMap tiles.

## Publish it (Amplify)

```bash
./scripts/deploy.sh web-api      # creates the Amplify app (once)
./scripts/deploy_web.sh          # uploads frontend/ and prints the public URL
```

`deploy_web.sh` generates the `config.js` of the published site from the `web-api` outputs,
so nothing secret or personal is committed. The Amplify URL is already registered in Cognito,
so the log-in works there too. Run `deploy_web.sh` again after every change to `frontend/`.
