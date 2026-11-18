"""Load the stations of a Ministry JSON snapshot into the smartfuel-stations table.

Phase D uses it to have real data for the API before phase B writes it.
Phase B must compute geohash5 the same way (same function, precision 5).

Usage (with your sandbox credentials loaded):
    python3 scripts/seed_stations.py                          # fixtures/fuel_prices_sample.json
    python3 scripts/seed_stations.py fixtures/raw_sample.json # another file
    python3 scripts/seed_stations.py --dry-run                # only print, no AWS
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

TABLE = "smartfuel-stations"
REGION = "us-east-1"
DEFAULT_FILE = Path(__file__).resolve().parent.parent / "fixtures" / "fuel_prices_sample.json"

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat: float, lon: float, precision: int = 5) -> str:
    """Standard geohash encoding (precision 5 = cells of about 5 x 5 km)."""
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    out, bits, ch, even = [], 0, 0, True
    while len(out) < precision:
        rng, val = (lon_rng, lon) if even else (lat_rng, lat)
        mid = (rng[0] + rng[1]) / 2
        if val >= mid:
            ch = (ch << 1) | 1
            rng[0] = mid
        else:
            ch <<= 1
            rng[1] = mid
        even = not even
        bits += 1
        if bits == 5:
            out.append(_BASE32[ch])
            bits, ch = 0, 0
    return "".join(out)


def to_float(text: str):
    """The API uses comma decimals: '41,385063' -> 41.385063. Empty -> None."""
    text = (text or "").strip().replace(",", ".")
    return float(text) if text else None


def station_items(snapshot: dict):
    for s in snapshot["ListaEESSPrecio"]:
        lat, lon = to_float(s.get("Latitud")), to_float(s.get("Longitud (WGS84)"))
        if lat is None or lon is None:
            continue
        yield {
            "station_id": s["IDEESS"],
            "name": s.get("Rótulo", "").strip(),
            "address": s.get("Dirección", "").strip(),
            "postal_code": s.get("C.P.", "").strip(),
            "municipality": s.get("Municipio", "").strip(),
            "province": s.get("Provincia", "").strip(),
            "lat": Decimal(str(lat)),  # DynamoDB needs Decimal, not float
            "lon": Decimal(str(lon)),
            "geohash5": geohash(lat, lon),
            "opening_hours": s.get("Horario", "").strip(),
        }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    path = Path(args[0]) if args else DEFAULT_FILE

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    items = list(station_items(snapshot))
    print(f"{len(items)} stations read from {path.name} (snapshot {snapshot.get('Fecha')})")

    if dry_run:
        for item in items[:3]:
            print(item)
        return

    import boto3

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    with table.batch_writer(overwrite_by_pkeys=["station_id"]) as batch:
        for i, item in enumerate(items, 1):
            batch.put_item(Item=item)
            if i % 1000 == 0:
                print(f"  {i} written...")
    print(f"Done: {len(items)} stations in {TABLE}")


if __name__ == "__main__":
    main()
