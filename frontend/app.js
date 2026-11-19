// SmartFuel Forecast · map of stations (Phase D)
// Public:  GET /stations?geohash=xxxxx, GET /stations/{id}, GET /predictions/{id},
//          GET /cheapest?geohash=a,b&fuel=... (cheapest stations in the visible area)
// Log-in:  GET/POST /subscriptions, DELETE /subscriptions/{station_fuel} (Cognito token, see auth.js)

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

// Private calls: send the Cognito token (API Gateway checks it)
async function apiRequest(path, { method = "GET", body } = {}) {
  const token = await Auth.getToken();
  if (!token) throw new Error("Tu sesión ha caducado: vuelve a iniciar sesión.");
  const res = await fetch(API_URL + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    Auth.clear();
    updateAuthUI();
    throw new Error("Tu sesión ha caducado: vuelve a iniciar sesión.");
  }
  if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
  return data;
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
    document.getElementById("cheapest").classList.add("hidden");
    return;
  }

  const b = map.getBounds();
  const cells = geohashCellsForBounds(b.getSouth(), b.getWest(), b.getNorth(), b.getEast());
  if (cells.length > MAX_CELLS) {
    setStatus("Zona demasiado grande: acerca un poco más el mapa.");
    document.getElementById("cheapest").classList.add("hidden");
    return;
  }

  setStatus("Cargando gasolineras…");
  try {
    const results = await Promise.all(cells.map(loadCell));
    const stations = results.flat();
    stations.forEach(addMarker);
    const visible = stations.filter(s => b.contains([s.lat, s.lon])).length;
    setStatus(visible === 1 ? "1 gasolinera en esta zona." : `${visible} gasolineras en esta zona.`);
    lastArea = { cells, bounds: b };
    loadCheapest();
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

const DIRECTION_LABELS = {
  up: { text: "Subirá", cls: "up" },
  down: { text: "Bajará", cls: "down" },
  flat: { text: "Se mantendrá", cls: "flat" },
};

function renderPredictions(predictions) {
  const box = document.getElementById("d-prediction");
  box.replaceChildren();
  const entries = Object.entries(predictions || {});
  if (entries.length === 0) {
    box.textContent = "Todavía no hay previsión para esta estación (la calculará el modelo).";
    return;
  }
  for (const [fuel, p] of entries) {
    const row = document.createElement("div");
    row.className = "prediction";
    const label = document.createElement("span");
    label.textContent = FUEL_LABELS[fuel] || fuel;
    const dir = DIRECTION_LABELS[p.direction] || { text: p.direction, cls: "flat" };
    const value = document.createElement("span");
    value.className = `direction ${dir.cls}`;
    value.textContent = p.prob != null ? `${dir.text} (${Math.round(p.prob * 100)}%)` : dir.text;
    row.append(label, value);
    box.append(row);
  }
}

async function showDetail(stationId) {
  currentStation = { id: stationId, prices: {} };
  setFollowMessage("");
  detailEl.classList.remove("hidden");
  document.getElementById("d-name").textContent = "Cargando…";
  document.getElementById("d-prediction").textContent = "Cargando…";
  try {
    const s = await fetchJson(`stations/${encodeURIComponent(stationId)}`);
    document.getElementById("d-brand").textContent = s.province || "Gasolinera";
    document.getElementById("d-name").textContent = s.municipality ? `${s.name} · ${s.municipality}` : s.name;
    document.getElementById("d-address").textContent = [s.address, s.postal_code, s.province].filter(Boolean).join(", ");
    document.getElementById("d-hours").textContent = s.opening_hours ? `Horario: ${s.opening_hours}` : "";
    renderPrices(s.prices);
    currentStation.prices = s.prices || {};
    prefillTarget();
  } catch (err) {
    document.getElementById("d-name").textContent = "No se ha podido cargar la estación";
    document.getElementById("d-address").textContent = err.message;
    return;
  }
  try {
    const pred = await fetchJson(`predictions/${encodeURIComponent(stationId)}`);
    renderPredictions(pred.predictions);
  } catch (err) {
    document.getElementById("d-prediction").textContent = "No se ha podido cargar la previsión.";
  }
}

// ---------------------------------------------------------------------------
// Cheapest stations in the visible area (GET /cheapest)
// ---------------------------------------------------------------------------
let lastArea = null; // { cells, bounds } of the last area loaded on the map
const cheapFuel = document.getElementById("cheap-fuel");
for (const [value, label] of Object.entries(FUEL_LABELS)) {
  cheapFuel.append(new Option(label, value));
}

function renderCheapest(data) {
  const list = document.getElementById("cheap-list");
  const note = document.getElementById("cheap-note");
  list.replaceChildren();
  if (data.cheapest.length === 0) {
    note.textContent = data.stations_in_area
      ? "Todavía no hay precios de este carburante en la zona."
      : "No hay gasolineras en esta zona.";
    return;
  }
  for (const st of data.cheapest) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    const name = document.createElement("span");
    name.className = "cheap-name";
    name.textContent = st.municipality ? `${st.name} · ${st.municipality}` : st.name;
    const price = document.createElement("span");
    price.className = "cheap-price";
    price.textContent = `${Number(st.price_eur).toFixed(3)} €/L`;
    btn.append(name, price);
    btn.addEventListener("click", () => {
      map.setView([st.lat, st.lon], Math.max(map.getZoom(), 15));
      showDetail(st.station_id);
    });
    li.append(btn);
    list.append(li);
  }
  note.textContent = `${data.with_price} de ${data.stations_in_area} gasolineras con precio de ${FUEL_LABELS[data.fuel]}.`;
}

async function loadCheapest() {
  if (!lastArea) return;
  const section = document.getElementById("cheapest");
  const b = lastArea.bounds;
  const params = new URLSearchParams({
    geohash: lastArea.cells.join(","),
    fuel: cheapFuel.value,
    limit: "5",
    bbox: [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map(n => n.toFixed(4)).join(","),
  });
  try {
    renderCheapest(await fetchJson(`cheapest?${params}`));
    section.classList.remove("hidden");
  } catch (err) {
    section.classList.add("hidden"); // the map keeps working without the ranking
    console.warn("cheapest:", err);
  }
}
cheapFuel.addEventListener("change", loadCheapest);

// ---------------------------------------------------------------------------
// Log-in and "follow this station"
// ---------------------------------------------------------------------------
let currentStation = null; // { id, prices } of the station open in the panel
const fuelSelect = document.getElementById("f-fuel");
for (const [value, label] of Object.entries(FUEL_LABELS)) {
  fuelSelect.append(new Option(label, value));
}

function setFollowMessage(text, cls = "") {
  const el = document.getElementById("f-message");
  el.textContent = text;
  el.className = `muted ${cls}`;
}

// Suggest a target 2 cents below the current price of the chosen fuel
function prefillTarget() {
  const price = currentStation && currentStation.prices[fuelSelect.value];
  const input = document.getElementById("f-target");
  input.value = price && price.price_eur != null ? (Number(price.price_eur) - 0.02).toFixed(3) : "";
}
fuelSelect.addEventListener("change", prefillTarget);

function updateAuthUI() {
  const show = (id, visible) => document.getElementById(id).classList.toggle("hidden", !visible);
  const enabled = Auth.enabled();
  const user = enabled ? Auth.user() : null;

  show("login", enabled && !user);
  show("logout", Boolean(user));
  show("user-email", Boolean(user));
  document.getElementById("user-email").textContent = user ? user.email : "";

  show("follow-form", Boolean(user));
  show("d-follow-login", enabled && !user);
  show("my-stations", Boolean(user));
  // Only a visual hint: the API itself returns 403 to non-admins
  show("admin-panel", Boolean(user && user.groups.includes("admins")));
}

// ---------------------------------------------------------------------------
// Admin panel (group "admins"): pipeline status and quarantined files
// ---------------------------------------------------------------------------
function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" }) : "—";
}

function renderAdmin(status, quarantine) {
  const dl = document.getElementById("admin-status");
  dl.replaceChildren();
  const row = (label, text, cls = "") => {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = text;
    if (cls) dd.className = cls;
    dl.append(dt, dd);
  };
  const raw = status.raw || {};
  const clean = status.clean || {};
  row("Ingesta", status.ingestion_ok ? "OK" : "Revisar", status.ingestion_ok ? "ok" : "bad");
  row("Última descarga", raw.latest
    ? `${formatDate(raw.latest.at)} (hace ${status.hours_since_last_ingestion} h)`
    : "Ninguna");
  row("Ficheros raw", raw.files ? `${raw.files} (${raw.size_mb} MB)` : "0");
  row("Procesamiento", status.processing_ok ? "OK" : "Sin datos procesados", status.processing_ok ? "ok" : "bad");
  row("Último procesado", clean.latest ? formatDate(clean.latest.at) : "—");
  row("En cuarentena", String((status.quarantine || {}).files || 0), (status.quarantine || {}).files ? "bad" : "");

  const list = document.getElementById("admin-quarantine");
  list.replaceChildren();
  if (quarantine.files.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Ninguno: todos los ficheros han pasado la validación.";
    list.append(li);
  }
  for (const f of quarantine.files) {
    const li = document.createElement("li");
    li.textContent = `${f.key} · ${f.size_kb} KB · ${formatDate(f.at)}`;
    list.append(li);
  }
}

async function loadAdmin() {
  const user = Auth.user();
  if (!user || !user.groups.includes("admins")) return;
  try {
    const [status, quarantine] = await Promise.all([apiRequest("admin/status"), apiRequest("admin/quarantine")]);
    renderAdmin(status, quarantine);
  } catch (err) {
    setStatus(`Panel de administración: ${err.message}`, true);
  }
}

document.getElementById("admin-refresh").addEventListener("click", loadAdmin);

function renderSubscriptions(subs) {
  const list = document.getElementById("subs-list");
  list.replaceChildren();
  if (subs.length === 0) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "Todavía no sigues ninguna gasolinera. Abre una en el mapa y pulsa «Seguir».";
    list.append(li);
    return;
  }
  for (const sub of subs) {
    const li = document.createElement("li");
    const info = document.createElement("div");
    info.className = "sub-info";
    const name = document.createElement("button");
    name.type = "button";
    name.className = "link";
    name.textContent = sub.municipality ? `${sub.station_name} · ${sub.municipality}` : sub.station_name || sub.station_id;
    name.addEventListener("click", () => showDetail(sub.station_id));
    const target = document.createElement("div");
    target.className = "sub-target";
    target.textContent = `${FUEL_LABELS[sub.fuel_type] || sub.fuel_type}: aviso por debajo de ${Number(sub.target_price).toFixed(3)} €/L`;
    info.append(name, target);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove";
    remove.textContent = "Quitar";
    remove.addEventListener("click", async () => {
      remove.disabled = true;
      try {
        await apiRequest(`subscriptions/${encodeURIComponent(sub.station_fuel)}`, { method: "DELETE" });
        await loadSubscriptions();
      } catch (err) {
        remove.disabled = false;
        setStatus(`No se ha podido quitar: ${err.message}`, true);
      }
    });
    li.append(info, remove);
    list.append(li);
  }
}

async function loadSubscriptions() {
  if (!Auth.user()) return;
  try {
    const data = await apiRequest("subscriptions");
    renderSubscriptions(data.subscriptions);
  } catch (err) {
    setStatus(`No se han podido cargar tus gasolineras: ${err.message}`, true);
  }
}

document.getElementById("follow-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentStation) return;
  const button = e.target.querySelector("button[type=submit]");
  button.disabled = true;
  setFollowMessage("Guardando…");
  try {
    const sub = await apiRequest("subscriptions", {
      method: "POST",
      body: {
        station_id: currentStation.id,
        fuel_type: fuelSelect.value,
        target_price: Number(document.getElementById("f-target").value),
      },
    });
    setFollowMessage(`Hecho: te avisaremos cuando ${FUEL_LABELS[sub.fuel_type]} baje de ${Number(sub.target_price).toFixed(3)} €/L.`, "ok");
    await loadSubscriptions();
  } catch (err) {
    setFollowMessage(err.message, "error");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("login").addEventListener("click", () => Auth.login());
document.getElementById("follow-login").addEventListener("click", () => Auth.login());
document.getElementById("logout").addEventListener("click", () => Auth.logout());

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

async function start() {
  try {
    await Auth.handleRedirect(); // finishes the log-in when Cognito sends us back
  } catch (err) {
    setStatus(`No se ha podido iniciar sesión: ${err.message}`, true);
  }
  updateAuthUI();
  loadSubscriptions();
  loadAdmin();
  refreshStations();
}

start();
