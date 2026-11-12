
import json
import pandas as pd
import os
import glob

# 1. Define the project folders
project_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

raw_folder = os.path.join(project_folder, "data", "raw")
processed_folder = os.path.join(project_folder, "data", "processed")

# 2. Create the processed folder if it does not exist
os.makedirs(processed_folder, exist_ok=True)

# 3. Find the latest raw JSON file
raw_files = glob.glob(os.path.join(raw_folder, "fuel_prices_*.json"))

if len(raw_files) == 0:
    raise FileNotFoundError("No raw JSON files found in data/raw/")

latest_raw_file = max(raw_files)

print("Processing file:", os.path.basename(latest_raw_file))

# 4. Load the raw JSON file
with open(latest_raw_file, "r", encoding="utf-8") as file:
    data = json.load(file)

stations = data["ListaEESSPrecio"]

print("Total stations:", len(stations))

# 5. Convert the JSON data into a DataFrame
df = pd.DataFrame(stations)

# 6. Select the columns we need
columns = [
    "IDEESS",
    "Rótulo",
    "Dirección",
    "Municipio",
    "Provincia",
    "Latitud",
    "Longitud (WGS84)",
    "Precio Gasolina 95 E5",
    "Precio Gasoleo A"
]

df = df[columns].copy()

# 7. Rename the columns
df.columns = [
    "station_id",
    "station_name",
    "address",
    "municipality",
    "province",
    "latitude",
    "longitude",
    "gasoline_95_price",
    "diesel_price"
]

# 8. Convert Spanish decimal numbers into numeric values
def convert_number(value):
    if pd.isna(value) or value == "":
        return None

    return float(str(value).replace(",", "."))


df["gasoline_95_price"] = df["gasoline_95_price"].apply(convert_number)
df["diesel_price"] = df["diesel_price"].apply(convert_number)
df["latitude"] = df["latitude"].apply(convert_number)
df["longitude"] = df["longitude"].apply(convert_number)

# 9. Add the snapshot date
df["snapshot_date"] = pd.to_datetime(
    data["Fecha"],
    format="%d/%m/%Y %H:%M:%S"
)

# 10. Remove rows without a station ID
df = df.dropna(subset=["station_id"])

# 11. Get the timestamp from the raw filename
raw_filename = os.path.basename(latest_raw_file)
timestamp = raw_filename.replace("fuel_prices_", "").replace(".json", "")

# 12. Save the cleaned CSV in the processed folder
output_filename = "fuel_prices_" + timestamp + ".csv"
output_path = os.path.join(processed_folder, output_filename)

df.to_csv(
    output_path,
    index=False,
    encoding="utf-8"
)

# 13. Display the results
print("\nCleaned dataset:")
print(df.head())

print("\nDataset information:")
df.info()

print("\nMissing prices:")
print("Gasoline 95:", df["gasoline_95_price"].isna().sum())
print("Diesel:", df["diesel_price"].isna().sum())

print("\nCleaned dataset saved successfully!")
print("File location:", output_path)
