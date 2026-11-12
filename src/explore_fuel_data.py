
import requests
import json
import os
from datetime import datetime

# 1. Define the API URL
url = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"

# 2. Download the data
response = requests.get(url)
response.raise_for_status()

data = response.json()

# 3. Create the raw data folder if it does not exist
project_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw_folder = os.path.join(project_folder, "data", "raw")

os.makedirs(raw_folder, exist_ok=True)

# 4. Get the date and time from the API
snapshot_date = datetime.strptime(
    data["Fecha"],
    "%d/%m/%Y %H:%M:%S"
)

timestamp = snapshot_date.strftime("%Y-%m-%d_%H%M")

# 5. Save the raw JSON file
filename = "fuel_prices_" + timestamp + ".json"
file_path = os.path.join(raw_folder, filename)

with open(file_path, "w", encoding="utf-8") as file:
    json.dump(data, file, ensure_ascii=False, indent=4)

# 6. Display information about the downloaded dataset
stations = data["ListaEESSPrecio"]

print("Full dataset downloaded successfully!")
print("Snapshot date:", data["Fecha"])
print("Number of stations:", len(stations))
print("Saved file:", file_path)

print("\nAvailable keys:")
print(data.keys())

print("\nFirst 3 stations:")
for station in stations[:3]:
    print(json.dumps(station, indent=4, ensure_ascii=False))
