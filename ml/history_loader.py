
"""Load SmartFuel historical fuel-price snapshots."""

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
