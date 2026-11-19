
"""Load SmartFuel historical fuel-price snapshots."""

import os
import json
import argparse
from pathlib import Path

import pandas as pd


FUEL_COLUMNS = {
    "Precio Gasolina 95 E5": "gasolina_95_e5",
    "Precio Gasoleo A": "gasoleo_a",
}


def load_history(folder):
    """Load historical JSON snapshots into a DataFrame."""

    folder = Path(folder).expanduser()
    files = sorted(folder.rglob("*.json"))

    if not files:
        raise FileNotFoundError(
            f"No JSON snapshots found in {folder}"
        )

    records = []

    for file in files:
        with open(file, encoding="utf-8") as f:
            data = json.load(f)

        timestamp = pd.to_datetime(
            data["Fecha"], dayfirst=True
        )

        for station in data["ListaEESSPrecio"]:
            station_id = str(
                station.get("IDEESS", "")
            ).strip()

            if not station_id:
                continue

            for column, fuel_type in FUEL_COLUMNS.items():
                raw_price = str(
                    station.get(column, "")
                ).strip()

                try:
                    price = float(
                        raw_price.replace(",", ".")
                    )
                except ValueError:
                    continue

                if price <= 0:
                    continue

                records.append({
                    "station_id": station_id,
                    "fuel_type": fuel_type,
                    "ts": timestamp,
                    "price_eur": price,
                    "province": station.get("Provincia", "")
                })

    df = pd.DataFrame(records)

    df = df.drop_duplicates(
        subset=["station_id", "fuel_type", "ts"]
    )

    return df.sort_values(
        ["station_id", "fuel_type", "ts"]
    ).reset_index(drop=True)


def load_history_from_s3(
    bucket,
    prefix="raw/",
    region=os.environ.get("AWS_DEFAULT_REGION", "eu-north-1")
):
    """Download S3 snapshots and load historical prices."""

    import boto3
    import tempfile

    s3 = boto3.client("s3", region_name=region)
    paginator = s3.get_paginator("list_objects_v2")

    prefix = prefix.rstrip("/") + "/"

    with tempfile.TemporaryDirectory() as tempdir:
        count = 0

        for page in paginator.paginate(
            Bucket=bucket,
            Prefix=prefix
        ):
            for obj in page.get("Contents", []):
                key = obj["Key"]

                if not key.endswith(".json"):
                    continue

                relative_path = key[len(prefix):]
                destination = Path(tempdir) / relative_path

                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                s3.download_file(
                    bucket,
                    key,
                    str(destination)
                )

                count += 1

        if count == 0:
            raise ValueError(
                "No historical JSON files found in S3."
            )

        print(f"Downloaded {count} snapshots from S3")

        return load_history(tempdir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    df = load_history(args.input)

    print("Historical observations:", len(df))
    print("Unique stations:", df["station_id"].nunique())
    print("Unique timestamps:", df["ts"].nunique())
    print("First snapshot:", df["ts"].min())
    print("Last snapshot:", df["ts"].max())

def load_history_from_athena(
    database="smartfuel_ml",
    table="clean_prices",
    workgroup="smartfuel-ml",
    lookback_days=14,
    region=None,
    station_sample_modulus=1,
):
    """Read clean historical prices through Athena."""

    import boto3
    import re
    import tempfile
    import time

    from datetime import datetime, timedelta, timezone
    from urllib.parse import urlparse

    for identifier in (database, table):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
            raise ValueError(f"Invalid Athena identifier: {identifier}")

    if lookback_days < 1 or station_sample_modulus < 1:
        raise ValueError("Lookback days and sample modulus must be positive.")

    region = region or os.environ.get("AWS_DEFAULT_REGION", "eu-north-1")

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=lookback_days - 1)

    sample_filter = ""
    if station_sample_modulus > 1:
        sample_filter = (
            "AND MOD(TRY_CAST(station_id AS BIGINT), "
            f"{station_sample_modulus}) = 0"
        )

    query = f"""
        SELECT station_id, fuel_type, price_eur, ts, province
        FROM "{database}"."{table}"
        WHERE "date" BETWEEN '{start_date}' AND '{end_date}'
          AND fuel_type IN ('gasolina_95_e5', 'gasoleo_a')
          AND price_eur > 0
          AND station_id IS NOT NULL
          AND ts IS NOT NULL
          AND province IS NOT NULL
          {sample_filter}
    """

    athena = boto3.client("athena", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    query_id = response["QueryExecutionId"]
    print(f"Athena query started: {query_id}")

    execution = None

    for _ in range(150):
        execution = athena.get_query_execution(
            QueryExecutionId=query_id
        )["QueryExecution"]

        status = execution["Status"]
        state = status["State"]

        if state == "SUCCEEDED":
            break

        if state in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason", "Unknown error")
            raise RuntimeError(f"Athena {state}: {reason}")

        time.sleep(2)
    else:
        raise TimeoutError(f"Athena query timed out: {query_id}")

    output_location = execution["ResultConfiguration"]["OutputLocation"]
    parsed = urlparse(output_location)

    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError("Invalid Athena result location.")

    with tempfile.TemporaryDirectory() as tempdir:
        csv_path = str(Path(tempdir) / "athena_history.csv")

        s3.download_file(
            parsed.netloc,
            parsed.path.lstrip("/"),
            csv_path,
        )

        history = pd.read_csv(
            csv_path,
            dtype={
                "station_id": "string",
                "fuel_type": "string",
                "province": "string",
            },
        )

    history["ts"] = pd.to_datetime(history["ts"], errors="coerce")
    history["price_eur"] = pd.to_numeric(
        history["price_eur"], errors="coerce"
    )

    history = history.dropna(
        subset=["station_id", "fuel_type", "price_eur", "ts", "province"]
    )

    history = history.drop_duplicates(
        subset=["station_id", "fuel_type", "ts"],
        keep="last",
    )

    history = history.sort_values(
        ["station_id", "fuel_type", "ts"]
    ).reset_index(drop=True)

    if history.empty:
        raise ValueError("No usable historical observations from Athena.")

    print(f"Loaded {len(history)} observations from Athena")
    print(f"Unique stations: {history['station_id'].nunique()}")
    print(f"Date range: {history['ts'].min()} to {history['ts'].max()}")

    return history