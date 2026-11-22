"use strict";

const FLAGS = [
  "has_children",
  "has_elderly",
  "respiratory_condition",
  "pregnant",
  "outdoor_worker",
  "has_purifier",
];

const PRESETS = {
  family: { city: "Mysuru", flags: ["has_children"], commute_mode: "car", commute_km: 8 },
  seniors: { city: "Delhi", flags: ["has_elderly"], commute_mode: "public_transport", commute_km: 5 },
  commuter: { city: "Bengaluru", flags: [], commute_mode: "car", commute_km: 15 },
  worker: { city: "Mumbai", flags: ["outdoor_worker"], commute_mode: "two_wheeler", commute_km: 12 },
};

const CATEGORY = {
  good: ["Good", "cat-good"],
  moderate: ["Moderate", "cat-moderate"],
  unhealthy_for_sensitive_groups: ["Unhealthy for sensitive groups", "cat-sensitive"],
  unhealthy: ["Unhealthy", "cat-unhealthy"],
  very_unhealthy: ["Very unhealthy", "cat-very"],
  hazardous: ["Hazardous", "cat-hazardous"],
};

const REQUEST_TIMEOUT_MS = 45000;
const DEFAULT_KM = 10;

const form = document.getElementById("advice-form");
const cityInput = document.getElementById("city");
const locateButton = document.getElementById("locate");
const locationNote = document.getElementById("location-note");
const submitButton = document.getElementById("submit");
const statusBox = document.getElementById("status");
const errorBox = document.getElementById("error");
const results = document.getElementById("results");

let coords = null;

class RequestError extends Error {}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setStatus(message) {
  statusBox.textContent = message;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function clearError() {
  errorBox.textContent = "";
  errorBox.hidden = true;
}

function setBusy(busy) {
  submitButton.disabled = busy;
  locateButton.disabled = busy;
  form.setAttribute("aria-busy", String(busy));
  setStatus(busy ? "Fetching live air quality and preparing your advice..." : "");
}

function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso || "unknown";
  return (
    date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) + " IST"
  );
}

function formatNumber(value) {
  return value === null || value === undefined ? "n/a" : String(Math.round(value * 10) / 10);
}

function clampKm(raw) {
  const value = parseFloat(raw);
  if (Number.isNaN(value)) return DEFAULT_KM;
  return Math.min(100, Math.max(0, value));
}

function buildBody() {
  const profile = {
    commute_mode: form.elements.commute_mode.value,
    commute_km: clampKm(form.elements.commute_km.value),
  };
  FLAGS.forEach((flag) => {
    profile[flag] = form.elements[flag].checked;
  });
  const body = { profile, language: form.elements.language.value };
  if (coords) {
    body.latitude = coords.latitude;
    body.longitude = coords.longitude;
    return body;
  }
  const city = cityInput.value.trim();
  if (city.length < 2) {
    showError('Please type your city, or tap "Use my current location".');
    cityInput.focus();
    return null;
  }
  body.city = city;
  return body;
}

function messageFor(status, data) {
  if (status === 422) {
    return "Please type a city in India, or use your location, and check your details.";
  }
  if (data && typeof data.detail === "string") return data.detail;
  return "Something went wrong. Please try again in a moment.";
}

function errorText(error) {
  if (error instanceof RequestError) return error.message;
  if (error && error.name === "AbortError") return "This is taking too long. Please try again.";
  return "Could not reach AirWise. Please check your connection and try again.";
}

async function requestAdvice(body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch("/api/advice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    let data = null;
    try {
      data = await response.json();
    } catch (parseError) {
      data = null;
    }
    if (!response.ok) throw new RequestError(messageFor(response.status, data));
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function factsList(rows) {
  const list = el("dl", "facts");
  rows.forEach(([term, value]) => {
    list.append(el("dt", "", term), el("dd", "", value));
  });
  return list;
}

function actionList(actions) {
  const list = el("ul", "advice-list");
  actions.forEach((action) => {
    const item = el("li");
    const why = el("p", "why");
    why.append(el("span", "", "Why: "), document.createTextNode(action.why));
    item.append(el("strong", "", action.title), el("p", "", action.detail), why);
    list.append(item);
  });
  return list;
}

function adviceSection(title, actions) {
  const section = el("section");
  section.append(el("h3", "", title), actionList(actions));
  return section;
}

function render(data) {
  const { location, reading, assessment, advice } = data;
  const [categoryLabel, categoryClass] = CATEGORY[assessment.category] || [assessment.category, "cat-moderate"];
  const personalLabel = (CATEGORY[assessment.personal_tier] || [assessment.personal_tier])[0];

  const heading = el("h2", "", "Air quality in " + location.name);
  heading.id = "results-heading";

  const card = el("div", "aqi-card " + categoryClass);
  card.append(
    el("p", "aqi-number", String(reading.us_aqi)),
    el("p", "aqi-label", "US AQI: " + categoryLabel),
    el("p", "aqi-personal", "For your household: " + personalLabel)
  );

  const rows = [["Data source", reading.source]];
  if (reading.station) {
    rows.push(["Monitoring station", reading.station + " (" + reading.distance_km + " km away)"]);
  } else {
    rows.push(["Note", "No monitoring station is within 25 km, so this is a model estimate."]);
  }
  rows.push(
    ["Measured at", formatTime(reading.observed_at)],
    ["PM2.5 and PM10", formatNumber(reading.pm2_5) + " and " + formatNumber(reading.pm10) + " ug/m3"],
    ["How AQI is calculated", reading.aqi_method]
  );

  const impact = el("section");
  impact.append(el("h3", "", "What your choices change"), el("p", "", advice.impact_explanation));

  const fromAi = data.advice_source === "gemini";
  const sourceNote = el(
    "p",
    "note",
    fromAi
      ? "Advice written by Gemini AI using the verified data above."
      : "Advice produced by AirWise's built-in rules from the verified data above."
  );
  if (!fromAi && form.elements.language.value !== "en") {
    sourceNote.append(" Translation needs the AI service, so this answer is in English.");
  }

  results.replaceChildren(
    heading,
    card,
    factsList(rows),
    el("p", "summary", advice.summary),
    adviceSection("Your routine today", advice.daily_routine),
    adviceSection("Cleaner air at home", advice.indoor_air_hacks),
    adviceSection("Sustainable alternatives", advice.sustainable_alternatives),
    impact,
    sourceNote,
    el("p", "note", data.disclaimer)
  );
  results.hidden = false;
  results.focus();
}

function applyPreset(preset) {
  coords = null;
  locationNote.textContent = "";
  cityInput.value = preset.city;
  FLAGS.forEach((flag) => {
    form.elements[flag].checked = preset.flags.includes(flag);
  });
  form.elements.commute_mode.value = preset.commute_mode;
  form.elements.commute_km.value = String(preset.commute_km);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  const body = buildBody();
  if (!body) return;
  setBusy(true);
  try {
    render(await requestAdvice(body));
  } catch (error) {
    showError(errorText(error));
  } finally {
    setBusy(false);
  }
});

document.getElementById("presets").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-preset]");
  if (!button) return;
  applyPreset(PRESETS[button.dataset.preset]);
  form.requestSubmit();
});

cityInput.addEventListener("input", () => {
  coords = null;
  locationNote.textContent = "";
});

locateButton.addEventListener("click", () => {
  clearError();
  if (!navigator.geolocation) {
    showError("This browser cannot share your location. Please type your city instead.");
    return;
  }
  setStatus("Finding your location...");
  navigator.geolocation.getCurrentPosition(
    (position) => {
      coords = {
        latitude: Math.round(position.coords.latitude * 100) / 100,
        longitude: Math.round(position.coords.longitude * 100) / 100,
      };
      cityInput.value = "";
      locationNote.textContent = "Using your current location (rounded to about 1 km).";
      form.requestSubmit();
    },
    () => {
      setStatus("");
      showError("We could not get your location. Please type your city instead.");
    },
    { timeout: 10000, maximumAge: 600000 }
  );
});
