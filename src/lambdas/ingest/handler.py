
import json
import os
import time
from datetime import datetime

import boto3
import requests

# Same data on two Ministry servers. "serviciosmin" answers reliably from AWS;
# "minetur" often resets connections coming from the cloud, so it is only a fallback.
API_URLS = [
    "https://energia.serviciosmin.gob.es/"
    "ServiciosRestCarburantes/PreciosCarburantes/"
    "EstacionesTerrestres/",
    "https://sedeaplicaciones.minetur.gob.es/"
    "ServiciosRESTCarburantes/PreciosCarburantes/"
    "EstacionesTerrestres/",
]

# If both servers fail, wait and try again (longer each time).
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = [5, 15, 30]

s3 = boto3.client("s3")


def download_with_retries():
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for url in API_URLS:
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": "SmartFuelForecast/1.0"},
                    timeout=(10, 60)
                )
                response.raise_for_status()
                print(f"Downloaded from {url} (attempt {attempt})")
                return response
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.HTTPError) as error:
                last_error = error
                print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed for {url}: {error}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF_SECONDS[attempt - 1])
    raise last_error


def lambda_handler(event, context):
    bucket_name = os.environ["LAKE_BUCKET"]

    # 1. Request the fuel-price data from the Ministry API (with retries)
    response = download_with_retries()

    # 2. Keep the original API response unchanged
    raw_data = response.content

    # 3. Read the snapshot date to create the S3 key
    data = response.json()

    snapshot_date = datetime.strptime(
        data["Fecha"],
        "%d/%m/%Y %H:%M:%S"
    )

    s3_key = (
        "raw/"
        + snapshot_date.strftime("%Y/%m/%d/%H%M")
        + ".json"
    )

    # 4. Upload the original JSON response to S3
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=raw_data,
        ContentType="application/json"
    )

    # 5. Count the retrieved stations
    stations = data["ListaEESSPrecio"]

    print("Ingestion completed successfully")
    print("Stations retrieved:", len(stations))
    print("S3 bucket:", bucket_name)
    print("S3 key:", s3_key)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Fuel data ingested successfully",
            "bucket": bucket_name,
            "key": s3_key,
            "snapshot_date": data["Fecha"],
            "station_count": len(stations)
        })
    }
