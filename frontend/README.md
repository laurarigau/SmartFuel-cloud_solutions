# Frontend (Phase D)

Static web app: map of Spain with the petrol stations, their current prices and (later) the prediction.
It only talks to our HTTP API (`GET /stations?geohash=` and `GET /stations/{id}`).

## Run it locally

1. Copy the config and put **your** API URL (the `api_url` output of `./scripts/deploy.sh web-api`):
   ```bash
   cp frontend/config.example.js frontend/config.js
   ```
2. Start a local web server (opening the file directly makes OpenStreetMap block the map):
   ```bash
   cd frontend
   python -m http.server 8000
   ```
   Then open http://localhost:8000 (stop the server with Ctrl + C).
3. Choose a city or zoom in: stations load when the zoom is 12 or more.

`config.js` is git-ignored, so every member can point to their own sandbox.

## How it works

| File | What it does |
| --- | --- |
| `index.html` | Page layout: header, map and side panel |
| `styles.css` | Look and feel |
| `geohash.js` | Same geohash (precision 5) as `scripts/seed_stations.py`: turns the visible map area into ~5 km cells |
| `app.js` | Asks the API for the stations of each visible cell, draws them, and shows the detail panel |
| `config.example.js` | Template for `config.js` (API URL) |

Map: [Leaflet](https://leafletjs.com) + OpenStreetMap tiles.

## Pending

- Login (Cognito) and "follow this station" (`/subscriptions`)
- Prediction from `GET /predictions/{id}`
- Public hosting with Amplify (pending sandbox permissions)
