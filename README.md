# ⏰ Smart Alarm — Wake Up Optimizer

A Flask web app that calculates the perfect alarm time based on your destination, travel time, and morning routine — so you never have to guess when to wake up.

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.3.3-black?logo=flask)
![OpenStreetMap](https://img.shields.io/badge/Maps-OpenStreetMap-green?logo=openstreetmap)

---

## 📌 Overview

Most alarm apps ask you to manually estimate your commute. Smart Alarm fetches real routing data, adjusts for time-of-day traffic patterns, applies a dynamic safety buffer, and works backwards from your required arrival time to give you an exact wake-up time.

```
Alarm Time = Arrival Time − Travel Time − Getting Ready Time − Safety Buffer
```

---

## 👩‍💻 My Contributions

This was a team project. My specific contributions:

- **Designed and implemented the three-tier routing fallback chain** — OpenRouteService is used as the primary routing provider (highest accuracy, distance metadata available). If it fails, the system automatically falls back to GraphHopper, then to OSRM as the final fallback. Each tier has its own timeout and error handling. This architecture means the app remains functional even if two of the three services are down, which is critical for a tool people depend on first thing in the morning.
- **Built the dynamic safety margin formula** — rather than a flat buffer, I implemented a margin that scales with trip length: base 15 minutes + up to 25% of the raw ETA, capped at 30 minutes. Longer commutes get proportionally larger buffers because they have more variance. The formula also applies separate multipliers for rush hour (1.30×), lunch hour (1.15×), short trips under 5km (1.20×), and weekends (0.90×) — layered independently so they compound correctly.

---

## 🌟 Features

- 📍 **Location autocomplete** — OpenStreetMap Nominatim, biased toward Pune, India
- 🚗 **Three-tier routing fallback** — OpenRouteService → GraphHopper → OSRM
- 🚦 **Traffic-aware ETA** — rush hour, lunch hour, weekday/weekend multipliers
- ⏱️ **Dynamic safety buffer** — scales with trip length, not a flat estimate
- 🔔 **In-browser alarm** — plays alarm sound + desktop notification at wake-up time
- ⚡ **5-minute result caching** — avoids redundant geocoding and routing API calls

---

## 🧭 Routing & Traffic Logic

### Fallback Chain

| Priority | Service           | Key Required | Distance Data |
| -------- | ----------------- | ------------ | ------------- |
| 1        | OpenRouteService  | Yes (free)   | ✅ Yes         |
| 2        | GraphHopper       | Yes (free)   | ✅ Yes         |
| 3        | OSRM              | No           | ❌ No          |

> Without ORS or GraphHopper, OSRM applies a flat 1.15× traffic multiplier since distance data is unavailable.

### Traffic Multipliers (applied independently, compounded)

| Condition    | Time / Distance         | Multiplier |
| ------------ | ----------------------- | ---------- |
| Rush hour    | 07:00–09:00, 16:00–18:00 | 1.30×     |
| Lunch hour   | 12:00–13:00             | 1.15×      |
| Off-peak     | All other hours         | 1.00×      |
| Short trip   | < 5 km                  | 1.20×      |
| Medium trip  | 5–20 km                 | 1.10×      |
| Long trip    | ≥ 20 km                 | 1.05×      |
| Weekend      | Saturday / Sunday       | 0.90×      |

### Safety Buffer Formula

```
buffer = 15 min + min(0.25 × raw_ETA, 30 min)
```

Floor: `max(adjusted_ETA, raw_ETA × 0.9)` — prevents over-optimistic reductions.

---

## 🛠️ Tech Stack

| Layer         | Technology                          |
| ------------- | ----------------------------------- |
| Backend       | Python, Flask                       |
| Geocoding     | OpenStreetMap Nominatim             |
| Routing       | OpenRouteService → GraphHopper → OSRM |
| Caching       | In-process TimedCache (TTL: 5 min)  |
| Frontend      | HTML, CSS, Vanilla JavaScript       |

---

## 🚀 Getting Started

```bash
git clone https://github.com/taneesha-beep/Smart-Alarm.git
cd Smart-Alarm

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### API Key (Optional but recommended)

```bash
cp .env.example .env
# Add your ORS_API_KEY from openrouteservice.org
```

> The app works without a key using OSRM, but ORS gives significantly better accuracy.

```bash
python3 app.py
```

Open **http://localhost:5001**

---

## 📁 Project Structure

```
smart-alarm/
├── app.py              # Flask backend — routing, geocoding, ETA, safety buffer
├── requirements.txt
├── .env                # API keys (not committed)
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── script.js       # Autocomplete, alarm scheduling, desktop notifications
```
