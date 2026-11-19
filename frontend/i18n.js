// SmartFuel Forecast · texts of the web in Spanish and English (Phase D)
//
// Spanish by default for Spanish browsers (the users are drivers in Spain),
// English for the rest. The choice is remembered in this browser.
// Station names, addresses and opening hours come from the Ministry: always in Spanish.
//
// Static texts: <element data-i18n="key">, data-i18n-placeholder, data-i18n-aria.
// Dynamic texts: t("key", { var: value }) with {var} placeholders.

const I18N = {
  es: {
    "page.title": "SmartFuel Forecast",
    "brand.subtitle": "Precios de carburantes en España y su previsión",
    "controls.goTo": "Ir a",
    "controls.pickCity": "Elige una ciudad…",
    "controls.locate": "Mi ubicación",
    "controls.login": "Iniciar sesión",
    "controls.logout": "Salir",
    "controls.language": "Idioma",
    "map.aria": "Mapa de gasolineras",
    "panel.close": "Cerrar",

    "status.zoomIn": "Acerca el mapa a una zona para ver sus gasolineras.",
    "status.noApi": "Falta configurar la URL de la API en frontend/config.js",
    "status.tooBig": "Zona demasiado grande: acerca un poco más el mapa.",
    "status.loading": "Cargando gasolineras…",
    "status.countOne": "1 gasolinera en esta zona.",
    "status.countMany": "{n} gasolineras en esta zona.",
    "status.loadError": "No se han podido cargar las gasolineras: {error}",
    "status.noGeo": "Tu navegador no permite la ubicación.",
    "status.geoError": "No se ha podido obtener tu ubicación. Elige una ciudad.",
    "status.loginError": "No se ha podido iniciar sesión: {error}",
    "status.adminError": "Panel de administración: {error}",
    "status.subsError": "No se han podido cargar tus gasolineras: {error}",
    "status.removeError": "No se ha podido quitar: {error}",

    "popup.station": "Gasolinera",
    "popup.prices": "Ver precios",

    "cheap.title": "Más baratas en esta zona",
    "cheap.fuel": "Carburante",
    "cheap.noPrices": "Todavía no hay precios de este carburante en la zona.",
    "cheap.noStations": "No hay gasolineras en esta zona.",
    "cheap.note": "{n} de {total} gasolineras con precio de {fuel}.",

    "detail.loading": "Cargando…",
    "detail.station": "Gasolinera",
    "detail.hours": "Horario: {hours}",
    "detail.loadError": "No se ha podido cargar la estación",
    "detail.prices": "Precios actuales",
    "detail.noPrices": "Todavía no hay precios para esta estación (los cargará la fase de procesamiento).",
    "detail.prediction": "Previsión",
    "detail.predictionSoon": "Disponible cuando el modelo esté en marcha.",
    "detail.noPrediction": "Todavía no hay previsión para esta estación (la calculará el modelo).",
    "detail.predictionError": "No se ha podido cargar la previsión.",
    "direction.up": "Subirá",
    "direction.down": "Bajará",
    "direction.flat": "Se mantendrá",

    "follow.title": "Avisarme cuando baje",
    "follow.loginLink": "Inicia sesión",
    "follow.loginText": "para recibir un email cuando el precio baje de tu objetivo.",
    "follow.fuel": "Carburante",
    "follow.target": "Precio objetivo (€/L)",
    "follow.submit": "Seguir",
    "follow.saving": "Guardando…",
    "follow.done": "Hecho: te avisaremos cuando {fuel} baje de {price} €/L.",

    "subs.title": "Mis gasolineras",
    "subs.empty": "Todavía no sigues ninguna gasolinera. Abre una en el mapa y pulsa «Seguir».",
    "subs.target": "{fuel}: aviso por debajo de {price} €/L",
    "subs.remove": "Quitar",

    "admin.title": "Administración",
    "admin.refresh": "Actualizar",
    "admin.quarantineTitle": "Ficheros en cuarentena",
    "admin.ingestion": "Ingesta",
    "admin.check": "Revisar",
    "admin.lastDownload": "Última descarga",
    "admin.hoursAgo": "{date} (hace {hours} h)",
    "admin.none": "Ninguna",
    "admin.rawFiles": "Ficheros raw",
    "admin.processing": "Procesamiento",
    "admin.noProcessed": "Sin datos procesados",
    "admin.lastProcessed": "Último procesado",
    "admin.inQuarantine": "En cuarentena",
    "admin.noQuarantine": "Ninguno: todos los ficheros han pasado la validación.",

    "auth.expired": "Tu sesión ha caducado: vuelve a iniciar sesión.",
    "auth.mismatch": "La sesión de login no coincide, vuelve a intentarlo.",

    "fuel.gasolina_95_e5": "Gasolina 95",
    "fuel.gasolina_98_e5": "Gasolina 98",
    "fuel.gasoleo_a": "Gasóleo A",
    "fuel.gasoleo_premium": "Gasóleo Premium",
    "fuel.glp": "GLP",
  },

  en: {
    "page.title": "SmartFuel Forecast",
    "brand.subtitle": "Fuel prices in Spain and their forecast",
    "controls.goTo": "Go to",
    "controls.pickCity": "Choose a city…",
    "controls.locate": "My location",
    "controls.login": "Log in",
    "controls.logout": "Log out",
    "controls.language": "Language",
    "map.aria": "Map of petrol stations",
    "panel.close": "Close",

    "status.zoomIn": "Zoom in on an area to see its petrol stations.",
    "status.noApi": "The API URL is missing in frontend/config.js",
    "status.tooBig": "Area too large: zoom in a bit more.",
    "status.loading": "Loading petrol stations…",
    "status.countOne": "1 petrol station in this area.",
    "status.countMany": "{n} petrol stations in this area.",
    "status.loadError": "Could not load the petrol stations: {error}",
    "status.noGeo": "Your browser does not allow location.",
    "status.geoError": "Could not get your location. Choose a city.",
    "status.loginError": "Could not log in: {error}",
    "status.adminError": "Admin panel: {error}",
    "status.subsError": "Could not load your stations: {error}",
    "status.removeError": "Could not remove it: {error}",

    "popup.station": "Petrol station",
    "popup.prices": "See prices",

    "cheap.title": "Cheapest in this area",
    "cheap.fuel": "Fuel",
    "cheap.noPrices": "No prices for this fuel in this area yet.",
    "cheap.noStations": "No petrol stations in this area.",
    "cheap.note": "{n} of {total} stations with a {fuel} price.",

    "detail.loading": "Loading…",
    "detail.station": "Petrol station",
    "detail.hours": "Opening hours: {hours}",
    "detail.loadError": "Could not load the station",
    "detail.prices": "Current prices",
    "detail.noPrices": "No prices for this station yet (the processing phase will load them).",
    "detail.prediction": "Forecast",
    "detail.predictionSoon": "Available when the model is running.",
    "detail.noPrediction": "No forecast for this station yet (the model will compute it).",
    "detail.predictionError": "Could not load the forecast.",
    "direction.up": "Will go up",
    "direction.down": "Will go down",
    "direction.flat": "Will stay the same",

    "follow.title": "Alert me when it drops",
    "follow.loginLink": "Log in",
    "follow.loginText": "to get an email when the price drops below your target.",
    "follow.fuel": "Fuel",
    "follow.target": "Target price (€/L)",
    "follow.submit": "Follow",
    "follow.saving": "Saving…",
    "follow.done": "Done: we will email you when {fuel} drops below {price} €/L.",

    "subs.title": "My stations",
    "subs.empty": "You don't follow any station yet. Open one on the map and press \"Follow\".",
    "subs.target": "{fuel}: alert below {price} €/L",
    "subs.remove": "Remove",

    "admin.title": "Admin",
    "admin.refresh": "Refresh",
    "admin.quarantineTitle": "Quarantined files",
    "admin.ingestion": "Ingestion",
    "admin.check": "Check",
    "admin.lastDownload": "Last download",
    "admin.hoursAgo": "{date} ({hours} h ago)",
    "admin.none": "None",
    "admin.rawFiles": "Raw files",
    "admin.processing": "Processing",
    "admin.noProcessed": "No processed data",
    "admin.lastProcessed": "Last processed",
    "admin.inQuarantine": "In quarantine",
    "admin.noQuarantine": "None: every file passed validation.",

    "auth.expired": "Your session has expired: please log in again.",
    "auth.mismatch": "The log-in session does not match, please try again.",

    "fuel.gasolina_95_e5": "Petrol 95",
    "fuel.gasolina_98_e5": "Petrol 98",
    "fuel.gasoleo_a": "Diesel",
    "fuel.gasoleo_premium": "Premium diesel",
    "fuel.glp": "LPG",
  },
};

const LANG_KEY = "smartfuel.lang";
const LANGS = Object.keys(I18N);

function detectLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (LANGS.includes(saved)) return saved;
  } catch {
    // storage blocked: fall back to the browser language
  }
  return (navigator.language || "es").toLowerCase().startsWith("es") ? "es" : "en";
}

let LANG = detectLang();

function t(key, vars = {}) {
  const text = (I18N[LANG] && I18N[LANG][key]) ?? I18N.es[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? vars[name] : `{${name}}`));
}

const fuelLabel = (fuel) => (I18N[LANG][`fuel.${fuel}`] ? t(`fuel.${fuel}`) : fuel);
const locale = () => (LANG === "es" ? "es-ES" : "en-GB");

// Translate every element marked in index.html
function applyStaticTexts() {
  document.documentElement.lang = LANG;
  document.title = t("page.title");
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  document.querySelectorAll("[data-lang]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.lang === LANG));
  });
}

function setLang(lang) {
  if (!LANGS.includes(lang)) return;
  LANG = lang;
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // not remembered, but still switched for this visit
  }
  applyStaticTexts();
  document.dispatchEvent(new CustomEvent("smartfuel:lang", { detail: { lang } }));
}
