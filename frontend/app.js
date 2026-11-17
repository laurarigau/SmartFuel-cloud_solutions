// SmartFuel Forecast · map of stations (Phase D)
// Reads stations from our API: GET /stations?geohash=xxxxx and GET /stations/{id}

const API_URL = (window.SMARTFUEL_CONFIG || {}).API_URL;
const MIN_ZOOM_FOR_STATIONS = 12; // below this, too many cells to load
const MAX_CELLS = 30;

const FUEL_LABELS = {
  gasolina_95_e5: "Gasolina 95",
  gasolina_98_e5: "Gasolina 98",
  gasoleo_a: "Gasóleo A",
  gasoleo_premium: "Gasóleo Premium",
  glp: "GLP",
};

const statusEl = document.getElementById("status");
const detailEl = document.getElementById("detail");

const map = L.map("map").setView([40.4168, -3.7038], 6);
// Base map: OpenStreetMap. Open the page through a local server
// (python -m http.server), not as file://, or OSM blocks the tiles.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const markers = L.layerGroup().addTo(map);
const cellCache = new Map(); // geohash -> stations already downloaded
const drawn = new Set();     // station ids already on the map

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

async function fetchJson(path) {
  const res = await fetch(API_URL + path);
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

async function loadCell(cell) {
  if (cellCache.has(cell)) return cellCache.get(cell);
  const data = await fetchJson(`stations?geohash=${cell}`);
  cellCache.set(cell, data.stations);
  return data.stations;
}

function addMarker(station) {
  if (drawn.has(station.station_id)) return;
  drawn.add(station.station_id);

  const marker = L.circleMarker([station.lat, station.lon], {
    radius: 7,
    color: "#ffffff",
    weight: 2,
    fillColor: "#0b6680",
    fillOpacity: 0.9,
  });

  const popup = document.createElement("div");
  const name = document.createElement("div");
  name.className = "popup-name";
  name.textContent = station.name || "Gasolinera";
  const place = document.createElement("div");
  place.textContent = station.municipality || "";
  const link = document.createElement("button");
  link.className = "popup-link";
  link.type = "button";
  link.textContent = "Ver precios";
  link.addEventListener("click", () => showDetail(station.station_id));
  popup.append(name, place, link);

  marker.bindPopup(popup);
  marker.addTo(markers);
}

async function refreshStations() {
  if (!API_URL || API_URL.includes("xxxxxxxxxx")) {
    setStatus("Falta configurar la URL de la API en frontend/config.js", true);
    return;
  }
  if (map.getZoom() < MIN_ZOOM_FOR_STATIONS) {
    setStatus("Acerca el mapa a una zona para ver sus gasolineras.");
    return;
  }

  const b = map.getBounds();
  const cells = geohashCellsForBounds(b.getSouth(), b.getWest(), b.getNorth(), b.getEast());
  if (cells.length > MAX_CELLS) {
    setStatus("Zona demasiado grande: acerca un poco más el mapa.");
    return;
  }

  setStatus("Cargando gasolineras…");
  try {
    const results = await Promise.all(cells.map(loadCell));
    const stations = results.flat();
    stations.forEach(addMarker);
    const visible = stations.filter(s => b.contains([s.lat, s.lon])).length;
    setStatus(visible === 1 ? "1 gasolinera en esta zona." : `${visible} gasolineras en esta zona.`);
  } catch (err) {
    setStatus(`No se han podido cargar las gasolineras: ${err.message}`, true);
  }
}

function renderPrices(prices) {
  const box = document.getElementById("d-prices");
  box.replaceChildren();
  const entries = Object.entries(prices || {}).filter(([, p]) => p && p.price_eur != null);
  if (entries.length === 0) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "Todavía no hay precios para esta estación (los cargará la fase de procesamiento).";
    box.append(p);
    return;
  }
  for (const [fuel, p] of entries) {
    const card = document.createElement("div");
    card.className = "price";
    const label = document.createElement("div");
    label.className = "fuel";
    label.textContent = FUEL_LABELS[fuel] || fuel;
    const value = document.createElement("div");
    value.className = "value";
    value.textContent = Number(p.price_eur).toFixed(3) + " ";
    const unit = document.createElement("small");
    unit.textContent = "€/L";
    value.append(unit);
    card.append(label, value);
    box.append(card);
  }
}

async function showDetail(stationId) {
  detailEl.classList.remove("hidden");
  document.getElementById("d-name").textContent = "Cargando…";
  try {
    const s = await fetchJson(`stations/${encodeURIComponent(stationId)}`);
    document.getElementById("d-brand").textContent = s.province || "Gasolinera";
    document.getElementById("d-name").textContent = s.municipality ? `${s.name} · ${s.municipality}` : s.name;
    document.getElementById("d-address").textContent = [s.address, s.postal_code, s.province].filter(Boolean).join(", ");
    document.getElementById("d-hours").textContent = s.opening_hours ? `Horario: ${s.opening_hours}` : "";
    renderPrices(s.prices);
  } catch (err) {
    document.getElementById("d-name").textContent = "No se ha podido cargar la estación";
    document.getElementById("d-address").textContent = err.message;
  }
}

document.getElementById("close-detail").addEventListener("click", () => detailEl.classList.add("hidden"));

document.getElementById("city").addEventListener("change", (e) => {
  if (!e.target.value) return;
  const [lat, lon] = e.target.value.split(",").map(Number);
  map.setView([lat, lon], 14);
});

document.getElementById("locate").addEventListener("click", () => {
  if (!navigator.geolocation) return setStatus("Tu navegador no permite la ubicación.", true);
  navigator.geolocation.getCurrentPosition(
    (pos) => map.setView([pos.coords.latitude, pos.coords.longitude], 14),
    () => setStatus("No se ha podido obtener tu ubicación. Elige una ciudad.", true)
  );
});

let timer;
map.on("moveend", () => {
  clearTimeout(timer);
  timer = setTimeout(refreshStations, 300); // wait until the user stops moving
});

refreshStations();
