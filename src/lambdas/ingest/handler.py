
import json
import os
from datetime import datetime

import boto3
import requests

API_URL = (
    "https://sedeaplicaciones.minetur.gob.es/"
    "ServiciosRESTCarburantes/PreciosCarburantes/"
    "EstacionesTerrestres/"
)

s3 = boto3.client("s3")


def lambda_handler(event, context):
    bucket_name = os.environ["LAKE_BUCKET"]

    # 1. Request the fuel-price data from the Ministry API
    response = requests.get(
        API_URL,
        headers={"User-Agent": "SmartFuelForecast/1.0"},
        timeout=(10, 60)
    )

    response.raise_for_status()

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
