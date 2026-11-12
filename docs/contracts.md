# Contracts between phases

Names and formats every phase relies on. Change them only in a PR that tags the
people affected. `<suffix>` = your AWS account id (set by `scripts/deploy.sh`). Region: `us-east-1`.

## S3 data lake — `smartfuel-lake-<suffix>` (core)

| Prefix | Content | Written by | Read by |
| --- | --- | --- | --- |
| `raw/YYYY/MM/DD/HHmm.json` | Ministry API response, untouched (`Fecha`, `ListaEESSPrecio`, ...) | A · ingest | B · validate |
| `quarantine/<same key>` | Raw files that failed validation | B · validate | admins |
| `clean/date=YYYY-MM-DD/HHmm.parquet` | One row per station × fuel (schema below) | B · clean | C (Athena), B (diff) |
| `models/production/model.joblib` + `metadata.json` | Current model | C | B · predict |
| `models/candidates/<timestamp>/` | Models from weekly retraining | C | C |
| `athena-results/` | Athena query output (expires after 7 days) | Athena | C |

Raw object keys use the API's `Fecha` field (Spain time), as in `scripts/exploration/explore_fuel_data.py`.

## `clean/` Parquet schema

| Column | Type | From the raw JSON |
| --- | --- | --- |
| `station_id` | string | `IDEESS` |
| `fuel_type` | string | `gasolina_95_e5`, `gasolina_98_e5`, `gasoleo_a`, `gasoleo_premium`, `glp` |
| `price_eur` | double | `Precio ...` (comma decimal → dot; empty → row dropped) |
| `ts` | timestamp | `Fecha` |
| `station_name` | string | `Rótulo` |
| `municipality`, `province` | string | `Municipio`, `Provincia` |
| `lat`, `lon` | double | `Latitud`, `Longitud (WGS84)` (comma decimal) |
| `geohash5` | string | computed from lat/lon, precision 5 (~5 km) |

## DynamoDB (on-demand, core)

| Table | Keys | Main attributes | Writer → readers |
| --- | --- | --- | --- |
| `smartfuel-stations` | PK `station_id` · GSI `geohash5-index` | name, address, municipality, province, lat, lon, geohash5 | B (D seed script) → D |
| `smartfuel-latest-prices` | PK `station_id` · SK `fuel_type` · **Stream NEW_AND_OLD_IMAGES** | price_eur, ts | B → C (stream), D |
| `smartfuel-predictions` | PK `station_fuel` (`<station_id>#<fuel_type>`) · SK `date` (YYYY-MM-DD) · TTL `expires_at` | direction (`up`/`down`/`flat`), prob, model_version | B → D |
| `smartfuel-subscriptions` | PK `user_id` (Cognito `sub`) · SK `station_fuel` · GSI `station_fuel-index` | email, target_price, created_at | D → C |

Only **changed** prices are written to `latest-prices` (keeps cost and stream noise low).

## Model interface (C → B)

```python
# models/production/ contains model.joblib + metadata.json
# metadata.json: {"version": "2026-11-20T03:00Z", "features": [...], "mae": 0.0, "baseline_mae": 0.0}
def predict(features: dict) -> dict:
    return {"direction": "up" | "down" | "flat", "prob": 0.0-1.0}
```

Until C delivers v0, B uses a stub that returns `{"direction": "flat", "prob": 1.0}`.

## SNS / SQS (core)

| Resource | Message | Publishers → subscribers |
| --- | --- | --- |
| `smartfuel-admin-alerts` | free text: what failed, which file / execution | B, C → admin emails |
| `smartfuel-price-alerts` | JSON `{user_id, email, station_id, fuel_type, old_price, new_price, target_price}` | C · check-alerts → C · send-email → SES |
| `smartfuel-dlq` | events that could not be delivered (EventBridge targets, stream Lambda failures) | A, B, C |

## HTTP API (D)

| Route | Auth | Returns |
| --- | --- | --- |
| `GET /stations?geohash=<5 chars>` | public | stations + latest prices in that cell |
| `GET /stations/{id}` | public | station, prices, prediction |
| `GET /predictions/{id}` | public | predictions for the station |
| `GET /subscriptions` · `POST /subscriptions` · `DELETE /subscriptions/{station_fuel}` | JWT | the user's followed stations |
| `/admin/*` | JWT + group `admins` | pipeline status, quarantine list |

## Naming & tags

Every resource: name prefix `smartfuel-`, tags `project=smartfuel`, `owner=core|phase-a|phase-b|phase-c|phase-d`.
Lambdas: `smartfuel-<name>` with code in `src/lambdas/<name>/`.
